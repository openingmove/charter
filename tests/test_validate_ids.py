import pytest
from conftest import FIXTURES


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, kind_yaml, notes, top=""):
    contract = f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_yaml}"
    files = {"charter.yaml": contract}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _note(kind="entry", **fields):
    return f"---\nkind: {kind}\n" + "".join(f"{name}: {value}\n" for name, value in fields.items()) + "---\n"


UNIQUE_ID = (
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      id: {type: int, unique: true}\n"
)


def _contiguous(field_yaml, collection="{contiguous: id}"):
    return (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        f"      id: {field_yaml}\n"
        f"    collection: {collection}\n"
    )


def test_ids_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "ids")

    assert result.exit_code == 1
    golden("ids", result.json())


def test_each_note_sharing_a_unique_value_names_the_others(charter, make_kb):
    kb = _kb(make_kb, UNIQUE_ID, {"a.md": _note(id=7), "b.md": _note(id=7), "c.md": _note(id=7), "d.md": _note(id=8)})

    result = _validate(charter, kb)

    assert _codes(result) == [(f"notes/{name}.md", 3, "ids/duplicate") for name in "abc"]
    messages = {d["path"]: d["message"] for d in result.json()["diagnostics"]}
    assert messages["notes/a.md"] == (
        "`id` is `7`, as in `notes/b.md`, `notes/c.md`; `id` must be unique across `entry` notes."
    )
    assert "`notes/a.md`, `notes/c.md`" in messages["notes/b.md"]


def test_unique_values_are_compared_within_a_kind_only(charter, make_kb):
    kind = UNIQUE_ID + "  other:\n" + UNIQUE_ID
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(kind="other", id=1)})

    result = _validate(charter, kb)

    assert _codes(result) == []


def test_missing_and_mistyped_values_are_left_to_the_schema_check(charter, make_kb):
    kb = _kb(make_kb, UNIQUE_ID, {
        "a.md": _note(),
        "b.md": _note(),
        "c.md": _note(id="seven"),
        "d.md": _note(id="seven"),
        "e.md": _note(id="''"),
        "f.md": _note(id="''"),
    })

    result = _validate(charter, kb)

    assert {code for _, _, code in _codes(result)} == {"schema/type"}


def test_unique_text_values_compare_exactly(charter, make_kb):
    kind = "    fields:\n      kind: {type: string, required: true}\n      code: {type: string, unique: true}\n"
    kb = _kb(make_kb, kind, {"a.md": _note(code="A1"), "b.md": _note(code="a1"), "c.md": _note(code="A1")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/a.md", 3, "ids/duplicate"), ("notes/c.md", 3, "ids/duplicate")]


def test_variant_notes_share_their_kinds_unique_values(charter, make_kb):
    kind = UNIQUE_ID + (
        "      shape: {type: string}\n"
        "    variants:\n"
        "      box: {set: {shape: box}}\n"
    )
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(id=1, shape="box")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/a.md", 3, "ids/duplicate"), ("notes/b.md", 3, "ids/duplicate")]


def test_a_field_unique_in_one_variant_only_reports_that_variants_notes(charter, make_kb):
    kind = (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      shape: {type: string}\n"
        "    variants:\n"
        "      box: {set: {shape: box}, fields: {serial: {type: int, unique: true}}}\n"
        "      tube: {set: {shape: tube}, fields: {serial: {type: int}}}\n"
    )
    kb = _kb(make_kb, kind, {
        "a.md": _note(shape="box", serial=1),
        "b.md": _note(shape="box", serial=1),
        "c.md": _note(shape="tube", serial=1),
        "d.md": _note(shape="tube", serial=2),
        "e.md": _note(shape="tube", serial=2),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("notes/a.md", 4, "ids/duplicate"),
        ("notes/b.md", 4, "ids/duplicate"),
    ]
    assert "`notes/b.md`, `notes/c.md`" in result.json()["diagnostics"][0]["message"]


def test_common_fields_may_be_unique_and_contiguous(charter, make_kb):
    kind = "    fields:\n      kind: {type: string, required: true}\n    collection: {contiguous: seq}\n"
    top = "common_fields:\n  seq: {type: int, unique: true, range: [1, 9]}\n"
    kb = _kb(make_kb, kind, {"a.md": _note(seq=2), "b.md": _note(seq=2)}, top=top)

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("charter.yaml", 9, "ids/gap"),
        ("notes/a.md", 3, "ids/duplicate"),
        ("notes/b.md", 3, "ids/duplicate"),
    ]


def test_file_mode_judges_uniqueness_against_the_whole_index(charter, make_kb):
    kb = _kb(make_kb, UNIQUE_ID, {
        "a.md": _note(id=1),
        "b.md": _note(id=1),
        "c.md": _note(id=2),
        "d.md": _note(id=2),
    })

    result = _validate(charter, kb, "--file", "notes/a.md")

    assert _codes(result) == [("notes/a.md", 3, "ids/duplicate")]
    assert "`notes/b.md`" in result.json()["diagnostics"][0]["message"]


def test_collection_count_reports_a_wrong_number_of_notes(charter, make_kb):
    kind = UNIQUE_ID + "    collection: {count: 3}\n"
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(id=2)})

    result = _validate(charter, kb)

    assert _codes(result) == [("charter.yaml", 8, "ids/count")]
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["message"] == "Kind `entry` has 2 notes, but its `collection` declares `count: 3`."


