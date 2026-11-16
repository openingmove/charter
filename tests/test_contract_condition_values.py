import pytest

HEADER = "charter: 1\nroot: notes\nkinds:\n  entry:\n"
SELECTED = "    variant_by: status\n    variants:\n      open: {}\n      closed: {}\n"


def _validate(charter, make_kb, contract):
    kb = make_kb({"charter.yaml": contract, "notes/entry.md": "---\nkind: entry\nstatus: open\nreason: x\n---\n"})
    return charter("validate", "--format", "json", cwd=kb)


def _selected(fields_yaml):
    return f"{HEADER}{SELECTED}    fields:\n{fields_yaml}"


def _plain(fields_yaml):
    return f"{HEADER}    fields:\n{fields_yaml}"


def _conditioned(target, value):
    return _plain(f"      r: {target}\n      a: {{type: string, required_when: {{r: {value}}}}}\n")


@pytest.mark.parametrize("key", ["required_when", "allowed_when"])
@pytest.mark.parametrize(("value", "named"), [("nope", "`nope`"), ("[open, nope]", "`nope`")])
def test_implicit_selector_value_naming_no_variant_is_rejected(charter, make_kb, key, value, named):
    contract = _selected(f"      reason: {{type: string, {key}: {{status: {value}}}}}\n")

    result = _validate(charter, make_kb, contract)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 10)
    assert named in diagnostic["message"]
    assert "the condition on `status` can never hold" in diagnostic["message"]
    assert "one of `open`, `closed`" in diagnostic["message"]


def test_implicit_selector_condition_in_a_variant_is_checked_too(charter, make_kb):
    contract = (
        f"{HEADER}    variant_by: status\n    variants:\n      open:\n        fields:\n"
        "          reason: {type: string, required_when: {status: nope}}\n      closed: {}\n"
    )

    result = _validate(charter, make_kb, contract)

    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 9)
    assert "one of `open`, `closed`" in diagnostic["message"]


def test_implicit_selector_value_naming_a_variant_loads(charter, make_kb):
    contract = _selected("      reason: {type: string, required_when: {status: [open, closed]}}\n")

    assert _validate(charter, make_kb, contract).exit_code == 0


@pytest.mark.parametrize(
    ("target", "value", "named", "bounds"),
    [
        ("{type: int, range: [1, 3]}", "9", "`9`", "1 to 3"),
        ("{type: int, range: [1, 3]}", "[2, 0]", "`0`", "1 to 3"),
        ("{type: number, range: [0.5, 1.5]}", "2", "`2`", "0.5 to 1.5"),
        ("{type: list, of: int, range: [1, 3]}", "[9]", "`9`", "1 to 3"),
    ],
)
def test_condition_value_outside_range_is_rejected(charter, make_kb, target, value, named, bounds):
    result = _validate(charter, make_kb, _conditioned(target, value))

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 7)
    assert "the condition on `r` can never hold" in diagnostic["message"]
    assert named in diagnostic["message"]
    assert f"range {bounds}" in diagnostic["message"]


@pytest.mark.parametrize(
    ("target", "value"),
    [
        ("{type: int, range: [1, 3]}", "[1, 3]"),
        ("{type: number, range: [0.5, 1.5]}", "1.5"),
        ("{type: list, of: int, range: [1, 3]}", "[1, 2]"),
    ],
)
def test_condition_value_inside_range_loads(charter, make_kb, target, value):
    assert _validate(charter, make_kb, _conditioned(target, value)).exit_code == 0


def test_condition_value_not_matching_pattern_is_rejected(charter, make_kb):
    contract = _plain(
        "      code: {type: string, pattern: '[A-Z]{2}-[0-9]+'}\n"
        "      a: {type: string, allowed_when: {code: [AB-1, abc]}}\n"
    )

    result = _validate(charter, make_kb, contract)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 7)
    assert "`abc`" in diagnostic["message"]
    assert "[A-Z]{2}-[0-9]+" in diagnostic["message"]


def test_pattern_must_match_the_whole_condition_value(charter, make_kb):
    contract = _plain("      code: {type: string, pattern: '[A-Z]+'}\n      a: {type: string, allowed_when: {code: ABc}}\n")

    assert _validate(charter, make_kb, contract).exit_code == 2


def test_matching_condition_values_load(charter, make_kb):
    contract = _plain(
        "      r: {type: int, range: [1, 3]}\n      code: {type: string, pattern: '[A-Z]+'}\n"
        "      a: {type: string, required_when: {r: [1, 3], code: ABC}}\n"
    )

    assert _validate(charter, make_kb, contract).exit_code == 0


def test_default_outside_range_or_pattern_is_rejected_with_the_same_wording(charter, make_kb):
    contract = _plain(
        "      r: {type: int, range: [1, 3], default: 9}\n      c: {type: string, pattern: '[A-Z]+', default: abc}\n"
    )

    result = _validate(charter, make_kb, contract)

    assert result.exit_code == 2
    messages = [d["message"] for d in result.json()["diagnostics"]]
    assert len(messages) == 2
    assert "outside the range 1 to 3" in messages[0]
    assert "does not match the pattern" in messages[1]
