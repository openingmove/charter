import pytest
from conftest import FIXTURES

KINDS = (
    "kinds:\n"
    "  book: {fields: {kind: {type: string, required: true}}}\n"
    "  research: {fields: {kind: {type: string, required: true}}}\n"
)


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, paths_yaml, notes):
    files = {"charter.yaml": f"charter: 1\nroot: notes\npaths:\n{paths_yaml}{KINDS}"}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def test_path_policies_ignore_files_and_restrict_kinds(charter, golden):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=FIXTURES / "paths")

    assert result.exit_code == 1
    golden("paths", result.json())


def test_ignored_file_is_not_a_note_even_when_unreadable(charter, make_kb):
    kb = _kb(make_kb, '  "Attachments/**": {ignore: true}\n', {"keep.md": "---\nkind: book\n---\n"})
    (kb / "notes/Attachments").mkdir()
    (kb / "notes/Attachments/blob.md").write_bytes(b"\xff\xfe\x00\x01not text")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize("order", ["general first", "specific first"])
def test_most_specific_glob_wins_regardless_of_declaration_order(charter, make_kb, order):
    general = '  "Research/**": {kinds: [research]}\n'
    specific = '  "Research/Library/**": {kinds: [book]}\n'
    paths_yaml = general + specific if order == "general first" else specific + general
    kb = _kb(make_kb, paths_yaml, {
        "Research/topic.md": "---\nkind: research\n---\n",
        "Research/Library/book.md": "---\nkind: book\n---\n",
        "Research/Library/misplaced.md": "---\nkind: research\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Research/Library/misplaced.md", 2, "paths/kind-not-allowed")]


def test_single_star_does_not_cross_folders(charter, make_kb):
    kb = _kb(make_kb, '  "Research/*.md": {kinds: [research]}\n', {
        "Research/top.md": "---\nkind: book\n---\n",
        "Research/Sub/deeper.md": "---\nkind: book\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Research/top.md", 2, "paths/kind-not-allowed")]


def test_double_star_matches_any_depth_including_none(charter, make_kb):
    kb = _kb(make_kb, '  "**/Drafts/**": {ignore: true}\n', {
        "Drafts/a.md": "---\nkind: nonsense\n---\n",
        "Books/Drafts/b.md": "---\nkind: nonsense\n---\n",
        "Books/Old/Drafts/c.md": "---\nkind: nonsense\n---\n",
        "Books/NotDrafts/d.md": "---\nkind: nonsense\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Books/NotDrafts/d.md", 2, "schema/unknown-kind")]


@pytest.mark.parametrize(
    "paths_yaml",
    [
        '  "Templates/**": {ignore: true}\n  "Research/**": {kinds: [research]}\n',
        "  'Templates\\**': {ignore: true}\n  'Research\\**': {kinds: [research]}\n",
    ],
    ids=["forward slashes", "backslashes"],
)
def test_globs_match_the_same_with_either_path_separator(charter, make_kb, paths_yaml):
    kb = _kb(make_kb, paths_yaml, {
        "Templates/Book.md": "# {{title}}\n",
        "Research/Deep/stray.md": "---\nkind: book\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Research/Deep/stray.md", 2, "paths/kind-not-allowed")]


def test_note_without_a_declared_kind_is_left_to_the_schema_check(charter, make_kb):
    kb = _kb(make_kb, '  "Research/**": {kinds: [research]}\n', {
        "Research/none.md": "No frontmatter.\n",
        "Research/odd.md": "---\nkind: [a, b]\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [
        ("notes/Research/none.md", 1, "schema/missing-frontmatter"),
        ("notes/Research/odd.md", 2, "schema/unknown-kind"),
    ]


def test_a_key_a_specific_glob_leaves_unset_falls_through_to_a_broader_glob(charter, make_kb):
    kb = _kb(make_kb, '  "Research/**": {kinds: [research]}\n  "Research/Drafts/**": {ignore: false}\n', {
        "Research/Drafts/stray.md": "---\nkind: book\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Research/Drafts/stray.md", 2, "paths/kind-not-allowed")]
    assert "`Research/**`" in result.json()["diagnostics"][0]["message"]


def test_a_specific_glob_can_lift_a_broader_ignore(charter, make_kb):
    kb = _kb(make_kb, '  "Archive/**": {ignore: true}\n  "Archive/Keep/**": {ignore: false}\n', {
        "Archive/old.md": "---\nkind: nonsense\n---\n",
        "Archive/Keep/kept.md": "---\nkind: nonsense\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/Archive/Keep/kept.md", 2, "schema/unknown-kind")]


@pytest.mark.parametrize(
    ("paths_yaml", "line"),
    [
        ('  "Research/**": {kinds: [poetry]}\n', 4),
        ('  "Research/**": {kinds: []}\n', 4),
        ('  "Research/**": {kinds: research}\n', 4),
        ('  "Research/**": {ignore: yes please}\n', 4),
        ('  "Research/**": {colour: blue}\n', 4),
        ('  "Research/**": true\n', 4),
        ('  "Research/**": {ignore: true, kinds: [book]}\n', 4),
        ('  "": {ignore: true}\n', 3),
        ('  "/": {ignore: true}\n', 3),
    ],
)
def test_invalid_path_policy_exits_two_with_contract_invalid(charter, make_kb, paths_yaml, line):
    kb = _kb(make_kb, paths_yaml, {"a.md": "---\nkind: book\n---\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", line, "contract/invalid")]
