"""The facts about the real `charter` CLI that the Establish, Migrate and adopt skill text relies on.

Each test runs the CLI in-process on a small invented knowledge base, so the skills' claims cannot drift from what
the commands do. The prose itself is pinned in test_skill_handoff_pins.py.
"""

import pytest
from conftest import commit_files, run_git

KIND_CONTRACT = """\
charter: 1
root: .
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
"""

# --- edit policies are judged per commit, by the contract in the commit's own tree (Migrate step 6) ---

RANGE_CONTRACT = """\
charter: 1
root: .
kinds:
  decision:
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
      created: {type: date, required: true}
paths:
  "decisions/**": {edit: create-only}
"""
UNDATED = "Hire a caretaker.\n"
DATED = "---\nkind: decision\ntitle: Hire a caretaker\ncreated: 2020-01-01\n---\nHire a caretaker.\n"


@pytest.fixture
def repo(tmp_path):
    run_git(tmp_path, "init", "-q", "--initial-branch=main")
    commit_files(tmp_path, {"decisions/Hire a caretaker.md": UNDATED}, "before the migration")
    return tmp_path


def _range_findings(charter, repo):
    result = charter("validate", "--config", "charter.yaml", "--range", "HEAD~2..HEAD", "--format", "json", cwd=repo)
    assert result.exit_code in (0, 1), result.stderr
    return [d["code"] for d in result.json()["diagnostics"]]


def test_one_commit_with_the_contract_and_an_edit_under_create_only_breaks_the_policy(charter, repo):
    commit_files(repo, {"decisions/Hire a caretaker.md": DATED, "charter.yaml": RANGE_CONTRACT}, "migration and contract")
    commit_files(repo, {"unrelated.txt": "x"}, "later")

    assert _range_findings(charter, repo) == ["paths/create-only"]


def test_the_edits_first_and_the_contract_in_its_own_commit_break_nothing(charter, repo):
    commit_files(repo, {"decisions/Hire a caretaker.md": DATED}, "migrated notes")
    commit_files(repo, {"charter.yaml": RANGE_CONTRACT}, "install the contract")

    assert _range_findings(charter, repo) == []


# --- a new folder: the old documents stay outside the knowledge base (plan with a Source bullet) ---

