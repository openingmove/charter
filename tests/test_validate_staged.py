import shutil

import pytest
from conftest import AGENTS_INCLUDE_OFF, FIXTURES, commit_files, run_git, write_files
from hostile_names import git_tree_with_paths

ENTRY = """\
charter: 1
root: notes
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""
GOOD = "---\nkind: entry\ntitle: A\n---\n"
BAD = "---\nkind: entry\n---\n"


def _codes(result):
    return [(d["path"], d["code"]) for d in result.json()["diagnostics"]]


def _staged(charter, kb, *argv):
    return charter("validate", "--staged", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _repo(make_kb, files, **options):
    kb = make_kb(files, **options)
    run_git(kb, "init", "-q", "--initial-branch=main")
    return kb


def _committed(make_kb, files, **options):
    kb = _repo(make_kb, files, **options)
    commit_files(kb, {})
    return kb


def _stage(kb, files):
    write_files(kb, files)
    run_git(kb, "add", "-A")


def test_staged_content_is_validated_not_the_working_copy(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    _stage(kb, {"notes/a.md": BAD})
    write_files(kb, {"notes/a.md": GOOD})

    staged = _staged(charter, kb)

    assert staged.exit_code == 1
    assert _codes(staged) == [("notes/a.md", "schema/required")]
    assert charter("validate", "--format", "json", cwd=kb).exit_code == 0


def test_unstaged_scratch_edits_do_not_block_a_commit(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    _stage(kb, {"notes/a.md": GOOD + "Body.\n"})
    write_files(kb, {"notes/a.md": BAD})

    staged = _staged(charter, kb)

    assert staged.exit_code == 0
    assert _codes(staged) == []


def test_only_staged_files_are_targeted(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/old.md": BAD})
    _stage(kb, {"notes/new.md": GOOD})

    assert _codes(_staged(charter, kb)) == []


def test_files_that_are_not_staged_are_not_part_of_the_knowledge_base(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    _stage(kb, {"notes/a.md": GOOD + "See [[b]].\n"})
    write_files(kb, {"notes/b.md": GOOD})

    assert _codes(_staged(charter, kb)) == [("notes/a.md", "links/unresolved")]
    assert _codes(charter("validate", "--profile", "ci", "--format", "json", cwd=kb)) == []


def test_a_repository_without_commits_validates_what_is_staged(charter, make_kb):
    kb = _repo(make_kb, {"charter.yaml": ENTRY, "notes/a.md": BAD, "notes/b.md": GOOD})
    run_git(kb, "add", "notes/a.md", "charter.yaml")

    assert _codes(_staged(charter, kb)) == [("notes/a.md", "schema/required")]


def test_staged_runs_use_the_commit_profile(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    _stage(kb, {"notes/a.md": GOOD.replace("title: A\n", "title: A\nmood: odd\n")})

    result = charter("validate", "--staged", "--format", "json", cwd=kb)

    assert result.json()["profile"] == "commit"
    assert [(d["code"], d["severity"]) for d in result.json()["diagnostics"]] == [("schema/unknown-field", "warning")]


def test_the_staged_contract_is_the_one_applied(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": BAD})
    relaxed = ENTRY.replace("title: {type: string, required: true}", "title: {type: string}")
    _stage(kb, {"charter.yaml": relaxed + AGENTS_INCLUDE_OFF})
    write_files(kb, {"charter.yaml": ENTRY + AGENTS_INCLUDE_OFF})

    assert _codes(_staged(charter, kb)) == []


def test_the_staged_template_is_the_one_applied(charter, make_kb):
    contract = ENTRY.replace("  entry:\n", "  entry:\n    template: Templates/Entry.md\n") + (
        'paths:\n  "Templates/**": {ignore: true}\n'
    )
    kb = _committed(make_kb, {"charter.yaml": contract, "notes/Templates/Entry.md": "# Title\n", "notes/a.md": GOOD})
    _stage(kb, {"notes/Templates/Entry.md": "# Title\n\n## Summary\n", "notes/a.md": GOOD + "# Title\n"})
    write_files(kb, {"notes/Templates/Entry.md": "# Title\n"})

    assert _codes(_staged(charter, kb)) == [("notes/a.md", "structure/missing-heading")]


CONTIGUOUS = """\
charter: 1
root: notes
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      id: {type: int}
    collection: {count: 3, contiguous: id}
  other:
    fields:
      kind: {type: string, required: true}
