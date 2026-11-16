import pytest
from conftest import commit_files, run_git, validate_commit_msg, write_files

CONTRACT = """\
charter: 1
root: notes
kinds:
  decision:
    fields:
      kind: {type: string, required: true}
      status: {type: string}
  memo:
    fields:
      kind: {type: string, required: true}
checks:
  agents-include: {enabled: false}
  protected-region: {enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}
"""
MARKER = "## Amendments (append-only)"
FRONTMATTER = "---\nkind: decision\nstatus: accepted\n---\n"
BODY = f"# Use tabs\n\nWe use tabs.\n\n{MARKER}\n\n- 2024-01-01: also in YAML.\n"
DECISION = FRONTMATTER + BODY
FILES = {
    "charter.yaml": CONTRACT,
    "notes/tabs.md": DECISION,
    "notes/memo.md": "---\nkind: memo\n---\nMemo.\n",
}
CHANGED = "protected-region/changed"


def _codes(result):
    return [(d["path"], d["line"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _committed(make_kb, files=FILES):
    kb = make_kb(files)
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


def _edit(make_kb, text, files=FILES):
    kb = _committed(make_kb, files)
    write_files(kb, {"notes/tabs.md": text})
    return kb


def test_changing_text_above_the_marker_is_reported_on_its_line(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "We use spaces."))

    result = _validate(charter, kb)

    assert result.exit_code == 1
    assert _codes(result) == [("notes/tabs.md", 7, "error", CHANGED)]
    diagnostic = result.json()["diagnostics"][0]
    assert "above" in diagnostic["message"] and f"`{MARKER}`" in diagnostic["message"]
    assert "Charter-Allow: protected-region/changed notes/tabs.md" in diagnostic["hint"]


def test_appending_below_the_marker_is_allowed(charter, make_kb):
    kb = _edit(make_kb, DECISION + "- 2024-02-01: and in JSON.\n")

    assert _codes(_validate(charter, kb)) == []


def test_changing_text_below_the_marker_is_reported(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("also in YAML", "also in TOML") + "- 2024-02-01: more.\n")

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", 11, "error", CHANGED)]
    assert "below" in result.json()["diagnostics"][0]["message"]


def test_inserting_text_between_amendments_is_reported(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("\n- 2024", "\n- 2023-12-01: earlier.\n- 2024"))

    assert _codes(_validate(charter, kb)) == [("notes/tabs.md", 11, "error", CHANGED)]


def test_removing_the_marker_is_reported(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace(MARKER, "## Amendments"))

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", 9, "error", CHANGED)]
    assert "marker" in result.json()["diagnostics"][0]["message"]


def test_moving_the_marker_down_is_reported_as_text_added_above_it(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace(f"{MARKER}\n", f"More reasons.\n\n{MARKER}\n"))

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", 9, "error", CHANGED)]
    assert "above" in result.json()["diagnostics"][0]["message"]


def test_removing_text_at_the_end_is_reported(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("- 2024-01-01: also in YAML.\n", ""))

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", None, "error", CHANGED)]
    assert "below" in result.json()["diagnostics"][0]["message"]


def test_frontmatter_is_not_protected(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("status: accepted", "status: superseded"))

    assert _codes(_validate(charter, kb)) == []


def test_line_endings_and_trailing_whitespace_are_not_changes(charter, make_kb):
    text = DECISION.replace("We use tabs.", "We use tabs.   ").replace("\n", "\r\n") + "\r\n\r\n"
    kb = _edit(make_kb, text)

    assert _codes(_validate(charter, kb)) == []


def test_a_missing_final_newline_is_not_a_change(charter, make_kb):
    kb = _edit(make_kb, DECISION.rstrip("\n"))

    assert _codes(_validate(charter, kb)) == []


def test_extending_the_last_line_is_not_appending(charter, make_kb):
    kb = _edit(make_kb, DECISION.rstrip("\n") + " And JSON.\n")

    assert _codes(_validate(charter, kb)) == [("notes/tabs.md", 11, "error", CHANGED)]


def test_a_marker_written_differently_is_still_the_marker(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace(MARKER, "##   Amendments   (append-only) ##") + "- more\n")

    # The marker's line itself changed, even if it reads the same.
    assert _codes(_validate(charter, kb)) == [("notes/tabs.md", 9, "error", CHANGED)]


def test_a_marker_inside_a_code_block_does_not_count(charter, make_kb):
    body = f"# Use tabs\n\n```\n{MARKER}\n```\n"
    kb = _edit(make_kb, FRONTMATTER + body + "Appended.\n", {**FILES, "notes/tabs.md": FRONTMATTER + body})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", 10, "error", CHANGED)]
    assert "no `## Amendments (append-only)` heading" in result.json()["diagnostics"][0]["message"]


def test_a_note_without_the_marker_is_protected_whole(charter, make_kb):
    before = FRONTMATTER + "# Use tabs\n\nWe use tabs.\n"
    kb = _edit(make_kb, before.replace("tabs.", "spaces."), {**FILES, "notes/tabs.md": before})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", 7, "error", CHANGED)]
    assert "no `## Amendments (append-only)` heading" in result.json()["diagnostics"][0]["message"]


def test_a_note_without_the_marker_may_gain_it_at_the_end(charter, make_kb):
    before = FRONTMATTER + "# Use tabs\n\nWe use tabs.\n"
    kb = _edit(make_kb, before + f"\n{MARKER}\n\n- an amendment\n", {**FILES, "notes/tabs.md": before})

    assert _codes(_validate(charter, kb)) == []


def test_a_note_without_the_marker_may_not_gain_text_outside_it(charter, make_kb):
    before = FRONTMATTER + "# Use tabs\n\nWe use tabs.\n"
    kb = _edit(make_kb, before + "\nMore.\n", {**FILES, "notes/tabs.md": before})

    assert _codes(_validate(charter, kb)) == [("notes/tabs.md", 9, "error", CHANGED)]


def test_deleting_a_protected_note_is_reported(charter, make_kb):
    kb = _committed(make_kb)
    (kb / "notes/tabs.md").unlink()

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", None, "error", CHANGED)]
    assert "delete" in result.json()["diagnostics"][0]["message"]


def test_a_note_moved_by_a_frontmatter_change_is_judged_at_its_new_path(charter, make_kb):
    kb = _committed(make_kb)
    (kb / "notes/tabs.md").unlink()
    moved = DECISION.replace("status: accepted", "status: superseded") + "- 2024-02-01: superseded.\n"
    write_files(kb, {"notes/superseded/tabs.md": moved})

    assert _codes(_validate(charter, kb)) == []


def test_a_note_moved_with_a_forbidden_edit_is_reported(charter, make_kb):
    kb = _committed(make_kb)
    (kb / "notes/tabs.md").unlink()
    write_files(kb, {"notes/superseded/tabs.md": DECISION.replace("We use tabs.", "We use spaces.")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", None, "error", CHANGED)]
    assert "no note it adds continues its text" in result.json()["diagnostics"][0]["message"]


def test_a_moved_note_must_keep_its_kind(charter, make_kb):
    kb = _committed(make_kb)
    (kb / "notes/tabs.md").unlink()
    write_files(kb, {"notes/other.md": DECISION.replace("kind: decision\nstatus: accepted", "kind: memo")})

    assert [code for *_, code in _codes(_validate(charter, kb))] == [CHANGED]


def test_one_added_note_continues_only_one_deleted_note(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/copy.md": DECISION})
    (kb / "notes/tabs.md").unlink()
    (kb / "notes/copy.md").unlink()
    write_files(kb, {"notes/moved.md": DECISION})

    assert _codes(_validate(charter, kb)) == [("notes/tabs.md", None, "error", CHANGED)]


def test_text_that_is_no_longer_utf8_is_reported(charter, make_kb):
    kb = _edit(make_kb, DECISION.encode("utf-8") + b"\xff\xfe broken\n")

    result = _validate(charter, kb)

    assert ("notes/tabs.md", None, "error", CHANGED) in _codes(result)
    [diagnostic] = [d for d in result.json()["diagnostics"] if d["code"] == CHANGED]
    assert "not UTF-8" in diagnostic["message"]


def test_committed_text_that_is_not_utf8_is_still_protected(charter, make_kb):
    kb = _undecodable(make_kb)
    write_files(kb, {"notes/tabs.md": DECISION + "- appended\n"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/tabs.md", None, "error", CHANGED)]
    assert "not UTF-8" in result.json()["diagnostics"][0]["message"]


def test_a_byte_order_mark_is_not_a_change(charter, make_kb):
    kb = _edit(make_kb, "﻿" + DECISION + "- appended\n")

    assert _codes(_validate(charter, kb)) == []


def test_new_notes_and_other_kinds_are_not_judged(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/new.md": DECISION, "notes/memo.md": "---\nkind: memo\n---\nRewritten.\n"})

    assert _codes(_validate(charter, kb)) == []


def test_the_kind_a_note_had_before_decides(charter, make_kb):
    retyped = DECISION.replace("kind: decision\nstatus: accepted", "kind: memo")
    kb = _edit(make_kb, retyped.replace("We use tabs.", "Gone."))

    assert [code for *_, code in _codes(_validate(charter, kb))] == [CHANGED]


def test_the_check_is_off_unless_the_contract_enables_it(charter, make_kb):
    contract = CONTRACT.replace("{enabled: true, with:", "{enabled: false, with:")
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."), {**FILES, "charter.yaml": contract})

    assert _codes(_validate(charter, kb)) == []


def test_file_runs_judge_only_the_named_files(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."))

    assert _codes(_validate(charter, kb, "--file", "notes/memo.md")) == []
    assert [code for *_, code in _codes(_validate(charter, kb, "--file", "notes/tabs.md"))] == [CHANGED]


def test_the_pre_commit_stage_defers_it_to_commit_msg(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."))
    run_git(kb, "add", "-A")

    result = _validate(charter, kb, "--staged")

    assert result.exit_code == 0
    assert _codes(result) == [("charter.yaml", None, "info", "protected-region/deferred")]


def test_the_pre_commit_stage_stays_quiet_when_the_commit_msg_hook_is_installed(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."))
    run_git(kb, "add", "-A")

    result = _validate(charter, kb, "--staged", "--commit-msg-installed")

    assert result.exit_code == 0
    assert _codes(result) == []


def test_the_commit_msg_stage_judges_it(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."))
    run_git(kb, "add", "-A")

    result = validate_commit_msg(charter, kb, "Change\n")

    assert result.exit_code == 1
    assert _codes(result) == [("notes/tabs.md", 7, "error", CHANGED)]


def test_a_trailer_allows_the_change(charter, make_kb):
    kb = _edit(make_kb, DECISION.replace("We use tabs.", "Gone."))
    run_git(kb, "add", "-A")
    trailer = "Charter-Allow: protected-region/changed notes/tabs.md — correct clause per review"

    result = validate_commit_msg(charter, kb, f"Fix\n\n{trailer}\n")

    assert result.exit_code == 0
    assert _codes(result) == [("notes/tabs.md", 7, "warning", CHANGED)]
    assert f"`{trailer}`" in result.json()["diagnostics"][0]["message"]


def test_without_history_it_is_skipped_with_an_info(charter, make_kb):
    kb = make_kb(FILES)

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert _codes(result) == [("charter.yaml", None, "info", "protected-region/skipped")]


def _range(charter, kb, revisions):
    return charter("validate", f"--range={revisions}", "--format", "json", cwd=kb)


def test_range_judges_each_commit_with_its_own_trailers(charter, make_kb):
    kb = make_kb(FILES)
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = commit_files(kb, {}, "base")
    commit_files(kb, {"notes/tabs.md": DECISION + "- appended\n"}, "amend")
    commit_files(
        kb,
        {"notes/tabs.md": DECISION.replace("We use tabs.", "Fixed.") + "- appended\n"},
        "fix\n\nCharter-Allow: protected-region/changed notes/tabs.md — typo",
    )
    commit_files(kb, {"notes/tabs.md": DECISION.replace("We use tabs.", "Again.") + "- appended\n"}, "again")
    again = run_git(kb, "rev-parse", "--short", "HEAD")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 1
    assert sorted(_codes(result), key=str) == [
        ("notes/tabs.md", 7, "error", CHANGED),
        ("notes/tabs.md", 7, "warning", CHANGED),
    ]
    [error] = [d for d in result.json()["diagnostics"] if d["severity"] == "error"]
    assert f"commit {again}" in error["message"] and f"Rewrite commit {again}" in error["hint"]


@pytest.mark.parametrize(
    ("setting", "named"),
    [
        ("{enabled: true}", "kinds"),
        ("{enabled: true, with: {kinds: [decision]}}", "marker"),
        ('{enabled: true, with: {kinds: [decisions], marker: "## A"}}', "`decisions`"),
        ('{enabled: true, with: {kinds: [decision], marker: "Amendments"}}', "heading"),
        ('{enabled: true, with: {kinds: [decision], marker: "## A", days: 3}}', "days"),
        ('{enabled: true, with: {kinds: decision, marker: "## A"}}', "list"),
    ],
)
def test_bad_parameters_are_a_contract_error(charter, make_kb, setting, named):
    contract = CONTRACT.replace(
        '{enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}', setting
    )
    kb = make_kb({**FILES, "charter.yaml": contract})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    diagnostics = result.json()["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["contract/invalid"]
    assert named in diagnostics[0]["message"]


def test_disabled_it_needs_no_parameters(charter, make_kb):
    contract = CONTRACT.replace(
        '{enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}', "{severity: warning}"
    )
    kb = _committed(make_kb, {**FILES, "charter.yaml": contract})

    assert _validate(charter, kb).exit_code == 0


def test_describe_lists_it_as_disabled_until_enabled(charter, make_kb):
    contract = CONTRACT.replace(
        '  protected-region: {enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}\n', ""
    )
    kb = make_kb({**FILES, "charter.yaml": contract})

    result = charter("describe", cwd=kb)

    assert (
        "| `protected-region` | no | base | "
        "`protected-region/changed`, `protected-region/deferred`, `protected-region/skipped` |" in result.stdout
    )


UNDECODABLE = DECISION.encode("utf-8") + b"\xe9 broken\n"
BAD_FRONTMATTER = UNDECODABLE.replace(b"status: accepted", b"status: caf\xe9")
UNREADABLE = "index/unreadable"


def _undecodable(make_kb, content=UNDECODABLE):
    kb = make_kb(FILES)
    write_files(kb, {"notes/tabs.md": content})  # raw bytes, which make_kb cannot take
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


def _moved(kb, content, to="notes/superseded/tabs.md"):
    (kb / "notes/tabs.md").unlink()
    write_files(kb, {to: content})


def _unreadable(path):
    return [(path, None, "error", UNREADABLE)]


def _no_traceback(result):
    assert "Traceback" not in result.stderr


def test_deleting_a_note_whose_committed_text_is_not_utf8_is_reported_as_a_deletion(charter, make_kb):
    kb = _undecodable(make_kb)
    (kb / "notes/tabs.md").unlink()

    result = _validate(charter, kb)

    _no_traceback(result)
    assert _codes(result) == [("notes/tabs.md", None, "error", CHANGED)]
    message = result.json()["diagnostics"][0]["message"]
    assert "deletes it" in message and "not UTF-8" not in message


def test_moving_a_note_whose_committed_text_is_not_utf8_is_not_reported(charter, make_kb):
    kb = _undecodable(make_kb)
    _moved(kb, UNDECODABLE.replace(b"status: accepted", b"status: superseded") + b"- 2024-02-01: superseded.\n")

    result = _validate(charter, kb)

    _no_traceback(result)
    # The moved copy is unreadable to the index, which is reported on its own, as for any such note.
    assert _codes(result) == _unreadable("notes/superseded/tabs.md")


def test_a_byte_identical_move_of_an_undecodable_note_is_not_reported(charter, make_kb):
    kb = _undecodable(make_kb)
    _moved(kb, UNDECODABLE)

    assert _codes(_validate(charter, kb)) == _unreadable("notes/superseded/tabs.md")


def test_a_moved_undecodable_note_may_gain_lines_below_the_marker(charter, make_kb):
    kb = _undecodable(make_kb)
    _moved(kb, UNDECODABLE + b"- 2024-02-01: a new amendment.\n")

    assert _codes(_validate(charter, kb)) == _unreadable("notes/superseded/tabs.md")


def test_line_endings_of_an_undecodable_note_are_not_text(charter, make_kb):
    kb = _undecodable(make_kb, UNDECODABLE.replace(b"\n", b"\r"))
    _moved(kb, UNDECODABLE.replace(b"\n", b"\r\n"))

    assert _codes(_validate(charter, kb)) == _unreadable("notes/superseded/tabs.md")


def test_moving_an_undecodable_note_with_a_forbidden_edit_is_reported_as_a_deletion(charter, make_kb):
    kb = _undecodable(make_kb)
    _moved(kb, UNDECODABLE.replace(b"We use tabs.", b"We use spaces."))

    result = _validate(charter, kb)

    _no_traceback(result)
    assert _codes(result) == [*_unreadable("notes/superseded/tabs.md"), ("notes/tabs.md", None, "error", CHANGED)]
    [diagnostic] = [d for d in result.json()["diagnostics"] if d["code"] == CHANGED]
    assert "no note it adds continues its text" in diagnostic["message"]


def test_a_byte_that_is_not_utf8_in_the_frontmatter_of_a_moved_copy_does_not_crash(charter, make_kb):
    kb = _undecodable(make_kb)
    _moved(kb, BAD_FRONTMATTER)

    result = _validate(charter, kb)

    _no_traceback(result)
    assert _codes(result) == _unreadable("notes/superseded/tabs.md")


def test_deleting_an_undecodable_note_beside_an_unrelated_undecodable_addition_does_not_crash(charter, make_kb):
    kb = _undecodable(make_kb)
    (kb / "notes/tabs.md").unlink()
    write_files(kb, {"notes/other.md": BAD_FRONTMATTER.replace(b"We use tabs.", b"Something else.")})

    result = _validate(charter, kb)

    _no_traceback(result)
    [diagnostic] = [d for d in result.json()["diagnostics"] if d["code"] == CHANGED]
    assert diagnostic["path"] == "notes/tabs.md" and "deletes it" in diagnostic["message"]


def test_range_reports_the_deletion_of_an_undecodable_note_as_a_deletion(charter, make_kb):
    kb = _undecodable(make_kb)
    base = run_git(kb, "rev-parse", "HEAD")
    (kb / "notes/tabs.md").unlink()
    commit_files(kb, {}, "delete")

    result = _range(charter, kb, f"{base}..HEAD")

    _no_traceback(result)
    [diagnostic] = [d for d in result.json()["diagnostics"] if d["code"] == CHANGED]
    assert diagnostic["path"] == "notes/tabs.md" and "deletes it" in diagnostic["message"]


@pytest.mark.parametrize("moved", [UNDECODABLE, BAD_FRONTMATTER], ids=["body", "frontmatter"])
def test_range_accepts_a_byte_identical_move_of_an_undecodable_note(charter, make_kb, moved):
    kb = _undecodable(make_kb, moved)
    base = run_git(kb, "rev-parse", "HEAD")
    (kb / "notes/tabs.md").unlink()
    commit_files(kb, {"notes/superseded/tabs.md": moved}, "move")

    result = _range(charter, kb, f"{base}..HEAD")

    _no_traceback(result)
    assert [code for *_, code in _codes(result) if code == CHANGED] == []
