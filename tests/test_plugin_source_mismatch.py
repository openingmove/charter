"""`plugin add`, `remove` and `update` refuse a plugin whose `checks.<id>.source` is not the directory `plugin add`
installs it in, and change nothing."""

import shutil

import pytest
from conftest import FIXTURES

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
NOTES = {"notes/a.md": "---\nkind: entry\n---\n# Plans\n"}
INSTALLED = ".charter/plugins/todo-free"
FROM = "v1.2.0"


@pytest.fixture
def installed(charter, make_kb, plugin_repo):
    """A knowledge base with todo-free added from git; returns (base, repo)."""
    base, repo = make_kb({"charter.yaml": CONTRACT, **NOTES}), plugin_repo()
    assert charter("plugin", "add", "--from", f"{repo.as_posix()}@{FROM}", cwd=base).exit_code == 0
    return base, repo


def _with_source(base, source):
    """Points `checks.todo-free.source` at `source`, written as given (quoted, so any spelling is one string)."""
    contract = base / "charter.yaml"
    text = contract.read_text(encoding="utf-8")
    assert f"source: {INSTALLED}" in text
    contract.write_text(text.replace(f"source: {INSTALLED}", f"source: '{source}'"), encoding="utf-8", newline="")
    # `add` needs a contract that loads, so the other place holds a plugin too.
    if not source.startswith(".."):
        shutil.copytree(FIXTURES / "plugins" / "todo-free", base / source, dirs_exist_ok=True)


def _snapshot(base):
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(base).parts
    }


def _run(charter, base, repo, command):
    argv = {
        "add": ["add", "--from", f"{repo.as_posix()}@{FROM}"],
        "update": ["update", "todo-free"],
        "remove": ["remove", "todo-free"],
    }
    return charter("plugin", *argv[command], cwd=base)


COMMANDS = ["add", "remove", "update"]
# `add` needs a contract that loads, which a source outside the knowledge base prevents (exit 2, nothing changed).
MISMATCHED = [
    (source, command)
    for source in ["tools/todo-free", ".charter/plugins/other", ".charter/plugins/todo-free-2", "../todo-free"]
    for command in ["add", "remove", "update"]
    if not (source.startswith("..") and command == "add")
]
MATCHING = [
    "./.charter/plugins/todo-free",
    ".charter\\plugins\\todo-free",
    ".charter/plugins/todo-free/",
    ".charter//plugins/./todo-free",
]


@pytest.mark.parametrize(("source", "command"), MISMATCHED)
def test_a_mismatched_source_is_refused_and_nothing_changes(charter, installed, command, source):
    base, repo = installed
    (base / ".gitignore").unlink(missing_ok=True)
    _with_source(base, source)
    before = _snapshot(base)

    result = _run(charter, base, repo, command)

    assert result.exit_code == 1
    assert "plugin/source-mismatch" in result.stdout
    assert "Plugin `todo-free`" in result.stdout
    assert f"`checks.todo-free.source` in `charter.yaml` is `{source}`" in result.stdout
    assert f"installed in `{INSTALLED}`" in result.stdout
    assert f"Edit `source` back to `{INSTALLED}`" in result.stdout
    assert "delete the `todo-free` entry under `plugins:` in `charter.lock` by hand" in result.stdout
    assert _snapshot(base) == before
    assert not (base / ".gitignore").exists()


def test_update_refuses_a_mismatch_before_it_fetches(charter, installed):
    base, repo = installed
    _with_source(base, "tools/todo-free")
    shutil.rmtree(repo, ignore_errors=True)
    before = _snapshot(base)

    result = _run(charter, base, repo, "update")

    assert result.exit_code == 1
    assert "plugin/source-mismatch" in result.stdout
    assert "fetch-failed" not in result.stdout
    assert _snapshot(base) == before


def test_a_mismatch_is_refused_for_a_plugin_that_update_could_not_update_anyway(charter, make_kb, tmp_path_factory):
    base = make_kb({"charter.yaml": CONTRACT, **NOTES})
    working = tmp_path_factory.mktemp("work")
    shutil.copytree(FIXTURES / "plugins" / "todo-free", working, dirs_exist_ok=True)
    assert charter("plugin", "add", "--dev", str(working), cwd=base).exit_code == 0
    _with_source(base, "tools/todo-free")
    before = _snapshot(base)

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert "plugin/source-mismatch" in result.stdout
    assert "not-updatable" not in result.stdout
    assert _snapshot(base) == before


@pytest.mark.parametrize("source", MATCHING)
@pytest.mark.parametrize("command", COMMANDS)
def test_other_spellings_of_the_installed_directory_still_match(charter, installed, command, source):
    base, repo = installed
    _with_source(base, source)

    result = _run(charter, base, repo, command)

    assert result.exit_code == 0, result.stdout
    assert "plugin/source-mismatch" not in result.stdout


def test_remove_with_a_matching_source_deletes_the_directory_and_lock_entry(charter, installed):
    base, repo = installed

    assert _run(charter, base, repo, "remove").exit_code == 0

    assert not (base / INSTALLED).exists()
    assert "todo-free" not in (base / "charter.lock").read_text(encoding="utf-8")


def test_an_unlocked_check_with_another_source_is_used_in_place_as_before(charter, make_kb, plugin_repo):
    contract = CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: false\n"
    base, repo = make_kb({"charter.yaml": contract, **NOTES}), plugin_repo()

    added = _run(charter, base, repo, "add")
    updated = _run(charter, base, repo, "update")
    removed = _run(charter, base, repo, "remove")

    assert (added.exit_code, "plugin/exists" in added.stdout) == (1, True)
    assert (updated.exit_code, "usage/not-updatable" in updated.stdout) == (2, True)
    assert removed.exit_code == 0
    assert "todo-free" not in (base / "charter.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("command", COMMANDS)
def test_a_locked_plugin_without_a_checks_entry_is_still_managed(charter, installed, command):
    base, repo = installed
    (base / "charter.yaml").write_text(CONTRACT, encoding="utf-8", newline="")

    result = _run(charter, base, repo, command)

    assert result.exit_code == 0, result.stdout
    assert "plugin/source-mismatch" not in result.stdout
    assert (base / INSTALLED).exists() is (command != "remove")
