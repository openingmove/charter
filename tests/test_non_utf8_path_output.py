import json

import pytest
from conftest import COMMIT_MSG, run_git
from hostile_names import git_tree_with_paths

CONTRACT = """\
charter: 1
root: notes
paths:
  "Locked/**": {edit: read-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"
# Not valid UTF-8; built from bytes so no filesystem or source encoding is involved.
BAD_NAME = b"notes/Locked/caf\xe9 \xff.md"
ESCAPED = "notes/Locked/caf\\xe9 \\xff.md"
GOOD_NAME = b"notes/Locked/plain.md"


@pytest.fixture
def repo(make_kb):
    kb = make_kb({"charter.yaml": CONTRACT})
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "charter.yaml")
    git_tree_with_paths(kb, [BAD_NAME, GOOD_NAME], NOTE)
    run_git(kb, "commit", "-q", "-m", "base")
    return kb


def _stage_edits(kb):
    git_tree_with_paths(kb, [BAD_NAME, GOOD_NAME], EDITED)
    (kb / COMMIT_MSG).write_text("Change\n", encoding="utf-8")
    return ("validate", "--staged", "--commit-msg", COMMIT_MSG, "--profile", "ci")


def _commit_edits(kb):
    git_tree_with_paths(kb, [BAD_NAME, GOOD_NAME], EDITED)
    run_git(kb, "commit", "-q", "-m", "edit")
    return ("validate", "--range=HEAD~1..HEAD", "--profile", "ci")


SELECTORS = [pytest.param(_stage_edits, id="staged"), pytest.param(_commit_edits, id="range")]


@pytest.mark.parametrize("select", SELECTORS)
def test_json_reports_the_path_escaped_and_parses(charter, repo, select):
    argv = select(repo)

    result = charter(*argv, "--format", "json", cwd=repo)

    assert result.exit_code == 1
    paths = [d["path"] for d in json.loads(result.stdout)["diagnostics"] if d["code"] == "paths/read-only"]
    assert paths == [ESCAPED, "notes/Locked/plain.md"]


@pytest.mark.parametrize("select", SELECTORS)
@pytest.mark.parametrize("output_format", ["text", "agent"])
def test_text_and_agent_report_the_path_escaped(charter, repo, select, output_format):
    argv = select(repo)

    result = charter(*argv, "--format", output_format, cwd=repo)

    assert result.exit_code == 1
    assert ESCAPED in result.stdout
    assert "notes/Locked/plain.md" in result.stdout
    assert result.stderr == ""


def test_a_valid_utf8_path_renders_as_it_does_today(charter, make_kb):
    kb = make_kb({"charter.yaml": CONTRACT})
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "charter.yaml")
    name = f"notes/Locked/caf{chr(0xE9)} {chr(0x4E2D)}.md".encode()
    git_tree_with_paths(kb, [name], NOTE)
    run_git(kb, "commit", "-q", "-m", "base")
    git_tree_with_paths(kb, [name], EDITED)

    (kb / COMMIT_MSG).write_text("Change\n", encoding="utf-8")
    result = charter(
        "validate", "--staged", "--commit-msg", COMMIT_MSG, "--profile", "ci", "--format", "agent", cwd=kb
    )

    assert result.stdout.startswith(f"notes/Locked/caf{chr(0xE9)} {chr(0x4E2D)}.md: error paths/read-only:")
