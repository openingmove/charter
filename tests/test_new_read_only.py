"""`charter new` refuses a note whose path an `edit: read-only` policy covers, like `validate` would later."""

import re

import pytest

from conftest import commit_files, run_git

CONTRACT = """\
charter: 1
root: docs
paths:
  "Archive/**": {edit: read-only}
  "Research/**": {edit: create-only}
  "Archive/Open/**": {edit: create-only}
  "Hidden/**": {ignore: true}
kinds:
  entry:
    path: "Archive/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  nested:
    path: "Archive/{title}/Note.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  study:
    path: "Research/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  open:
    path: "Archive/Open/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  plain:
    path: "Plain/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""

CODE = "paths/read-only"


@pytest.fixture
def kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, "docs/Plain/Old.md": "---\nkind: plain\ntitle: Old\n---\n"})


def _new(charter, kb, *argv):
    return charter("new", *argv, "--format", "agent", cwd=kb)


def _line(result):
    """The text of the `paths/read-only` diagnostic and the lines after it (its hint), as printed."""
    match = re.search(rf"^.*{CODE}:.*(?:\n[ \t]+.*)*", result.stdout, re.MULTILINE)
    assert match, result.stdout
    return match.group(0)


def _tree(kb):
    return sorted(p.relative_to(kb).as_posix() for p in kb.rglob("*"))


@pytest.mark.parametrize("dry_run", [[], ["--dry-run"]], ids=["real", "dry-run"])
def test_a_note_under_a_read_only_path_is_refused_and_nothing_is_written(charter, kb, dry_run):
    before = _tree(kb)

    result = _new(charter, kb, "entry", "Ledger", *dry_run)

    assert result.exit_code == 1
    assert f"docs/Archive/Ledger.md: error {CODE}" in result.stdout
    assert _tree(kb) == before


def test_a_nested_title_path_is_tested_whole_and_no_folder_is_created(charter, kb):
    before = _tree(kb)

    result = _new(charter, kb, "nested", "Ledger")

    assert result.exit_code == 1
    assert CODE in result.stdout
    assert _tree(kb) == before
    assert not (kb / "docs" / "Archive").exists()


def test_the_message_is_the_one_validate_gives_a_file_added_there(charter, kb):
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {}, "base")
    refused = _new(charter, kb, "entry", "Ledger")
    commit_files(kb, {"docs/Archive/Ledger.md": "---\nkind: entry\ntitle: Ledger\n---\n"}, "add")
    # The same file as an uncommitted addition: what validate says about a note `new` had let through.
    run_git(kb, "rm", "-q", "--cached", "docs/Archive/Ledger.md")
    judged = charter("validate", "--format", "agent", cwd=kb)

    assert _line(refused) == _line(judged)


def test_a_create_only_path_still_allows_the_note(charter, kb):
    result = _new(charter, kb, "study", "Findings")

    assert result.exit_code == 0, result.stdout
    assert (kb / "docs/Research/Findings.md").is_file()


def test_a_narrower_create_only_glob_inside_a_read_only_folder_allows_the_note(charter, kb):
    result = _new(charter, kb, "open", "Gate")

    assert result.exit_code == 0, result.stdout
    assert (kb / "docs/Archive/Open/Gate.md").is_file()


def test_it_works_outside_a_git_repository(charter, kb):
    assert not (kb / ".git").exists()

    result = _new(charter, kb, "entry", "Ledger")

    assert result.exit_code == 1
    assert CODE in result.stdout
    assert "paths/edit-skipped" not in result.stdout
    assert not (kb / "docs/Archive").exists()


def test_a_note_outside_every_policy_is_written(charter, kb):
    result = _new(charter, kb, "plain", "Fresh")

    assert result.exit_code == 0, result.stdout
    assert (kb / "docs/Plain/Fresh.md").is_file()


def test_the_refusal_comes_with_the_note_s_other_problems(charter, kb):
    (kb / "docs/Archive").mkdir()
    (kb / "docs/Archive/Ledger.md").write_text("---\nkind: entry\ntitle: Ledger\n---\n", encoding="utf-8")

    result = _new(charter, kb, "entry", "Ledger")

    assert result.exit_code == 1
    assert CODE in result.stdout
    assert "new/exists" in result.stdout
