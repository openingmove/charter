import re

import pytest
import yaml

LINK_LINE = "read @CHARTER.md before creating or editing any note here"

DRAFT = """\
# Draft for the garden notes.
charter: 1     # format version
root: notes    # the notes live below here

kinds:
  plant:   # one kind
    path: "{title}.md"
    fields:
      kind:  {type: string, required: true}
      title: {type: string, required: true, matches_filename: true}
"""


def _contract(base):
    return (base / "charter.yaml").read_text(encoding="utf-8")


def _names(base):
    return sorted(p.name for p in base.iterdir())


@pytest.fixture
def draft(tmp_path_factory):
    folder = tmp_path_factory.mktemp("drafts")
    file = folder / "draft.yaml"
    file.write_text(DRAFT, encoding="utf-8", newline="")
    return file


# --- the default: the contract and nothing else ---


def test_init_writes_a_commented_contract_and_nothing_else(charter, tmp_path):
    result = charter("init", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.stdout == (
        "Wrote `charter.yaml`.\n"
        "Next: declare your kinds of note in `charter.yaml`, then run `charter validate`.\n"
    )
    assert _names(tmp_path) == ["charter.yaml"]
    contract = _contract(tmp_path)
    assert contract.startswith("#")
    assert re.search(r"^charter: 1 ", contract, re.MULTILINE)
    assert re.search(r"^root: \.", contract, re.MULTILINE)


def test_the_default_contract_and_output_never_mention_agents(charter, tmp_path):
    result = charter("init", cwd=tmp_path)

    data = yaml.safe_load(_contract(tmp_path))
    assert "agents" not in data and "docs" not in data
    assert "agent" not in (result.stdout + _contract(tmp_path)).lower()


def test_a_freshly_initialised_knowledge_base_validates_cleanly(charter, tmp_path):
    charter("init", cwd=tmp_path)

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.json()["diagnostics"] == []


def test_the_starter_explains_kinds_fields_and_paths_and_points_at_describe(charter, tmp_path):
    charter("init", cwd=tmp_path)
    contract = _contract(tmp_path)

    for word in ("kind", "fields", "path", "charter describe"):
        assert word in contract


def test_the_commented_example_kind_is_a_valid_contract_once_uncommented(charter, tmp_path):
    charter("init", cwd=tmp_path)
    # The example is the commented block after `kinds: {}`; uncommenting it means dropping `{}` and each `# `.
    head, example = _contract(tmp_path).split("kinds: {}\n")
    uncommented = re.sub(r"^# ?", "", example, flags=re.MULTILINE)
    (tmp_path / "charter.yaml").write_text(head + "kinds:\n" + uncommented, encoding="utf-8")

    created = charter("new", "note", "First steps", cwd=tmp_path)
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=tmp_path)

    assert created.exit_code == 0
    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


def test_init_writes_no_gitignore_even_with_agents(charter, tmp_path):
    charter("init", cwd=tmp_path)
    charter("init", "again", "--agents", cwd=tmp_path)

    assert not list(tmp_path.rglob(".gitignore"))


