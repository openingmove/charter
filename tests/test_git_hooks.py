"""The documented hooks, run by real git in a temporary repository."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import commit_files, run_git, write_files

REPO = Path(__file__).resolve().parent.parent
CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      title: {type: string}
  decision:
    fields:
      kind: {type: string, required: true}
checks:
  protected-region: {enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}
"""
NOTE = "---\nkind: entry\n---\n"
ALLOW = "Charter-Allow: paths/read-only notes/Archive/old.md — typo"

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("python3") is None, reason="needs git and python3 on PATH"
)


@pytest.fixture
def hooked_kb(make_kb, monkeypatch):
    scripts = Path(sys.executable).parent
    if not (scripts / ("charter.exe" if os.name == "nt" else "charter")).exists():
        pytest.skip("the charter console script is not installed next to this interpreter")
    monkeypatch.setenv("PATH", str(scripts) + os.pathsep + os.environ["PATH"])
    kb = make_kb({"charter.yaml": CONTRACT, "notes/Archive/old.md": NOTE, "notes/free.md": NOTE})
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    shutil.copytree(REPO / ".githooks", kb / ".githooks")
    run_git(kb, "config", "core.hooksPath", ".githooks")
    return kb


def _commit(kb, message):
    return subprocess.run(
        [
            "git",
            *("-c", "user.name=Test", "-c", "user.email=t@example.com"),
            *("-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"),
            *("commit", "-q", "-m", message),
        ],
        cwd=kb,
        capture_output=True,
        text=True,
    )


def _stage(kb, files):
    write_files(kb, files)
    run_git(kb, "add", "-A")


def test_the_pre_commit_hook_blocks_an_invalid_staged_note(hooked_kb):
    _stage(hooked_kb, {"notes/free.md": "---\nkind: entry\ntitle: [x]\n---\n"})

    result = _commit(hooked_kb, "Add a note")

    assert result.returncode != 0
    assert "schema/type" in result.stdout + result.stderr
    assert run_git(hooked_kb, "rev-list", "--count", "HEAD") == "1"


def test_the_commit_msg_hook_blocks_an_edit_the_contract_forbids(hooked_kb):
    _stage(hooked_kb, {"notes/Archive/old.md": NOTE + "Edited.\n"})

    result = _commit(hooked_kb, "Fix a typo")

    assert result.returncode != 0
    assert "paths/read-only" in result.stdout + result.stderr
    assert run_git(hooked_kb, "rev-list", "--count", "HEAD") == "1"


def test_a_charter_allow_trailer_lets_the_forbidden_edit_through(hooked_kb):
    _stage(hooked_kb, {"notes/Archive/old.md": NOTE + "Edited.\n"})

    result = _commit(hooked_kb, f"Fix a typo\n\n{ALLOW}\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert run_git(hooked_kb, "rev-list", "--count", "HEAD") == "2"


def test_a_clean_commit_passes_both_hooks(hooked_kb):
    _stage(hooked_kb, {"notes/free.md": NOTE + "More.\n"})

    assert _commit(hooked_kb, "Add prose").returncode == 0


def test_a_commit_with_both_hooks_prints_no_deferral_info(hooked_kb):
    _stage(hooked_kb, {"notes/free.md": NOTE + "More.\n"})

    result = _commit(hooked_kb, "Add prose")

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "paths/edit-deferred" not in output
    assert "protected-region/deferred" not in output


def test_a_pre_commit_only_setup_still_prints_the_deferral_info(hooked_kb):
    # Plain `charter validate --staged`, as a setup without the commit-msg hook would run it.
    plain = hooked_kb / "plain-hooks"
    plain.mkdir()
    hook = plain / "pre-commit"
    hook.write_text(
        "#!/usr/bin/env python3\nimport subprocess, sys\nsys.exit(subprocess.call(['charter', 'validate', '--staged']))\n"
    )
    hook.chmod(0o755)
    run_git(hooked_kb, "config", "core.hooksPath", "plain-hooks")
    _stage(hooked_kb, {"notes/free.md": NOTE + "More.\n"})

    result = _commit(hooked_kb, "Add prose")

    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "paths/edit-deferred" in output
    assert "protected-region/deferred" in output


def test_the_pre_commit_config_hooks_pass_the_message_file_last():
    hooks = {hook["id"]: hook for hook in yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text("utf-8"))}

    assert hooks["charter"]["entry"] == "charter validate --staged --commit-msg-installed"
    assert hooks["charter"]["stages"] == ["pre-commit"]
    assert hooks["charter"]["pass_filenames"] is False
    # pre-commit appends the message file path to a commit-msg hook's argv, which is what --commit-msg takes.
    assert hooks["charter-commit-msg"]["entry"] == "charter validate --staged --commit-msg"
    assert hooks["charter-commit-msg"]["stages"] == ["commit-msg"]
    assert hooks["charter-commit-msg"].get("pass_filenames", True) is True
