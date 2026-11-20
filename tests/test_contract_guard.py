"""The contract guard: Claude Code hook commands that refuse a write to an opted-in `charter.yaml` unless the human
started Establish, Evolve or Migrate in that session."""

import io
import json
import os
import sys

import pytest
from conftest import Result

from charter import guard, shellwrites

GUARDED = """\
charter: 1
agents: {file: AGENTS.md, guard: true}
kinds: {}
"""

UNGUARDED = """\
charter: 1
agents: {file: AGENTS.md}
kinds: {}
"""


def run_hook(capsys, monkeypatch, argv, data, cwd):
    """Run the `charter-hook` command in-process from `cwd` with `data` on stdin, capturing its streams."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))
    exit_code = guard.main(argv)
    captured = capsys.readouterr()
    return Result(exit_code, captured.out, captured.err)


@pytest.fixture
def hook(capsys, monkeypatch, tmp_path):
    """Feed one hook event to `charter-hook EVENT` on stdin, with markers kept under a test state folder."""
    monkeypatch.setenv("CHARTER_STATE_DIR", str(tmp_path / "state"))

    def run(event, payload, cwd):
        return run_hook(capsys, monkeypatch, [event], json.dumps(payload).encode("utf-8"), cwd)

    return run


@pytest.fixture
def kb(tmp_path):
    folder = tmp_path / "repo" / "kb"
    folder.mkdir(parents=True)
    (folder / "charter.yaml").write_text(GUARDED, encoding="utf-8")
    return folder


def started(hook, cwd, session="s1", command="charter:evolve"):
    return hook(
        "skill-started",
        {
            "session_id": session,
            "cwd": str(cwd),
            "hook_event_name": "UserPromptExpansion",
            "expansion_type": "slash_command",
            "command_name": command,
            "command_args": "",
            "command_source": "plugin",
            "prompt": f"/{command}",
        },
        cwd,
    )


def tool_call(hook, cwd, tool, tool_input, session="s1"):
    return hook(
        "pre-tool-use",
        {
            "session_id": session,
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": tool,
            "tool_input": tool_input,
        },
        cwd,
    )


def edit(hook, kb, session="s1", new_string="charter: 1 # changed"):
    return tool_call(
        hook,
        kb.parent,
        "Edit",
        {"file_path": str(kb / "charter.yaml"), "old_string": "charter: 1", "new_string": new_string},
        session,
    )


def denied(result):
    assert result.exit_code == 0
    output = result.json()["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    return output["permissionDecisionReason"]


def allowed(result):
    # Silence is no decision: the call goes on through Claude Code's own permission flow, never auto-approved.
    return result.exit_code == 0 and result.stdout == ""


def test_an_edit_of_a_guarded_contract_without_a_marker_is_denied_and_points_at_evolve(hook, kb):
    reason = denied(edit(hook, kb))

    assert "/charter:evolve" in reason
    assert "charter.yaml" in reason


@pytest.mark.parametrize("command", ["charter:evolve", "charter:establish", "charter:migrate"])
def test_after_the_human_types_a_charter_skill_the_same_session_may_edit_the_contract(hook, kb, command):
    assert started(hook, kb, command=command).exit_code == 0

    assert allowed(edit(hook, kb))


def test_a_marker_from_another_session_does_not_let_this_session_edit_the_contract(hook, kb):
    started(hook, kb, session="other")

    denied(edit(hook, kb, session="s1"))


def test_another_typed_command_leaves_no_marker(hook, kb):
    started(hook, kb, command="charter:survey")
    started(hook, kb, command="evolve")

    denied(edit(hook, kb))


def test_a_contract_that_does_not_opt_in_is_left_alone(hook, kb):
    (kb / "charter.yaml").write_text(UNGUARDED, encoding="utf-8")

    assert allowed(edit(hook, kb))


@pytest.mark.parametrize("text", ["charter: 1\nagents: {guard: false}\nkinds: {}\n", "charter: 1\nkinds: {}\n"])
def test_a_guard_that_is_off_or_absent_allows_the_edit(hook, kb, text):
    (kb / "charter.yaml").write_text(text, encoding="utf-8")

    assert allowed(edit(hook, kb))


def test_without_a_contract_the_hook_allows_everything_and_prints_nothing(hook, tmp_path):
    result = tool_call(hook, tmp_path, "Write", {"file_path": str(tmp_path / "charter.yaml"), "content": "x"})

    assert allowed(result)
    assert result.stderr == ""


def test_a_contract_that_does_not_parse_has_no_opt_in_the_guard_can_see(hook, kb):
    (kb / "charter.yaml").write_text("charter: [1\n", encoding="utf-8")

    assert allowed(edit(hook, kb))


def test_an_edit_that_removes_the_opt_in_is_itself_a_contract_write_and_is_denied(hook, kb):
    # The hook judges the contract on disk, before the edit, so the edit that switches the guard off is guarded.
    denied(edit(hook, kb, new_string="charter: 1\nagents: {file: AGENTS.md}"))
    denied(tool_call(hook, kb.parent, "Write", {"file_path": str(kb / "charter.yaml"), "content": UNGUARDED}))

    assert "guard: true" in (kb / "charter.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("tool", ["Write", "MultiEdit"])
def test_every_file_tool_that_writes_the_contract_is_guarded(hook, kb, tool):
    denied(tool_call(hook, kb.parent, tool, {"file_path": str(kb / "charter.yaml"), "content": "x", "edits": []}))


def test_a_relative_file_path_is_resolved_from_the_session_folder(hook, kb):
    denied(tool_call(hook, kb.parent, "Edit", {"file_path": "kb/charter.yaml", "old_string": "a", "new_string": "b"}))


def test_a_file_tool_writing_any_other_file_is_left_alone(hook, kb):
    (kb / "notes.md").write_text("x", encoding="utf-8")

    assert allowed(tool_call(hook, kb, "Write", {"file_path": str(kb / "notes.md"), "content": "y"}))
    assert allowed(tool_call(hook, kb, "Write", {"file_path": str(kb / "charter.yaml.bak"), "content": "y"}))


@pytest.mark.parametrize("data", [b"", b"not json", b"[1, 2]", b"\xff\xfe"])
def test_an_unreadable_event_never_blocks(kb, capsys, monkeypatch, data):
    for event in ("pre-tool-use", "skill-started"):
        result = run_hook(capsys, monkeypatch, [event], data, kb)
        assert result.exit_code == 0
        assert result.stdout == ""


@pytest.mark.parametrize("argv", [[], ["no-such-event"], ["pre-tool-use", "extra"], ["--version"]])
def test_an_unknown_hook_event_never_blocks(kb, capsys, monkeypatch, argv):
    # Exit 2 would block the skill or the tool call, so a hooks.json newer than this command must not get it.
    result = run_hook(capsys, monkeypatch, argv, b"{}", kb)

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "charter-hook" in result.stderr


@pytest.mark.parametrize("argv", [["--help"], ["-h"]])
def test_the_help_names_both_events_and_the_guarded_skills(kb, capsys, monkeypatch, argv):
    result = run_hook(capsys, monkeypatch, argv, b"", kb)

    assert result.exit_code == 0
    for text in ("skill-started", "pre-tool-use", *(f"/{skill}" for skill in guard.GUARDED_SKILLS)):
        assert text in result.stdout


def bash(hook, cwd, command, session="s1"):
    return tool_call(hook, cwd, "Bash", {"command": command, "description": "x"}, session)


@pytest.mark.parametrize(
    "command",
    [
        "echo 'agents: {}' > kb/charter.yaml",
        "printf x >> kb/charter.yaml",
        "cat x.yaml 2>/dev/null >| kb/charter.yaml",
        "echo x | tee kb/charter.yaml",
        "echo x | tee -a kb/charter.yaml > /dev/null",
        "sed -i 's/true/false/' kb/charter.yaml",
        "sed -i.bak -e 's/true/false/' kb/charter.yaml",
        "perl -pi -e 's/true/false/' kb/charter.yaml",
        "cd kb && sed -i 's/true/false/' charter.yaml",
        "cd kb; rm charter.yaml",
        "mv kb/charter.yaml kb/old.yaml",
        "mv new/charter.yaml kb/",
        "mv new/charter.yaml kb",
        "cp new.yaml kb/charter.yaml",
        "cp kb/charter.yaml kb/",
        "truncate -s 0 kb/charter.yaml",
        "dd if=new.yaml of=kb/charter.yaml",
        "git checkout -- kb/charter.yaml",
        "git restore --source HEAD~1 kb/charter.yaml",
        "git rm kb/charter.yaml",
        "git mv kb/charter.yaml kb/old.yaml",
        "LANG=C sed -i s/a/b/ kb/charter.yaml",
        "sudo tee kb/charter.yaml < new.yaml",
        "python3 -c \"open('kb/charter.yaml', 'w').write('x')\"",
        "uv run python -c \"open('kb/charter.yaml', 'w').write('x')\"",
        "sh -c 'echo x > kb/charter.yaml'",
        "echo x > \"kb/charter.yaml\"",
        "echo 'unbalanced > kb/charter.yaml",
        "true\necho x > kb/charter.yaml",
    ],
)
def test_a_bash_command_that_writes_a_guarded_contract_is_denied(hook, kb, command):
    denied(bash(hook, kb.parent, command))


@pytest.mark.parametrize(
    "command",
    [
        "charter validate --config kb/charter.yaml --all",
        "charter describe --config kb/charter.yaml",
        "cat kb/charter.yaml",
        "grep guard kb/charter.yaml > found.txt",
        "git diff -- kb/charter.yaml",
        "git add kb/charter.yaml",
        "git log -p -- kb/charter.yaml",
        "cp kb/charter.yaml backup.yaml",
        "sed -n 1,5p kb/charter.yaml",
        "diff kb/charter.yaml kb/charter.draft.yaml",
        "echo x > kb/charter.draft.yaml",
        "cat kb/charter.yaml | tee copy.yaml",
    ],
)
def test_a_bash_command_that_only_reads_the_contract_is_left_alone(hook, kb, command):
    assert allowed(bash(hook, kb.parent, command))


def test_a_bash_write_to_a_contract_that_does_not_opt_in_is_left_alone(hook, kb):
    (kb / "charter.yaml").write_text(UNGUARDED, encoding="utf-8")

    assert allowed(bash(hook, kb.parent, "sed -i s/a/b/ kb/charter.yaml"))


def test_a_bash_write_after_the_human_typed_evolve_is_allowed(hook, kb):
    started(hook, kb)

    assert allowed(bash(hook, kb.parent, "sed -i s/a/b/ kb/charter.yaml"))


def test_the_marker_is_kept_in_the_state_folder_never_in_the_repository(hook, kb, tmp_path):
    started(hook, kb)

    assert list((tmp_path / "repo").rglob("*")) == [kb, kb / "charter.yaml"]
    assert len(list((tmp_path / "state").rglob("*.json"))) == 1


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/c/kb/charter.yaml", "c:/kb/charter.yaml"),
        ("/D/kb/charter.yaml", "D:/kb/charter.yaml"),
        ("/c", "c:/"),
        ("/cd/kb/charter.yaml", "/cd/kb/charter.yaml"),
        ("kb/charter.yaml", "kb/charter.yaml"),
        ("C:/kb/charter.yaml", "C:/kb/charter.yaml"),
        ("~/kb/charter.yaml", "~/kb/charter.yaml"),
    ],
)
def test_a_git_bash_drive_path_names_that_drive_on_windows_only(path, expected):
    # Claude Code runs Bash through Git Bash on Windows, where `/c/kb` is `C:\kb`; elsewhere it is a real folder.
    assert shellwrites.native(path, windows=True) == expected
    assert shellwrites.native(path, windows=False) == path


@pytest.mark.skipif(os.name != "nt", reason="Git Bash drive paths exist only on Windows")
def test_a_git_bash_path_to_a_guarded_contract_is_denied_on_windows(hook, kb):
    folder = f"/{kb.drive[0].lower()}{kb.as_posix()[len(kb.drive) :]}"
    edit_input = {"file_path": f"{folder}/charter.yaml", "old_string": "a", "new_string": "b"}

    denied(tool_call(hook, kb.parent, "Edit", edit_input))
    denied(bash(hook, kb.parent, f"sed -i s/a/b/ {folder}/charter.yaml"))
    denied(bash(hook, kb.parent, f"cd {folder} && rm charter.yaml"))


def test_a_move_of_the_contract_to_an_overlong_name_is_denied(hook, kb):
    # Checking whether a 5000-character target is a folder raises an OSError; the guarded source must still count.
    denied(bash(hook, kb.parent, f"mv kb/charter.yaml {'x' * 5000}"))


def test_a_move_of_the_contract_is_denied_when_the_target_cannot_be_checked(hook, kb, monkeypatch):
    def unreadable(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(shellwrites.Path, "is_dir", unreadable)

    denied(bash(hook, kb.parent, "mv kb/charter.yaml elsewhere"))


def crashed(result):
    # A crash is a hook error to Claude Code, never exit 2, which would block the call.
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "charter-hook" in result.stderr
    return result.stderr


def test_a_session_id_that_is_not_valid_text_never_blocks(kb, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("CHARTER_STATE_DIR", str(tmp_path / "state"))
    data = b'{"session_id": "\\ud800", "command_name": "charter:evolve", "cwd": "."}'

    crashed(run_hook(capsys, monkeypatch, ["skill-started"], data, kb))


@pytest.mark.skipif(os.name == "nt", reason="Windows spells any `~user` as a folder beside the user's own home")
def test_a_home_folder_of_an_unknown_user_never_blocks(hook, kb):
    crashed(bash(hook, kb.parent, "cp x ~nosuchuser-charter-test/charter.yaml"))


def test_a_deeply_nested_event_never_blocks(kb, capsys, monkeypatch):
    data = b"[" * 100_000 + b"]" * 100_000

    crashed(run_hook(capsys, monkeypatch, ["pre-tool-use"], data, kb))


def test_a_deeply_nested_contract_never_blocks(hook, kb):
    (kb / "charter.yaml").write_text("agents: " + "[" * 100_000 + "]" * 100_000 + "\n", encoding="utf-8")

    crashed(edit(hook, kb))
