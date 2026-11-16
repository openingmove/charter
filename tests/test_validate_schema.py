import pytest
from conftest import FIXTURES


def test_clean_knowledge_base_exits_zero(charter, golden):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=FIXTURES / "clean")

    assert result.exit_code == 0
    golden("clean", result.json())


def test_schema_violations_yield_schema_diagnostics_and_exit_one(charter, golden):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=FIXTURES / "schema")

    assert result.exit_code == 1
    golden("schema", result.json())


def _single_field_kb(make_kb, field_type, value_yaml, required=False):
    return make_kb({
        "charter.yaml": (
            "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n"
            f"      value: {{type: {field_type}, required: {str(required).lower()}}}\n"
        ),
        "notes/entry.md": f"---\nkind: entry\nvalue: {value_yaml}\n---\n",
    })


@pytest.mark.parametrize(
    ("field_type", "value_yaml"),
    [
        ("string", "hello"),
        ("int", "42"),
        ("int", "-3"),
        ("number", "4.5"),
        ("number", "7"),
        ("bool", "false"),
        ("date", "2026-10-13"),
        ("link", '"[[entry]]"'),
        ("link", "entry.md"),
        ("list", "[a, b]"),
    ],
)
def test_value_of_declared_type_is_accepted(charter, make_kb, field_type, value_yaml):
    kb = _single_field_kb(make_kb, field_type, value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


@pytest.mark.parametrize(
    ("field_type", "value_yaml"),
    [
        ("string", "12"),
        ("string", "[a, b]"),
        ("int", "4.5"),
        ("int", "true"),
        ("int", "'42'"),
        ("number", "yes please"),
        ("number", "false"),
        ("bool", "'true'"),
        ("bool", "1"),
        ("date", "'2026-10-13'"),
        ("date", "2026-10-13 09:30:00"),
        ("link", "[[Somewhere]]"),
        ("list", "single"),
    ],
)
def test_value_of_wrong_type_yields_schema_type(charter, make_kb, field_type, value_yaml):
    kb = _single_field_kb(make_kb, field_type, value_yaml)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("notes/entry.md", 3, "schema/type")
    ]


@pytest.mark.parametrize("value_yaml", ["", "null", "''", "[]"])
def test_required_field_without_value_yields_schema_required(charter, make_kb, value_yaml):
    kb = _single_field_kb(make_kb, "string", value_yaml, required=True)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert [(d["line"], d["code"]) for d in result.json()["diagnostics"]] == [(3, "schema/required")]


def test_optional_field_without_value_is_accepted(charter, make_kb):
    kb = _single_field_kb(make_kb, "int", "null")

    assert charter("validate", cwd=kb).exit_code == 0


def test_discriminator_field_name_is_configurable(charter, make_kb):
    kb = make_kb({
        "charter.yaml": (
            "charter: 1\nroot: notes\ndiscriminator: type\n"
            "kinds:\n  entry:\n    fields:\n      type: {type: string, required: true}\n"
        ),
        "notes/good.md": "---\ntype: entry\n---\n",
        "notes/bad.md": "---\nkind: entry\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert [(d["path"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("notes/bad.md", "schema/missing-kind")
    ]


def test_crlf_notes_report_the_same_lines_as_lf(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\r\nroot: notes\r\nkinds:\r\n  entry:\r\n    fields:\r\n      n: {type: int}\r\n",
        "notes/entry.md": "---\r\nkind: entry\r\nn: many\r\n---\r\n\r\n# Body\r\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert [(d["line"], d["code"]) for d in result.json()["diagnostics"]] == [(3, "schema/type")]


@pytest.mark.parametrize(
    "value_yaml",
    ["2026-13-45", "!!int one", "!!float x", "!!timestamp soon"],
)
def test_unconstructable_frontmatter_value_is_reported_and_the_run_continues(charter, make_kb, value_yaml):
    kb = _single_field_kb(make_kb, "string", value_yaml)
    (kb / "notes/other.md").write_text("---\nkind: nope\n---\n", encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("notes/entry.md", 3, "index/invalid-frontmatter"),
        ("notes/other.md", 2, "schema/unknown-kind"),
    ]


def test_undecodable_note_is_reported_and_the_run_continues(charter, make_kb):
    kb = _single_field_kb(make_kb, "string", "fine")
    (kb / "notes/binary.md").write_bytes(b"\xff\xfe\x00\x01not text")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("notes/binary.md", None, "index/unreadable"),
    ]


def test_directory_named_like_a_note_is_not_a_note(charter, make_kb):
    kb = _single_field_kb(make_kb, "string", "fine")
    (kb / "notes/archive.md").mkdir()
    (kb / "notes/archive.md/inner.md").write_text("---\nkind: entry\nvalue: ok\n---\n", encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


def test_validate_defaults_to_all(charter):
    assert charter("validate", cwd=FIXTURES / "clean").exit_code == 0
    assert charter("validate", "--all", cwd=FIXTURES / "clean").exit_code == 0
