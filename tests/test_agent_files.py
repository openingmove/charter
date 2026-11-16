"""Agent files follow the repository's layout: which files `charter docs --link-agents` writes."""

import pytest

CONTRACT = """\
charter: 1
agents: {file: AGENTS.md}
kinds:
  entry:
    path: "{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true, matches_filename: true}
"""
IMPORT = "read @CHARTER.md before creating or editing any note here"


@pytest.fixture
def repo(make_kb, tmp_path):
    def make(files=None):
        make_kb({"kb/charter.yaml": CONTRACT, **(files or {})}, agents_include=True)
        return tmp_path, tmp_path / "kb"

    return make


def _link(charter, kb):
    return charter("docs", "--link-agents", cwd=kb)


def test_no_agent_files_get_only_an_agents_md_importing_the_rulebook(charter, repo):
    root, kb = repo()

    result = _link(charter, kb)

    assert result.exit_code == 0
    assert result.stdout == "Wrote `CHARTER.md`.\nCreated `AGENTS.md` importing `CHARTER.md`.\n"
    assert (kb / "AGENTS.md").read_bytes() == (IMPORT + "\n").encode()
    assert not list(root.rglob("CLAUDE.md"))


def test_an_existing_agents_md_gets_one_appended_line_and_nothing_else_changes(charter, repo):
    root, kb = repo({"kb/AGENTS.md": "# Agents\n\nBe kind.\n"})

    _link(charter, kb)

    assert (kb / "AGENTS.md").read_bytes() == f"# Agents\n\nBe kind.\n{IMPORT}\n".encode()
    assert not list(root.rglob("CLAUDE.md"))


def test_a_claude_md_at_the_repository_root_gets_a_knowledge_base_claude_md_importing_agents_md(charter, repo):
    root, kb = repo({"CLAUDE.md": "# Project\r\n"})

    result = _link(charter, kb)

    assert result.stdout.splitlines() == [
        "Wrote `CHARTER.md`.",
        "Created `AGENTS.md` importing `CHARTER.md`.",
        "Created `CLAUDE.md` importing `AGENTS.md`.",
    ]
    assert (kb / "AGENTS.md").read_bytes() == (IMPORT + "\n").encode()
    assert (kb / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"
    assert (root / "CLAUDE.md").read_bytes() == b"# Project\r\n"


def test_both_files_existing_are_each_extended_by_one_line(charter, repo):
    root, kb = repo({"kb/AGENTS.md": "# Agents\n", "kb/CLAUDE.md": "# Claude\n"})

    result = _link(charter, kb)

    assert "Added an import of `AGENTS.md` to `CLAUDE.md`." in result.stdout
    assert (kb / "AGENTS.md").read_bytes() == f"# Agents\n{IMPORT}\n".encode()
    assert (kb / "CLAUDE.md").read_bytes() == b"# Claude\n@AGENTS.md\n"


def test_a_claude_md_in_the_knowledge_base_folder_alone_counts_as_at_or_above(charter, repo):
    root, kb = repo({"kb/CLAUDE.md": "# Claude\n"})

    _link(charter, kb)

    assert (kb / "CLAUDE.md").read_bytes() == b"# Claude\n@AGENTS.md\n"


def test_a_claude_md_that_already_imports_agents_md_is_left_byte_identical(charter, repo):
    root, kb = repo({"CLAUDE.md": "x\n", "kb/CLAUDE.md": "Rules: @./AGENTS.md\r\n", "kb/AGENTS.md": f"{IMPORT}\r\n"})
    before = {path: path.read_bytes() for path in (kb / "CLAUDE.md", kb / "AGENTS.md")}

    result = _link(charter, kb)

    assert result.stdout.splitlines()[1:] == [
        "`AGENTS.md` already points at `CHARTER.md`.",
        "`CLAUDE.md` already points at `AGENTS.md`.",
    ]
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    "pointer",
    [IMPORT + "\n", "# Mine\n\n@CHARTER.md\n", "See [rules](CHARTER.md).", "Read <CHARTER.md>\r\n"],
)
def test_an_agents_md_already_pointing_at_the_rulebook_stays_byte_identical(charter, repo, pointer):
    root, kb = repo({"kb/AGENTS.md": pointer})

    _link(charter, kb)

    assert (kb / "AGENTS.md").read_bytes() == pointer.encode()


