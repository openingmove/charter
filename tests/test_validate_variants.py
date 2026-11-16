import pytest
from conftest import FIXTURES


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, kind_yaml, notes, top=""):
    contract = f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_yaml}"
    files = {"charter.yaml": contract}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _validate(charter, kb):
    return charter("validate", "--profile", "ci", "--format", "json", cwd=kb)


def _note(**fields):
    return "---\nkind: entry\n" + "".join(f"{name}: {value}\n" for name, value in fields.items()) + "---\n"


def test_variants_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "variants")

    assert result.exit_code == 1
    golden("variants", result.json())


def test_a_wrong_path_names_the_variant_and_its_pattern(charter):
    result = _validate(charter, FIXTURES / "variants")

    wrong = next(d for d in result.json()["diagnostics"] if d["code"] == "filenames/path")
    assert "`boat/sailboat`" in wrong["message"]
    assert "`docs/Sailboats/Gull (ketch).md`" in wrong["message"]


def test_an_unknown_variant_suggests_the_closest_name(charter):
    result = _validate(charter, FIXTURES / "variants")

    unknown = next(d for d in result.json()["diagnostics"] if d["code"] == "schema/unknown-variant")
    assert "`refit`" in unknown["message"] and "`log`" in unknown["message"]
    assert "`repair`" in unknown["hint"]


SET_BY_TWO = (
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      shape: {type: string}\n"
    "      size: {type: int}\n"
    "    variants:\n"
    "      big_box:\n"
    "        set: {shape: box, size: 3}\n"
    "        fields:\n"
    "          lid: {type: bool, required: true}\n"
)


@pytest.mark.parametrize(
    ("fields", "is_variant"),
    [
        ({"shape": "box", "size": 3}, True),
        ({"shape": "box", "size": 2}, False),
        ({"shape": "box"}, False),
        ({"shape": "box", "size": "'3'"}, False),
    ],
    ids=["all match", "one differs", "one missing", "text for int"],
)
def test_a_note_is_a_variant_only_when_every_set_value_matches(charter, make_kb, fields, is_variant):
    kb = _kb(make_kb, SET_BY_TWO, {"a.md": _note(**fields)})

    result = _validate(charter, kb)

    codes = [code for _, _, code in _codes(result)]
    assert ("schema/required" in codes) == is_variant


