import pytest

NOTE = "---\nkind: entry\n---\n"


def _load(charter, make_kb, contract):
    kb = make_kb({"charter.yaml": contract, "a.md": NOTE})
    result = charter("validate", "--format", "json", cwd=kb)
    return result, [(d["line"], d["code"], d["message"], d["hint"]) for d in result.json()["diagnostics"]]


@pytest.mark.parametrize("key", ["1", "true", "2026-01-01"])
@pytest.mark.parametrize(
    ("contract", "line", "where"),
    [
        ("charter: 1\nkinds:\n  entry: {}\n  KEY: {}\n", 4, "kinds.KEY"),
        ("charter: 1\nkinds:\n  entry:\n    fields:\n      KEY: {type: string}\n", 5, "kinds.entry.fields.KEY"),
        (
            "charter: 1\nkinds:\n  entry:\n    variant_by: form\n    variants:\n      KEY: {}\n",
            6,
            "kinds.entry.variants.KEY",
        ),
        (
            "charter: 1\nkinds:\n  entry:\n    variants:\n      one: {fields: {KEY: {type: string}}}\n",
            5,
            "kinds.entry.variants.one.fields.KEY",
        ),
        ("charter: 1\ncommon_fields:\n  KEY: {type: string}\nkinds:\n  entry: {}\n", 3, "common_fields.KEY"),
    ],
)
def test_a_non_string_name_is_contract_invalid(charter, make_kb, contract, line, where, key):
    result, found = _load(charter, make_kb, contract.replace("KEY", key))

    assert result.exit_code == 2
    assert [(ln, code) for ln, code, _, _ in found] == [(line, "contract/invalid")]
    _, _, message, hint = found[0]
    assert message.startswith(where.replace("KEY", key) + ":")
    assert f"`{key}`" in message
    assert f'"{key}"' in hint


@pytest.mark.parametrize("key", ["on", "yes", "no"])
def test_a_field_named_like_a_yaml_boolean_asks_for_quotes(charter, make_kb, key):
    contract = f"charter: 1\nkinds:\n  entry:\n    fields:\n      {key}: {{type: string}}\n      title: {{type: string}}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert [code for _, code, _, _ in found] == ["contract/invalid"]
    assert f'"{key}"' in found[0][3]


def test_a_set_key_that_is_a_yaml_boolean_does_not_crash_the_suggestion(charter, make_kb):
    contract = (
        "charter: 1\nkinds:\n  entry:\n    fields:\n      title: {type: string}\n"
        "    variants:\n      one:\n        set: {yes: x}\n"
    )

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert [(line, code) for line, code, _, _ in found] == [(8, "contract/invalid")]
    assert found[0][2] == "kinds.entry.variants.one.set.yes: the name `yes` is not text; YAML reads it as true or false."
    assert found[0][3] == 'Quote it: `"yes"`.'


def test_a_null_name_is_shown_as_null(charter, make_kb):
    result, found = _load(charter, make_kb, "charter: 1\nkinds:\n  entry:\n    fields:\n      ?\n      : {type: string}\n")

    assert result.exit_code == 2
    assert [(line, code) for line, code, _, _ in found] == [(5, "contract/invalid")]
    assert found[0][2].startswith("kinds.entry.fields.null: the name `null` is not text")


def test_mixed_string_and_non_string_kind_names_are_contract_invalid(charter, make_kb):
    result, found = _load(charter, make_kb, "charter: 1\nkinds:\n  entry: {}\n  1: {}\n  true: {}\n  other: {}\n")

    assert result.exit_code == 2
    assert [(line, code) for line, code, _, _ in found] == [(4, "contract/invalid"), (5, "contract/invalid")]


def test_variant_by_naming_the_discriminator_is_contract_invalid(charter, make_kb):
    contract = "charter: 1\nkinds:\n  entry:\n    variant_by: kind\n    variants:\n      one: {}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert [(line, code) for line, code, _, _ in found] == [(4, "contract/invalid")]
    assert "discriminator" in found[0][2]


def test_variant_by_naming_a_custom_discriminator_is_contract_invalid(charter, make_kb):
    contract = "charter: 1\ndiscriminator: type\nkinds:\n  entry:\n    variant_by: type\n    variants:\n      one: {}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert [(line, code) for line, code, _, _ in found] == [(5, "contract/invalid")]


def test_the_hint_for_a_kind_without_fields_does_not_print_an_empty_list(charter, make_kb):
    contract = "charter: 1\nkinds:\n  entry:\n    variants:\n      one: {set: {shelf: top}}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert found[0][1] == "contract/invalid"
    assert ": ." not in found[0][3]
    assert "fields" in found[0][3]
