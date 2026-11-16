import pytest
from conftest import run_git, validate_commit_msg
from hostile_names import git_tree_with_paths

from charter.globs import compile_glob

# Built with chr() so no invisible character sits in this source file.
TERMINATORS = [chr(code) for code in (0x0A, 0x0D, 0x0B, 0x0C, 0x2028, 0x85)]
NEWLINE = chr(10)


@pytest.mark.parametrize("char", TERMINATORS, ids=[f"U+{ord(c):04X}" for c in TERMINATORS])
@pytest.mark.parametrize(
    ("glob", "template"),
    [
        ("Locked/**", "Locked/a{c}b.md"),
        ("Locked/**", "Locked/sub/{c}"),
        ("**", "x{c}y/z.md"),
        ("Locked/*.md", "Locked/a{c}b.md"),
        ("Locked/*", "Locked/{c}"),
        ("Locked/a?b.md", "Locked/a{c}b.md"),
        ("Locked/?", "Locked/{c}"),
    ],
)
def test_wildcards_match_names_containing_a_line_terminator(glob, template, char):
    assert compile_glob(glob).fullmatch(template.format(c=char))


def test_slash_semantics_are_unchanged_by_line_terminators():
    assert not compile_glob("Locked/*").fullmatch(f"Locked/a{NEWLINE}b/c")
    assert not compile_glob("Locked/?").fullmatch(f"Locked/{NEWLINE}/")
    assert not compile_glob("Locked/*.md").fullmatch(f"Other/a{NEWLINE}b.md")


CONTRACT = """\
charter: 1
root: notes
paths:
  "Locked/**": {edit: read-only}
  "Create/**": {edit: create-only}
  "Skipped/**": {ignore: true}
  "Typed/**": {kinds: [entry]}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
  other:
    fields:
      kind: {type: string, required: true}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"
WRONG_KIND = "---\nkind: other\n---\n"


def _repo(make_kb, committed):
    kb = make_kb({"charter.yaml": CONTRACT})
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "charter.yaml")
    for path, text in committed.items():
        git_tree_with_paths(kb, [path], text)
    run_git(kb, "commit", "-q", "-m", "base")
    return kb


@pytest.mark.parametrize(("folder", "code"), [("Locked", "paths/read-only"), ("Create", "paths/create-only")])
def test_an_edited_newline_named_file_under_an_edit_policy_is_reported(charter, make_kb, folder, code):
    name = f"notes/{folder}/nl{NEWLINE}name.md"
    kb = _repo(make_kb, {name: NOTE})
    git_tree_with_paths(kb, [name], EDITED)

    result = validate_commit_msg(charter, kb, "Change\n")

    assert [(d["path"], d["code"]) for d in result.json()["diagnostics"]] == [(name, code)]


def _kb_with_newline_file(make_kb, folder, text):
    kb = make_kb({"charter.yaml": CONTRACT})
    path = kb / "notes" / folder / f"nl{NEWLINE}name.md"
    path.parent.mkdir(parents=True)
    try:
        path.write_text(text, encoding="utf-8", newline="")
    except OSError:
        pytest.skip("this filesystem cannot hold a newline in a file name")
    return kb


def _full_run(charter, kb):
    diagnostics = charter("validate", "--profile", "ci", "--format", "json", cwd=kb).json()["diagnostics"]
    return [d for d in diagnostics if d["severity"] != "info"]


def test_an_ignored_newline_named_file_is_not_validated(charter, make_kb):
    kb = _kb_with_newline_file(make_kb, "Skipped", "no front matter\n")

    assert _full_run(charter, kb) == []


def test_kinds_apply_to_a_newline_named_file(charter, make_kb):
    kb = _kb_with_newline_file(make_kb, "Typed", WRONG_KIND)

    diagnostics = _full_run(charter, kb)

    assert [d["path"] for d in diagnostics] == [f"notes/Typed/nl{NEWLINE}name.md"], diagnostics