def test_init_in_a_folder_of_untyped_notes_still_succeeds(charter, tmp_path):
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")

    charter("init", cwd=tmp_path)
    result = charter("validate", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 0
    assert [d["code"] for d in result.json()["diagnostics"]] == ["schema/missing-frontmatter"]


# --- FOLDER ---


def test_init_installs_the_contract_in_the_named_folder_creating_it(charter, tmp_path):
    result = charter("init", "notes/garden", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.stdout.startswith("Wrote `notes/garden/charter.yaml`.\n")
    assert _names(tmp_path / "notes" / "garden") == ["charter.yaml"]
    assert charter("validate", cwd=tmp_path / "notes" / "garden").exit_code == 0


def test_init_does_not_search_upward_for_a_contract(charter, tmp_path):
    charter("init", cwd=tmp_path)
    (tmp_path / "inner").mkdir()

    result = charter("init", cwd=tmp_path / "inner")

    assert result.exit_code == 0
    assert (tmp_path / "inner" / "charter.yaml").is_file()


def test_init_with_a_folder_that_is_a_file_writes_nothing(charter, tmp_path):
    (tmp_path / "kb").write_text("not a folder", encoding="utf-8")

    result = charter("init", "kb", cwd=tmp_path)

    assert result.exit_code == 1
    assert "init/no-folder" in result.stdout
    assert _names(tmp_path) == ["kb"]


def test_init_never_overwrites_an_existing_contract(charter, tmp_path):
    (tmp_path / "charter.yaml").write_text("charter: 1\nkinds: {}\n# mine\n", encoding="utf-8")

    result = charter("init", cwd=tmp_path)

    assert result.exit_code == 1
    assert "init/exists" in result.stdout
    assert "`charter.yaml` already exists" in result.stdout
    assert _contract(tmp_path) == "charter: 1\nkinds: {}\n# mine\n"
    assert _names(tmp_path) == ["charter.yaml"]


# --- --agents ---


def test_agents_adds_the_sections_the_rulebook_and_the_agents_file(charter, tmp_path):
    result = charter("init", "--agents", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.stdout == (
        "Wrote `charter.yaml`.\n"
        "Added `agents:` and `docs:` to `charter.yaml`.\n"
        "Wrote `CHARTER.md`.\n"
        "Created `AGENTS.md` importing `CHARTER.md`.\n"
        "Next: declare your kinds of note in `charter.yaml`, then run `charter docs` and `charter validate`.\n"
    )
    assert _names(tmp_path) == ["AGENTS.md", "CHARTER.md", "charter.yaml"]
    data = yaml.safe_load(_contract(tmp_path))
    assert (data["agents"], data["docs"]) == ({"file": "AGENTS.md"}, {"output": "CHARTER.md"})
    assert _contract(tmp_path).startswith("# The contract for this knowledge base")
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == LINK_LINE + "\n"


def test_an_agents_knowledge_base_validates_cleanly_with_an_up_to_date_rulebook(charter, tmp_path):
    charter("init", "--agents", cwd=tmp_path)

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=tmp_path)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])
    assert charter("docs", "--check", cwd=tmp_path).exit_code == 0


def test_agents_writes_into_the_named_folder(charter, tmp_path):
    result = charter("init", "kb", "--agents", cwd=tmp_path)

    assert result.exit_code == 0
    assert _names(tmp_path / "kb") == ["AGENTS.md", "CHARTER.md", "charter.yaml"]
    # Every written path shows the same way, from the working directory.
    assert result.stdout.splitlines()[:4] == [
        "Wrote `kb/charter.yaml`.",
        "Added `agents:` and `docs:` to `kb/charter.yaml`.",
        "Wrote `kb/CHARTER.md`.",
        "Created `kb/AGENTS.md` importing `CHARTER.md`.",
    ]
    assert charter("validate", "--profile", "ci", cwd=tmp_path / "kb").exit_code == 0