def test_collection_count_counts_variants_and_too_many_notes_is_reported(charter, make_kb):
    kind = (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      shape: {type: string}\n"
        "    variants:\n"
        "      box: {set: {shape: box}}\n"
        "    collection: {count: 1}\n"
    )
    kb = _kb(make_kb, kind, {"a.md": _note(), "b.md": _note(shape="box")})

    result = _validate(charter, kb)

    assert _codes(result) == [("charter.yaml", 10, "ids/count")]
    assert "has 2 notes" in result.json()["diagnostics"][0]["message"]


def test_the_right_count_is_clean(charter, make_kb):
    kb = _kb(make_kb, UNIQUE_ID + "    collection: {count: 2}\n", {"a.md": _note(id=1), "b.md": _note(id=2)})

    assert _codes(_validate(charter, kb)) == []


def test_contiguous_reports_gaps_from_the_range_minimum(charter, make_kb):
    kind = _contiguous("{type: int, range: [1, 100]}")
    notes = {f"{value}.md": _note(id=value) for value in (3, 4, 6, 10)}
    kb = _kb(make_kb, kind, notes)

    result = _validate(charter, kb)

    assert _codes(result) == [("charter.yaml", 8, "ids/gap")]
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["message"] == (
        "`entry` notes skip `id` 1–2, 5, 7–9; the collection's `id` values must have no gaps."
    )


def test_contiguous_without_a_range_starts_at_the_smallest_value(charter, make_kb):
    kind = _contiguous("{type: int}")
    kb = _kb(make_kb, kind, {"a.md": _note(id=2020), "b.md": _note(id=2021), "c.md": _note(id=2023)})

    result = _validate(charter, kb)

    assert "skip `id` 2022;" in result.json()["diagnostics"][0]["message"]


def test_contiguous_ignores_duplicates_missing_and_mistyped_values(charter, make_kb):
    kind = _contiguous("{type: int, range: [1, 9]}")
    kb = _kb(make_kb, kind, {
        "a.md": _note(id=1),
        "b.md": _note(id=2),
        "c.md": _note(id=2),
        "d.md": _note(),
        "e.md": _note(id="three"),
    })

    result = _validate(charter, kb)

    assert {code for _, _, code in _codes(result)} == {"schema/type"}


def test_file_mode_reports_a_collection_when_a_note_of_its_kind_is_touched(charter, make_kb):
    kind = _contiguous("{type: int}", "{count: 3, contiguous: id}") + "  other:\n" + UNIQUE_ID
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(id=3), "x.md": _note(kind="other", id=1)})

    touched = _validate(charter, kb, "--file", "notes/a.md")
    unrelated = _validate(charter, kb, "--file", "notes/x.md")
    contract = _validate(charter, kb, "--file", "charter.yaml")

    assert _codes(touched) == [("charter.yaml", 8, "ids/count"), ("charter.yaml", 8, "ids/gap")]
    assert _codes(unrelated) == []
    assert _codes(contract) == _codes(touched)


