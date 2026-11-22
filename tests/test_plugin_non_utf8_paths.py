"""A staged path that is not valid UTF-8 is left out of a plugin's request, with a warning naming it."""

import json
import os

import pytest
from conftest import run_git
from hostile_names import can_create, git_tree_with_paths
from plugin_support import plugin_kb, probe, rewrite_manifest

TODO_FREE = "  todo-free:\n    source: tools/todo-free\n"
NOTE = "---\nkind: entry\n---\n# TODO write this\n"
# Not valid UTF-8; built from bytes so no file system or source encoding is involved.
BAD_NAME = b"notes/caf\xe9.md"
ESCAPED = "notes/caf\\xe9.md"
GOOD_NAME = b"notes/plain.md"


@pytest.fixture
def repo(make_kb):
    base = plugin_kb(make_kb)(TODO_FREE, ["todo-free"], notes={})
    run_git(base, "init", "-q", "--initial-branch=main")
    run_git(base, "add", "-A")
    git_tree_with_paths(base, [BAD_NAME, GOOD_NAME], NOTE)
    return base


def _by_code(result):
    return [(d["path"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def test_plugin_run_warns_about_the_skipped_path_and_still_checks_the_others(charter, repo):
    result = charter("plugin", "run", "todo-free", "--staged", "--format", "json", cwd=repo)

    assert result.stderr == ""
    assert sorted(_by_code(result)) == [
        (ESCAPED, "warning", "plugin/skipped-path"),
        ("notes/plain.md", "error", "todo-free/todo"),
    ]
    assert result.exit_code == 1


def test_dump_input_prints_the_request_without_the_skipped_path(charter, repo):
    result = charter("plugin", "run", "todo-free", "--staged", "--dump-input", cwd=repo)

    assert (result.exit_code, result.stderr) == (0, "")
    request = json.loads(result.stdout)
    assert request["targets"] == ["plain.md"]
    assert [note["path"] for note in request["index"]["notes"]] == ["plain.md"]


def test_before_leaves_out_the_skipped_path(charter, make_kb):
    base = probe(plugin_kb(make_kb), notes={}, needs="[before]")
    run_git(base, "init", "-q", "--initial-branch=main")
    run_git(base, "add", "-A")
    git_tree_with_paths(base, [BAD_NAME, GOOD_NAME], NOTE)
    run_git(base, "commit", "-q", "-m", "base")
    git_tree_with_paths(base, [BAD_NAME, GOOD_NAME], NOTE + "Edited.\n")

    result = charter("plugin", "run", "probe", "--staged", "--dump-input", cwd=base)

    assert (result.exit_code, result.stderr) == (0, "")
    assert [file["path"] for file in json.loads(result.stdout)["before"]["files"]] == ["plain.md"]


def test_validate_warns_about_the_skipped_path_and_still_runs_the_plugin(charter, repo):
    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=repo)

    assert result.stderr == ""
    found = _by_code(result)
    assert (ESCAPED, "warning", "plugin/skipped-path") in found
    assert ("notes/plain.md", "error", "todo-free/todo") in found
    assert result.exit_code == 1


def test_the_warning_names_the_plugin_and_the_escaped_path(charter, repo):
    result = charter("plugin", "run", "todo-free", "--staged", "--format", "agent", cwd=repo)

    assert f"{ESCAPED}: warning plugin/skipped-path: Plugin `todo-free` was not sent `{ESCAPED}`" in result.stdout


def test_a_profile_can_turn_the_warning_off(charter, repo):
    contract = repo / "charter.yaml"
    contract.write_text(
        contract.read_text(encoding="utf-8") + "profiles:\n  quiet:\n    plugin/skipped-path: off\n", encoding="utf-8"
    )
    run_git(repo, "add", "charter.yaml")

    result = charter("validate", "--staged", "--profile", "quiet", "--format", "json", cwd=repo)

    assert result.stderr == ""
    assert "plugin/skipped-path" not in [code for _, _, code in _by_code(result)]
    assert ("notes/plain.md", "error", "todo-free/todo") in _by_code(result)


def test_strict_makes_the_warning_an_error(charter, repo):
    result = charter("plugin", "run", "todo-free", "--staged", "--strict", "--format", "json", cwd=repo)

    assert (ESCAPED, "error", "plugin/skipped-path") in _by_code(result)


def _received(base):
    request = base / "tools" / "probe" / "request.json"
    return json.loads(request.read_text(encoding="utf-8")) if request.exists() else None


def _staged(base):
    run_git(base, "init", "-q", "--initial-branch=main")
    run_git(base, "add", "-A")
    git_tree_with_paths(base, [BAD_NAME, GOOD_NAME], NOTE)
    return base


def _todo_free_triggered_by(make_kb, triggers):
    base = plugin_kb(make_kb)(TODO_FREE, ["todo-free"], notes={})
    rewrite_manifest(base / "tools" / "todo-free", triggers=triggers)
    return _staged(base)


def test_a_glob_that_matches_only_the_skipped_path_does_not_start_the_plugin_but_still_warns(charter, make_kb):
    base = _todo_free_triggered_by(make_kb, "{globs: ['caf*']}")

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=base)

    assert result.stderr == ""
    found = _by_code(result)
    assert (ESCAPED, "warning", "plugin/skipped-path") in found
    assert ("notes/plain.md", "error", "todo-free/todo") not in found


def test_a_glob_that_matches_a_sent_path_starts_the_plugin_and_warns(charter, make_kb):
    base = _todo_free_triggered_by(make_kb, "{globs: ['*.md']}")

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=base)

    assert result.stderr == ""
    found = _by_code(result)
    assert (ESCAPED, "warning", "plugin/skipped-path") in found
    assert ("notes/plain.md", "error", "todo-free/todo") in found