"""


def test_a_staged_deletion_touches_its_kind(charter, make_kb):
    notes = {f"notes/{n}.md": f"---\nkind: entry\nid: {n}\n---\n" for n in (1, 2, 3)}
    kb = _committed(make_kb, {"charter.yaml": CONTIGUOUS, **notes})
    run_git(kb, "rm", "-q", "notes/2.md")

    assert _codes(_staged(charter, kb)) == [("charter.yaml", "ids/count"), ("charter.yaml", "ids/gap")]


def test_a_staged_deletion_of_another_kind_leaves_a_kind_untouched(charter, make_kb):
    notes = {f"notes/{n}.md": f"---\nkind: entry\nid: {n}\n---\n" for n in (1, 3)}
    kb = _committed(make_kb, {"charter.yaml": CONTIGUOUS, **notes, "notes/x.md": "---\nkind: other\n---\n"})
    run_git(kb, "rm", "-q", "notes/x.md")

    assert _codes(_staged(charter, kb)) == []


@pytest.mark.parametrize("deleted", ["notes/Templates/t.md", "elsewhere/t.md"])
def test_deleting_a_file_the_knowledge_base_does_not_index_touches_no_kind(charter, make_kb, deleted):
    notes = {f"notes/{n}.md": f"---\nkind: entry\nid: {n}\n---\n" for n in (1, 3)}
    contract = CONTIGUOUS + 'paths:\n  "Templates/**": {ignore: true}\n'
    kb = _committed(make_kb, {"charter.yaml": contract, **notes, deleted: "---\nkind: entry\nid: 2\n---\n"})
    run_git(kb, "rm", "-q", deleted)

    assert _codes(_staged(charter, kb)) == []


def test_a_note_leaving_its_kind_touches_the_kind_it_had(charter, make_kb):
    notes = {f"notes/{n}.md": f"---\nkind: entry\nid: {n}\n---\n" for n in (1, 2, 3)}
    kb = _committed(make_kb, {"charter.yaml": CONTIGUOUS, **notes})
    _stage(kb, {"notes/2.md": "---\nkind: other\n---\n"})

    assert _codes(_staged(charter, kb)) == [("charter.yaml", "ids/count"), ("charter.yaml", "ids/gap")]


def test_a_note_turned_into_a_link_touches_the_kind_it_had(charter, make_kb):
    notes = {f"notes/{n}.md": f"---\nkind: entry\nid: {n}\n---\n" for n in (1, 2, 3)}
    kb = _committed(make_kb, {"charter.yaml": CONTIGUOUS, **notes, "notes/x.md": "---\nkind: other\n---\n"})
    _stage_link(kb, "notes/2.md", "x.md")

    assert _codes(_staged(charter, kb)) == [("charter.yaml", "ids/count"), ("charter.yaml", "ids/gap")]


def _stage_link(kb, path, target):
    """Stages a symbolic link at `path` without making one on disk, which not every OS allows."""
    target_file = kb / ".git" / "link-target"
    target_file.write_bytes(target.encode("utf-8"))
    object_id = run_git(kb, "hash-object", "-w", str(target_file))
    run_git(kb, "update-index", "--add", "--cacheinfo", f"120000,{object_id},{path}")


def test_a_staged_link_to_a_note_reads_as_that_note(charter, make_kb):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    _stage(kb, {"notes/a.md": BAD})
    _stage_link(kb, "notes/sub/b.md", "../a.md")

    assert _codes(_staged(charter, kb)) == [
        ("notes/a.md", "schema/required"),
        ("notes/sub/b.md", "schema/required"),
    ]


@pytest.mark.parametrize("target", ["missing.md", "../../outside.md", "sub"])
def test_a_staged_link_to_no_file_in_the_tree_is_left_out(charter, make_kb, target):
    kb = _committed(make_kb, {"charter.yaml": ENTRY, "outside.md": GOOD, "notes/sub/c.md": GOOD})
    _stage(kb, {"notes/a.md": GOOD + "See [[b]].\n"})
    _stage_link(kb, "notes/b.md", target)

    assert _codes(_staged(charter, kb)) == [("notes/a.md", "links/unresolved")]


def test_a_staged_agents_file_may_be_a_link_to_another(charter, make_kb):
    contract = ENTRY + "agents:\n  file: CLAUDE.md\n"
    kb = _repo(make_kb, {"charter.yaml": contract, "notes/a.md": GOOD, "AGENTS.md": AGENTS_LINK}, agents_include=True)
    assert charter("docs", cwd=kb).exit_code == 0
    commit_files(kb, {})
    _stage_link(kb, "CLAUDE.md", "AGENTS.md")

    assert _codes(_staged(charter, kb)) == []


AGENTS_LINK = "Read [CHARTER.md](CHARTER.md) first.\n"


ENTRY_WITH_AGENTS = ENTRY.replace("root: notes\n", "root: notes\nagents: {file: AGENTS.md}\n")


def _agents_kb(charter, make_kb):
    kb = _repo(make_kb, {"charter.yaml": ENTRY_WITH_AGENTS, "notes/a.md": GOOD, "AGENTS.md": AGENTS_LINK}, agents_include=True)
    assert charter("docs", cwd=kb).exit_code == 0
    commit_files(kb, {})
    return kb


def test_the_staged_agents_file_is_the_one_checked(charter, make_kb):
    kb = _agents_kb(charter, make_kb)
    _stage(kb, {"AGENTS.md": "No link here.\n"})
    write_files(kb, {"AGENTS.md": AGENTS_LINK})

    assert _codes(_staged(charter, kb)) == [("AGENTS.md", "agents-include/missing-link")]


def test_the_staged_rulebook_is_the_one_checked(charter, make_kb):
    kb = _agents_kb(charter, make_kb)
    rulebook = (kb / "CHARTER.md").read_text(encoding="utf-8")
    _stage(kb, {"CHARTER.md": rulebook + "Edited by hand.\n"})
    write_files(kb, {"CHARTER.md": rulebook})

    assert _codes(_staged(charter, kb)) == [("CHARTER.md", "agents-include/stale")]


def test_a_staged_contract_change_needs_the_rulebook_regenerated(charter, make_kb):
    kb = _agents_kb(charter, make_kb)
    relaxed = ENTRY_WITH_AGENTS.replace("title: {type: string, required: true}", "title: {type: string}")
    _stage(kb, {"charter.yaml": relaxed})
    assert charter("docs", cwd=kb).exit_code == 0

    assert _codes(_staged(charter, kb)) == [("CHARTER.md", "agents-include/stale")]


def test_staged_reads_the_index_git_names_from_the_repository_root(charter, make_kb, monkeypatch):
    kb = _committed(make_kb, {"kb/charter.yaml": ENTRY, "kb/notes/a.md": GOOD})
    write_files(kb, {"kb/notes/a.md": BAD})
    # A commit hook runs from the repository root, and may have GIT_DIR, and GIT_INDEX_FILE naming a temporary
    # index (as `git commit -a` does), relative to it.
    shutil.copyfile(kb / ".git" / "index", kb / ".git" / "next-index")
    monkeypatch.setenv("GIT_INDEX_FILE", ".git/next-index")
    monkeypatch.setenv("GIT_DIR", ".git")
    run_git(kb, "add", "kb/notes/a.md")

    result = _staged(charter, kb, "--config", "kb/charter.yaml")

    assert _codes(result) == [("notes/a.md", "schema/required")]


def test_staged_outside_a_git_repository_is_a_usage_error(charter, make_kb):
    kb = make_kb({"charter.yaml": ENTRY, "notes/a.md": GOOD})

    result = _staged(charter, kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", "usage/not-a-git-repository")]
    assert "--staged" in result.json()["diagnostics"][0]["message"]


def test_an_unstaged_contract_is_a_usage_error(charter, make_kb):
    kb = _repo(make_kb, {"charter.yaml": ENTRY, "notes/a.md": GOOD})
    run_git(kb, "add", "notes/a.md")

    result = _staged(charter, kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", "usage/contract-not-staged")]


PLUGIN_CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
PLAN = "---\nkind: entry\n---\n# Plans\n"
VENDORED = ".charter/plugins/todo-free/check.py"


def _vendored(charter, make_kb):
    kb = _repo(make_kb, {"charter.yaml": PLUGIN_CONTRACT, "notes/a.md": PLAN})
    assert charter("plugin", "add", "--dev", str(FIXTURES / "plugins" / "todo-free"), cwd=kb).exit_code == 0
    commit_files(kb, {})
    return kb


def test_an_unstaged_edit_to_a_vendored_plugin_does_not_block_a_commit(charter, make_kb):
    kb = _vendored(charter, make_kb)
    _stage(kb, {"notes/a.md": PLAN + "\nMore.\n"})
    write_files(kb, {VENDORED: "scratch\n"})

    assert ("charter.yaml", "plugin/modified") in _codes(charter("validate", "--format", "json", cwd=kb))
    assert _codes(_staged(charter, kb)) == []


def test_a_staged_edit_to_a_vendored_plugin_is_caught_though_the_working_copy_is_intact(charter, make_kb):
    kb = _vendored(charter, make_kb)
    original = (kb / VENDORED).read_bytes()
    _stage(kb, {VENDORED: original + b"# tampered\n", "notes/a.md": PLAN + "\nMore.\n"})
    write_files(kb, {VENDORED: original})

    assert _codes(charter("validate", "--format", "json", cwd=kb)) == []
    assert _codes(_staged(charter, kb)) == [("charter.yaml", "plugin/modified")]


def test_the_staged_plugin_is_the_one_run(charter, make_kb):
    contract = PLUGIN_CONTRACT + "  todo-free: {source: tools/todo-free}\n"
    kb = _repo(make_kb, {"charter.yaml": contract, "notes/a.md": PLAN})
    shutil.copytree(FIXTURES / "plugins" / "todo-free", kb / "tools" / "todo-free")
    commit_files(kb, {})
    original = (kb / "tools" / "todo-free" / "check.py").read_bytes()
    _stage(kb, {"tools/todo-free/check.py": "import sys\nsys.exit(4)\n", "notes/a.md": PLAN + "\nMore.\n"})
    write_files(kb, {"tools/todo-free/check.py": original})

    assert _codes(charter("validate", "--format", "json", cwd=kb)) == []
    assert _codes(_staged(charter, kb)) == [("charter.yaml", "plugin/failed")]


def _plugin_kb(make_kb):
    contract = PLUGIN_CONTRACT + "  todo-free: {source: tools/todo-free}\n"
    kb = _repo(make_kb, {"charter.yaml": contract, "notes/a.md": PLAN})
    shutil.copytree(FIXTURES / "plugins" / "todo-free", kb / "tools" / "todo-free")
    commit_files(kb, {})
    return kb


def _assert_plugin_failed_without_traceback(result, expected_cause):
    assert result.exit_code == 3
    assert "Traceback" not in result.stderr
    failed = [d for d in result.json()["diagnostics"] if d["code"] == "plugin/failed"]
    assert [(d["path"], d["severity"]) for d in failed] == [("charter.yaml", "error")]
    assert "`todo-free`" in failed[0]["message"]
    assert expected_cause in failed[0]["message"]
    assert "enabled: false" in failed[0]["hint"]


def test_an_error_materialising_a_staged_plugin_is_a_plugin_failure_and_the_rest_is_still_judged(
    charter, make_kb, monkeypatch
):
    kb = _plugin_kb(make_kb)
    _stage(kb, {"notes/a.md": PLAN + "\n[[missing]]\n"})

    def full_disk(self, path):
        raise OSError(28, "No space left on device")

    # GitTree.directory is the one place a staged plugin is written out.
    monkeypatch.setattr("charter.git.GitTree.directory", full_disk)
    result = _staged(charter, kb)

    _assert_plugin_failed_without_traceback(result, "No space left on device")
    assert ("notes/a.md", "links/unresolved") in _codes(result)


def _strerror_of(action):
    """The text of the OSError `action` provokes on this file system."""
    with pytest.raises(OSError) as raised:
        action()
    return raised.value.strerror


def test_a_staged_plugin_with_a_file_name_no_file_system_accepts_is_a_plugin_failure(charter, make_kb, tmp_path):
    # The index cannot hold a file and a directory of one name, so a name too long to write is the collision
    # that fails on every OS.
    long_name = "n" * 300
    cause = _strerror_of(lambda: (tmp_path / long_name).write_bytes(b""))
    kb = _plugin_kb(make_kb)
    _stage(kb, {"notes/a.md": PLAN + "\n[[missing]]\n"})
    # After `_stage`: `git add -A` would stage the entry's deletion where git finds no such file.
    git_tree_with_paths(kb, ["tools/todo-free/" + long_name])

    result = _staged(charter, kb)

    _assert_plugin_failed_without_traceback(result, cause)
    assert ("notes/a.md", "links/unresolved") in _codes(result)


def _stage_unreadable_plugin_file(kb):
    """Stages an edit to the plugin's script, then deletes the blob git would read it from."""
    _stage(kb, {"tools/todo-free/check.py": "import sys\n# edited\n", "notes/a.md": PLAN + "\nMore.\n"})
    blob = run_git(kb, "rev-parse", ":tools/todo-free/check.py")
    (kb / ".git" / "objects" / blob[:2] / blob[2:]).unlink()


