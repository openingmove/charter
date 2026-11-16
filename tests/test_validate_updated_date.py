
import pytest
from conftest import commit_files, run_git, validate_commit_msg, write_files

CONTRACT = """\
charter: 1
root: notes
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      title: {type: string}
      updated: {type: date}
  memo:
    fields:
      kind: {type: string, required: true}
checks:
  agents-include: {enabled: false}
  updated-date: {enabled: true}
"""
OLD = "2000-01-01"


def _entry(updated=OLD, body="", title="A"):
    lines = ["---", "kind: entry", f"title: {title}"]
    if updated is not None:
        lines.append(f"updated: {updated}")
    return "\n".join([*lines, "---", body])


FILES = {
    "charter.yaml": CONTRACT,
    "notes/a.md": _entry(),
    "notes/b.md": _entry(),
    "notes/memo.md": "---\nkind: memo\n---\n",
}


TODAY = "2026-02-10"


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    monkeypatch.setenv("CHARTER_TODAY", TODAY)


def _codes(result):
    return [(d["path"], d["line"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _committed(make_kb, files=FILES):
    kb = make_kb(files)
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


STALE = [("notes/a.md", 4, "error", "updated-date/stale")]


def test_a_changed_note_whose_updated_date_did_not_move_is_reported(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})

    result = _validate(charter, kb)

    assert result.exit_code == 1
    assert _codes(result) == STALE
    diagnostic = result.json()["diagnostics"][0]
    assert f"`updated` is {OLD}" in diagnostic["message"]
    assert f"`updated: {TODAY}`" in diagnostic["hint"]


def test_the_check_is_off_unless_the_contract_enables_it(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "charter.yaml": CONTRACT.replace("  updated-date: {enabled: true}\n", "")})
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})

    assert _codes(_validate(charter, kb)) == []


def test_configuring_the_check_without_enabling_it_leaves_it_off(charter, make_kb):
    contract = CONTRACT.replace("{enabled: true}", "{severity: warning}")
    kb = _committed(make_kb, {**FILES, "charter.yaml": contract})
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})

    assert _codes(_validate(charter, kb)) == []


@pytest.mark.parametrize("updated", ["today", "2000-01-02", "2999-01-01"])
def test_today_or_any_date_later_than_before_satisfies_it(charter, make_kb, updated):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(updated=TODAY if updated == "today" else updated, body="Edited.\n")})

    assert _codes(_validate(charter, kb)) == []


def test_today_satisfies_it_even_when_the_date_before_was_later(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/a.md": _entry(updated="2999-01-01")})
    write_files(kb, {"notes/a.md": _entry(updated=TODAY, body="Edited.\n")})

    assert _codes(_validate(charter, kb)) == []


def test_a_date_moved_back_is_reported(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/a.md": _entry(updated="2001-01-01")})
    write_files(kb, {"notes/a.md": _entry(updated="2000-06-01", body="Edited.\n")})

    result = _validate(charter, kb)

    assert _codes(result) == STALE
    assert "later than 2001-01-01" in result.json()["diagnostics"][0]["message"]


def test_a_changed_note_without_the_field_is_reported(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(updated=None, body="Edited.\n")})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/a.md", None, "error", "updated-date/stale")]
    assert "no `updated`" in result.json()["diagnostics"][0]["message"]


def test_a_mistyped_date_is_left_to_the_schema_check(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(updated="soon", body="Edited.\n")})

    assert [code for *_, code in _codes(_validate(charter, kb))] == ["schema/type"]


def test_a_frontmatter_only_change_counts_as_a_change(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(title="Renamed")})

    assert _codes(_validate(charter, kb)) == STALE


def test_unchanged_and_new_notes_are_not_judged(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/new.md": _entry()})

    assert _codes(_validate(charter, kb)) == []


def test_notes_of_kinds_without_the_field_are_not_judged(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/memo.md": "---\nkind: memo\n---\nEdited.\n"})

    assert _codes(_validate(charter, kb)) == []


def test_line_endings_alone_are_not_a_change(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry().replace("\n", "\r\n")})
    run_git(kb, "add", "-A")

    assert _codes(_validate(charter, kb, "--staged")) == []


def test_a_permission_change_alone_is_not_a_content_change(charter, make_kb):
    kb = _committed(make_kb)
    run_git(kb, "update-index", "--chmod=+x", "notes/a.md")

    assert _codes(_validate(charter, kb, "--staged")) == []


def test_the_field_is_configurable(charter, make_kb):
    contract = CONTRACT.replace("updated: {type: date}", "revised: {type: date}").replace(
        "{enabled: true}", "{enabled: true, with: {field: revised}}"
    )
    note = _entry(updated=None).replace("title: A", "title: A\nrevised: 2000-01-01")
    files = {**FILES, "charter.yaml": contract, "notes/a.md": note, "notes/b.md": note}
    kb = _committed(make_kb, files)
    write_files(kb, {"notes/a.md": files["notes/a.md"] + "Edited.\n"})

    result = _validate(charter, kb)

    assert _codes(result) == STALE
    assert "`revised`" in result.json()["diagnostics"][0]["message"]


def test_its_severity_can_be_overridden(charter, make_kb):
    contract = CONTRACT.replace("{enabled: true}", "{enabled: true, severity: warning}")
    kb = _committed(make_kb, {**FILES, "charter.yaml": contract})
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert _codes(result) == [("notes/a.md", 4, "warning", "updated-date/stale")]


def test_staged_runs_judge_the_staged_content(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})
    run_git(kb, "add", "-A")
    write_files(kb, {"notes/a.md": _entry(updated=TODAY, body="Edited.\n")})

    assert _codes(_validate(charter, kb, "--staged")) == STALE
    assert _codes(_validate(charter, kb)) == []