def test_a_touched_note_of_a_variant_or_unknown_variant_touches_its_kinds_collection(charter, make_kb):
    kind = (
        "    variant_by: form\n"
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "    variants:\n"
        "      short: {}\n"
        "    collection: {count: 3}\n"
    )
    kb = _kb(make_kb, kind, {"a.md": _note(form="short"), "b.md": _note(form="shrot")})

    result = _validate(charter, kb, "--file", "notes/b.md")

    assert _codes(result) == [("charter.yaml", 10, "ids/count"), ("notes/b.md", 3, "schema/unknown-variant")]
    assert "has 2 notes" in result.json()["diagnostics"][0]["message"]


def test_contiguous_gaps_stop_at_the_range_maximum(charter, make_kb):
    kind = _contiguous("{type: int, range: [1, 5]}")
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(id=3), "c.md": _note(id=9)})

    result = _validate(charter, kb)

    gap = next(d for d in result.json()["diagnostics"] if d["code"] == "ids/gap")
    assert gap["message"].startswith("`entry` notes skip `id` 2, 4–5;")
    assert ("notes/c.md", 3, "schema/range") in _codes(result)


def test_ids_check_can_be_disabled(charter, make_kb):
    kind = UNIQUE_ID + "    collection: {count: 9}\n"
    kb = _kb(make_kb, kind, {"a.md": _note(id=1), "b.md": _note(id=1)}, top="checks:\n  agents-include: {enabled: false}\n  ids: {enabled: false}\n")

    assert _codes(_validate(charter, kb)) == []


@pytest.mark.parametrize(
    ("kind_yaml", "line", "message"),
    [
        (
            "    fields:\n      tags: {type: list, unique: true}\n",
            6,
            "kinds.entry.fields.tags.unique: `unique` applies to single values, not lists.",
        ),
        (
            "    fields:\n      id: {type: int}\n    collection: {contiguous: ix}\n",
            7,
            "kinds.entry.collection.contiguous: `ix` is not a field of this kind.",
        ),
        (
            "    fields:\n      code: {type: string}\n    collection: {contiguous: code}\n",
            7,
            "kinds.entry.collection.contiguous: `code` holds `string`, but a contiguous sequence needs `int`.",
        ),
        (
            "    fields:\n      id: {type: int}\n    collection: {count: -1}\n",
            7,
            "kinds.entry.collection.count: must be at least 0, got `-1`.",
        ),
        (
            "    collection: {}\n",
            5,
            "kinds.entry.collection: must not be empty.",
        ),
        (
            "    collection: {size: 3}\n",
            5,
            "kinds.entry.collection: unknown key `size`.",
        ),
    ],
    ids=["unique list", "unknown field", "text field", "negative count", "empty", "unknown key"],
)
def test_invalid_ids_declarations_exit_two(charter, make_kb, kind_yaml, line, message):
    kb = _kb(make_kb, kind_yaml, {"a.md": "Untyped.\n"})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", line, "contract/invalid")]
    assert result.json()["diagnostics"][0]["message"] == message


def test_a_contiguous_field_suggests_the_closest_name(charter, make_kb):
    kb = _kb(make_kb, "    fields:\n      id: {type: int}\n    collection: {contiguous: ix}\n", {"a.md": "Untyped.\n"})

    result = _validate(charter, kb)

    assert result.json()["diagnostics"][0]["hint"] == "Did you mean `id`?"


def test_a_huge_gap_is_reported_as_one_counted_span(charter, make_kb):
    kind = _contiguous("{type: int}")
    kb = _kb(make_kb, kind, {"a.md": _note(id=3), "b.md": _note(id=50000000), "c.md": _note(id=5)})

    result = _validate(charter, kb)

    assert result.json()["diagnostics"][0]["message"] == (
        "`entry` notes skip `id` 4, 6–49999999 (49999994 values); the collection's `id` values must have no gaps."
    )


