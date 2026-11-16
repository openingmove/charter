import pytest
from conftest import FIXTURES

NOTE = "---\nkind: entry\n---\n"


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def test_invalid_contract_exits_two_with_contract_diagnostics(charter, golden):
    result = charter("validate", "--format", "json", cwd=FIXTURES / "contract-invalid")

    assert result.exit_code == 2
    golden("contract-invalid", result.json())


def test_missing_contract_exits_two(charter, tmp_path):
    result = charter("validate", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", None, "contract/not-found")]


def test_missing_contract_elsewhere_uses_the_same_path_base(charter, tmp_path):
    result = charter("validate", "--config", "site/charter.yaml", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", None, "contract/not-found")]
    assert "site/charter.yaml" in result.json()["diagnostics"][0]["message"]


@pytest.mark.parametrize(
    ("contract", "line"),
    [
        ("charter: 1\nroot: 2026-13-45\nkinds:\n  entry: {}\n", 2),
        ("charter: !!int one\nkinds:\n  entry: {}\n", 1),
        ("charter: 1\nkinds:\n  entry: {}\nwhen: !!timestamp soon\n", 4),
    ],
)
def test_unconstructable_yaml_value_exits_two_with_contract_yaml(charter, make_kb, contract, line):
    kb = make_kb({"charter.yaml": contract, "a.md": NOTE})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", line, "contract/yaml")]


def test_undecodable_contract_exits_two_with_contract_yaml(charter, tmp_path):
    (tmp_path / "charter.yaml").write_bytes(b"\xff\xfecharter: 1\n")

    result = charter("validate", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert [code for _, _, code in _codes(result)] == ["contract/yaml"]


def test_config_option_points_at_a_contract_elsewhere(charter, make_kb):
    kb = make_kb({
        "site/charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: {}\n",
        "site/notes/a.md": "---\nkind: other\n---\n",
    })

    result = charter("validate", "--config", "site/charter.yaml", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert _codes(result) == [("notes/a.md", 2, "schema/unknown-kind")]


def test_malformed_yaml_exits_two_with_its_line(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  entry: {fields: {a: {type: string}\n",
        "a.md": NOTE,
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", 4, "contract/yaml")]


@pytest.mark.parametrize(
    ("contract", "line"),
    [
        ("kinds:\n  entry: {}\n", 1),
        ("charter: 2\nkinds:\n  entry: {}\n", 1),
        ("charter: 1\n", 1),
        ("charter: 1\nkinds: [entry]\n", 2),
        ("charter: 1\nkinds:\n  entry:\n    fields:\n      a: {type: strng}\n", 5),
        ("charter: 1\nkinds:\n  entry:\n    fields:\n      a: {required: true}\n", 5),
        ("charter: 1\nkinds:\n  entry:\n    fields:\n      a: {type: int, required: maybe}\n", 5),
        ("charter: 1\nkinds:\n  entry:\n    feilds: {}\n", 3),
        ("charter: 1\nkinds:\n  entry: {}\nextra: true\n", 1),
        ("charter: 1\nroot: missing\nkinds:\n  entry: {}\n", 2),
        ("charter: 1\nroot: ..\nkinds:\n  entry: {}\n", 2),
        ("", 1),
        ("- just\n- a list\n", 1),
    ],
)
def test_contract_violation_exits_two_with_contract_invalid(charter, make_kb, contract, line):
    kb = make_kb({"charter.yaml": contract, "a.md": NOTE})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert {code for _, _, code in _codes(result)} == {"contract/invalid"}
    assert _codes(result)[0][1] == line


def test_contract_errors_are_reported_before_any_note_is_checked(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  entry:\n    fields:\n      a: {type: strng}\n",
        "a.md": "---\nkind: nonsense\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert all(code.startswith("contract/") for _, _, code in _codes(result))
