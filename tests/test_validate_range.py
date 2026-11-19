import pytest
from charter import git as charter_git
from conftest import FIXTURES, commit_files, run_git

CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
  "Research/**": {edit: create-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      title: {type: string}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"
FILES = {
    "charter.yaml": CONTRACT,
    "notes/Archive/old.md": NOTE,
    "notes/Research/topic.md": NOTE,
    "notes/free.md": NOTE,
}
ALLOW_OLD = "Fix a typo\n\nCharter-Allow: paths/read-only notes/Archive/old.md — typo\n"


def _diagnostics(result):
    return [(d["path"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _range(charter, kb, revisions, *argv):
    return charter("validate", f"--range={revisions}", "--format", "json", *argv, cwd=kb)


def _base(make_kb, files=FILES):
    """A repository whose one commit holds `files`; returns it and that commit."""
    kb = make_kb(files)
    run_git(kb, "init", "-q", "--initial-branch=main")
    return kb, commit_files(kb, {}, "base")


def _short(kb, commit):
    return run_git(kb, "rev-parse", "--short", commit)


def test_each_commit_is_checked_against_its_parent(charter, make_kb):
    kb, base = _base(make_kb)
    first = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit the archive")
    commit_files(kb, {"notes/free.md": EDITED}, "Edit a free note")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 1
    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]
    assert f"commit {_short(kb, first)}" in result.json()["diagnostics"][0]["message"]


def test_a_violation_undone_by_a_later_commit_is_still_reported(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/Research/topic.md": EDITED}, "Edit")
    commit_files(kb, {"notes/Research/topic.md": NOTE}, "Undo")

    result = _range(charter, kb, f"{base}..HEAD")

    assert _diagnostics(result) == [
        ("notes/Research/topic.md", "error", "paths/create-only"),
        ("notes/Research/topic.md", "error", "paths/create-only"),
    ]


def test_a_commit_trailer_allows_its_own_violation(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/Archive/old.md": EDITED}, ALLOW_OLD)

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 0
    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]
    assert "Charter-Allow: paths/read-only notes/Archive/old.md — typo" in result.json()["diagnostics"][0]["message"]


def test_a_trailer_in_one_commit_does_not_excuse_a_violation_in_another(charter, make_kb):
    kb, base = _base(make_kb)
    first = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit the archive")
    second = commit_files(kb, {"notes/free.md": EDITED}, ALLOW_OLD)

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
    ]
    unused, violation = result.json()["diagnostics"]
    assert f"of commit {_short(kb, second)}" in unused["message"]
    assert f"commit {_short(kb, first)}" in violation["message"]


def test_the_same_file_allowed_in_one_commit_and_not_another(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/Archive/old.md": EDITED}, ALLOW_OLD)
    commit_files(kb, {"notes/Archive/old.md": NOTE}, "Edit it again")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 1
    assert sorted(_diagnostics(result)) == [
        ("notes/Archive/old.md", "error", "paths/read-only"),
        ("notes/Archive/old.md", "warning", "paths/read-only"),
    ]


def test_range_selects_the_ci_profile(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/free.md": EDITED})

    assert _range(charter, kb, f"{base}..HEAD").json()["profile"] == "ci"


def test_the_profile_can_still_be_chosen(charter, make_kb):
    kb, base = _base(make_kb, {**FILES, "charter.yaml": CONTRACT + "profiles:\n  lenient: {paths: warning}\n"})
    commit_files(kb, {"notes/Archive/old.md": EDITED})

    result = _range(charter, kb, f"{base}..HEAD", "--profile", "lenient")

    assert result.json()["profile"] == "lenient"
    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


def test_only_edit_policies_are_checked(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/free.md": "---\ntitle: [x]\n---\n"})

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 0
    assert _diagnostics(result) == []


def test_each_commit_is_judged_by_its_own_contract(charter, make_kb):
    kb, base = _base(make_kb, {**FILES, "charter.yaml": CONTRACT.replace("{edit: read-only}", "{kinds: [entry]}")})
    commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit before the archive was protected")
    commit_files(kb, {"charter.yaml": CONTRACT}, "Protect the archive")
    last = commit_files(kb, {"notes/Archive/old.md": NOTE}, "Edit after")

    result = _range(charter, kb, f"{base}..HEAD")

    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]
    assert f"commit {_short(kb, last)}" in result.json()["diagnostics"][0]["message"]


def test_commits_without_the_contract_are_not_judged(charter, make_kb):
    kb, base = _base(make_kb, {"notes/Archive/old.md": NOTE})
    commit_files(kb, {"notes/Archive/old.md": EDITED}, "Before charter")
    commit_files(kb, {"charter.yaml": CONTRACT}, "Adopt charter")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 0
    assert _diagnostics(result) == []


def test_a_commit_with_an_invalid_contract_is_a_usage_error_naming_it(charter, make_kb):
    kb, base = _base(make_kb)
    broken = commit_files(kb, {"charter.yaml": "charter: 1\nkinds: 3\n"}, "Break the contract")
    commit_files(kb, {"charter.yaml": CONTRACT}, "Fix it")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 2
    assert all(d["path"] == "charter.yaml" for d in result.json()["diagnostics"])
    assert f"commit {_short(kb, broken)}" in result.json()["diagnostics"][0]["message"]


def test_a_merge_is_judged_only_on_what_it_decides_itself(charter, make_kb):
    kb, base = _base(make_kb)
    run_git(kb, "checkout", "-q", "-b", "side")
    commit_files(kb, {"notes/Archive/old.md": EDITED}, ALLOW_OLD)
    run_git(kb, "checkout", "-q", "main")
    commit_files(kb, {"notes/free.md": EDITED}, "Main moves on")
    run_git(kb, "merge", "-q", "--no-ff", "--no-edit", "side")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 0
    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


def test_an_edit_a_merge_makes_itself_is_reported_on_the_merge(charter, make_kb):
    kb, base = _base(make_kb)
    run_git(kb, "checkout", "-q", "-b", "side")
    commit_files(kb, {"notes/free.md": EDITED}, "Side")
    run_git(kb, "checkout", "-q", "main")
    commit_files(kb, {"notes/Research/new.md": NOTE}, "Main moves on")
    run_git(kb, "merge", "-q", "--no-ff", "--no-commit", "side")
    merge = commit_files(kb, {"notes/Research/topic.md": EDITED}, "Merge side")

    result = _range(charter, kb, f"{base}..HEAD")

    assert _diagnostics(result) == [("notes/Research/topic.md", "error", "paths/create-only")]
    assert f"commit {_short(kb, merge)}" in result.json()["diagnostics"][0]["message"]


def test_a_root_commit_has_nothing_to_compare_with(charter, make_kb):
    kb, _ = _base(make_kb)
    run_git(kb, "checkout", "-q", "--orphan", "fresh")
    root = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Start over")

    result = _range(charter, kb, "main..fresh")

    assert result.exit_code == 0
    assert _diagnostics(result) == [("charter.yaml", "info", "paths/edit-skipped")]
    assert f"commit {_short(kb, root)}" in result.json()["diagnostics"][0]["message"]


def test_an_empty_range_is_clean(charter, make_kb):
    kb, _ = _base(make_kb)

    result = _range(charter, kb, "HEAD..HEAD")

    assert result.exit_code == 0
    assert result.json()["diagnostics"] == []
    assert result.json()["profile"] == "ci"


def test_an_omitted_end_means_head(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/Archive/old.md": EDITED})

    assert _diagnostics(_range(charter, kb, f"{base}..")) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_a_knowledge_base_below_the_repository_top(charter, make_kb):
    kb = make_kb({f"kb/{path}": text for path, text in FILES.items()})
    run_git(kb, "init", "-q", "--initial-branch=main")
    base = commit_files(kb, {"outside.md": "x\n"}, "base")
    commit_files(kb, {"kb/notes/Archive/old.md": EDITED, "outside.md": "y\n"})

    result = _range(charter, kb, f"{base}..HEAD", "--config", "kb/charter.yaml")

    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_violations_hint_at_rewriting_the_commit(charter, make_kb):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/Archive/old.md": EDITED})

    hint = _range(charter, kb, f"{base}..HEAD").json()["diagnostics"][0]["hint"]

    assert "`Charter-Allow: paths/read-only notes/Archive/old.md — <reason>`" in hint
    assert "rebase" in hint


@pytest.mark.parametrize("revisions", ["HEAD", "HEAD~1...HEAD", "-n..HEAD", "nope..HEAD", "HEAD..a..b"])
def test_an_invalid_range_is_a_usage_error(charter, make_kb, revisions):
    kb, _ = _base(make_kb)
    commit_files(kb, {"notes/free.md": EDITED})

    result = _range(charter, kb, revisions)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/invalid-range"]
    assert f"`{revisions}`" in result.json()["diagnostics"][0]["message"]


def test_range_outside_a_git_repository_is_a_usage_error(charter, make_kb):
    kb = make_kb(FILES)

    result = _range(charter, kb, "a..b")

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/not-a-git-repository"]
    assert "--range" in result.json()["diagnostics"][0]["message"]


def test_range_excludes_the_other_target_modes(charter, make_kb):
    kb, _ = _base(make_kb)

    assert charter("validate", "--range", "HEAD..HEAD", "--staged", cwd=kb).exit_code == 2


@pytest.mark.parametrize(("folder", "code"), [("Research", "paths/create-only"), ("Archive", "paths/read-only")])
def test_a_merge_that_edits_a_file_a_parent_added_changes_it(charter, make_kb, folder, code):
    kb, base = _base(make_kb)
    path = f"notes/{folder}/side.md"
    run_git(kb, "checkout", "-q", "-b", "side")
    commit_files(kb, {path: NOTE}, f"Add it\n\nCharter-Allow: paths/read-only {path} — new\n")
    run_git(kb, "checkout", "-q", "main")
    commit_files(kb, {"notes/free.md": EDITED}, "Main moves on")
    run_git(kb, "merge", "-q", "--no-ff", "--no-commit", "side")
    merge = commit_files(kb, {path: EDITED}, "Merge side")

    result = _range(charter, kb, f"{base}..HEAD")

    merged = [d for d in result.json()["diagnostics"] if f"commit {_short(kb, merge)}" in d["message"]]
    assert [(d["path"], d["severity"], d["code"]) for d in merged] == [(path, "error", code)]
    assert "changed it" in merged[0]["message"]


def test_a_commit_that_deletes_the_contract_is_a_usage_error_naming_it(charter, make_kb):
    kb, base = _base(make_kb)
    run_git(kb, "rm", "-q", "charter.yaml")
    run_git(kb, "commit", "-q", "-m", "Drop charter")
    deleting = run_git(kb, "rev-parse", "HEAD")

    # The working copy no longer has a contract to find upward, so the range names where it was.
    result = _range(charter, kb, f"{base}..HEAD", "--config", "charter.yaml")

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/contract-deleted"]
    assert f"Commit {_short(kb, deleting)} deletes" in result.json()["diagnostics"][0]["message"]


def test_a_contract_made_invalid_by_its_template_alone_is_noticed(charter, make_kb):
    contract = CONTRACT.replace("      title: {type: string}\n", "      title: {type: string}\n    template: T/entry.md\n")
    kb, base = _base(make_kb, {**FILES, "charter.yaml": contract, "notes/T/entry.md": "# {{title}}\n"})
    commit_files(kb, {"notes/free.md": EDITED})
    broken = commit_files(kb, {"notes/T/entry.md": "---\nkind: entry\n---\n# {{title}}\n"})

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 2
    assert f"commit {_short(kb, broken)}" in result.json()["diagnostics"][0]["message"]


def _clone(tmp_path_factory, origin, *argv):
    clone = tmp_path_factory.mktemp("clone")
    run_git(clone, "clone", "-q", *argv, origin.as_uri(), ".")
    return clone


def test_a_range_reaching_past_a_shallow_clone_is_a_usage_error(charter, make_kb, tmp_path_factory):
    kb, _ = _base(make_kb)
    run_git(kb, "tag", "start")
    commit_files(kb, {"notes/Archive/old.md": EDITED})
    commit_files(kb, {"notes/free.md": EDITED})
    clone = _clone(tmp_path_factory, kb, "--depth", "1")
    run_git(clone, "fetch", "-q", "--depth", "1", "origin", "tag", "start")

    result = _range(charter, clone, "start..HEAD")

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/shallow-history"]
    assert "fetch-depth: 0" in result.json()["diagnostics"][0]["hint"]


def test_a_range_starting_outside_a_shallow_clone_is_a_usage_error(charter, make_kb, tmp_path_factory):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/free.md": EDITED})
    clone = _clone(tmp_path_factory, kb, "--depth", "1")

    result = _range(charter, clone, f"{base}..HEAD")

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/shallow-history"]


def test_a_shallow_clone_deep_enough_for_the_range_works(charter, make_kb, tmp_path_factory):
    kb, _ = _base(make_kb)
    commit_files(kb, {"notes/free.md": EDITED})
    commit_files(kb, {"notes/Archive/old.md": EDITED})
    clone = _clone(tmp_path_factory, kb, "--depth", "2")

    result = _range(charter, clone, "HEAD~1..HEAD")

    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_a_push_creating_a_branch_gets_its_own_hint(charter, make_kb):
    kb, _ = _base(make_kb)

    result = _range(charter, kb, f"{'0' * 40}..HEAD")

    assert result.exit_code == 2
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["code"] == "usage/invalid-range"
    assert "new branch" in diagnostic["message"]
    assert "default branch" in diagnostic["hint"]


def test_more_dots_are_not_called_a_symmetric_difference(charter, make_kb):
    kb, _ = _base(make_kb)

    result = _range(charter, kb, "HEAD....HEAD")

    assert "more than one" in result.json()["diagnostics"][0]["message"]


def test_an_empty_range_still_reports_an_unknown_profile(charter, make_kb):
    kb, _ = _base(make_kb)

    result = _range(charter, kb, "HEAD..HEAD", "--profile", "nope")

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/unknown-profile"]


# `%as` is what a git older than 2.25 prints for the placeholder it does not know.
@pytest.mark.parametrize("bad_date", [b"%as", b"23/10/2026"])
def test_an_author_date_that_is_not_a_day_is_a_git_failure(charter, make_kb, monkeypatch, bad_date):
    kb, base = _base(make_kb)
    commit_files(kb, {"notes/free.md": EDITED}, "Edit a free note")
    real_run = charter_git._Git.run

    def stubbed(self, *args, **kwargs):
        output = real_run(self, *args, **kwargs)
        if not any(arg.startswith("--format=%h %as") for arg in args):
            return output
        lines = output.splitlines()
        assert len(lines) == 2, "rev-list prints `commit ID`, then `NAME DATE PARENTS`, per commit"
        name, day, *parents = lines[1].split()
        assert day.count(b"-") == 2, "the stub expects git's YYYY-MM-DD here"
        return b"\n".join([lines[0], b" ".join([name, bad_date, *parents])])

    monkeypatch.setattr(charter_git._Git, "run", stubbed)

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 2
    assert _diagnostics(result) == [("charter.yaml", "error", "usage/git-failed")]
    diagnostic = result.json()["diagnostics"][0]
    assert "git 2.25" in diagnostic["message"]
    assert "Upgrade git" in diagnostic["hint"]


VENDORED_MANIFEST = ".charter/plugins/todo-free/charter-plugin.yaml"


def _with_vendored_plugin(charter, make_kb):
    """A repository whose base commit has no plugin, then a commit that vendors one; returns it and the base."""
    kb, base = _base(make_kb)
    assert charter("plugin", "add", "--dev", str(FIXTURES / "plugins" / "todo-free"), cwd=kb).exit_code == 0
    commit_files(kb, {}, "Vendor a plugin")
    return kb, base


def test_range_writes_no_plugin_out_of_a_commit(charter, make_kb, monkeypatch):
    kb, base = _with_vendored_plugin(charter, make_kb)
    commit_files(kb, {"notes/free.md": EDITED}, "Edit a free note")
    written = []
    real_directory = charter_git.GitTree.directory

    def recorded(self, path):
        written.append(path)
        return real_directory(self, path)

    # GitTree.directory is the one place a commit's files are written to disk.
    monkeypatch.setattr(charter_git.GitTree, "directory", recorded)
    result = _range(charter, kb, f"{base}..HEAD")

    assert (result.exit_code, _diagnostics(result)) == (0, [])
    assert written == []


@pytest.mark.parametrize(
    ("manifest", "problem"),
    [
        ("charter_plugin: 1\nid: todo-free\nversion: 1.2.0\n", "plugin manifest"),
        (
            'charter_plugin: 1\nid: todo-free\nversion: 1.2.0\nrun: ["python", "check.py"]\ndocs: RULES.md\n',
            "`docs` file `RULES.md` could not be read",
        ),
    ],
    ids=["manifest", "docs"],
)
def test_a_commit_with_an_invalid_plugin_manifest_is_a_contract_error_naming_it(charter, make_kb, manifest, problem):
    kb, base = _with_vendored_plugin(charter, make_kb)
    broken = commit_files(kb, {VENDORED_MANIFEST: manifest}, "Break the plugin manifest")

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 2
    diagnostics = result.json()["diagnostics"]
    assert [(d["path"], d["code"]) for d in diagnostics] == [("charter.yaml", "contract/invalid")]
    assert f"commit {_short(kb, broken)}" in diagnostics[0]["message"]
    assert problem in diagnostics[0]["message"]


def test_a_plugin_manifest_git_cannot_read_in_a_commit_is_a_git_failure(charter, make_kb):
    kb, base = _with_vendored_plugin(charter, make_kb)
    blob = run_git(kb, "rev-parse", f"HEAD:{VENDORED_MANIFEST}").strip()
    (kb / ".git" / "objects" / blob[:2] / blob[2:]).unlink()

    result = _range(charter, kb, f"{base}..HEAD")

    assert result.exit_code == 2
    assert "Traceback" not in result.stderr
    assert _diagnostics(result) == [("charter.yaml", "error", "usage/git-failed")]
    assert result.json()["diagnostics"][0]["message"].startswith("--range could not read ")