def test_a_glob_that_matches_neither_path_reports_nothing_about_it(charter, make_kb):
    base = _todo_free_triggered_by(make_kb, "{globs: ['Places/**']}")

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=base)

    assert result.stderr == ""
    assert [code for _, _, code in _by_code(result) if code.startswith(("plugin/", "todo-free/"))] == []


def test_a_vault_scope_plugin_is_sent_the_whole_index_without_the_skipped_path(charter, make_kb):
    base = _staged(probe(plugin_kb(make_kb), notes={"other.md": NOTE}, scope="vault"))

    dumped = charter("plugin", "run", "probe", "--staged", "--dump-input", cwd=base)
    result = charter("plugin", "run", "probe", "--staged", "--format", "json", cwd=base)

    assert (dumped.exit_code, dumped.stderr, result.stderr) == (0, "", "")
    request = json.loads(dumped.stdout)
    assert (request["mode"], [note["path"] for note in request["index"]["notes"]]) == (
        "vault",
        ["other.md", "plain.md"],
    )
    assert (ESCAPED, "warning", "plugin/skipped-path") in _by_code(result)


def test_a_file_scope_plugin_warns_about_a_skipped_target(charter, make_kb):
    base = _staged(probe(plugin_kb(make_kb), notes={}, scope="file"))

    dumped = charter("plugin", "run", "probe", "--staged", "--dump-input", cwd=base)
    result = charter("plugin", "run", "probe", "--staged", "--format", "json", cwd=base)

    assert (dumped.exit_code, dumped.stderr, result.stderr) == (0, "", "")
    request = json.loads(dumped.stdout)
    assert (request["mode"], request["targets"]) == ("file", ["plain.md"])
    assert (ESCAPED, "warning", "plugin/skipped-path") in _by_code(result)


def test_a_whole_run_leaves_the_skipped_path_out_and_warns(charter, make_kb, tmp_path):
    if not can_create(BAD_NAME.split(b"/")[-1], tmp_path):
        pytest.skip("this file system cannot hold a name that is not valid UTF-8")
    base = probe(plugin_kb(make_kb), notes={"plain.md": NOTE})
    with open(os.fsencode(base) + b"/" + BAD_NAME, "wb") as file:
        file.write(NOTE.encode())

    result = charter("validate", "--all", "--format", "json", cwd=base)

    assert result.stderr == ""
    request = _received(base)
    assert (request["mode"], [note["path"] for note in request["index"]["notes"]]) == ("vault", ["plain.md"])
    assert (ESCAPED, "warning", "plugin/skipped-path") in _by_code(result)


def test_a_kinds_trigger_that_matches_only_the_skipped_path_does_not_start_the_plugin_but_still_warns(
    charter, make_kb
):
    base = plugin_kb(make_kb)(TODO_FREE, ["todo-free"], notes={})
    # A plugin that cannot start: were it started, the run would report `plugin/failed`.
    rewrite_manifest(base / "tools" / "todo-free", triggers="{kinds: [entry]}", run='["no-such-program-charter"]')
    run_git(base, "init", "-q", "--initial-branch=main")
    run_git(base, "add", "-A")
    # Committed, so the staged change targets the note alone: a staged contract would touch every kind.
    run_git(base, "commit", "-q", "-m", "base")
    git_tree_with_paths(base, [BAD_NAME], NOTE)

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=base)

    assert result.stderr == ""
    found = _by_code(result)
    assert (ESCAPED, "warning", "plugin/skipped-path") in found
    assert "plugin/failed" not in [code for _, _, code in found]


def test_a_modified_plugin_whose_glob_matches_only_the_skipped_path_reports_modified(charter, make_kb, plugin_repo):
    base = make_kb({"charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: {}\n", "notes/.keep": ""})
    added = charter("plugin", "add", "--from", f"{plugin_repo().as_posix()}@v1.2.0", cwd=base)
    assert added.exit_code == 0, added.stdout
    # Changing the vendored manifest is itself the change the lock catches.
    rewrite_manifest(base / ".charter" / "plugins" / "todo-free", triggers="{globs: ['caf*']}")
    _staged(base)

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=base)

    assert result.stderr == ""
    assert ("charter.yaml", "error", "plugin/modified") in _by_code(result)
