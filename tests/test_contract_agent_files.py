import pytest


def _load(charter, make_kb, contract):
    kb = make_kb({"charter.yaml": contract, "a.md": "---\nkind: entry\n---\n"})
    result = charter("validate", "--format", "json", cwd=kb)
    return result, [(d["line"], d["code"], d["message"], d["hint"]) for d in result.json()["diagnostics"]]


@pytest.mark.parametrize("entry", ["docs/AGENTS.md", "docs\\AGENTS.md", "/AGENTS.md", "docs/"])
def test_an_agent_file_with_a_path_separator_is_contract_invalid(charter, make_kb, entry):
    contract = f"charter: 1\nagent_files:\n  - HELPERS.md\n  - '{entry}'\nkinds:\n  entry: {{}}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 2
    assert [(ln, code) for ln, code, _, _ in found] == [(4, "contract/invalid")]
    _, _, message, hint = found[0]
    assert message.startswith("agent_files.1:")
    assert "bare file names" in hint
    assert "untyped: allow" in hint


def test_bare_agent_file_names_still_load(charter, make_kb):
    contract = "charter: 1\nagent_files: [HELPERS.md, NOTES.txt]\nkinds:\n  entry: {}\n"

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 0, found
