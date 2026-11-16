import pytest
from conftest import FIXTURES


def test_every_field_rule_reports_its_own_diagnostic(charter, golden):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=FIXTURES / "fields")

    assert result.exit_code == 1
    golden("fields", result.json())


def _kb(make_kb, field_spec, value_yaml, extra_contract=""):
    return make_kb({
        "charter.yaml": (
            f"charter: 1\nroot: notes\n{extra_contract}kinds:\n  entry:\n    fields:\n"
            f"      value: {field_spec}\n"
        ),
        "notes/entry.md": f"---\nkind: entry\nvalue: {value_yaml}\n---\n",
    })


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


VOCABULARIES = "vocabularies:\n  stage: [idea, draft, locked]\n"


@pytest.mark.parametrize(
    ("field_spec", "value_yaml"),
    [
        ("{enum: stage}", "draft"),
        ("{type: string, enum: stage}", "idea"),
        ("{values: [red, green]}", "green"),
        ("{type: list, enum: stage}", "[idea, locked]"),
        ("{type: list, of: enum, enum: stage}", "[draft]"),
        ("{type: list, of: string, values: [red, green]}", "[red, green]"),
    ],
)
def test_value_in_the_allowed_set_is_accepted(charter, make_kb, field_spec, value_yaml):
    kb = _kb(make_kb, field_spec, value_yaml, VOCABULARIES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("field_spec", "value_yaml"),
    [
        ("{enum: stage}", "drafty"),
        ("{type: string, enum: stage}", "Idea"),
        ("{values: [red, green]}", "blue"),
        ("{type: list, enum: stage}", "[idea, cut]"),
        ("{type: list, of: enum, enum: stage}", "[nope]"),
        ("{type: list, values: [red, green]}", "[red, blue]"),
    ],
)
def test_value_outside_the_allowed_set_yields_schema_enum(charter, make_kb, field_spec, value_yaml):
    kb = _kb(make_kb, field_spec, value_yaml, VOCABULARIES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert _codes(result) == [("notes/entry.md", 3, "schema/enum")]


@pytest.mark.parametrize(("field_spec", "value_yaml"), [("{enum: stage}", "3"), ("{values: [a]}", "[a]")])
def test_enum_field_of_the_wrong_type_yields_schema_type(charter, make_kb, field_spec, value_yaml):
    kb = _kb(make_kb, field_spec, value_yaml, VOCABULARIES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/entry.md", 3, "schema/type")]


def test_enum_hint_suggests_the_closest_value(charter, make_kb):
    kb = _kb(make_kb, "{enum: stage}", "drafty", VOCABULARIES)

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert "`draft`" in diagnostic["hint"]


def _contract_kb(make_kb, fields_yaml, extra_contract=""):
    return make_kb({
        "charter.yaml": f"charter: 1\nroot: notes\n{extra_contract}kinds:\n  entry:\n    fields:\n{fields_yaml}",
        "notes/entry.md": "---\nkind: entry\n---\n",
    })


@pytest.mark.parametrize(
    ("fields_yaml", "line"),
    [
        ("      a: {required: true}\n", 8),
        ("      a: {enum: colour}\n", 8),
        ("      a: {enum: stage, values: [x]}\n", 8),
        ("      a: {type: int, enum: stage}\n", 8),
        ("      a: {type: list, of: int, values: [x]}\n", 8),
        ("      a: {type: string, of: string}\n", 8),
        ("      a: {type: list, of: enum}\n", 8),
        ("      a: {type: list, of: list}\n", 8),
        ("      a: {values: []}\n", 8),
        ("      a: {values: [yes, no]}\n", 8),
        ("      a: {type: string, range: [1, 2]}\n", 8),
        ("      a: {type: list, pattern: x, range: [1, 2]}\n", 8),
        ("      kind: {type: string}\n      a: {type: string, required: true, allowed_when: {kind: entry}}\n", 9),
        ("      kind: {type: string}\n      a: {type: string, required_when: {kind: {x: y}}}\n", 9),
        ("      kind: {type: string}\n      a: {type: string, required_when: {kind: 2026-10-13T09:30:00}}\n", 9),
        ("      a: {type: int, range: [5, 1]}\n", 8),
        ("      a: {type: int, range: [1]}\n", 8),
        ("      a: {type: int, range: [1, x]}\n", 8),
        ("      a: {type: int, pattern: '\\d+'}\n", 8),
        ("      a: {type: list, of: int, pattern: '\\d+'}\n", 8),
        ("      a: {type: string, pattern: '([a-z'}\n", 8),
        ("      a: {type: string, required_when: {b: x}}\n", 8),
        ("      a: {type: string, allowed_when: {a: x}}\n", 8),
        ("      a: {type: string, required_when: {}}\n", 8),
        ("      a: {type: string, allowed_when: {kind: [x, [y]]}}\n", 8),
        ("      a: {type: string, required_when: {kind: []}}\n", 8),
        ("      a: {type: string, required: true, required_when: {kind: entry}}\n", 8),
    ],
)
def test_invalid_field_spec_exits_two_with_contract_invalid(charter, make_kb, fields_yaml, line):
    kb = _contract_kb(make_kb, fields_yaml, VOCABULARIES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert {code for _, _, code in _codes(result)} == {"contract/invalid"}
    assert _codes(result)[0][1] == line


@pytest.mark.parametrize(
    "vocabularies",
    ["vocabularies: [idea]\n", "vocabularies:\n  stage: []\n", "vocabularies:\n  stage: [a, a]\n"],
)
def test_malformed_vocabularies_exit_two(charter, make_kb, vocabularies):
    kb = _contract_kb(make_kb, "      a: {type: string}\n", vocabularies)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert {code for _, _, code in _codes(result)} == {"contract/invalid"}


def test_unknown_vocabulary_hint_names_the_declared_ones(charter, make_kb):
    kb = _contract_kb(make_kb, "      a: {enum: stages}\n", VOCABULARIES)

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert "`stage`" in diagnostic["hint"]


@pytest.mark.parametrize(
    ("field_spec", "value_yaml", "code"),
    [
        ("{type: int, range: [1, 100]}", "1", None),
        ("{type: int, range: [1, 100]}", "100", None),
        ("{type: int, range: [1, 100]}", "0", "schema/range"),
        ("{type: int, range: [1, 100]}", "101", "schema/range"),
        ("{type: number, range: [0, 1]}", "0.5", None),
        ("{type: number, range: [0, 1]}", "1.01", "schema/range"),
        ("{type: number, range: [-2.5, 2.5]}", "-3", "schema/range"),
        ("{type: list, of: int, range: [0, 60]}", "[0, 30, 60]", None),
        ("{type: list, of: int, range: [0, 60]}", "[0, 61]", "schema/range"),
        ("{type: string, pattern: '[A-Z]{2}-\\d+'}", "AB-12", None),
        ("{type: string, pattern: '[A-Z]{2}-\\d+'}", "AB-12x", "schema/pattern"),
        ("{type: string, pattern: '[A-Z]{2}-\\d+'}", "xAB-12", "schema/pattern"),
        ("{type: string, pattern: 'a|b'}", "ab", "schema/pattern"),
        ("{type: list, of: string, pattern: '#\\w+'}", "['#one', '#two']", None),
        ("{type: list, of: string, pattern: '#\\w+'}", "['#one', two]", "schema/pattern"),
    ],
)
def test_range_and_pattern(charter, make_kb, field_spec, value_yaml, code):
    kb = _kb(make_kb, field_spec, value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    expected = [] if code is None else [("notes/entry.md", 3, code)]
    assert _codes(result) == expected
    assert result.exit_code == (0 if code is None else 1)


@pytest.mark.parametrize(
    ("of", "value_yaml", "accepted"),
    [
        ("int", "[1, 2]", True),
        ("int", "[1, two]", False),
        ("number", "[1, 2.5]", True),
        ("number", "[1, true]", False),
        ("bool", "[true, false]", True),
        ("bool", "[true, 'no']", False),
        ("date", "[2026-10-13]", True),
        ("date", "['2026-10-13']", False),
        ("string", "[a, b]", True),
        ("string", "[a, 3]", False),
        ("link", "['[[entry]]', '[[entry]]']", True),
        ("link", "[[[A]]]", False),
    ],
)
def test_list_elements_are_checked_against_of(charter, make_kb, of, value_yaml, accepted):
    kb = _kb(make_kb, f"{{type: list, of: {of}}}", value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == ([] if accepted else [("notes/entry.md", 3, "schema/item-type")])


def test_list_without_of_accepts_any_elements(charter, make_kb):
    kb = _kb(make_kb, "{type: list}", "[1, a, true, 2026-10-13]")

    assert charter("validate", cwd=kb).exit_code == 0


@pytest.mark.parametrize(
    "value_yaml",
    ["2026-1-5", "2026-10-5", "'2026-10-13'", "2026-10-13T09:30:00", "20261013", "13/10/2026"],
)
def test_date_must_be_iso_year_month_day(charter, make_kb, value_yaml):
    kb = _kb(make_kb, "{type: date}", value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/entry.md", 3, "schema/type")]


CONDITIONAL_CONTRACT = """charter: 1
root: notes
kinds:
  task:
    fields:
      kind: {type: string, required: true}
      status: {values: [open, done, dropped], required: true}
      urgent: {type: bool}
      reason: {type: string, required_when: {status: dropped}}
      closed: {type: date, required_when: {status: [done, dropped], urgent: true}}
      verdict: {type: string, allowed_when: {status: [done, dropped]}}
      escalation: {type: string, allowed_when: {status: open, urgent: true}}
"""


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("status: open", []),
        ("status: dropped\nreason: duplicate", []),
        ("status: dropped", [(1, "schema/required")]),
        ("status: dropped\nreason: ''", [(4, "schema/required")]),
        ("status: open\nreason: not needed but harmless", []),
        ("status: done\nurgent: true", [(1, "schema/required")]),
        ("status: done\nurgent: true\nclosed: 2026-10-13", []),
        ("status: done\nurgent: false", []),
        ("status: open\nurgent: true", []),
        ("status: done", []),
        ("status: done\nverdict: shipped", []),
        ("status: dropped\nreason: stale\nverdict: shelved", []),
        ("status: open\nverdict: early", [(4, "schema/not-allowed")]),
        ("status: open\nurgent: true\nescalation: page the lead", []),
        ("status: open\nescalation: page the lead", [(4, "schema/not-allowed")]),
        ("status: done\nurgent: true\nclosed: 2026-10-13\nescalation: x", [(6, "schema/not-allowed")]),
        ("status: open\nverdict: 12", [(4, "schema/not-allowed")]),
    ],
)
def test_conditional_fields_apply_when_every_condition_holds(charter, make_kb, frontmatter, expected):
    kb = make_kb({"charter.yaml": CONDITIONAL_CONTRACT, "notes/task.md": f"---\nkind: task\n{frontmatter}\n---\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert [(line, code) for _, line, code in _codes(result)] == expected
    assert result.exit_code == (1 if expected else 0)


def test_condition_on_a_number_does_not_match_a_boolean(charter, make_kb):
    kb = make_kb({
        "charter.yaml": (
            "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n"
            "      level: {type: number}\n      note: {type: string, required_when: {level: 1}}\n"
        ),
        "notes/a.md": "---\nkind: entry\nlevel: true\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert [code for _, _, code in _codes(result)] == ["schema/type"]


def test_condition_is_named_in_the_message(charter, make_kb):
    kb = make_kb({"charter.yaml": CONDITIONAL_CONTRACT, "notes/task.md": "---\nkind: task\nstatus: open\nverdict: x\n---\n"})

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert "`status` is `done` or `dropped`" in diagnostic["message"]


@pytest.mark.parametrize(
    ("field_spec", "value_yaml", "code"),
    [
        ("{type: list, pattern: '#\\w+'}", "['#a', '#b']", None),
        ("{type: list, pattern: '#\\w+'}", "['#a', b]", "schema/pattern"),
        ("{type: list, pattern: '#\\w+'}", "['#a', 3]", "schema/item-type"),
        ("{type: list, values: [x, y]}", "[x, 3]", "schema/item-type"),
        ("{type: list, range: [0, 1]}", "[0, 0.5, 1]", None),
        ("{type: list, range: [0, 1]}", "[0.5, 2]", "schema/range"),
        ("{type: list, range: [0, 1]}", "[0.5, x]", "schema/item-type"),
    ],
)
def test_element_rules_on_a_list_without_of_imply_the_element_type(charter, make_kb, field_spec, value_yaml, code):
    kb = _kb(make_kb, field_spec, value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == ([] if code is None else [("notes/entry.md", 3, code)])


LIST_CONDITION_CONTRACT = """charter: 1
root: notes
kinds:
  task:
    fields:
      kind: {type: string, required: true}
      tags: {type: list, of: string}
      owner: {type: string, required_when: {tags: [urgent, blocked]}}
      pager: {type: string, allowed_when: {tags: urgent}}
"""


@pytest.mark.parametrize(
    ("frontmatter", "expected"),
    [
        ("tags: [urgent]", [(1, "schema/required")]),
        ("tags: [calm, blocked]", [(1, "schema/required")]),
        ("tags: [calm]", []),
        ("tags: [urgent]\nowner: ana\npager: '555'", []),
        ("tags: [calm]\npager: '555'", [(4, "schema/not-allowed")]),
        ("pager: '555'", [(3, "schema/not-allowed")]),
    ],
)
def test_condition_on_a_list_field_holds_when_the_list_contains_a_value(charter, make_kb, frontmatter, expected):
    kb = make_kb({"charter.yaml": LIST_CONDITION_CONTRACT, "notes/task.md": f"---\nkind: task\n{frontmatter}\n---\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert [(line, code) for _, line, code in _codes(result)] == expected


def test_condition_on_a_list_field_reads_as_membership(charter, make_kb):
    kb = make_kb({"charter.yaml": LIST_CONDITION_CONTRACT, "notes/task.md": "---\nkind: task\npager: x\n---\n"})

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert "`tags` includes `urgent`" in diagnostic["message"]


@pytest.mark.parametrize(
    ("due", "expected"),
    [("2026-01-01", ["schema/required"]), ("2026-01-02", []), ("'2026-01-01'", ["schema/type"])],
)
def test_condition_may_name_a_date(charter, make_kb, due, expected):
    kb = make_kb({
        "charter.yaml": (
            "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n"
            "      due: {type: date}\n      reason: {type: string, required_when: {due: 2026-01-01}}\n"
        ),
        "notes/a.md": f"---\nkind: entry\ndue: {due}\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert [code for _, _, code in _codes(result)] == expected


@pytest.mark.parametrize(
    "field_spec",
    [
        "{type: 2026-01-01}",
        "{type: string, required: 2026-01-01}",
        "{type: date, values: [2026-01-01, 2026-01-01]}",
        "{type: int, range: [2026-01-01, 2]}",
        "{type: int, range: [1, 2, 3]}",
        "{type: string, pattern: 2026-01-01}",
        "{type: string, pattern: ''}",
        "{enum: [a]}",
        "{type: string, required_when: {}}",
        "{type: string, required_when: {kind: {x: 2026-01-01}}}",
        "{type: string, allowed_when: [kind]}",
        "[string]",
    ],
)
def test_contract_messages_for_field_specs_are_written_for_people(charter, make_kb, field_spec):
    kb = _contract_kb(make_kb, f"      kind: {{type: string}}\n      a: {field_spec}\n")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    for diagnostic in result.json()["diagnostics"]:
        assert diagnostic["code"] == "contract/invalid"
        for leak in ("datetime", "valid under", "{'", "['", "was expected", "is not of type"):
            assert leak not in diagnostic["message"], diagnostic["message"]


@pytest.mark.parametrize(
    ("fields_yaml", "line", "named"),
    [
        # A typo outside the vocabulary.
        ("      stage: {values: [draft, cut]}\n      a: {type: string, required_when: {stage: cutt}}\n", 9, "`cutt`"),
        ("      stage: {enum: stage}\n      a: {type: string, allowed_when: {stage: [draft, nope]}}\n", 9, "`nope`"),
        # A string against an int field.
        ("      n: {type: int}\n      a: {type: string, required_when: {n: '5'}}\n", 9, '"5"'),
        # On a list field the value is held to the element type.
        ("      tags: {type: list, values: [x, y]}\n      a: {type: string, required_when: {tags: [x, z]}}\n", 9, "`z`"),
        ("      flags: {type: list, of: int}\n      a: {type: string, allowed_when: {flags: yes_}}\n", 9, '"yes_"'),
    ],
)
def test_condition_value_that_cannot_match_its_field_is_a_contract_problem(charter, make_kb, fields_yaml, line, named):
    kb = _contract_kb(make_kb, fields_yaml, VOCABULARIES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", line)
    assert named in diagnostic["message"]


@pytest.mark.parametrize(
    "fields_yaml",
    [
        "      stage: {values: [draft, cut]}\n      a: {type: string, required_when: {stage: [draft, cut]}}\n",
        "      n: {type: number}\n      a: {type: string, required_when: {n: 5}}\n",
        "      tags: {type: list, values: [x, y]}\n      a: {type: string, required_when: {tags: [x, y]}}\n",
        "      tags: {type: list}\n      a: {type: string, required_when: {tags: anything}}\n",
        "      due: {type: date}\n      a: {type: string, required_when: {due: 2026-01-01}}\n",
        "      urgent: {type: bool}\n      a: {type: string, allowed_when: {urgent: true}}\n",
    ],
)
def test_condition_value_the_field_can_hold_still_loads(charter, make_kb, fields_yaml):
    kb = _contract_kb(make_kb, fields_yaml)

    assert charter("validate", "--format", "json", cwd=kb).exit_code == 0


def test_null_list_item_is_described_as_empty(charter, make_kb):
    kb = _kb(make_kb, "{type: list, of: string}", "[a, null]")

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert (diagnostic["line"], diagnostic["code"]) == (3, "schema/item-type")
    assert diagnostic["message"].endswith("got an empty (null) value.")
    assert "mapping" not in diagnostic["message"]


def test_text_against_a_bool_field_says_it_is_text(charter, make_kb):
    kb = _contract_kb(make_kb, "      urgent: {type: bool}\n      a: {type: string, required_when: {urgent: 'true'}}\n")

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert diagnostic["message"].endswith(
        'the condition on `urgent` can never hold: the text `"true"` is not true or false.'
    )


@pytest.mark.parametrize(
    ("target", "condition"),
    [
        ("{type: list, of: bool}", "[true, 'yes']"),
        ("{type: list, of: date}", "[2026-01-01, 'soon']"),
        ("{type: list, of: int}", "[1, x]"),
    ],
)
def test_bad_element_in_a_list_condition_is_reported(charter, make_kb, target, condition):
    kb = _contract_kb(make_kb, f"      tags: {target}\n      a: {{type: string, required_when: {{tags: {condition}}}}}\n")

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 7)


def test_list_vocabulary_typo_is_reported_even_without_of(charter, make_kb):
    # A vocabulary implies string elements, so `of` is not needed for the check.
    kb = _contract_kb(make_kb, "      tags: {type: list, values: [x, y]}\n      a: {type: string, required_when: {tags: z}}\n")

    [diagnostic] = charter("validate", "--format", "json", cwd=kb).json()["diagnostics"]

    assert "`z` is not one of" in diagnostic["message"]


def test_condition_on_an_untyped_list_is_deliberately_unchecked(charter, make_kb):
    kb = _contract_kb(make_kb, "      tags: {type: list}\n      a: {type: string, required_when: {tags: [1, x]}}\n")

    assert charter("validate", "--format", "json", cwd=kb).exit_code == 0
