import unicodedata

import pytest
from charter.validate import contract_at
from conftest import FIXTURES, run_git, validate_commit_msg


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, kind_yaml, notes, top=""):
    contract = f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_yaml}"
    files = {"charter.yaml": contract}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _validate(charter, kb, *extra):
    return charter("validate", "--profile", "ci", "--format", "json", *extra, cwd=kb)


def _note(**fields):
    return "---\nkind: entry\n" + "".join(f"{name}: {value}\n" for name, value in fields.items()) + "---\n"


TITLED = (
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      title: {type: string, required: true}\n"
)
MATCHED = TITLED.replace("title: {type: string, required: true}", "title: {type: string, required: true, matches_filename: true}")


def test_filenames_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "filenames")

    assert result.exit_code == 1
    golden("filenames", result.json())


def test_wrong_path_names_the_expected_path(charter, make_kb):
    kb = _kb(make_kb, '    path: "Entries/{title}.md"\n' + TITLED, {"Elsewhere/Tide.md": _note(title="Tide")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Elsewhere/Tide.md", 2, "filenames/path")]
    assert "`notes/Entries/Tide.md`" in result.json()["diagnostics"][0]["message"]


def test_path_pattern_is_relative_to_the_contract_directory_when_root_is_it(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  entry:\n" + '    path: "Entries/{title}.md"\n' + TITLED,
        "Entries/Tide.md": _note(title="Tide"),
        "Tide.md": _note(title="Tide"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("Tide.md", 2, "filenames/path")]
    assert "`Entries/Tide.md`" in result.json()["diagnostics"][0]["message"]


SUFFIXED = (
    '    path: "Entries/{title}{status|suffix}.md"\n'
    '    suffix: {deferred: " (Deferred)", true: " (Yes)"}\n'
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      title: {type: string, required: true}\n"
    "      status: {type: string}\n"
    "      flag: {type: bool}\n"
)


@pytest.mark.parametrize(
    ("status", "filename"),
    [
        ("deferred", "Tide (Deferred).md"),
        ("open", "Tide.md"),
        (None, "Tide.md"),
        ("true", "Tide (Yes).md"),
    ],
    ids=["mapped", "unmapped", "missing", "yaml-true"],
)
def test_suffix_filter_maps_values_through_the_kinds_table(charter, make_kb, status, filename):
    fields = {"title": "Tide"} if status is None else {"title": "Tide", "status": status}
    kind = SUFFIXED.replace("status: {type: string}", "status: {type: bool}") if status == "true" else SUFFIXED
    kb = _kb(make_kb, kind, {f"Entries/{filename}": _note(**fields)})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("pattern", "title", "filename"),
    [
        ("{title|lower}", "Tide TABLES", "tide tables.md"),
        ("{title|slug}", "Storm at the Quay!", "storm-at-the-quay.md"),
        ("{title|slug}", "  Café -- Crème_Brûlée  ", "cafe-creme-brulee.md"),
        ("{title|slug}", "灯台 の 記録", "灯台-の-記録.md"),
        ("{title|slug|lower}", "Ünder Way", "under-way.md"),
        ("{title} ({title|lower})", "Tide", "Tide (tide).md"),
    ],
)
def test_lower_and_slug_filters(charter, make_kb, pattern, title, filename):
    kind = f'    path: "Entries/{pattern}.md"\n' + TITLED
    kb = _kb(make_kb, kind, {f"Entries/{filename}": _note(title=f'"{title}"')})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_numbers_dates_and_bools_render_as_written(charter, make_kb):
    kind = (
        '    path: "Entries/{id} {day} {ratio} {done}.md"\n'
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      id: {type: int, required: true}\n"
        "      day: {type: date, required: true}\n"
        "      ratio: {type: number, required: true}\n"
        "      done: {type: bool, required: true}\n"
    )
    kb = _kb(make_kb, kind, {"Entries/7 2026-03-01 0.5 false.md": _note(id=7, day="2026-03-01", ratio=0.5, done="false")})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_a_missing_or_mistyped_path_field_is_left_to_the_schema_check(charter, make_kb):
    kb = _kb(make_kb, '    path: "Entries/{title}.md"\n' + TITLED, {
        "Entries/a.md": _note(),
        "Entries/b.md": _note(title="[x, y]"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("notes/Entries/a.md", 1, "schema/required"),
        ("notes/Entries/b.md", 3, "schema/type"),
    ]


def test_matches_filename_compares_the_placeholder_part_of_the_path(charter, make_kb):
    kind = (
        '    path: "Entries/{id} {title}.md"\n'
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      id: {type: int, required: true}\n"
        "      title: {type: string, required: true, matches_filename: true}\n"
    )
    kb = _kb(make_kb, kind, {
        "Entries/1 Tide.md": _note(id=1, title="Tide"),
        "Entries/2 Old Name.md": _note(id=2, title="New Name"),
        "Entries/9 Ferry.md": _note(id=3, title="Ferry"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("notes/Entries/2 Old Name.md", 4, "filenames/matches-filename"),
        ("notes/Entries/9 Ferry.md", 2, "filenames/path"),
    ]
    mismatch = result.json()["diagnostics"][0]
    assert "`New Name`" in mismatch["message"] and "`Old Name`" in mismatch["message"]
    assert "`notes/Entries/2 New Name.md`" in mismatch["hint"]


TWO_MATCHED = (
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      a: {type: string, required: true, matches_filename: true}\n"
    "      b: {type: string, required: true, matches_filename: true}\n"
)


def test_literals_between_matched_placeholders_anchor_the_split(charter, make_kb):
    kb = _kb(make_kb, '    path: "Entries/{a} - {b}.md"\n' + TWO_MATCHED, {
        "Entries/Tide - Old Name.md": _note(a="Tide", b="New Name"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Entries/Tide - Old Name.md", 4, "filenames/matches-filename")]
    assert "`Old Name`" in result.json()["diagnostics"][0]["message"]


def test_an_ambiguous_split_reports_the_expected_path_instead_of_blaming_a_field(charter, make_kb):
    kb = _kb(make_kb, '    path: "Entries/{a} {b}.md"\n' + TWO_MATCHED, {
        "Entries/x y z.md": _note(a="p", b="q"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Entries/x y z.md", 2, "filenames/path")]
    assert "`notes/Entries/p q.md`" in result.json()["diagnostics"][0]["message"]


UNSAFE_KIND = (
    '    path: "Entries/{folder}/{title|lower} {code|slug}.md"\n'
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      title: {type: string, required: true}\n"
    "      folder: {type: string, required: true}\n"
    "      code: {type: string, required: true}\n"
)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("title", '"../../Escape"', "`/`"),
        ("title", '"Up/Down"', "`/`"),
        ("title", '"A\\\\B"', "`\\`"),
        ("title", '"What?"', "`?`"),
        ("title", '"Tide: High"', "`:`"),
        ("title", '"Pipe|Dream"', "`|`"),
        ("title", '"Bell\\tTower"', "control character"),
        ("folder", "CON", "reserves"),
        ("folder", "nul", "reserves"),
        ("folder", '"Harbour."', "dot or space"),
        ("folder", '"Harbour "', "dot or space"),
        ("folder", '".."', "named `..`"),
        ("code", '"!!!"', "renders as nothing"),
    ],
)
def test_a_value_that_cannot_form_a_portable_path_is_unsafe(charter, make_kb, field, value, reason):
    fields = {"title": "Tide", "folder": "Docks", "code": "A1", field: value}
    kb = _kb(make_kb, UNSAFE_KIND, {"Elsewhere/note.md": _note(**fields)})

    result = _validate(charter, kb)

    line = {"title": 3, "folder": 4, "code": 5}[field]
    assert _codes(result) == [("notes/Elsewhere/note.md", line, "filenames/unsafe-value")]
    assert reason in result.json()["diagnostics"][0]["message"]


def test_slug_makes_any_value_safe(charter, make_kb):
    kind = '    path: "Entries/{title|slug}.md"\n' + TITLED
    kb = _kb(make_kb, kind, {"Entries/up-down-what-con.md": _note(title='"Up/Down: What? CON"')})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("field_yaml", "value"),
    [
        ("title: {type: string, required: true}", "007"),
        ("title: {type: date, required: true}", "2026-03-01 10:00:00"),
        ("title: {type: int, required: true}", "true"),
    ],
    ids=["number for string", "datetime for date", "bool for int"],
)
def test_a_mistyped_value_is_left_to_the_schema_check(charter, make_kb, field_yaml, value):
    kind = '    path: "Entries/{title}.md"\n' + TITLED.replace("title: {type: string, required: true}", field_yaml)
    kb = _kb(make_kb, kind, {"Elsewhere/note.md": _note(title=value)})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Elsewhere/note.md", 3, "schema/type")]


def test_a_mistyped_suffix_value_is_left_to_the_schema_check(charter, make_kb):
    kb = _kb(make_kb, SUFFIXED, {"Elsewhere/Tide.md": _note(title="Tide", status=7)})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Elsewhere/Tide.md", 4, "schema/type")]


def test_matches_filename_without_a_path_pattern_compares_the_filename(charter, make_kb):
    kind = (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      id: {type: int, required: true, matches_filename: true}\n"
    )
    kb = _kb(make_kb, kind, {
        "Anywhere/12.md": _note(id=12),
        "Deep/er/13.md": _note(id=13),
        "14.md": _note(id=15),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/14.md", 3, "filenames/matches-filename")]
    assert "`notes/15.md`" in result.json()["diagnostics"][0]["hint"]


def test_unicode_normalisation_does_not_cause_a_mismatch(charter, make_kb):
    title = "Café"
    kind = '    path: "Entries/{title}.md"\n' + MATCHED
    filename = unicodedata.normalize("NFD", title)
    kb = _kb(make_kb, kind, {f"Entries/{filename}.md": _note(title=unicodedata.normalize("NFC", title))})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_rendering_is_the_same_with_backslashes_and_crlf(charter, make_kb):
    kind = "    path: 'Entries\\{title}.md'\n" + TITLED
    kb = _kb(make_kb, kind, {
        "Entries/Tide.md": _note(title="Tide").replace("\n", "\r\n"),
        "Other/Tide.md": _note(title="Tide").replace("\n", "\r\n"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Other/Tide.md", 2, "filenames/path")]
    assert "`notes/Entries/Tide.md`" in result.json()["diagnostics"][0]["message"]


def test_file_mode_checks_only_the_named_notes(charter, make_kb):
    kb = _kb(make_kb, '    path: "Entries/{title}.md"\n' + TITLED, {
        "Wrong/A.md": _note(title="A"),
        "Wrong/B.md": _note(title="B"),
    })

    result = _validate(charter, kb, "--file", "notes/Wrong/B.md")

    assert _codes(result) == [("notes/Wrong/B.md", 2, "filenames/path")]


def test_the_check_can_be_disabled(charter, make_kb):
    kb = _kb(
        make_kb,
        '    path: "Entries/{title}.md"\n' + TITLED,
        {"Wrong/A.md": _note(title="A")},
        top="checks:\n  agents-include: {enabled: false}\n  filenames: {enabled: false}\n",
    )

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("kind_yaml", "line"),
    [
        ('    path: "Entries/{tilte}.md"\n' + TITLED, 5),
        ('    path: "Entries/{title|upper}.md"\n' + TITLED, 5),
        ('    path: "Entries/{title.md"\n' + TITLED, 5),
        ('    path: "Entries/title}.md"\n' + TITLED, 5),
        ('    path: "Entries/{}.md"\n' + TITLED, 5),
        ('    path: "Entries/{title}"\n' + TITLED, 5),
        ('    path: "/Entries/{title}.md"\n' + TITLED, 5),
        ('    path: "C:/Entries/{title}.md"\n' + TITLED, 5),
        ('    path: "../Entries/{title}.md"\n' + TITLED, 5),
        ('    path: "Entries//{title}.md"\n' + TITLED, 5),
        ('    path: ""\n' + TITLED, 5),
        ('    path: "Entries/{title}{title|suffix}.md"\n' + TITLED, 5),
        ('    path: "Entries/{title}.md"\n    suffix: {a: " (A)"}\n' + TITLED, 6),
        ("    suffix: {a: \" (A)\"}\n" + TITLED, 5),
        ('    path: "Entries/{title}.md"\n    suffix: {a: [x]}\n' + TITLED, 6),
        ('    path: "Entries/{note}.md"\n' + TITLED + "      note: {type: string}\n", 5),
        ('    path: "Entries/{tags}.md"\n' + TITLED + "      tags: {type: list, required: true}\n", 5),
        (
            '    path: "Entries/{title|slug}.md"\n' + MATCHED,
            5,
        ),
        (TITLED + "      tags: {type: list, matches_filename: true}\n", 8),
        (TITLED.replace("title: {type: string, required: true}", "title: {type: string, matches_filename: 1}"), 7),
    ],
    ids=[
        "unknown field",
        "unknown filter",
        "unclosed brace",
        "unopened brace",
        "empty placeholder",
        "not markdown",
        "absolute",
        "drive",
        "parent folder",
        "empty folder",
        "empty path",
        "suffix filter without table",
        "suffix table without filter",
        "suffix table without path",
        "suffix value not text",
        "optional field",
        "list field",
        "matches_filename only filtered",
        "matches_filename on a list",
        "matches_filename not a bool",
    ],
)
def test_invalid_path_pattern_exits_two_with_contract_invalid(charter, make_kb, kind_yaml, line):
    kb = _kb(make_kb, kind_yaml, {"a.md": _note(title="a")})

    result = _validate(charter, kb)

    assert result.exit_code == 2, result.stdout
    assert _codes(result) == [("charter.yaml", line, "contract/invalid")]


@pytest.mark.parametrize(
    ("title", "code", "slugged"),
    [("Tide", '"!!!"', True), ('"What?"', "A1", False)],
)
def test_the_slug_hint_depends_on_whether_the_placeholder_already_uses_it(charter, make_kb, title, code, slugged):
    kb = _kb(make_kb, UNSAFE_KIND, {"Elsewhere/note.md": _note(title=title, folder="Docks", code=code)})

    hint = _validate(charter, kb).json()["diagnostics"][0]["hint"]

    assert ("render it through `|slug`" in hint) is not slugged
    assert ("at least one letter or digit" in hint) is slugged


@pytest.mark.parametrize(
    ("pattern", "fragment"),
    [
        ("Things?/{title}.md", "`?`"),
        ("Things/{title}?.md", "`?`"),
        ("Things:/{title}.md", "`:`"),
        ("CON/{title}.md", "reserves"),
        ("Docs/aux.old/{title}.md", "reserves"),
        ("Things./{title}.md", "dot or space"),
        ("Things /{title}.md", "dot or space"),
        ("Things/{title}. /{title}.md", "dot or space"),
    ],
)
def test_an_unportable_literal_segment_fails_at_load(charter, make_kb, pattern, fragment):
    kb = _kb(make_kb, f'    path: "{pattern}"\n' + TITLED, {"keep.md": _note(title="Tide")})

    result = charter("validate", "--format", "json", cwd=kb)

    diagnostics = result.json()["diagnostics"]
    assert result.exit_code == 2
    assert [(d["line"], d["code"]) for d in diagnostics] == [(5, "contract/invalid")]
    assert diagnostics[0]["message"].startswith("kinds.entry.path:")
    assert fragment in diagnostics[0]["message"]


def test_a_portable_literal_segment_still_loads(charter, make_kb):
    kb = _kb(make_kb, '    path: "Concord/{title}.md"\n' + TITLED, {"Concord/Tide.md": _note(title="Tide")})

    assert _validate(charter, kb).exit_code == 0


def test_a_decomposed_root_matches_nfc_note_paths(charter, make_kb):
    # The directory is created from the very string the contract holds, so this works on any file system.
    root = unicodedata.normalize("NFD", "Café")
    contract = f"charter: 1\nroot: {root}\nkinds:\n  entry:\n    path: \"Entries/{{title}}.md\"\n{TITLED}"
    kb = make_kb({"charter.yaml": contract, f"{root}/Entries/Tide.md": _note(title="Tide")})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout
    assert result.json()["diagnostics"] == []


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_misplacement_compares_the_root_in_nfc_whatever_the_note_path_form(make_kb, form):
    root = unicodedata.normalize("NFD", "Café")
    contract = f"charter: 1\nroot: {root}\nkinds:\n  entry:\n    path: \"Entries/{{title}}.md\"\n{TITLED}"
    kb = make_kb({"charter.yaml": contract, f"{root}/Entries/Tide.md": _note(title="Tide")})
    loaded = contract_at(kb / "charter.yaml")
    frontmatter = {"kind": "entry", "title": "Tide"}

    path = unicodedata.normalize(form, f"{root}/Entries/Tide.md")

    assert loaded.root_path == root
    assert loaded.misplacement(path, loaded.shape_of(frontmatter), frontmatter) is None


@pytest.mark.parametrize(("root_form", "path_form"), [("NFD", "NFC"), ("NFC", "NFD")])
def test_a_path_in_another_normal_form_is_held_and_still_has_its_policy(make_kb, root_form, path_form):
    root = unicodedata.normalize(root_form, "Café")
    contract = f"charter: 1\nroot: {root}\npaths:\n  \"Drafts/**\": {{ignore: true}}\nkinds:\n  entry:\n{TITLED}"
    kb = make_kb({"charter.yaml": contract, f"{root}/Entries/Tide.md": _note(title="Tide")})
    loaded = contract_at(kb / "charter.yaml")
    under = unicodedata.normalize(path_form, root)

    assert loaded.holds(f"{under}/Entries/Tide.md")
    assert not loaded.holds(f"{under}/Drafts/Tide.md")
    assert not loaded.holds(f"{unicodedata.normalize(path_form, 'Other')}/Tide.md")


def _index_entry(repo, path, content):
    # Written straight to the index so git keeps the exact spelling whatever the file system or git config does.
    blob = run_git(repo, "hash-object", "-w", "--stdin", input=content)
    run_git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")


def test_an_edit_policy_applies_to_a_staged_path_in_another_normal_form_than_the_root(charter, make_kb):
    nfd, nfc = (unicodedata.normalize(form, "Café") for form in ("NFD", "NFC"))
    contract = f'charter: 1\nroot: {nfd}\npaths:\n  "Archive/**": {{edit: read-only}}\nkinds:\n  entry:\n{TITLED}'
    kb = make_kb({"charter.yaml": contract})
    run_git(kb, "init", "-q", "--initial-branch=main")
    # macOS git otherwise reports every name precomposed, which would hide the decomposed root.
    run_git(kb, "config", "core.precomposeunicode", "false")
    run_git(kb, "add", "charter.yaml")
    _index_entry(kb, f"{nfd}/Archive/old.md", _note(title="Old"))
    run_git(kb, "commit", "-q", "-m", "base")
    _index_entry(kb, f"{nfc}/Archive/new.md", _note(title="New"))

    result = validate_commit_msg(charter, kb, "Add a note\n")

    found = [(d["path"], d["code"]) for d in result.json()["diagnostics"]]
    assert (f"{nfc}/Archive/new.md", "paths/read-only") in found


def test_a_named_file_that_is_itself_a_note_is_not_mapped_to_its_look_alike(charter, make_kb):
    nfd, nfc = (unicodedata.normalize(form, "Café") for form in ("NFD", "NFC"))
    contract = f"charter: 1\nroot: {nfd}\nkinds:\n  entry:\n    path: \"Entries/{{title}}.md\"\n{TITLED}"
    # The NFC copy is correctly named and the NFD copy is not; naming the NFC copy must not judge the NFD one.
    kb = make_kb(
        {"charter.yaml": contract, f"{nfd}/Entries/Tide.md": _note(title="Other"), f"{nfc}/Entries/Tide.md": _note(title="Tide")}
    )
    if len(list(kb.iterdir())) < 3:  # charter.yaml and one directory per spelling
        pytest.skip("this file system folds the two spellings into one directory")

    result = charter("validate", "--format", "json", "--file", f"{nfc}/Entries/Tide.md", cwd=kb)

    assert result.json()["diagnostics"] == []


@pytest.mark.parametrize(("root_form", "path_form"), [("NFD", "NFC"), ("NFC", "NFD")])
def test_validate_file_judges_a_path_whose_form_differs_from_the_root(charter, make_kb, root_form, path_form):
    root = unicodedata.normalize(root_form, "Café")
    other = unicodedata.normalize(path_form, "Café")
    contract = f"charter: 1\nroot: {root}\nkinds:\n  entry:\n    path: \"Entries/{{title}}.md\"\n{TITLED}"
    misnamed = _note(title="Other")
    # Where the two spellings are one directory (APFS), the second write replaces the first and the --file path
    # names the root's note in another form.
    kb = make_kb({"charter.yaml": contract, f"{root}/Entries/Tide.md": misnamed, f"{other}/Entries/Tide.md": misnamed})
    if len(list(kb.iterdir())) == 3:  # charter.yaml and one directory per spelling
        # Two files: the path names a file of its own, which the look-alike test above covers.
        pytest.skip("this file system keeps the two spellings apart")

    result = charter("validate", "--format", "json", "--file", f"{other}/Entries/Tide.md", cwd=kb)

    assert result.exit_code == 1, result.stdout
    assert [d["code"] for d in result.json()["diagnostics"]] == ["filenames/path"]