def test_a_gap_before_the_range_maximum_is_not_enumerated(charter, make_kb):
    kind = _contiguous("{type: int, range: [1, 90000000]}")
    kb = _kb(make_kb, kind, {"a.md": _note(id=2), "b.md": _note(id=90000000)})

    message = _validate(charter, kb).json()["diagnostics"][0]["message"]

    assert "skip `id` 1, 3–89999999 (89999997 values);" in message


def _variants(kind_fields="", variants=(("round", "{type: string}"),), collection=""):
    """A kind selected by `shape`; each variant redeclares `id`, and its line carries a `# here` marker."""
    text = "    variant_by: shape\n    fields:\n      kind: {type: string, required: true}\n"
    text += f"      shape: {{type: string}}\n{kind_fields}    variants:\n"
    for name, spec in variants:
        text += f"      {name}:\n        fields:\n          id: {spec}  # here\n"
    return text + collection


def _marked_line(top, kind_yaml):
    contract = f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_yaml}"
    return [number for number, text in enumerate(contract.splitlines(), 1) if text.endswith("# here")]


COMMON_UNIQUE = "common_fields:\n  id: {type: int, unique: true}\n"
INT_UNIQUE = "      id: {type: int, unique: true}\n"


@pytest.mark.parametrize(
    ("top", "kind_yaml", "message"),
    [
        (
            "",
            _variants("      id: {type: int}\n", collection="    collection: {contiguous: id}\n"),
            "`id` holds `string` here, but a contiguous sequence needs `int`.",
        ),
        (
            "",
            _variants("      id: {type: int}\n", [("round", "{type: bool}")], "    collection: {contiguous: id}\n"),
            "`id` holds `bool` here, but a contiguous sequence needs `int`.",
        ),
        (
            "",
            _variants(INT_UNIQUE, [("round", "{type: bool, unique: true}")]),
            "`id` holds `bool` here but `int` in the kind; a `unique` field keeps one type.",
        ),
        (
            "",
            _variants(INT_UNIQUE),
            "`id` holds `string` here but `int` in the kind; a `unique` field keeps one type.",
        ),
        (
            COMMON_UNIQUE,
            _variants("", [("round", "{type: bool}")]),
            "`id` holds `bool` here but `int` in the kind; a `unique` field keeps one type.",
        ),
        (
            "common_fields:\n  id: {type: int}\n",
            _variants("", [("round", "{type: bool}")], "    collection: {contiguous: id}\n"),
            "`id` holds `bool` here, but a contiguous sequence needs `int`.",
        ),
        (
            "",
            _variants("", [("round", "{type: int, unique: true}"), ("square", "{type: string}")]),
            "`id` holds `string` here but `int` in variant `round`; a `unique` field keeps one type.",
        ),
    ],
    ids=[
        "contiguous retyped",
        "contiguous retyped to bool",
        "unique retyped",
        "unique kind, plain variant",
        "unique common field",
        "contiguous common field",
        "unique in two variants",
    ],
)
def test_a_variant_cannot_retype_a_compared_field(charter, make_kb, top, kind_yaml, message):
    kb = _kb(make_kb, kind_yaml, {"a.md": _note(shape="round", id="x")}, top=top)

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", line, "contract/invalid") for line in _marked_line(top, kind_yaml)[-1:]]
    assert result.json()["diagnostics"][0]["message"].endswith(message)
    assert "Traceback" not in result.stderr


def test_a_variant_may_retype_a_field_that_is_neither_unique_nor_contiguous(charter, make_kb):
    kind_yaml = _variants("      id: {type: int}\n", [("round", "{type: string}")])
    kb = _kb(make_kb, kind_yaml, {"a.md": _note(shape="round", id="x")})

    assert _validate(charter, kb).exit_code == 0

    kb = _kb(make_kb, _variants("", [("round", "{type: bool}")]), {"a.md": _note(shape="round", id="true")},
             top="common_fields:\n  id: {type: int}\n")

    assert _validate(charter, kb).exit_code == 0