def test_appending_to_a_crlf_file_adds_a_crlf_line_and_ends_an_unterminated_last_line(charter, repo):
    root, kb = repo({"CLAUDE.md": "x\n"})
    (kb / "AGENTS.md").write_bytes(b"# Agents\r\n\r\nBe kind.")
    (kb / "CLAUDE.md").write_bytes(b"# Claude\r\n")

    _link(charter, kb)

    assert (kb / "AGENTS.md").read_bytes() == f"# Agents\r\n\r\nBe kind.\r\n{IMPORT}\r\n".encode()
    assert (kb / "CLAUDE.md").read_bytes() == b"# Claude\r\n@AGENTS.md\r\n"


def test_a_claude_md_far_above_a_nested_knowledge_base_still_gets_the_knowledge_base_claude_md(charter, make_kb, tmp_path):
    make_kb({"CLAUDE.md": "# Top\n", "docs/team/kb/charter.yaml": CONTRACT}, agents_include=True)
    kb = tmp_path / "docs" / "team" / "kb"

    _link(charter, kb)

    assert (kb / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"
    assert not (tmp_path / "docs" / "CLAUDE.md").exists()
    assert (tmp_path / "CLAUDE.md").read_bytes() == b"# Top\n"


def test_a_claude_md_is_never_created_where_none_exists_at_or_above(charter, repo):
    root, kb = repo({"other/CLAUDE.md": "elsewhere\n", "kb/notes/CLAUDE.md": "below\n"})

    _link(charter, kb)
    _link(charter, kb)

    assert not (kb / "CLAUDE.md").exists()
    assert sorted(path.relative_to(root).as_posix() for path in root.rglob("CLAUDE.md")) == [
        "kb/notes/CLAUDE.md",
        "other/CLAUDE.md",
    ]


def test_running_it_twice_changes_nothing_the_second_time(charter, repo):
    root, kb = repo({"CLAUDE.md": "x\n"})
    _link(charter, kb)
    once = {path.name: path.read_bytes() for path in kb.glob("*.md")}

    again = _link(charter, kb)

    assert {path.name: path.read_bytes() for path in kb.glob("*.md")} == once
    assert again.stdout.count("already") == 2


def test_the_agents_file_follows_the_configured_path_and_the_validator_accepts_the_import(charter, repo):
    contract = CONTRACT.replace("{file: AGENTS.md}", "{file: guides/AGENTS.md}") + "docs: {output: rules/CHARTER.md}\n"
    root, kb = repo({"CLAUDE.md": "x\n", "kb/charter.yaml": contract})

    _link(charter, kb)

    assert (kb / "guides" / "AGENTS.md").read_bytes() == b"read @../rules/CHARTER.md before creating or editing any note here\n"
    assert (kb / "guides" / "CLAUDE.md").read_bytes() == b"@AGENTS.md\n"
    assert charter("validate", "--profile", "ci", cwd=kb).exit_code == 0


def test_an_agents_md_that_is_a_folder_is_refused_and_nothing_is_written(charter, repo):
    root, kb = repo({"CLAUDE.md": "x\n"})
    (kb / "AGENTS.md").mkdir()

    result = _link(charter, kb)

    assert result.exit_code == 1
    assert "agents-include/missing-file" in result.stdout
    assert not (kb / "CLAUDE.md").exists()


def test_a_rulebook_path_with_a_space_falls_back_to_a_link_line_and_is_idempotent(charter, repo):
    root, kb = repo({"kb/charter.yaml": CONTRACT + "docs: {output: My Rules.md}\n"})
    expected = b"Read [My Rules.md](<My Rules.md>) before creating or editing any note here.\n"

    first = _link(charter, kb)
    again = _link(charter, kb)

    assert (kb / "AGENTS.md").read_bytes() == expected
    assert "Created `AGENTS.md` with a link to `My Rules.md`." in first.stdout
    assert "`AGENTS.md` already points at `My Rules.md`." in again.stdout
    assert charter("validate", "--profile", "ci", cwd=kb).exit_code == 0


def test_a_rulebook_path_with_parentheses_is_still_an_import(charter, repo):
    root, kb = repo({"kb/charter.yaml": CONTRACT + "docs: {output: Rules(v1).md}\n"})

    _link(charter, kb)

    assert (kb / "AGENTS.md").read_bytes() == b"read @Rules(v1).md before creating or editing any note here\n"
