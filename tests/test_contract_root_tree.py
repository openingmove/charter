"""`root` is checked against the tree a contract is loaded from, not the working copy on disk."""

import shutil

import pytest
from conftest import commit_files, run_git, write_files

from charter import git

NOTE = "---\nkind: entry\n---\n"


def _contract(root):
    return f"charter: 1\nroot: {root}\nkinds:\n  entry:\n    fields:\n      kind: {{type: string, required: true}}\n"


def _repo(make_kb, root, folder):
    kb = make_kb({"charter.yaml": _contract(root), f"{folder}/a.md": NOTE})
    run_git(kb, "init", "-q", "--initial-branch=main")
    return kb, commit_files(kb, {}, "base")


def _move_root(kb, old, new):
    (kb / new).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(kb / old, kb / new)
    write_files(kb, {"charter.yaml": _contract(new)})


def _range(charter, kb, base):
    return charter("validate", f"--range={base}..HEAD", "--format", "json", cwd=kb)


def _output(result):
    return result.stderr + result.stdout


def test_a_range_that_renames_the_root_folder_loads_each_commits_own_root(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    _move_root(kb, "notes", "docs")
    commit_files(kb, {}, "Rename the root")
    # The checkout ends on a third name, so the middle commit's root is not on disk.
    _move_root(kb, "docs", "pages")
    commit_files(kb, {}, "Rename it again")

    assert _range(charter, kb, base).exit_code == 0


def test_a_staged_rename_of_the_root_folder_loads_the_staged_root(charter, make_kb):
    kb, _ = _repo(make_kb, "notes", "notes")
    _move_root(kb, "notes", "docs")
    run_git(kb, "add", "-A")
    # Moved away so only the index can say where the root is.
    shutil.move(kb / "docs", kb / "elsewhere")

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.exit_code == 0


def test_a_nested_root_of_several_segments_is_found_in_the_tree(charter, make_kb):
    kb, base = _repo(make_kb, "a/b/notes", "a/b/notes")
    _move_root(kb, "a/b/notes", "c/d/e")
    commit_files(kb, {}, "Move the root")
    _move_root(kb, "c/d/e", "f/g/h")
    commit_files(kb, {}, "Move it again")

    assert _range(charter, kb, base).exit_code == 0


def test_a_root_of_dot_needs_no_directory_in_the_tree(charter, make_kb):
    kb = make_kb({"charter.yaml": _contract("."), "a.md": NOTE})
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = commit_files(kb, {}, "base")
    commit_files(kb, {"b.md": NOTE}, "More")

    assert _range(charter, kb, base).exit_code == 0


def test_a_root_that_is_a_file_in_the_tree_is_not_a_directory(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    commit_files(kb, {"charter.yaml": _contract("file.md"), "file.md": NOTE}, "Point the root at a file")

    result = _range(charter, kb, base)

    assert result.exit_code == 2
    assert "directory `file.md` does not exist." in _output(result)


def test_a_root_missing_from_the_working_copy_still_fails_without_a_tree(charter, make_kb):
    kb = make_kb({"charter.yaml": _contract("nowhere"), "a.md": NOTE})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert "directory `nowhere` does not exist." in _output(result)


def test_a_root_that_is_an_empty_folder_on_disk_but_absent_from_the_tree_is_called_empty(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    commit_files(kb, {"charter.yaml": _contract("ghost")}, "Point at a folder that is not committed")
    (kb / "ghost").mkdir()

    result = _range(charter, kb, base)

    assert result.exit_code == 2
    assert "no files under `ghost` in the commit." in _output(result)


def test_a_commit_that_removes_the_root_is_not_given_the_previous_commits_contract(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    commit_files(kb, {"notes/b.md": NOTE}, "Add a note")
    shutil.rmtree(kb / "notes")
    commit_files(kb, {}, "Remove every note")
    (kb / "notes").mkdir()  # the checkout has the folder, the commit does not

    result = _range(charter, kb, base)

    assert result.exit_code == 2
    assert "no files under `notes` in the commit." in _output(result)


def test_the_memo_does_not_reuse_a_directory_answer_for_a_tree_that_lost_it(make_kb):
    # Pins the recorded ("directory", path) question: a contract's root check must be replayed on a later tree.
    kb, _ = _repo(make_kb, "notes", "notes")
    memo = git.ContentMemo()
    asked = []

    def compute(tree):
        asked.append(tree.is_directory("notes"))
        return asked[-1]

    first = git.staged(kb)
    try:
        assert first.tree.answer(("directory", "notes")) is True
        assert memo.get(first.tree, compute) is True
    finally:
        first.close()
    run_git(kb, "rm", "-q", "-r", "--cached", "notes")
    second = git.staged(kb)
    try:
        assert second.tree.answer(("directory", "notes")) is False
        assert memo.get(second.tree, compute) is False
    finally:
        second.close()
    assert asked == [True, False]


def test_a_root_that_is_a_directory_link_passes_on_disk_but_is_named_a_link_in_a_tree(charter, make_kb):
    # A tree has no directory entry for a link, so only the working copy follows such a root.
    kb = make_kb({"charter.yaml": _contract("link"), "real/a.md": NOTE})
    try:
        (kb / "link").symlink_to("real", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create symbolic links")
    assert charter("validate", "--format", "json", cwd=kb).exit_code == 0
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "-A")

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert "`link` is a link, which the index cannot follow" in _output(result)
    assert "does not exist" not in _output(result)


def test_a_staged_root_with_no_files_says_so_though_the_directory_exists(charter, make_kb):
    # A tree holds no empty directories, so a root with nothing at or below it is empty there, not missing.
    kb, _ = _repo(make_kb, "notes", "notes")
    (kb / "empty").mkdir()
    write_files(kb, {"charter.yaml": _contract("empty")})
    run_git(kb, "add", "-A")

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert "no files under `empty` in the index." in _output(result)


def test_a_committed_root_with_no_files_says_so_though_the_directory_exists(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    (kb / "empty").mkdir()
    commit_files(kb, {"charter.yaml": _contract("empty")}, "Point the root at an empty folder")

    result = _range(charter, kb, base)

    assert result.exit_code == 2
    assert "no files under `empty` in the commit." in _output(result)


def test_a_committed_root_that_is_a_directory_link_is_named_a_link_in_the_commit(charter, make_kb):
    kb, base = _repo(make_kb, "notes", "notes")
    try:
        (kb / "link").symlink_to("notes", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create symbolic links")
    commit_files(kb, {"charter.yaml": _contract("link")}, "Point the root at a link")

    result = _range(charter, kb, base)

    assert result.exit_code == 2
    assert "`link` is a link, which the commit cannot follow" in _output(result)


def test_a_root_inside_a_linked_folder_is_named_a_link_in_a_tree(charter, make_kb):
    kb, _ = _repo(make_kb, "notes", "notes")
    try:
        (kb / "link").symlink_to("notes", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create symbolic links")
    (kb / "notes" / "sub").mkdir()
    write_files(kb, {"charter.yaml": _contract("link/sub")})
    run_git(kb, "add", "-A")

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert "`link/sub` is a link" in _output(result)


def test_a_root_missing_everywhere_keeps_its_message_in_a_tree(charter, make_kb):
    kb, _ = _repo(make_kb, "notes", "notes")
    write_files(kb, {"charter.yaml": _contract("nowhere")})
    run_git(kb, "add", "-A")

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert "directory `nowhere` does not exist." in _output(result)