def _assert_git_failed_without_traceback(result):
    assert result.exit_code == 2
    assert "Traceback" not in result.stderr
    assert _codes(result) == [("charter.yaml", "usage/git-failed")]
    assert result.json()["diagnostics"][0]["message"].startswith("--staged could not read what is staged: ")


def test_a_staged_plugin_file_git_cannot_read_is_a_git_failure(charter, make_kb):
    kb = _plugin_kb(make_kb)
    _stage_unreadable_plugin_file(kb)

    _assert_git_failed_without_traceback(_staged(charter, kb))


def test_plugin_run_on_a_staged_plugin_file_git_cannot_read_is_a_git_failure(charter, make_kb):
    kb = _plugin_kb(make_kb)
    _stage_unreadable_plugin_file(kb)

    result = charter("plugin", "run", "todo-free", "--staged", "--profile", "ci", "--format", "json", cwd=kb)

    _assert_git_failed_without_traceback(result)


def test_validate_range_over_a_plugin_that_cannot_be_written_out_does_not_crash(charter, make_kb):
    kb = _plugin_kb(make_kb)
    base = run_git(kb, "rev-parse", "HEAD").strip()
    git_tree_with_paths(kb, ["tools/todo-free/" + "n" * 300])
    run_git(kb, "commit", "-q", "-m", "Add a long name")

    result = charter("validate", f"--range={base}..HEAD", "--format", "json", cwd=kb)

    assert "Traceback" not in result.stderr
    assert result.exit_code == 0


