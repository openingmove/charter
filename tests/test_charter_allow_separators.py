import pytest
from conftest import run_git, validate_commit_msg
from hostile_names import git_tree_with_paths

# Built with chr() so no invisible character sits in this source file. str.splitlines() splits on every one.
SEPARATORS = [chr(code) for code in (0x2028, 0x85, 0x0C, 0x0B)]
IDS = [f"U+{ord(c):04X}" for c in SEPARATORS]
CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"


def _kb_editing(make_kb, name):
    kb = make_kb({"charter.yaml": CONTRACT})
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "charter.yaml")
    git_tree_with_paths(kb, [name], NOTE)
    run_git(kb, "commit", "-q", "-m", "base")
    git_tree_with_paths(kb, [name], EDITED)
    return kb


@pytest.mark.parametrize("char", SEPARATORS, ids=IDS)
def test_a_trailer_allows_a_path_containing_a_line_separator(charter, make_kb, char):
    name = f"notes/Archive/a{char}b.md"
    kb = _kb_editing(make_kb, name)

    result = validate_commit_msg(charter, kb, f"Fix\n\nCharter-Allow: paths/read-only {name} — typo\n".encode())

    diagnostics = result.json()["diagnostics"]
    assert [(d["path"], d["code"], d["severity"]) for d in diagnostics] == [(name, "paths/read-only", "warning")]
    assert result.exit_code == 0


@pytest.mark.parametrize("char", SEPARATORS, ids=IDS)
def test_a_crlf_message_allows_a_path_containing_a_line_separator(charter, make_kb, char):
    name = f"notes/Archive/a{char}b.md"
    kb = _kb_editing(make_kb, name)
    message = f"Fix\n\nCharter-Allow: paths/read-only {name} — typo\n".replace("\n", "\r\n")

    result = validate_commit_msg(charter, kb, message.encode())

    assert [(d["code"], d["severity"]) for d in result.json()["diagnostics"]] == [("paths/read-only", "warning")]
