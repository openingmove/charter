"""`validate --file` asks git only when something judges the named files, and then in as few calls as it can."""

import pytest
from conftest import commit_files, run_git, write_files

from charter import git as charter_git

NOTE = "---\nkind: entry\n---\n"
KINDS = "kinds:\n  entry:\n    fields:\n      kind: {type: string, required: true}\n"
PLAIN = "charter: 1\nroot: notes\n" + KINDS
GUARDED = 'charter: 1\nroot: notes\npaths:\n  "Archive/**": {edit: read-only}\n' + KINDS
PROTECTING = (
    "charter: 1\nroot: notes\nchecks:\n  protected-region:\n    enabled: true\n"
    '    with: {kinds: [entry], marker: "## Amendments"}\n' + KINDS
)
FILES = {"notes/free.md": NOTE, "notes/Archive/old.md": NOTE}


@pytest.fixture
def git_calls(monkeypatch):
    """The argument lists of the git commands charter starts."""
    calls = []
    real = charter_git._run_git

    def counted(args, *rest, **named):
        calls.append(list(args))
        return real(args, *rest, **named)

    monkeypatch.setattr(charter_git, "_run_git", counted)
    return calls


def _repo(make_kb, contract):
    kb = make_kb({"charter.yaml": contract, **FILES})
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


def _file(charter, kb, *paths):
    return charter("validate", "--profile", "ci", "--format", "json", "--file", *paths, cwd=kb)


def _codes(result):
    return [(d["path"], d["code"]) for d in result.json()["diagnostics"]]


def test_a_contract_with_no_edit_policy_or_history_check_makes_no_git_call(charter, make_kb, git_calls):
    kb = _repo(make_kb, PLAIN)
    git_calls.clear()

    result = _file(charter, kb, "notes/free.md")

    assert result.exit_code == 0
    assert git_calls == []


def test_an_edit_policy_that_covers_none_of_the_named_files_makes_no_git_call(charter, make_kb, git_calls):
    kb = _repo(make_kb, GUARDED)
    write_files(kb, {"notes/free.md": NOTE + "Edited.\n"})
    git_calls.clear()

    result = _file(charter, kb, "notes/free.md")

    assert result.exit_code == 0
    assert git_calls == []


def test_uncovered_file_outside_a_repository_makes_no_call_and_no_info(charter, make_kb, git_calls):
    # The documented exception: charter cannot know git is unusable without asking it.
    kb = make_kb({"charter.yaml": GUARDED, **FILES})

    result = _file(charter, kb, "notes/free.md")

    assert result.exit_code == 0
    assert _codes(result) == []
    assert git_calls == []


def test_an_edit_policy_that_covers_a_named_file_judges_it_in_two_git_calls(charter, make_kb, git_calls):
    kb = _repo(make_kb, GUARDED)
    write_files(kb, {"notes/Archive/old.md": NOTE + "Edited.\n"})
    git_calls.clear()

    result = _file(charter, kb, "notes/Archive/old.md", "notes/free.md")

    assert _codes(result) == [("notes/Archive/old.md", "paths/read-only")]
    assert [call[0] for call in git_calls] == ["diff", "ls-files"]


def test_protected_region_judges_in_two_git_calls(charter, make_kb, git_calls):
    kb = _repo(make_kb, PROTECTING)
    git_calls.clear()

    result = _file(charter, kb, "notes/free.md")

    assert result.exit_code == 0
    assert [call[0] for call in git_calls] == ["diff", "ls-files"]


def test_covered_file_outside_a_repository_is_reported_as_unchecked(charter, make_kb):
    kb = make_kb({"charter.yaml": GUARDED, **FILES})

    result = _file(charter, kb, "notes/Archive/old.md")

    assert _codes(result) == [("charter.yaml", "paths/edit-skipped")]


def test_a_failing_diff_in_a_healthy_repository_is_reported_without_a_retry(
    charter, make_kb, git_calls, monkeypatch
):
    kb = _repo(make_kb, GUARDED)
    real = charter_git._Git.run

    def failing(self, *args, **kwargs):
        if args[0] == "diff":
            raise charter_git.GitError("`git diff` failed.")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(charter_git._Git, "run", failing)
    git_calls.clear()

    result = _file(charter, kb, "notes/Archive/old.md")

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", "usage/git-failed")]
    assert "`git diff` failed." in result.json()["diagnostics"][0]["message"]
    # The two probes ran once; the diff was not run again.
    assert [call[0] for call in git_calls] == ["rev-parse", "rev-parse"]


def test_git_that_cannot_be_started_is_reported_as_unchecked(charter, make_kb, monkeypatch):
    kb = make_kb({"charter.yaml": GUARDED, **FILES})

    def missing(*args, **kwargs):
        raise charter_git.GitUnavailable("git could not be run: not found.")

    monkeypatch.setattr(charter_git, "_run_git", missing)

    result = _file(charter, kb, "notes/Archive/old.md")

    assert _codes(result) == [("charter.yaml", "paths/edit-skipped")]
    assert "git could not be run" in result.json()["diagnostics"][0]["message"]


def test_a_repository_with_no_commit_is_reported_as_unchecked(charter, make_kb):
    kb = make_kb({"charter.yaml": GUARDED, **FILES})
    run_git(kb, "init", "-q", "--initial-branch=main")

    result = _file(charter, kb, "notes/Archive/old.md")

    assert _codes(result) == [("charter.yaml", "paths/edit-skipped")]
    assert "no commit yet" in result.json()["diagnostics"][0]["message"]
