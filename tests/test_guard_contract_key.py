"""`agents: {guard: true}`: the contract key that opts into the contract guard, as the contract, `charter describe`
and the rulebook show it."""

import pytest

CONTRACT = """\
charter: 1
root: notes
{agents}
kinds:
  entry:
    path: "{{title}}.md"
    fields:
      kind: {{type: string, required: true}}
      title: {{type: string, required: true, matches_filename: true}}
"""
NOTE = "---\nkind: entry\ntitle: A\n---\n"


def _kb(make_kb, agents):
    return make_kb({"charter.yaml": CONTRACT.format(agents=agents), "notes/A.md": NOTE})


def test_a_contract_with_the_guard_on_loads(charter, make_kb):
    kb = _kb(make_kb, "agents: {file: AGENTS.md, guard: true}")

    result = charter("describe", "--format", "json", cwd=kb)

    assert result.exit_code == 0
    assert result.json()["guard"] is True


@pytest.mark.parametrize("agents", ["agents: {file: AGENTS.md}", "agents: {file: AGENTS.md, guard: false}", ""])
def test_the_description_shows_the_guard_off_unless_the_contract_opts_in(charter, make_kb, agents):
    result = charter("describe", "--format", "json", cwd=_kb(make_kb, agents))

    assert result.json()["guard"] is False


@pytest.mark.parametrize("value", ['"yes"', "1", "[true]"])
def test_the_guard_takes_only_true_or_false(charter, make_kb, value):
    result = charter("validate", "--format", "json", cwd=_kb(make_kb, f"agents: {{guard: {value}}}"))

    assert result.exit_code == 2
    [problem] = result.json()["diagnostics"]
    assert problem["code"] == "contract/invalid"
    assert "guard" in problem["message"] + (problem.get("hint") or "")


def test_the_rulebook_tells_agents_about_the_guard_when_it_is_on(charter, make_kb):
    kb = _kb(make_kb, "agents: {file: AGENTS.md, guard: true}")

    markdown = charter("describe", cwd=kb).stdout

    assert "# Contract guard" in markdown
    assert "/charter:evolve" in markdown
    assert charter("docs", cwd=kb).exit_code == 0
    assert "# Contract guard" in (kb / "CHARTER.md").read_text(encoding="utf-8")


def test_the_rulebook_says_nothing_of_a_guard_that_is_off(charter, make_kb):
    kb = _kb(make_kb, "agents: {file: AGENTS.md}")

    assert "guard" not in charter("describe", cwd=kb).stdout.lower()


def test_a_kind_description_never_carries_the_guard(charter, make_kb):
    kb = _kb(make_kb, "agents: {file: AGENTS.md, guard: true}")

    result = charter("describe", "entry", "--format", "json", cwd=kb)

    assert "guard" not in result.json()
    assert "guard" not in charter("describe", "entry", cwd=kb).stdout.lower()
