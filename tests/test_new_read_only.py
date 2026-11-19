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


def test_the_agent_format_refusal_is_one_line_with_the_exact_wording(charter, kb):
    # Pinned here because `validate` and `new` share the builder, so comparing the two alone would miss a change.
    result = _new(charter, kb, "entry", "Ledger")

    assert result.stdout == (
        f"docs/Archive/Ledger.md: error {CODE}: This file is read-only under path policy `Archive/**`, "
        "but it was added. (hint: Remove the file; nothing may be added under a read-only path. "
        "If a human decided on this edit, they can allow it with the commit-message trailer "
        f"`Charter-Allow: {CODE} docs/Archive/Ledger.md — <reason>`.)\n"
    )


def test_an_unplaceable_note_under_a_read_only_folder_is_refused_as_unplaceable_only(charter, make_kb):
    # Schema off, so nothing else explains why `{number}` cannot be rendered from a mistyped value.
    contract = CONTRACT.replace("kinds:\n", "checks:\n  schema: {enabled: false}\nkinds:\n", 1) + (
        "  numbered:\n"
        '    path: "Archive/{number}.md"\n'
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      number: {type: int, required: true}\n"
    )
    # Old.md only makes the `docs` root exist; without it the contract is invalid.
    kb = make_kb({"charter.yaml": contract, "docs/Plain/Old.md": "---\nkind: plain\ntitle: Old\n---\n"})
    before = _tree(kb)

    result = _new(charter, kb, "numbered", "--set", "number=four")

    assert result.exit_code == 1
    assert "new/unplaceable" in result.stdout
    # No path was rendered, so there is no file to judge against the read-only policy.
    assert CODE not in result.stdout
    assert _tree(kb) == before
