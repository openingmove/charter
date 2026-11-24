import pytest
from conftest import commit_files, run_git, validate_commit_msg, write_files

CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
  "Archive/Open/**": {edit: create-only}
  "Research/**": {edit: create-only}
  "Research/Drafts/**": {kinds: [entry]}
  "Research/Scratch/**": {ignore: true}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"
FILES = {
    "charter.yaml": CONTRACT,
    "notes/Archive/old.md": NOTE,
    "notes/Archive/gone.md": NOTE,
    "notes/Archive/Open/log.md": NOTE,
    "notes/Research/topic.md": NOTE,
    "notes/Research/Drafts/draft.md": NOTE,
    "notes/Research/Scratch/pad.md": NOTE,
    "notes/free.md": NOTE,
}


def _codes(result):
    return [(d["path"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _committed(make_kb, files=FILES):
    kb = make_kb(files)
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


def _stage(kb, files=None, removed=()):
    write_files(kb, files or {})
    for path in removed:
        (kb / path).unlink()
    run_git(kb, "add", "-A")


def test_adding_changing_or_deleting_a_read_only_file_is_reported(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED, "notes/Archive/new.md": NOTE}, removed=["notes/Archive/gone.md"])

    result = validate_commit_msg(charter, kb, "Change\n")

    assert result.exit_code == 1
    assert _codes(result) == [
        ("notes/Archive/gone.md", "error", "paths/read-only"),
        ("notes/Archive/new.md", "error", "paths/read-only"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
    ]
    gone, new, old = result.json()["diagnostics"]
    assert "deleted" in gone["message"] and "`Archive/**`" in gone["message"]
    assert "added" in new["message"]
    assert "changed" in old["message"]


def test_create_only_allows_new_files_but_not_changes_to_existing_ones(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Research/topic.md": EDITED, "notes/Research/another.md": NOTE})

    result = validate_commit_msg(charter, kb, "Change\n")

    assert _codes(result) == [("notes/Research/topic.md", "error", "paths/create-only")]
    assert "`Research/**`" in result.json()["diagnostics"][0]["message"]


def test_create_only_forbids_deleting_an_existing_file(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, removed=["notes/Research/topic.md"])

    result = validate_commit_msg(charter, kb, "Change\n")

    assert _codes(result) == [("notes/Research/topic.md", "error", "paths/create-only")]
    assert "deleted" in result.json()["diagnostics"][0]["message"]


def test_a_permission_change_is_a_change(charter, make_kb):
    kb = _committed(make_kb)
    run_git(kb, "update-index", "--chmod=+x", "notes/Archive/old.md")

    result = validate_commit_msg(charter, kb, "Change\n")

    assert _codes(result) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_edit_policies_cascade_per_key(charter, make_kb):
    kb = _committed(make_kb)
    # Drafts sets only `kinds`, so it keeps Research's create-only; Archive/Open overrides Archive's read-only.
    _stage(kb, {"notes/Research/Drafts/draft.md": EDITED, "notes/Archive/Open/log.md": EDITED})

    assert _codes(validate_commit_msg(charter, kb, "Change\n")) == [
        ("notes/Archive/Open/log.md", "error", "paths/create-only"),
        ("notes/Research/Drafts/draft.md", "error", "paths/create-only"),
    ]


def test_files_without_an_edit_policy_or_ignored_may_change(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": EDITED, "notes/Research/Scratch/pad.md": EDITED})

    assert _codes(validate_commit_msg(charter, kb, "Change\n")) == []


def test_staged_runs_judge_the_staged_change_not_the_working_copy(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/Archive/old.md": EDITED})

    assert _codes(validate_commit_msg(charter, kb, "Change\n")) == []


def test_a_whole_run_compares_the_working_copy_with_head(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {
        "notes/Archive/old.md": EDITED,
        "notes/Archive/untracked.md": NOTE,
        "notes/Research/untracked.md": NOTE,
    })
    (kb / "notes/Archive/gone.md").unlink()

    result = _validate(charter, kb)

    assert result.exit_code == 1
    assert _codes(result) == [
        ("notes/Archive/gone.md", "error", "paths/read-only"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
        ("notes/Archive/untracked.md", "error", "paths/read-only"),
    ]


def test_a_whole_run_reports_staged_changes_too(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Research/topic.md": EDITED})

    assert _codes(_validate(charter, kb, "--all")) == [("notes/Research/topic.md", "error", "paths/create-only")]


def test_file_runs_judge_only_the_named_files(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {"notes/Archive/old.md": EDITED, "notes/Research/topic.md": EDITED})

    result = _validate(charter, kb, "--file", "notes/Research/topic.md")

    assert _codes(result) == [("notes/Research/topic.md", "error", "paths/create-only")]


def test_a_file_run_on_a_deleted_tracked_file_judges_the_deletion(charter, make_kb):
    kb = _committed(make_kb)
    (kb / "notes/Archive/gone.md").unlink()

    result = _validate(charter, kb, "--file", "notes/Archive/gone.md")

    assert result.exit_code == 1
    assert _codes(result) == [("notes/Archive/gone.md", "error", "paths/read-only")]
    assert "deleted" in result.json()["diagnostics"][0]["message"]


def test_a_file_run_on_a_tracked_file_removed_with_its_folder_and_from_the_index_judges_the_deletion(
    charter, make_kb
):
    kb = _committed(make_kb)
    run_git(kb, "rm", "-q", "-r", "notes/Archive")

    result = _validate(charter, kb, "--file", "notes/Archive/gone.md")

    assert _codes(result) == [("notes/Archive/gone.md", "error", "paths/read-only")]


@pytest.mark.parametrize("name", ["notes/free.md", "notes/Research/Scratch/pad.md"])
def test_a_file_run_on_a_deleted_tracked_file_no_policy_covers_passes(charter, make_kb, name):
    kb = _committed(make_kb)
    (kb / name).unlink()

    result = _validate(charter, kb, "--file", name)

    assert (result.exit_code, _codes(result)) == (0, [])


@pytest.mark.parametrize("name", ["notes/Archive/never.md", "notes/Archive"])
def test_a_file_run_on_a_missing_untracked_path_or_a_deleted_folder_is_a_usage_error(charter, make_kb, name):
    kb = _committed(make_kb)
    if name == "notes/Archive":
        run_git(kb, "rm", "-q", "-r", name)

    result = _validate(charter, kb, "--file", name)

    assert result.exit_code == 2
    assert _codes(result) == [(name, "error", "usage/file-not-found")]


def test_a_file_run_on_a_missing_path_outside_git_is_a_usage_error(charter, make_kb):
    kb = make_kb(FILES)
    (kb / "notes/Archive/gone.md").unlink()

    result = _validate(charter, kb, "--file", "notes/Archive/gone.md")

    assert result.exit_code == 2
    assert _codes(result) == [("notes/Archive/gone.md", "error", "usage/file-not-found")]


def test_file_runs_read_names_literally(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/Archive/[a].md": NOTE, "notes/Archive/a.md": NOTE})
    write_files(kb, {"notes/Archive/a.md": EDITED})

    assert _codes(_validate(charter, kb, "--file", "notes/Archive/[a].md")) == []


def test_before_the_first_commit_edit_policies_are_skipped_with_an_info(charter, make_kb):
    kb = make_kb(FILES)
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "-A")

    for result in (_validate(charter, kb), validate_commit_msg(charter, kb, "Change\n")):
        assert _codes(result) == [("charter.yaml", "info", "paths/edit-skipped")]
        assert "no commit yet" in result.json()["diagnostics"][0]["message"]


def test_outside_a_git_repository_edit_policies_are_skipped_with_an_info(charter, make_kb):
    kb = make_kb(FILES)

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert _codes(result) == [("charter.yaml", "info", "paths/edit-skipped")]
    assert "git" in result.json()["diagnostics"][0]["message"]


def test_outside_a_git_repository_without_edit_policies_nothing_is_said(charter, make_kb):
    kb = make_kb({"charter.yaml": CONTRACT.replace("edit: read-only", "kinds: [entry]").replace(
        "edit: create-only", "kinds: [entry]"
    ), "notes/free.md": NOTE})

    assert _codes(_validate(charter, kb)) == []


def test_an_unknown_edit_policy_is_a_contract_error(charter, make_kb):
    kb = make_kb({"charter.yaml": CONTRACT.replace("edit: read-only", "edit: frozen")})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["contract/invalid"]


def test_describe_explains_edit_policies(charter, make_kb):
    kb = make_kb(FILES)

    result = charter("describe", cwd=kb)

    assert "| `Archive/**` | read-only: no files may be added, changed or deleted |" in result.stdout
    assert (
        "| `Research/**` | create-only: new files may be added; existing files may not change or be deleted |"
        in result.stdout
    )


def test_without_git_installed_edit_policies_are_skipped_with_an_info(charter, make_kb, tmp_path_factory, monkeypatch):
    kb = _committed(make_kb)
    write_files(kb, {"notes/Archive/old.md": EDITED})
    monkeypatch.setenv("PATH", str(tmp_path_factory.mktemp("no-git")))

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert _codes(result) == [("charter.yaml", "info", "paths/edit-skipped")]


def test_a_repository_git_refuses_is_an_error_not_a_skip(charter, make_kb):
    kb = _committed(make_kb)
    run_git(kb, "config", "core.repositoryformatversion", "99")
    write_files(kb, {"notes/Archive/old.md": EDITED})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    assert [(d["path"], d["code"]) for d in result.json()["diagnostics"]] == [("charter.yaml", "usage/git-failed")]


def test_a_head_naming_a_missing_commit_is_an_error_not_an_empty_history(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {".git/refs/heads/main": "0123456789012345678901234567890123456789\n"})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    diagnostic = result.json()["diagnostics"][0]
    assert (diagnostic["code"], "HEAD" in diagnostic["message"]) == ("usage/git-failed", True)


def test_a_gitignored_file_is_not_seen_as_added_unless_it_is_force_added(charter, make_kb):
    kb = _committed(make_kb, {**FILES, ".gitignore": "*.tmp\n"})
    write_files(kb, {"notes/Archive/seen.md": NOTE, "notes/Archive/scratch.tmp": "x"})

    plain = _validate(charter, kb)

    assert _codes(plain) == [("notes/Archive/seen.md", "error", "paths/read-only")]

    run_git(kb, "add", "-f", "notes/Archive/scratch.tmp")
    forced = _validate(charter, kb)
    staged = validate_commit_msg(charter, kb, "Add\n")

    assert ("notes/Archive/scratch.tmp", "error", "paths/read-only") in _codes(forced)
    assert ("notes/Archive/scratch.tmp", "error", "paths/read-only") in _codes(staged)

    base = run_git(kb, "rev-parse", "HEAD")
    run_git(kb, "commit", "-q", "-m", "Add")
    ranged = _validate(charter, kb, "--range", f"{base}..HEAD")

    assert ("notes/Archive/scratch.tmp", "error", "paths/read-only") in _codes(ranged)
    added = next(d for d in ranged.json()["diagnostics"] if d["path"] == "notes/Archive/scratch.tmp")
    assert "added" in added["message"]


@pytest.mark.parametrize("source", ["info/exclude", "core.excludesFile"])
def test_a_file_git_ignores_through_exclude_files_is_not_seen_as_added(charter, make_kb, source):
    kb = _committed(make_kb)
    if source == "info/exclude":
        write_files(kb, {".git/info/exclude": "*.tmp\n"})
    else:
        write_files(kb, {".git/global-excludes": "*.tmp\n"})
        run_git(kb, "config", "core.excludesFile", str(kb / ".git" / "global-excludes"))
    write_files(kb, {"notes/Archive/seen.md": NOTE, "notes/Archive/scratch.tmp": "x"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Archive/seen.md", "error", "paths/read-only")]


def test_a_tracked_file_that_git_later_ignores_is_reported_as_changed(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/Archive/kept.tmp": "x"})
    write_files(kb, {".git/info/exclude": "*.tmp\n", "notes/Archive/kept.tmp": "y"})

    plain = _validate(charter, kb)
    _stage(kb)
    staged = validate_commit_msg(charter, kb, "Change\n")
    base = run_git(kb, "rev-parse", "HEAD")
    run_git(kb, "commit", "-q", "-m", "Change")
    ranged = _validate(charter, kb, "--range", f"{base}..HEAD")

    for result in (plain, staged, ranged):
        assert _codes(result) == [("notes/Archive/kept.tmp", "error", "paths/read-only")]
        assert "changed" in result.json()["diagnostics"][0]["message"]