def test_the_commit_msg_stage_leaves_it_to_pre_commit(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})
    run_git(kb, "add", "-A")

    assert _codes(validate_commit_msg(charter, kb, "Change\n")) == []


def test_file_runs_judge_only_the_named_files(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n"), "notes/b.md": _entry(body="Edited.\n")})

    assert _codes(_validate(charter, kb, "--file", "notes/a.md")) == STALE


def test_all_runs_judge_every_change_since_the_last_commit_staged_or_not(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/a.md": _entry(body="Edited.\n")})
    run_git(kb, "add", "-A")
    write_files(kb, {"notes/b.md": _entry(body="Edited.\n")})

    assert _codes(_validate(charter, kb, "--all")) == [*STALE, ("notes/b.md", 4, "error", "updated-date/stale")]


def test_a_clock_override_that_is_not_a_date_is_a_usage_error(charter, make_kb, monkeypatch):
    kb = _committed(make_kb)
    monkeypatch.setenv("CHARTER_TODAY", "tomorrow")

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/invalid-today"]


def test_without_history_it_is_skipped_with_an_info(charter, make_kb):
    kb = make_kb(FILES)

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert _codes(result) == [("charter.yaml", None, "info", "updated-date/skipped")]
    assert "git" in result.json()["diagnostics"][0]["message"]


def _range(charter, kb, revisions):
    return charter("validate", f"--range={revisions}", "--format", "json", cwd=kb)


def _commit_on(monkeypatch, kb, day, files, message="change"):
    # Early morning east of UTC: the author's day is not UTC's.
    monkeypatch.setenv("GIT_AUTHOR_DATE", f"{day}T01:30:00+05:00")
    # Committed (rebased, say) much later: the author date is the one that counts.
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2030-12-31T12:00:00+00:00")
    return commit_files(kb, files, message)


def test_range_judges_each_commit_as_of_its_own_date(charter, make_kb, monkeypatch):
    kb = make_kb(FILES)
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = _commit_on(monkeypatch, kb, "2024-03-01", {}, "base")
    _commit_on(monkeypatch, kb, "2024-03-05", {"notes/a.md": _entry(updated="2024-03-05", body="One.\n")})
    # Edited again the same day: the date it already holds is that commit's today.
    _commit_on(monkeypatch, kb, "2024-03-05", {"notes/a.md": _entry(updated="2024-03-05", body="Two.\n")})
    _commit_on(monkeypatch, kb, "2024-03-06", {"notes/a.md": _entry(updated="2024-03-04", body="Three.\n")})
    late = run_git(kb, "rev-parse", "--short", "HEAD")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 1
    assert _codes(result) == [STALE[0]]
    diagnostic = result.json()["diagnostics"][0]
    assert f"commit {late}" in diagnostic["message"] and "2024-03-06" in diagnostic["message"]
    assert f"Rewrite commit {late}" in diagnostic["hint"] and "`updated: 2024-03-06`" in diagnostic["hint"]


def test_range_ignores_the_clock_override(charter, make_kb, monkeypatch):
    kb = make_kb(FILES)
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = _commit_on(monkeypatch, kb, "2024-03-01", {}, "base")
    _commit_on(monkeypatch, kb, "2024-03-05", {"notes/a.md": _entry(updated="2000-01-01", body="One.\n")})
    monkeypatch.setenv("CHARTER_TODAY", "2000-01-01")

    assert _codes(_range(charter, kb, f"{base}..HEAD")) == [STALE[0]]


def test_range_skips_commits_whose_contract_leaves_it_off(charter, make_kb, monkeypatch):
    kb = make_kb({**FILES, "charter.yaml": CONTRACT.replace("  updated-date: {enabled: true}\n", "")})
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = _commit_on(monkeypatch, kb, "2024-03-01", {}, "base")
    _commit_on(monkeypatch, kb, "2024-03-05", {"notes/a.md": _entry(body="One.\n")})

    assert _codes(_range(charter, kb, f"{base}..HEAD")) == []


def test_an_undeclared_field_is_a_contract_error(charter, make_kb):
    contract = CONTRACT.replace("{enabled: true}", "{enabled: true, with: {field: revised}}")
    kb = make_kb({**FILES, "charter.yaml": contract})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["code"] == "contract/invalid"
    assert "`revised`" in diagnostic["message"]


def test_a_field_that_is_not_a_date_is_a_contract_error(charter, make_kb):
    kb = make_kb({**FILES, "charter.yaml": CONTRACT.replace("updated: {type: date}", "updated: {type: string}")})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert "date" in result.json()["diagnostics"][0]["message"]


def test_unknown_parameters_are_a_contract_error(charter, make_kb):
    kb = make_kb({**FILES, "charter.yaml": CONTRACT.replace("{enabled: true}", "{enabled: true, with: {days: 3}}")})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["contract/invalid"]


def test_describe_lists_it_as_disabled_until_enabled(charter, make_kb):
    kb = make_kb({**FILES, "charter.yaml": CONTRACT.replace("  updated-date: {enabled: true}\n", "")})

    result = charter("describe", cwd=kb)

    assert "| `updated-date` | no | base | `updated-date/skipped`, `updated-date/stale` |" in result.stdout
