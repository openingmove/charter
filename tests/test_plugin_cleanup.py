"""Cleanup after plugin commands and `--staged` runs: read-only files do not stop it, and a folder that cannot be
removed is a warning naming it, never a different exit code."""

import os
import shutil
import stat
import tempfile
from pathlib import Path

import pytest
from conftest import FIXTURES, commit_files, run_git, write_files

from charter import files

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
NOTES = {"notes/a.md": "---\nkind: entry\n---\n# Plans\n"}
PLUGIN = str(FIXTURES / "plugins" / "todo-free")
INSTALLED = ".charter/plugins/todo-free"
# The plugin file the simulated lock refuses to delete.
STUCK = "check.py"


@pytest.fixture
def kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, **NOTES})


@pytest.fixture
def instant(monkeypatch):
    monkeypatch.setattr(files, "_REMOVE_PAUSE_SECONDS", 0)


def _patch_unlink(monkeypatch):
    """Makes deleting any file named STUCK fail, as a file another program holds open does on Windows."""
    real = os.unlink

    def unlink(path, *args, **kwargs):
        if Path(os.fsdecode(path)).name == STUCK:
            raise PermissionError(13, "The process cannot access the file", os.fsdecode(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)


@pytest.fixture
def stuck_file(monkeypatch):
    _patch_unlink(monkeypatch)


def _make_read_only(directory):
    """A read-only file, and one inside a read-only folder (which on POSIX blocks deleting its contents)."""
    (directory / "locked").mkdir()
    (directory / "locked" / "inner.txt").write_text("x", encoding="utf-8")
    (directory / "locked" / "inner.txt").chmod(stat.S_IREAD)
    (directory / "locked").chmod(stat.S_IREAD | stat.S_IEXEC)
    (directory / "top.txt").write_text("x", encoding="utf-8")
    (directory / "top.txt").chmod(stat.S_IREAD)


def _staging(base):
    return sorted((base / ".charter" / "plugins").glob(".staging-*")) + sorted(base.glob(".adding-*"))


def _install_with_read_only_files(charter, kb):
    assert charter("plugin", "add", "--dev", PLUGIN, cwd=kb).exit_code == 0
    _make_read_only(kb / INSTALLED)


def test_remove_tree_deletes_read_only_files_and_folders(tmp_path):
    folder = tmp_path / "doomed"
    folder.mkdir()
    _make_read_only(folder)

    assert files.remove_tree(folder) == []
    assert not folder.exists()


def test_remove_tree_of_a_missing_folder_is_a_quiet_success(tmp_path):
    assert files.remove_tree(tmp_path / "never-made") == []


def test_remove_tree_reports_what_it_could_not_delete_after_a_bounded_number_of_attempts(
    tmp_path, instant, stuck_file, monkeypatch
):
    folder = tmp_path / "doomed"
    folder.mkdir()
    (folder / STUCK).write_text("x", encoding="utf-8")
    (folder / "fine.txt").write_text("x", encoding="utf-8")
    attempts = []
    real = shutil.rmtree
    monkeypatch.setattr(files.shutil, "rmtree", lambda *args, **kwargs: attempts.append(args) or real(*args, **kwargs))

    assert files.remove_tree(folder) == [folder / STUCK]
    assert len(attempts) == 4
    assert not (folder / "fine.txt").exists()


def test_replacing_a_plugin_whose_old_files_are_read_only_leaves_no_staging_folder(charter, kb):
    _install_with_read_only_files(charter, kb)

    result = charter("plugin", "add", "--dev", PLUGIN, cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert result.stderr == ""
    assert _staging(kb) == []
    assert not (kb / INSTALLED / "locked").exists()


def test_removing_a_plugin_whose_files_are_read_only_leaves_no_staging_folder(charter, kb):
    _install_with_read_only_files(charter, kb)

    result = charter("plugin", "remove", "todo-free", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert _staging(kb) == []
    assert not (kb / INSTALLED).exists()


def test_a_staging_folder_that_cannot_be_deleted_is_a_warning_and_the_exit_code_stays_zero(
    charter, kb, instant, monkeypatch
):
    assert charter("plugin", "add", "--dev", PLUGIN, cwd=kb).exit_code == 0
    clean = charter("plugin", "add", "--dev", PLUGIN, cwd=kb)
    _patch_unlink(monkeypatch)

    result = charter("plugin", "add", "--dev", PLUGIN, cwd=kb)

    assert result.exit_code == clean.exit_code == 0
    assert result.stdout == clean.stdout
    [left] = _staging(kb)
    assert f"{left.relative_to(kb).as_posix()}/previous/{STUCK}" in result.stderr
    assert "warning" in result.stderr
    assert "files/leftover" in result.stderr
    assert (left / "previous" / STUCK).is_file()


def test_a_staging_folder_that_cannot_be_deleted_after_remove_is_a_warning_too(charter, kb, instant, monkeypatch):
    assert charter("plugin", "add", "--dev", PLUGIN, cwd=kb).exit_code == 0
    _patch_unlink(monkeypatch)

    result = charter("plugin", "remove", "todo-free", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert "files/leftover" in result.stderr
    [left] = _staging(kb)
    assert f"{left.relative_to(kb).as_posix()}/previous/{STUCK}" in result.stderr


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    """The folder Python's temporary folders go in for this test, so a leftover can be found and is cleaned up."""
    folder = tmp_path / "scratch"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def _add_from_git(charter, kb, repo):
    return charter("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0", cwd=kb)


def test_a_staging_folder_that_cannot_be_deleted_after_update_is_a_warning_and_the_exit_code_stays_zero(
    charter, kb, plugin_repo, scratch, instant, monkeypatch
):
    assert _add_from_git(charter, kb, plugin_repo()).exit_code == 0
    clean = charter("plugin", "update", "todo-free", cwd=kb)
    _patch_unlink(monkeypatch)

    result = charter("plugin", "update", "todo-free", cwd=kb)

    assert result.exit_code == clean.exit_code == 0
    assert result.stdout == clean.stdout
    [left] = _staging(kb)
    assert f"{left.relative_to(kb).as_posix()}/previous/{STUCK}" in result.stderr
    assert "warning" in result.stderr
    assert "files/leftover" in result.stderr


# --- the folder a plugin is cloned into ---


def _stuck_checkout(monkeypatch):
    """Make the folder a plugin is cloned into one that cannot be deleted."""
    real = files.remove_tree

    def remove_tree(path):
        return [path] if path.name.startswith("charter-plugin-") else real(path)

    monkeypatch.setattr("charter.install.remove_tree", remove_tree)


@pytest.mark.parametrize("command", [("add", "--from", "{repo}@v1.2.0"), ("update", "todo-free")])
def test_a_clone_folder_that_cannot_be_deleted_is_a_warning_not_a_traceback(
    charter, kb, plugin_repo, scratch, monkeypatch, command
):
    repo = plugin_repo()
    assert _add_from_git(charter, kb, repo).exit_code == 0
    argv = [word.format(repo=repo.as_posix()) for word in command]
    clean = charter("plugin", *argv, cwd=kb)
    _stuck_checkout(monkeypatch)

    result = charter("plugin", *argv, cwd=kb)

    assert result.exit_code == clean.exit_code == 0
    assert result.stdout == clean.stdout
    [left] = scratch.iterdir()
    assert left.name.startswith("charter-plugin-")
    assert left.as_posix() in result.stderr
    assert "files/leftover" in result.stderr
    assert "warning" in result.stderr


def test_a_clone_folder_that_cannot_be_deleted_after_a_failed_fetch_is_named_in_the_refusal(
    charter, kb, plugin_repo, scratch, monkeypatch
):
    repo = plugin_repo()
    _stuck_checkout(monkeypatch)

    result = charter("plugin", "add", "--from", f"{repo.as_posix()}@no-such-ref", cwd=kb)

    assert result.exit_code == 1
    assert "plugin/fetch-failed" in result.stdout
    assert "files/leftover" in result.stdout
    [left] = scratch.iterdir()
    assert left.as_posix() in result.stdout


# --- a failing command whose staging folder cannot be deleted ---


def _lock_write_fails(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("charter.install.write_lock", fail)


def test_a_refused_add_keeps_its_failure_and_adds_the_leftover_warning(charter, kb, instant, monkeypatch):
    _lock_write_fails(monkeypatch, OSError(5, "disk on fire"))
    _patch_unlink(monkeypatch)

    result = charter("plugin", "add", "--dev", PLUGIN, cwd=kb)

    [left] = _staging(kb)
    assert result.exit_code == 1
    assert "plugin/write-failed" in result.stdout
    assert "disk on fire" in result.stdout
    assert "files/leftover" in result.stdout
    assert left.relative_to(kb).as_posix() in result.stdout


def test_a_non_refused_failure_gets_a_note_naming_the_leftover(charter, kb, instant, monkeypatch):
    _lock_write_fails(monkeypatch, RuntimeError("boom"))
    _patch_unlink(monkeypatch)

    with pytest.raises(RuntimeError, match="boom") as raised:
        charter("plugin", "add", "--dev", PLUGIN, cwd=kb)

    [left] = _staging(kb)
    assert any(left.relative_to(kb).as_posix() in note for note in raised.value.__notes__)


# --- the --staged temporary directory ---


def _staged_plugin_kb(make_kb):
    contract = CONTRACT + "  todo-free: {source: tools/todo-free}\n"
    kb = make_kb({"charter.yaml": contract, **NOTES})
    run_git(kb, "init", "-q", "--initial-branch=main")
    shutil.copytree(FIXTURES / "plugins" / "todo-free", kb / "tools" / "todo-free")
    commit_files(kb, {})
    write_files(kb, {"notes/a.md": NOTES["notes/a.md"] + "\nMore.\n"})
    run_git(kb, "add", "-A")
    return kb


def _validate_staged(charter, kb):
    return charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=kb)


def test_a_staged_run_leaves_no_temporary_directory_behind(charter, make_kb, monkeypatch, tmp_path):
    kb = _staged_plugin_kb(make_kb)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    result = _validate_staged(charter, kb)

    assert result.exit_code == 0, result.stdout
    assert result.stderr == ""
    assert list(scratch.iterdir()) == []


def test_a_staged_temporary_directory_that_cannot_be_deleted_is_a_warning_and_the_exit_code_stays(
    charter, make_kb, instant, monkeypatch, tmp_path
):
    kb = _staged_plugin_kb(make_kb)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    clean = _validate_staged(charter, kb)
    with monkeypatch.context() as stuck:
        _patch_unlink(stuck)

        result = _validate_staged(charter, kb)

    assert result.exit_code == clean.exit_code == 0
    assert result.stdout == clean.stdout
    [left] = scratch.iterdir()
    assert (left / "tools" / "todo-free" / STUCK).as_posix() in result.stderr
    assert "files/leftover" in result.stderr
    assert "warning" in result.stderr
