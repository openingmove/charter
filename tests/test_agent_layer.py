"""The agent layer is opt-in: it switches on through `agents:`, and a standalone knowledge base never hears of it."""

import pytest

STANDALONE = """\
charter: 1
root: notes
kinds:
  entry:
    path: "{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true, matches_filename: true}
"""
NOTE = "---\nkind: entry\ntitle: A\n---\n"
DOCS = "docs: {output: CHARTER.md}\n"
AGENTS = "agents: {file: AGENTS.md}\n"


def _with(section):
    return STANDALONE.replace("root: notes\n", f"root: notes\n{section}")


def _kb(make_kb, section="", **extra):
    return make_kb({"charter.yaml": _with(section), "notes/A.md": NOTE, **extra}, agents_include=True)


def _says_nothing_of_agents(*results):
    for result in results:
        assert "agent" not in (result.stdout + result.stderr).lower()


def test_a_standalone_folder_validates_clean_with_no_agent_files(charter, make_kb):
    kb = _kb(make_kb)

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])
    assert sorted(path.name for path in kb.iterdir()) == ["charter.yaml", "notes"]
    _says_nothing_of_agents(result, charter("validate", "--profile", "ci", cwd=kb))


def test_a_standalone_description_never_mentions_agents(charter, make_kb):
    kb = _kb(make_kb)

    results = [charter("describe", cwd=kb), charter("describe", "--format", "json", cwd=kb)]

    assert all(result.exit_code == 0 for result in results)
    _says_nothing_of_agents(*results)
    assert "agents-include" not in results[1].stdout


def test_an_explicitly_enabled_agents_include_has_nothing_to_check_without_the_layer(charter, make_kb):
    kb = _kb(make_kb, section="checks: {agents-include: {enabled: true}}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


def test_docs_with_neither_section_is_a_usage_error_saying_how_to_declare_one(charter, make_kb):
    kb = _kb(make_kb)

    result = charter("docs", cwd=kb)

    assert result.exit_code == 2
    assert "usage/no-rulebook" in result.stdout
    assert "Add a `docs:` section" in result.stdout
    assert "an `agents:` section also produces one" in result.stdout
    assert not (kb / "CHARTER.md").exists()
    checked = charter("docs", "--check", cwd=kb)
    assert (checked.exit_code, checked.stdout) == (2, result.stdout)


def test_docs_alone_writes_a_rulebook_and_reports_a_stale_one_without_naming_agents(charter, make_kb):
    kb = _kb(make_kb, section=DOCS)

    written = charter("docs", cwd=kb)
    (kb / "CHARTER.md").write_text("Edited.\n", encoding="utf-8")
    stale = charter("docs", "--check", cwd=kb)

    assert (written.exit_code, written.stdout) == (0, "Wrote `CHARTER.md`.\n")
    assert stale.exit_code == 1
    assert "docs/stale" in stale.stdout
    _says_nothing_of_agents(written, stale)
    assert (kb / "AGENTS.md").exists() is False


def test_link_agents_without_the_layer_is_a_usage_error_saying_how_to_turn_it_on(charter, make_kb):
    kb = _kb(make_kb, section=DOCS)

    result = charter("docs", "--link-agents", cwd=kb)

    assert result.exit_code == 2
    assert "usage/no-agent-layer" in result.stdout
    assert "Add an `agents:` section" in result.stdout
    assert not (kb / "CHARTER.md").exists()
    assert not (kb / "AGENTS.md").exists()


def test_the_agent_layer_implies_the_rulebook_and_the_default_agents_file(charter, make_kb):
    kb = _kb(make_kb, section="agents: {}\n")

    before = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)
    linked = charter("docs", "--link-agents", cwd=kb)
    after = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert [(d["path"], d["code"]) for d in before.json()["diagnostics"]] == [
        ("AGENTS.md", "agents-include/missing-file"),
        ("CHARTER.md", "agents-include/stale"),
    ]
    assert linked.exit_code == 0
    assert (kb / "AGENTS.md").exists() and (kb / "CHARTER.md").exists()
    assert (after.exit_code, after.json()["diagnostics"]) == (0, [])


@pytest.mark.parametrize("section", [DOCS, AGENTS, DOCS + AGENTS])
def test_a_declared_rulebook_needs_no_kind(charter, make_kb, section):
    contract = _with(section).replace("root: notes\n", "root: .\n")
    kb = make_kb({"charter.yaml": contract, "A.md": NOTE, "CHARTER.md": "Rules.\n"}, agents_include=True)

    result = charter("validate", "--format", "json", cwd=kb)

    assert "CHARTER.md" not in [d["path"] for d in result.json()["diagnostics"] if d["code"].startswith("schema/")]


def test_a_file_named_like_the_rulebook_is_an_ordinary_note_without_a_rulebook(charter, make_kb):
    contract = _with("").replace("root: notes\n", "root: .\n")
    kb = make_kb({"charter.yaml": contract, "CHARTER.md": "Plain.\n"}, agents_include=True)

    result = charter("validate", "--format", "json", cwd=kb)

    diagnostics = [(d["path"], d["code"]) for d in result.json()["diagnostics"]]
    assert diagnostics == [("CHARTER.md", "schema/missing-frontmatter")]