def test_a_staged_plugin_whose_file_and_directory_differ_only_by_case_is_a_plugin_failure(charter, make_kb, tmp_path):
    (tmp_path / "Probe").write_text("x")
    if not (tmp_path / "probe").exists():
        pytest.skip("this file system tells names apart by case, so the two do not collide")
    (tmp_path / "Data").write_bytes(b"")
    cause = _strerror_of(lambda: (tmp_path / "data").mkdir(parents=True))
    kb = _plugin_kb(make_kb)
    _stage(kb, {"notes/a.md": PLAN + "\nMore.\n"})
    # After `_stage`: `git add -A` would stage the deletion of both entries, which have no working copy.
    git_tree_with_paths(kb, ["tools/todo-free/Data", "tools/todo-free/data/more"])

    _assert_plugin_failed_without_traceback(_staged(charter, kb), cause)


def _plugin_diagnostics(result):
    return [(d["path"], d["line"], d["code"], d["message"], d["hint"]) for d in result.json()["diagnostics"]]


def test_a_staged_link_in_a_vendored_plugin_is_reported_as_the_working_copy_reports_it(charter, make_kb):
    working = _vendored(charter, make_kb)
    try:
        (working / ".charter/plugins/todo-free/lib").mkdir()
        (working / ".charter/plugins/todo-free/lib/shared.py").symlink_to("../check.py")
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot create symbolic links")
    from_working_copy = charter("validate", "--format", "json", cwd=working)

    # Back to what was committed, so the same knowledge base can be staged with a link instead.
    shutil.rmtree(working / ".charter/plugins/todo-free/lib")
    _stage(working, {"notes/a.md": PLAN + "\nMore.\n"})
    _stage_link(working, ".charter/plugins/todo-free/lib/shared.py", "../check.py")
    from_index = _staged(charter, working)

    assert (from_index.exit_code, from_working_copy.exit_code) == (3, 3)
    reported = _plugin_diagnostics(from_index)
    assert [(code, "`lib/shared.py`" in message) for _, _, code, message, _ in reported] == [("plugin/modified", True)]
    assert reported == _plugin_diagnostics(from_working_copy)


def test_a_staged_link_in_a_vendored_plugin_is_found_by_its_mode_though_it_leads_nowhere(charter, make_kb):
    kb = _vendored(charter, make_kb)
    # A link to nothing in the tree is not materialised at all, so only its index entry mode can give it away.
    _stage(kb, {"notes/a.md": PLAN + "\nMore.\n"})
    _stage_link(kb, ".charter/plugins/todo-free/lib/copy.py", "missing.py")

    result = _staged(charter, kb)

    assert result.exit_code == 3
    assert [(code, "`lib/copy.py`" in message) for _, _, code, message, _ in _plugin_diagnostics(result)] == [
        ("plugin/modified", True)
    ]


def test_a_vendored_plugin_without_links_is_unchanged_by_the_link_check(charter, make_kb):
    kb = _vendored(charter, make_kb)
    _stage(kb, {"notes/a.md": PLAN + "\nMore.\n"})

    assert _codes(_staged(charter, kb)) == []