def test_a_variant_field_may_override_the_kinds_declaration(charter, make_kb):
    kind = (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      shape: {type: string}\n"
        "      size: {type: int}\n"
        "    variants:\n"
        "      box:\n"
        "        set: {shape: box}\n"
        "        fields:\n"
        "          size: {type: int, required: true, range: [1, 3]}\n"
    )
    kb = _kb(make_kb, kind, {"a.md": _note(shape="box", size=9), "b.md": _note(shape="tube", size=9), "c.md": _note(shape="box")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/a.md", 4, "schema/range"), ("notes/c.md", 1, "schema/required")]


def test_variant_by_field_is_implicitly_a_required_text_field(charter, make_kb):
    kind = (
        "    variant_by: form\n"
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "    variants:\n"
        "      short: {}\n"
        "      long: {}\n"
    )
    kb = _kb(make_kb, kind, {
        "a.md": _note(form="short"),
        "b.md": _note(),
        "c.md": _note(form=3),
        "d.md": _note(form="shrot"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("notes/b.md", 1, "schema/required"),
        ("notes/c.md", 3, "schema/type"),
        ("notes/d.md", 3, "schema/unknown-variant"),
    ]


def test_a_declared_variant_by_field_keeps_its_own_rules(charter, make_kb):
    kind = (
        "    variant_by: form\n"
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      form: {type: string, pattern: '[a-z]+'}\n"
        "    variants:\n"
        "      short: {}\n"
    )
    kb = _kb(make_kb, kind, {"a.md": _note(), "b.md": _note(form="Short"), "c.md": _note(form="short")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/b.md", 3, "schema/pattern"), ("notes/b.md", 3, "schema/unknown-variant")]


def test_variant_path_may_use_a_field_its_selection_guarantees(charter, make_kb):
    kind = (
        '    path: "Entries/{title}.md"\n'
        "    variant_by: form\n"
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      title: {type: string, required: true}\n"
        "      form: {type: string}\n"
        "    variants:\n"
        "      short:\n"
        '        path: "Entries/{form}/{title}.md"\n'
    )
    kb = _kb(make_kb, kind, {
        "Entries/short/Tide.md": _note(form="short", title="Tide"),
        "Entries/Ferry.md": _note(title="Ferry"),
        "Entries/Pier.md": _note(form="short", title="Pier"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Entries/Pier.md", 2, "filenames/path")]


def test_set_fields_may_render_a_variant_path_without_being_required(charter, make_kb):
    kind = (
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      title: {type: string, required: true}\n"
        "      shelf: {type: string}\n"
        "    variants:\n"
        "      top:\n"
        "        set: {shelf: top}\n"
        '        path: "{shelf}/{title}.md"\n'
    )
    kb = _kb(make_kb, kind, {"top/Tide.md": _note(shelf="top", title="Tide"), "x/Ferry.md": _note(title="Ferry")})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_a_variant_inherits_the_kinds_path_and_suffix_table(charter, make_kb):
    kind = (
        '    path: "Entries/{title}{status|suffix}.md"\n'
        '    suffix: {gone: " (Gone)"}\n'
        "    fields:\n"
        "      kind: {type: string, required: true}\n"
        "      title: {type: string, required: true}\n"
        "      status: {type: string}\n"
        "    variants:\n"
        "      gone:\n"
        "        set: {status: gone}\n"
        "        fields:\n"
        "          reason: {type: string}\n"
    )
    kb = _kb(make_kb, kind, {
        "Entries/Tide (Gone).md": _note(title="Tide", status="gone", reason="silted"),
        "Entries/Ferry.md": _note(title="Ferry", status="gone"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Entries/Ferry.md", 2, "filenames/path")]


def test_variant_link_fields_are_checked_for_their_target_kind(charter, make_kb):
    kb = make_kb({
        "charter.yaml": (
            "charter: 1\nkinds:\n"
            "  place: {}\n"
            "  entry:\n"
            "    variant_by: form\n"
            "    variants:\n"
            "      trip:\n"
            "        fields:\n"
            "          to: {type: link, to: place}\n"
        ),
        "Pier.md": "---\nkind: place\n---\n",
        "a.md": "---\nkind: entry\nform: trip\nto: '[[b]]'\n---\n",
        "b.md": "---\nkind: entry\nform: trip\nto: '[[Pier]]'\n---\n",
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("a.md", 4, "links/wrong-kind")]


KIND = "    fields:\n      kind: {type: string, required: true}\n      shape: {type: string}\n      tags: {type: list}\n"
# A kind whose path the `box` variant keeps; each case appends the variant's `fields`.
INHERITED = (
    '    path: "B/{name}.md"\n'
    + KIND
    + "      name: {type: string, required: true}\n"
    + "    variants:\n      box:\n        set: {shape: box}\n"
)


@pytest.mark.parametrize("name_yaml", ["{type: string}", "{type: list, of: string}"], ids=["optional", "list"])
def test_a_variant_keeping_the_kinds_path_cannot_redeclare_its_fields_unfit_for_it(charter, make_kb, name_yaml):
    kb = _kb(make_kb, INHERITED + f"        fields: {{name: {name_yaml}}}\n", {"a.md": _note()})

    result = _validate(charter, kb)

    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    assert diagnostic["message"].startswith("kinds.entry.variants.box.fields.name: `name` is")
    assert "`B/{name}.md`" in diagnostic["hint"]


def test_a_variant_keeping_the_kinds_path_may_tighten_its_fields(charter, make_kb):
    kb = _kb(make_kb, INHERITED + "        fields: {name: {type: string, required: true, pattern: '[A-Z].*'}}\n", {
        "B/Tide.md": _note(shape="box", name="Tide"),
        "B/pier.md": _note(shape="box", name="pier"),
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/B/pier.md", 4, "schema/pattern")]


def test_a_required_field_with_allowed_values_lists_them_in_the_hint(charter, make_kb):
    kind = "    fields:\n      kind: {type: string, required: true}\n      size: {values: [small, large], required: true}\n"
    kb = _kb(make_kb, kind, {"a.md": _note()})

    result = _validate(charter, kb)

    assert result.json()["diagnostics"][0]["hint"] == "Set `size` to a string, one of `small`, `large`."


@pytest.mark.parametrize(
    ("kind_yaml", "line"),
    [
        (KIND + "    variants: {}\n", 9),
        (KIND + "    variants:\n      box: {sett: {shape: box}}\n", 10),
        (KIND + "    variants:\n      box: {}\n", 10),
        (KIND + "    variants:\n      box: {set: {}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shap: box}}\n", 10),
        (KIND + "    variants:\n      box: {set: {tags: box}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: 3}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: [a]}}\n", 10),
        (KIND.replace("{type: string}", "{values: [box, tube]}") + "    variants:\n      box: {set: {shape: cube}}\n", 10),
        (
            KIND + "    variants:\n      box: {set: {shape: box}}\n      crate: {set: {shape: box}}\n",
            11,
        ),
        (
            KIND
            + "      size: {type: int}\n"
            + "    variants:\n      box: {set: {shape: box}}\n      big: {set: {size: 3}}\n",
            12,
        ),
        (KIND + "    variants:\n      box: {set: {shape: box}, fields: {shape: {type: string}}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, fields: {x: {type: strng}}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, fields: {x: {type: link, to: nowhere}}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, fields: {x: {type: string, required_when: {y: 1}}}}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, path: 'B/{title}.md'}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, path: 'B/{tags}.md'}\n", 10),
        (KIND + "    variants:\n      box: {set: {shape: box}, path: 'B/{shape}{shape|suffix}.md'}\n", 10),
        (
            KIND + "      name: {type: string}\n"
            "    variants:\n      box: {set: {shape: box}, path: 'B/{name}.md'}\n",
            11,
        ),
        (
            KIND + "    variants:\n      box:\n        set: {shape: box}\n        path: 'B/{shape}.md'\n"
            "        fields: {name: {type: string, required: true, matches_filename: true}}\n",
            12,
        ),
        (
            '    path: "E/{shape|suffix}x.md"\n    suffix: {box: " (Box)"}\n' + KIND
            + "    variants:\n      box:\n        set: {shape: box}\n"
            "        fields: {name: {type: string, required: true, matches_filename: true}}\n",
            14,
        ),
        (KIND + "    variant_by: shape\n", 9),
        (KIND + "    variant_by: shape\n    variants:\n      box: {set: {shape: box}}\n", 11),
        (KIND + "    variant_by: tags\n    variants:\n      box: {}\n", 9),
        (KIND.replace("{type: string}", "{type: int}") + "    variant_by: shape\n    variants:\n      box: {}\n", 9),
        (KIND.replace("{type: string}", "{values: [box]}") + "    variant_by: shape\n    variants:\n      box: {}\n", 9),
        (KIND + "    variant_by: shape\n    variants:\n      box: {fields: {shape: {type: string}}}\n", 11),
        (KIND + "    variant_by: [shape]\n    variants:\n      box: {}\n", 9),
    ],
    ids=[
        "no variants",
        "unknown variant key",
        "no set",
        "empty set",
        "set names unknown field",
        "set names list field",
        "set value of wrong type",
        "set value a list",
        "set value not allowed",
        "two variants with the same set",
        "two variants that can both match",
        "variant redeclares a set field",
        "invalid variant field",
        "variant link to unknown kind",
        "variant condition on unknown field",
        "variant path names unknown field",
        "variant path names list field",
        "variant path suffix without table",
        "variant path field not required",
        "variant matches_filename without placeholder",
        "matches_filename absent from inherited path",
        "variant_by without variants",
        "set with variant_by",
        "variant_by names list field",
        "variant_by names int field",
        "variant_by field declares allowed values",
        "variant redeclares the variant_by field",
        "variant_by not text",
    ],
)
def test_invalid_variant_declaration_exits_two_with_contract_invalid(charter, make_kb, kind_yaml, line):
    kb = _kb(make_kb, kind_yaml, {"a.md": _note()})

    result = _validate(charter, kb)

    assert result.exit_code == 2, result.stdout
    assert {code for _, _, code in _codes(result)} == {"contract/invalid"}
    assert _codes(result)[0][1] == line