NEW_DRAFT = """\
charter: 1
root: .
paths:
  "charter.migration-plan.md": {ignore: true}
kinds:
  story:
    path: "stories/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""
OLD_DOC = "# Town history\n\nThe quay opened in 1870. See [the tour](walking-tour.md) and [[walking-tour]].\n"


@pytest.fixture
def folders(tmp_path):
    source = tmp_path / "docs"
    source.mkdir()
    (source / "town-history.md").write_text(OLD_DOC, encoding="utf-8")
    (source / "walking-tour.md").write_text("# Walking tour\n\nStart at the quay.\n", encoding="utf-8")
    new = tmp_path / "kb"
    new.mkdir()
    (new / "charter.draft.yaml").write_text(NEW_DRAFT, encoding="utf-8")
    (new / "charter.migration-plan.md").write_text("# Migration plan\n", encoding="utf-8")
    return source, new


def test_the_source_can_be_surveyed_from_the_new_folder_by_a_relative_path(charter, folders):
    _, new = folders

    result = charter("survey", "../docs", "--format", "json", cwd=new)

    assert result.exit_code == 0, result.stderr
    assert "town-history.md" in result.stdout


def test_a_note_copied_from_the_source_reports_its_old_links_as_unresolved_until_they_are_repointed(charter, folders):
    source, new = folders
    made = charter("new", "--config", "charter.draft.yaml", "story", "The founding", cwd=new)
    assert made.exit_code == 0, made.stderr
    note = new / "stories" / "The founding.md"
    note.write_text(note.read_text("utf-8") + "See [the tour](../../docs/walking-tour.md) and [[walking-tour]].\n", encoding="utf-8")
    before = {p.name: p.read_bytes() for p in source.iterdir()}

    result = charter("validate", "--config", "charter.draft.yaml", "--all", "--format", "json", cwd=new)

    assert len([d for d in result.json()["diagnostics"] if d["code"] == "links/unresolved"]) == 2
    note.write_text(
        note.read_text("utf-8").replace("[the tour](../../docs/walking-tour.md)", "[the tour](Mill Lane.md)").replace("[[walking-tour]]", "[[Mill Lane]]"),
        encoding="utf-8",
    )
    (new / "stories" / "Mill Lane.md").write_text("---\nkind: story\ntitle: Mill Lane\n---\n", encoding="utf-8")
    again = charter("validate", "--config", "charter.draft.yaml", "--all", "--format", "json", cwd=new)
    assert [d for d in again.json()["diagnostics"] if d["code"] == "links/unresolved"] == []
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before


def test_the_new_folder_installs_with_init_while_the_source_stays_outside_it(charter, folders):
    source, new = folders
    draft = new / "charter.draft.yaml"
    draft.write_text(draft.read_text("utf-8").replace('paths:\n  "charter.migration-plan.md": {ignore: true}\n', ""), encoding="utf-8")
    (new / "charter.migration-plan.md").unlink()

    result = charter("init", ".", "--from", "charter.draft.yaml", cwd=new)

    assert result.exit_code == 0, result.stderr
    assert (new / "charter.yaml").is_file()
    assert sorted(p.name for p in source.iterdir()) == ["town-history.md", "walking-tour.md"]


# --- install conflicts and editor folders (Establish steps 5 and 8) ---


def test_init_never_overwrites_a_hand_written_charter_md_but_installs_when_the_draft_names_another_output(charter, tmp_path):
    (tmp_path / "CHARTER.md").write_text("My own rules.\n", encoding="utf-8")
    (tmp_path / "charter.draft.yaml").write_text(KIND_CONTRACT, encoding="utf-8")

    refused = charter("init", ".", "--from", "charter.draft.yaml", "--agents", cwd=tmp_path)

    assert refused.exit_code != 0
    assert "init/exists" in refused.stdout
    assert (tmp_path / "CHARTER.md").read_text("utf-8") == "My own rules.\n"

    (tmp_path / "charter.draft.yaml").write_text(KIND_CONTRACT + "docs: {output: RULEBOOK.md}\n", encoding="utf-8")
    installed = charter("init", ".", "--from", "charter.draft.yaml", "--agents", cwd=tmp_path)

    assert installed.exit_code == 0, installed.stdout
    assert (tmp_path / "RULEBOOK.md").is_file()
    assert (tmp_path / "CHARTER.md").read_text("utf-8") == "My own rules.\n"


def test_validate_reads_markdown_under_obsidian_until_an_ignore_rule_says_otherwise(charter, tmp_path):
    plugin = tmp_path / ".obsidian" / "plugins" / "p"
    plugin.mkdir(parents=True)
    (plugin / "README.md").write_text("# plugin\n", encoding="utf-8")
    (tmp_path / "Note.md").write_text("---\nkind: entry\n---\n", encoding="utf-8")
    contract = tmp_path / "charter.yaml"
    contract.write_text(KIND_CONTRACT, encoding="utf-8")

    before = charter("validate", "--all", "--format", "json", cwd=tmp_path)
    contract.write_text(KIND_CONTRACT + 'paths:\n  ".obsidian/**": {ignore: true}\n', encoding="utf-8")
    after = charter("validate", "--all", "--format", "json", cwd=tmp_path)

    assert [d["path"] for d in before.json()["diagnostics"]] == [".obsidian/plugins/p/README.md"]
    assert after.json()["diagnostics"] == []


# --- the adopt gate (Establish step 2) ---


def test_a_note_without_frontmatter_is_a_warning_with_exit_0_unless_strict(charter, tmp_path):
    # Why the adopt gate reads the diagnostics of a --strict run and not the plain exit code.
    (tmp_path / "charter.yaml").write_text(KIND_CONTRACT, encoding="utf-8")
    (tmp_path / "Loose.md").write_text("No frontmatter here.\n", encoding="utf-8")

    plain = charter("validate", "--config", "charter.yaml", "--all", "--format", "json", cwd=tmp_path)
    strict = charter("validate", "--config", "charter.yaml", "--all", "--strict", "--format", "json", cwd=tmp_path)

    assert plain.exit_code == 0
    assert [(d["code"], d["severity"]) for d in plain.json()["diagnostics"]] == [("schema/missing-frontmatter", "warning")]
    assert strict.exit_code == 1