def test_agents_appends_one_link_line_to_existing_agent_instructions(charter, tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Agents\n\nBe kind.\n", encoding="utf-8")

    result = charter("init", "--agents", cwd=tmp_path)

    assert "Added an import of `CHARTER.md` to `AGENTS.md`.\n" in result.stdout
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == f"# Agents\n\nBe kind.\n{LINK_LINE}\n"


def test_agents_leaves_agent_instructions_that_already_link_the_rulebook(charter, tmp_path):
    (tmp_path / "AGENTS.md").write_text("@CHARTER.md\n", encoding="utf-8")

    result = charter("init", "--agents", cwd=tmp_path)

    assert "`AGENTS.md` already points at `CHARTER.md`.\n" in result.stdout
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "@CHARTER.md\n"


def test_agents_creates_a_claude_md_importing_agents_md_where_one_exists_above(charter, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
    kb = tmp_path / "kb"
    kb.mkdir()

    result = charter("init", "--agents", cwd=kb)

    assert "Created `CLAUDE.md` importing `AGENTS.md`.\n" in result.stdout
    assert (kb / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "# Project\n"


def test_agents_extends_an_existing_claude_md_with_one_import_line(charter, tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"# Claude\r\n")

    result = charter("init", "--agents", cwd=tmp_path)

    assert "Added an import of `AGENTS.md` to `CLAUDE.md`.\n" in result.stdout
    assert (tmp_path / "CLAUDE.md").read_bytes() == b"# Claude\r\n@AGENTS.md\r\n"


def test_agents_creates_no_claude_md_where_none_exists_at_or_above(charter, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    charter("init", "--agents", cwd=kb)

    assert not list(tmp_path.rglob("CLAUDE.md"))


def test_agents_never_overwrites_an_existing_rulebook_and_writes_nothing(charter, tmp_path):
    (tmp_path / "CHARTER.md").write_text("My charter.\n", encoding="utf-8")

    result = charter("init", "--agents", cwd=tmp_path)

    assert result.exit_code == 1
    assert "`CHARTER.md` already exists" in result.stdout
    assert (tmp_path / "CHARTER.md").read_text(encoding="utf-8") == "My charter.\n"
    assert _names(tmp_path) == ["CHARTER.md"]


def test_an_existing_rulebook_does_not_stop_a_plain_init(charter, tmp_path):
    (tmp_path / "CHARTER.md").write_text("My charter.\n", encoding="utf-8")

    assert charter("init", cwd=tmp_path).exit_code == 0
    assert (tmp_path / "CHARTER.md").read_text(encoding="utf-8") == "My charter.\n"


def test_agents_refuses_an_agents_file_it_cannot_add_to_writing_nothing_and_can_be_retried(charter, tmp_path):
    (tmp_path / "AGENTS.md").mkdir()

    refused = charter("init", "--agents", cwd=tmp_path)

    assert refused.exit_code == 1
    assert "init/not-writable" in refused.stdout
    assert "`AGENTS.md` is not a file charter init can add to." in refused.stdout
    assert _names(tmp_path) == ["AGENTS.md"]

    (tmp_path / "AGENTS.md").rmdir()
    retried = charter("init", "--agents", cwd=tmp_path)

    assert retried.exit_code == 0
    assert charter("validate", "--profile", "ci", cwd=tmp_path).exit_code == 0


def test_init_reports_every_obstacle_at_once(charter, tmp_path):
    (tmp_path / "charter.yaml").write_text("charter: 1\nkinds: {}\n", encoding="utf-8")
    (tmp_path / "CHARTER.md").write_text("Mine.\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").mkdir()

    result = charter("init", "--agents", cwd=tmp_path)

    assert result.exit_code == 1
    assert "`charter.yaml` already exists" in result.stdout
    assert "`CHARTER.md` already exists" in result.stdout
    assert "`AGENTS.md` is not a file charter init can add to." in result.stdout


def _dangling(link, target):
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available here")


@pytest.mark.parametrize("existing", [None, b"# Agents\r\n"])
def test_a_write_failing_midway_undoes_everything_so_init_can_be_retried(charter, tmp_path, draft, existing):
    # A dangling CLAUDE.md passes every check but cannot be written through, and comes after the other files.
    (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "notes").mkdir()
    draft.write_text(DRAFT + "docs: {output: docs/RULES.md}\n", encoding="utf-8", newline="")
    _dangling(kb / "CLAUDE.md", tmp_path / "missing" / "claude")
    if existing is not None:
        (kb / "AGENTS.md").write_bytes(existing)

    failed = charter("init", "kb", "--from", str(draft), "--agents", cwd=tmp_path)

    assert failed.exit_code == 1
    assert "init/write-failed" in failed.stdout
    # The contract, the rulebook, its new folder and the agents file are all gone or as they were.
    assert _names(kb) == sorted(["CLAUDE.md", "notes", *(["AGENTS.md"] if existing else [])])
    if existing is not None:
        assert (kb / "AGENTS.md").read_bytes() == existing

    (kb / "CLAUDE.md").unlink()
    assert charter("init", "kb", "--from", str(draft), "--agents", cwd=tmp_path).exit_code == 0


def test_a_rulebook_that_cannot_be_written_undoes_the_contract(charter, tmp_path, draft):
    (tmp_path / "blocker").write_text("a file where a folder belongs", encoding="utf-8")
    (tmp_path / "notes").mkdir()
    draft.write_text(DRAFT + "docs: {output: blocker/RULES.md}\n", encoding="utf-8", newline="")

    failed = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert failed.exit_code == 1
    assert "init/write-failed" in failed.stdout
    assert _names(tmp_path) == ["blocker", "notes"]


def test_a_refused_init_leaves_an_existing_contract_untouched(charter, tmp_path, draft):
    original = "charter: 1\n# mine\nkinds: {}\n"
    (tmp_path / "charter.yaml").write_text(original, encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    for argv in (["init"], ["init", "--agents"], ["init", "--from", str(draft)], ["init", "--from", str(draft), "--agents"]):
        assert charter(*argv, cwd=tmp_path).exit_code == 1
        assert _contract(tmp_path) == original
    assert _names(tmp_path) == ["charter.yaml", "notes"]



# --- --from ---


def test_from_installs_the_draft_byte_for_byte_in_place_of_the_starter(charter, tmp_path, draft):
    kb = tmp_path / "kb"
    (kb / "notes").mkdir(parents=True)

    result = charter("init", "kb", "--from", str(draft), cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    assert (kb / "charter.yaml").read_bytes() == draft.read_bytes()
    assert _names(kb) == ["charter.yaml", "notes"]
    assert charter("validate", "--profile", "ci", cwd=kb).exit_code == 0


def test_from_says_what_was_installed_and_what_to_run_next(charter, tmp_path, draft):
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), cwd=tmp_path)

    assert result.stdout == "Wrote `charter.yaml` from the draft.\nNext: run `charter validate`.\n"


def test_from_with_agents_does_not_ask_for_kinds_to_be_declared(charter, tmp_path, draft):
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.stdout.splitlines()[0] == "Wrote `charter.yaml` from the draft."
    assert result.stdout.splitlines()[-1] == "Next: run `charter validate`."
    assert "declare" not in result.stdout


def test_from_keeps_a_drafts_crlf_line_endings(charter, tmp_path, draft):
    draft.write_bytes(DRAFT.replace("\n", "\r\n").encode("utf-8"))
    (tmp_path / "notes").mkdir()

    charter("init", "--from", str(draft), cwd=tmp_path)

    assert (tmp_path / "charter.yaml").read_bytes() == draft.read_bytes()


def test_from_with_agents_appends_the_missing_sections_keeping_the_drafts_comments(charter, tmp_path, draft):
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    contract = _contract(tmp_path)
    assert contract.startswith(DRAFT)
    assert contract[len(DRAFT) :].splitlines() == ["", "agents: {file: AGENTS.md}", "docs: {output: CHARTER.md}"]
    assert _names(tmp_path) == ["AGENTS.md", "CHARTER.md", "charter.yaml", "notes"]
    # The draft's own root is kept: the notes are read from `notes`, the agent files sit beside the contract.
    assert yaml.safe_load(contract)["root"] == "notes"
    assert charter("validate", "--profile", "ci", "--format", "json", cwd=tmp_path).json()["diagnostics"] == []


def test_from_with_agents_does_not_duplicate_sections_the_draft_declares(charter, tmp_path, draft):
    declared = DRAFT + "agents: {file: AGENTS.md}\ndocs: {output: CHARTER.md}\n"
    draft.write_text(declared, encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    assert _contract(tmp_path) == declared
    assert "Added `agents:`" not in result.stdout
    assert _names(tmp_path) == ["AGENTS.md", "CHARTER.md", "charter.yaml", "notes"]


def test_from_with_agents_adds_only_the_section_the_draft_lacks_and_honours_its_paths(charter, tmp_path, draft):
    draft.write_text(DRAFT + "docs: {output: docs/RULES.md}\n", encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    assert "Added `agents:` to `charter.yaml`." in result.stdout
    assert _contract(tmp_path).count("docs:") == 1
    assert (tmp_path / "docs" / "RULES.md").is_file()
    assert "@docs/RULES.md" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def test_from_with_agents_appends_to_a_draft_without_a_final_newline(charter, tmp_path, draft):
    draft.write_bytes(DRAFT.rstrip("\n").replace("\n", "\r\n").encode("utf-8"))
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "charter.yaml").read_bytes().endswith(b"\r\nagents: {file: AGENTS.md}\r\ndocs: {output: CHARTER.md}\r\n")


@pytest.mark.parametrize(
    "text",
    ["charter: 1\nkinds: [unclosed\n", "kinds: {}\n", "- just\n- a list\n", "charter: 1\nroot: nowhere\nkinds: {}\n"],
    ids=["bad-yaml", "no-version", "not-a-mapping", "root-missing"],
)
def test_a_draft_that_does_not_load_is_refused_with_nothing_written(charter, tmp_path, draft, text):
    draft.write_text(text, encoding="utf-8")

    result = charter("init", "new/deep/kb", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 2
    assert "contract/" in result.stdout
    assert draft.as_posix() in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_a_missing_draft_is_a_usage_error_writing_nothing(charter, tmp_path):
    result = charter("init", "--from", "nope.yaml", cwd=tmp_path)

    assert result.exit_code == 2
    assert "init/bad-draft" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_from_never_overwrites_an_existing_contract(charter, tmp_path, draft):
    (tmp_path / "charter.yaml").write_text("charter: 1\nkinds: {}\n", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), cwd=tmp_path)

    assert result.exit_code == 1
    assert _contract(tmp_path) == "charter: 1\nkinds: {}\n"


def test_a_drafts_missing_root_is_refused_with_a_hint_about_where_it_must_exist(charter, tmp_path, draft):
    result = charter("init", "kb", "--from", str(draft), cwd=tmp_path)

    assert result.exit_code == 2
    assert "directory `notes` does not exist" in result.stdout
    assert "must exist inside the folder it is installed in" in result.stdout
    assert list(tmp_path.iterdir()) == []


# --- --agents edits the draft as text: the shapes of draft it has to get right ---


def test_agents_appends_after_a_document_start_marker(charter, tmp_path, draft):
    draft.write_text("---\n" + DRAFT, encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    assert _contract(tmp_path).startswith("---\n" + DRAFT)
    assert yaml.safe_load(_contract(tmp_path))["docs"] == {"output": "CHARTER.md"}


@pytest.mark.parametrize("text", ["{charter: 1, root: notes, kinds: {}}\n", DRAFT + "...\n"], ids=["flow-root", "end-marker"])
def test_agents_refuses_a_draft_it_cannot_extend_without_changing_it_writing_nothing(charter, tmp_path, draft, text):
    draft.write_text(text, encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 2
    assert "init/bad-draft" in result.stdout
    assert "block-style" in result.stdout
    assert _names(tmp_path) == ["notes"]


@pytest.mark.parametrize("declared", ["docs: {}\n", "agents: {}\n"])
def test_an_empty_section_in_the_draft_counts_as_declared_and_is_not_repeated(charter, tmp_path, draft, declared):
    draft.write_text(DRAFT + declared, encoding="utf-8", newline="")
    (tmp_path / "notes").mkdir()

    result = charter("init", "--from", str(draft), "--agents", cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    contract = _contract(tmp_path)
    assert contract.count("docs:") == 1 and contract.count("agents:") == 1
    assert _names(tmp_path) == ["AGENTS.md", "CHARTER.md", "charter.yaml", "notes"]
