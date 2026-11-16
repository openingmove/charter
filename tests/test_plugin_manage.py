import os
import shutil
import sys

import pytest
import yaml
from charter.install import GITIGNORE_ENTRIES
from conftest import FIXTURES, commit_files, run_git

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
NOTES = {
    "notes/a.md": "---\nkind: entry\n---\n# TODO plans\n",
    "notes/b.md": "---\nkind: entry\n---\n# Done\n",
}
INSTALLED = ".charter/plugins/todo-free"
TODO_FREE_SHA256 = "68f78f6fafd9119b4812edb8015ebfe8921c5cc49425847b7206dd05686281c4"
OTHER_MANIFEST = "charter_plugin: 1\nid: other\nversion: 0.1.0\nrun: [python, x.py]\n"


@pytest.fixture
def kb(make_kb):
    def make(contract=CONTRACT, notes=None):
        return make_kb({"charter.yaml": contract, **(NOTES if notes is None else notes)})

    return make


@pytest.fixture
def installed(charter, kb, plugin_repo):
    """A knowledge base with todo-free added from a git repository at v1.2.0; returns (base, repo)."""

    def make(contract=CONTRACT):
        base, repo = kb(contract), plugin_repo()
        result = charter("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0", cwd=base)
        assert result.exit_code == 0, result.stdout
        return base, repo

    return make


def _release(repo, version, extra=None):
    """Commits todo-free at `version` to `repo` and tags it `v<version>`."""
    manifest = (repo / "charter-plugin.yaml").read_text(encoding="utf-8").replace("1.2.0", version)
    commit = commit_files(repo, {"charter-plugin.yaml": manifest, **(extra or {})})
    run_git(repo, "tag", f"v{version}")
    return commit


def _lock(base):
    return yaml.safe_load((base / "charter.lock").read_text(encoding="utf-8"))


def _contract(base):
    return (base / "charter.yaml").read_text(encoding="utf-8")


def _local(base, plugin_id="todo-free", fixture="todo-free"):
    shutil.copytree(FIXTURES / "plugins" / fixture, base / "tools" / plugin_id)


def _codes(result):
    return [d["code"] for d in result.json()["diagnostics"]]


# --- list ---


def test_list_shows_each_plugin_with_its_version_state_and_source(charter, installed, tmp_path_factory):
    base, repo = installed(
        CONTRACT + "  banned-words:\n    source: tools/banned-words\n    enabled: false\n"
        "    with: {words: [later]}\n"
    )
    _local(base, "banned-words", "banned-words")
    working = tmp_path_factory.mktemp("work") / "other"
    working.mkdir()
    (working / "charter-plugin.yaml").write_text(OTHER_MANIFEST, encoding="utf-8")
    assert charter("plugin", "add", "--dev", str(working), cwd=base).exit_code == 0

    result = charter("plugin", "list", cwd=base)

    assert result.exit_code == 0
    assert result.stdout == (
        "banned-words  0.1.0  disabled  used in place from tools/banned-words\n"
        "other         0.1.0  enabled   a working copy, installed with --dev\n"
        f"todo-free     1.2.0  enabled   git {repo.as_posix()}@v1.2.0\n"
    )


def test_list_as_json(charter, installed):
    base, repo = installed()
    commit = run_git(repo, "rev-parse", "HEAD")

    result = charter("plugin", "list", "--format", "json", cwd=base)

    assert result.exit_code == 0
    assert result.json() == {
        "plugins": [
            {
                "id": "todo-free",
                "version": "1.2.0",
                "enabled": True,
                "source": {"git": repo.as_posix(), "ref": "v1.2.0", "commit": commit},
                "directory": INSTALLED,
            }
        ]
    }


def test_list_without_plugins(charter, kb):
    result = charter("plugin", "list", cwd=kb())

    assert (result.exit_code, result.stdout) == (0, "No plugins: no `checks.<id>` in `charter.yaml` has a `source`.\n")


def test_list_shows_a_plugin_whose_directory_is_missing_without_a_version(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: false\n")

    result = charter("plugin", "list", "--format", "json", cwd=base)

    assert result.json()["plugins"][0]["version"] is None
    assert charter("plugin", "list", cwd=base).stdout.startswith("todo-free  ?  disabled")


def test_list_works_on_a_contract_a_plugin_made_invalid(charter, kb):
    base = kb(CONTRACT + "  banned-words:\n    source: tools/banned-words\n")
    _local(base, "banned-words", "banned-words")
    assert charter("validate", cwd=base).exit_code == 2

    result = charter("plugin", "list", cwd=base)

    assert (result.exit_code, result.stdout) == (0, "banned-words  0.1.0  enabled  used in place from tools/banned-words\n")


def test_list_on_invalid_checks_is_a_usage_error(charter, make_kb):
    base = make_kb({"charter.yaml": "charter: 1\nkinds: {}\nchecks: {todo-free: {source: 1}}\n"})

    result = charter("plugin", "list", "--format", "json", cwd=base)

    assert result.exit_code == 2
    assert _codes(result) == ["contract/invalid"]


# --- info ---


def test_info_shows_the_lock_state_and_the_manifest(charter, installed):
    base, repo = installed()
    commit = run_git(repo, "rev-parse", "HEAD")

    result = charter("plugin", "info", "todo-free", "--format", "json", cwd=base)

    assert result.exit_code == 0
    assert result.json() == {
        "id": "todo-free",
        "version": "1.2.0",
        "enabled": True,
        "source": {"git": repo.as_posix(), "ref": "v1.2.0", "commit": commit},
        "directory": INSTALLED,
        "description": "Headings must not say TODO.",
        "sha256": TODO_FREE_SHA256,
        "modified": False,
        "manifest": {
            "run": ["uv", "run", "--script", "check.py"],
            "scope": "vault",
            "needs": [],
            "triggers": None,
            "hook": True,
            "timeout_ms": 10000,
        },
    }


def test_info_as_text(charter, installed):
    base, repo = installed()
    commit = run_git(repo, "rev-parse", "HEAD")
    (base / INSTALLED / "helper.py").write_text("", encoding="utf-8")

    result = charter("plugin", "info", "todo-free", cwd=base)

    assert result.exit_code == 0
    assert result.stdout == (
        "todo-free 1.2.0\n"
        "Headings must not say TODO.\n"
        "\n"
        "enabled:   yes\n"
        f"source:    git {repo.as_posix()}@v1.2.0 (commit {commit})\n"
        f"directory: {INSTALLED}\n"
        f"sha256:    {TODO_FREE_SHA256} (no longer matches the directory, so charter will not run it)\n"
        "run:       uv run --script check.py\n"
        "scope:     vault\n"
        "needs:     -\n"
        "triggers:  none: it runs on every run\n"
        "hook:      yes\n"
        "timeout:   10000 ms\n"
    )


def test_info_on_a_local_plugin_reports_its_manifest_problems(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: false\n")

    result = charter("plugin", "info", "todo-free", "--format", "json", cwd=base)

    assert result.exit_code == 0
    described = result.json()
    assert (described["source"], described["enabled"], described["version"]) == (
        {"path": "tools/todo-free"},
        False,
        None,
    )
    assert described["problems"] == ["`charter-plugin.yaml`: the file could not be read."]


def test_info_on_an_unknown_plugin_is_a_usage_error(charter, installed):
    base, _ = installed()

    result = charter("plugin", "info", "schema", "--format", "json", cwd=base)

    assert result.exit_code == 2
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["code"] == "usage/unknown-plugin"
    assert diagnostic["hint"] == "Plugins: `todo-free`."


# --- update ---


def test_update_moves_to_a_new_ref_and_refreshes_the_lock(charter, installed):
    base, repo = installed()
    commit = _release(repo, "1.3.0", {"extra.txt": "x\n"})
    contract = _contract(base)

    result = charter("plugin", "update", "todo-free", "--ref", "v1.3.0", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert "from 1.2.0 to 1.3.0" in result.stdout
    entry = _lock(base)["plugins"]["todo-free"]
    assert (entry["version"], entry["source"]) == ("1.3.0", {"git": repo.as_posix(), "ref": "v1.3.0", "commit": commit})
    assert entry["sha256"] != TODO_FREE_SHA256
    assert (base / INSTALLED / "extra.txt").exists()
    assert _contract(base) == contract
    assert charter("validate", cwd=base).exit_code == 1


def test_update_without_a_ref_fetches_the_recorded_ref_again(charter, kb, plugin_repo):
    base, repo = kb(), plugin_repo()
    charter("plugin", "add", "--from", f"{repo.as_posix()}@main", cwd=base)
    commit = _release(repo, "1.3.0")

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    entry = _lock(base)["plugins"]["todo-free"]
    assert (entry["version"], entry["source"]["ref"], entry["source"]["commit"]) == ("1.3.0", "main", commit)


def test_update_restores_a_modified_directory(charter, installed):
    base, _ = installed()
    (base / INSTALLED / "check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    assert charter("validate", cwd=base).exit_code == 3

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _lock(base)["plugins"]["todo-free"]["sha256"] == TODO_FREE_SHA256
    assert charter("validate", cwd=base).exit_code == 1


def test_update_refuses_a_ref_holding_another_plugin(charter, installed):
    base, repo = installed()
    commit_files(repo, {"charter-plugin.yaml": OTHER_MANIFEST})
    run_git(repo, "tag", "v2")
    lock = (base / "charter.lock").read_bytes()

    result = charter("plugin", "update", "todo-free", "--ref", "v2", cwd=base)

    assert result.exit_code == 1
    assert "plugin/invalid-manifest" in result.stdout
    assert "but the plugin being updated is `todo-free`" in result.stdout
    assert (base / "charter.lock").read_bytes() == lock
    assert not (base / ".charter/plugins/other").exists()
    assert (base / INSTALLED / "check.py").exists()


def test_update_to_an_unknown_ref_changes_nothing(charter, installed):
    base, _ = installed()
    lock = (base / "charter.lock").read_bytes()

    result = charter("plugin", "update", "todo-free", "--ref", "v9", cwd=base)

    assert result.exit_code == 1
    assert "plugin/fetch-failed" in result.stdout
    assert (base / "charter.lock").read_bytes() == lock


@pytest.mark.parametrize("ref", ["-v1", "a:b", ""])
def test_update_refuses_a_ref_git_would_misread(charter, installed, ref):
    base, _ = installed()

    result = charter("plugin", "update", "todo-free", f"--ref={ref}", cwd=base)

    assert result.exit_code == 2
    assert "usage/invalid-source" in result.stdout


def test_update_refuses_a_plugin_installed_from_a_working_copy(charter, kb, tmp_path_factory):
    working = tmp_path_factory.mktemp("work") / "todo-free"
    shutil.copytree(FIXTURES / "plugins" / "todo-free", working)
    base = kb()
    charter("plugin", "add", "--dev", str(working), cwd=base)

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 2
    assert "usage/not-updatable" in result.stdout
    assert "charter plugin add --dev" in result.stdout


def test_update_refuses_a_plugin_used_in_place(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n")
    _local(base)

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 2
    assert "usage/not-updatable" in result.stdout
    assert "`tools/todo-free`" in result.stdout


def test_update_of_an_unknown_plugin_is_a_usage_error(charter, kb):
    result = charter("plugin", "update", "todo-free", cwd=kb())

    assert result.exit_code == 2
    assert "usage/unknown-plugin" in result.stdout
    assert "This knowledge base has no plugins." in result.stdout


def test_update_leaves_a_disabled_plugin_disabled(charter, installed):
    base, repo = installed()
    charter("plugin", "disable", "todo-free", cwd=base)
    contract = _contract(base)
    _release(repo, "1.3.0")

    result = charter("plugin", "update", "todo-free", "--ref", "v1.3.0", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == contract
    assert _lock(base)["plugins"]["todo-free"]["version"] == "1.3.0"
    assert "It is not enabled in `charter.yaml`; `charter plugin enable todo-free` runs it." in result.stdout


def test_update_does_not_add_a_missing_checks_entry(charter, installed):
    base, repo = installed()
    (base / "charter.yaml").write_text(CONTRACT, encoding="utf-8")
    _release(repo, "1.3.0")

    result = charter("plugin", "update", "todo-free", "--ref", "v1.3.0", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == CONTRACT
    assert _lock(base)["plugins"]["todo-free"]["version"] == "1.3.0"
    assert "is not enabled" in result.stdout


def test_update_at_the_same_ref_says_it_is_already_there(charter, installed):
    base, repo = installed()

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert (result.exit_code, result.stdout) == (0, f"Plugin `todo-free` is already at 1.2.0, `{repo.as_posix()}@v1.2.0`.\n")


def test_update_at_the_same_ref_reports_restoring_a_modified_directory(charter, installed):
    base, _ = installed()
    (base / INSTALLED / "helper.py").write_text("", encoding="utf-8")

    result = charter("plugin", "update", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert f"Restored `{INSTALLED}`, which no longer matched `charter.lock`." in result.stdout
    assert not (base / INSTALLED / "helper.py").exists()


# --- failures part way: all or nothing ---


@pytest.fixture
def failing(monkeypatch):
    """Makes replacing a file named in `names` fail, and replacing one in `after_first` fail after the first time;
    with `restore_dir`, also moving a directory back to that path once a replacement has failed."""

    def make(*names, restore_dir=None, after_first=()):
        replace, rename = os.replace, os.rename
        failed, seen = [], []

        def fake_replace(source, destination):
            name = os.path.basename(destination)
            seen.append(name)
            if name in names or (name in after_first and seen.count(name) > 1):
                failed.append(name)
                raise PermissionError(13, "Permission denied")
            return replace(source, destination)

        def fake_rename(source, destination):
            if failed and restore_dir is not None and os.fspath(destination) == os.fspath(restore_dir):
                raise PermissionError(13, "Permission denied")
            return rename(source, destination)

        monkeypatch.setattr(os, "replace", fake_replace)
        monkeypatch.setattr(os, "rename", fake_rename)

    return make


def _state(base):
    return sorted((path.relative_to(base).as_posix(), path.read_bytes()) for path in base.rglob("*") if path.is_file())


def test_remove_puts_everything_back_when_the_contract_cannot_be_written(charter, installed, failing):
    base, _ = installed()
    before = _state(base)
    failing("charter.yaml")

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert "`charter.yaml` could not be written" in result.stdout
    assert _state(base) == before
    assert [p.name for p in (base / ".charter/plugins").iterdir()] == ["todo-free"]


def test_remove_keeps_the_plugin_directory_when_it_cannot_be_put_back(charter, installed, failing):
    base, _ = installed()
    lock = (base / "charter.lock").read_bytes()
    failing("charter.yaml", restore_dir=base / INSTALLED)

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    unrestored = [line for line in result.stdout.splitlines() if "could not be put back" in line]
    assert unrestored and INSTALLED in unrestored[0]
    staging = [p for p in (base / ".charter/plugins").iterdir() if p.name != "todo-free"]
    assert len(staging) == 1
    kept = staging[0] / "previous"
    assert (kept / "check.py").exists()
    assert f"`.charter/plugins/{staging[0].name}/previous`" in result.stdout
    assert (base / "charter.lock").read_bytes() == lock


def test_lock_that_cannot_be_put_back_is_reported_against_the_lock(charter, installed, failing):
    base, _ = installed()
    failing("charter.yaml", after_first=("charter.lock",))

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    reported_on_lock = result.stdout.split("\ncharter.yaml\n")[0]
    assert reported_on_lock.startswith("charter.lock\n")
    assert "`charter.lock` could not be put back" in reported_on_lock
    assert (base / INSTALLED / "check.py").exists()


def test_update_puts_everything_back_when_the_lock_cannot_be_written(charter, installed, failing):
    base, repo = installed()
    _release(repo, "1.3.0", {"extra.txt": "x\n"})
    before = _state(base)
    failing("charter.lock")

    result = charter("plugin", "update", "todo-free", "--ref", "v1.3.0", cwd=base)

    assert result.exit_code == 1
    assert "`charter.lock` could not be written" in result.stdout
    assert _state(base) == before
    assert [p.name for p in (base / ".charter/plugins").iterdir()] == ["todo-free"]


def test_add_writes_nothing_when_the_contract_cannot_be_written(charter, kb, plugin_repo, failing):
    base = kb()
    failing("charter.yaml")

    result = charter("plugin", "add", "--from", f"{plugin_repo().as_posix()}@v1.2.0", cwd=base)

    assert result.exit_code == 1
    assert not (base / "charter.lock").exists()
    assert not (base / ".charter").exists()
    assert _contract(base) == CONTRACT


# --- enable and disable ---


def test_disable_adds_enabled_false_in_the_contracts_own_style(charter, installed):
    base, _ = installed()

    result = charter("plugin", "disable", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == CONTRACT + f"  todo-free:\n    source: {INSTALLED}\n    enabled: false\n"
    assert charter("validate", cwd=base).exit_code == 0


@pytest.mark.parametrize(
    ("contract", "expected"),
    [
        (
            CONTRACT + "  todo-free: {source: tools/todo-free}\n",
            CONTRACT + "  todo-free: {source: tools/todo-free, enabled: false}\n",
        ),
        (
            "charter: 1\r\nroot: notes\r\nkinds: {entry: {}}\r\nchecks:\r\n    agents-include: {enabled: false}\r\n"
            "    todo-free:\r\n        source: tools/todo-free  # vendored by hand\r\n\r\n# The end\r\n",
            "charter: 1\r\nroot: notes\r\nkinds: {entry: {}}\r\nchecks:\r\n    agents-include: {enabled: false}\r\n"
            "    todo-free:\r\n        source: tools/todo-free  # vendored by hand\r\n        enabled: false\r\n"
            "\r\n# The end\r\n",
        ),
        (
            CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: true   # for now\n",
            CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: false   # for now\n",
        ),
    ],
    ids=["flow", "crlf-indent-comment", "in-place"],
)
def test_disable_keeps_the_rest_of_the_contract_as_written(charter, kb, contract, expected):
    base = kb(contract)
    _local(base)

    result = charter("plugin", "disable", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert (base / "charter.yaml").read_bytes().decode("utf-8") == expected


def test_enable_sets_enabled_back_to_true_in_place(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: no  # paused\n")
    _local(base)

    result = charter("plugin", "enable", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert "`checks.todo-free.enabled` to true" in result.stdout
    assert _contract(base) == CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: true  # paused\n"
    assert charter("validate", cwd=base).exit_code == 1


@pytest.mark.parametrize(("command", "state"), [("enable", "enabled"), ("disable", "disabled")])
def test_toggling_to_the_current_state_changes_nothing(charter, kb, command, state):
    enabled = "true" if command == "enable" else "false"
    contract = CONTRACT + f"  todo-free:\n    source: tools/todo-free\n    enabled: {enabled}\n"
    base = kb(contract)
    _local(base)

    result = charter("plugin", command, "todo-free", cwd=base)

    assert (result.exit_code, result.stdout) == (0, f"Plugin `todo-free` is already {state}.\n")
    assert _contract(base) == contract


def test_enable_adds_the_checks_entry_of_a_locked_plugin_without_one(charter, installed):
    base, _ = installed()
    (base / "charter.yaml").write_text(CONTRACT, encoding="utf-8")
    assert charter("plugin", "disable", "todo-free", cwd=base).stdout == "Plugin `todo-free` is already disabled.\n"

    result = charter("plugin", "enable", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == CONTRACT + f"  todo-free:\n    source: {INSTALLED}\n"


def test_disable_fixes_a_contract_the_plugin_made_invalid(charter, kb):
    base = kb(CONTRACT + "  banned-words:\n    source: tools/banned-words\n")
    _local(base, "banned-words", "banned-words")

    result = charter("plugin", "disable", "banned-words", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert charter("validate", cwd=base).exit_code == 0


def test_enable_reports_what_the_contract_still_needs(charter, kb):
    base = kb(CONTRACT + "  banned-words:\n    source: tools/banned-words\n    enabled: false\n")
    _local(base, "banned-words", "banned-words")

    result = charter("plugin", "enable", "banned-words", cwd=base)

    assert result.exit_code == 1
    assert "checks.banned-words.with: missing required key `words`." in result.stdout


@pytest.mark.parametrize("command", ["enable", "disable"])
def test_toggling_a_built_in_check_or_unknown_id_is_a_usage_error(charter, kb, command):
    base = kb()

    for check_id in ("agents-include", "nothing"):
        result = charter("plugin", command, check_id, cwd=base)

        assert result.exit_code == 2
        assert "usage/unknown-plugin" in result.stdout
    assert _contract(base) == CONTRACT


def test_disable_refuses_when_the_entry_cannot_be_edited_cleanly(charter, kb):
    contract = (
        CONTRACT + "  todo-free:\n    source: tools/todo-free\n    with:\n      intro: |\n"
        "        first\n        # part of the text, not a comment\n"
    )
    base = kb(contract)

    result = charter("plugin", "disable", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert "`checks.todo-free.enabled` could not be set in `charter.yaml`" in result.stdout
    assert _contract(base) == contract


# --- remove ---


@pytest.mark.parametrize(
    "contract",
    [
        CONTRACT,
        "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks: {agents-include: {enabled: false}}\n",
        "charter: 1\nroot: notes\nkinds:\n  entry: {}\n",
        "# Mine\ncharter: 1\r\nroot: notes\r\nchecks:\r\n    agents-include: {enabled: false}  # off\r\n\r\n"
        "# Kinds follow\r\nkinds:\r\n  entry: {}\r\n",
    ],
    ids=["block", "flow", "no-checks", "crlf-and-comments"],
)
def test_remove_undoes_add(charter, make_kb, plugin_repo, contract):
    base = make_kb({"charter.yaml": contract, **NOTES}, agents_include=True)
    assert charter("plugin", "add", "--from", f"{plugin_repo().as_posix()}@v1.2.0", cwd=base).exit_code == 0

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert (base / "charter.yaml").read_bytes().decode("utf-8") == contract
    assert not (base / INSTALLED).exists()
    assert _lock(base)["plugins"] == {}
    assert result.stdout == (
        "Removed plugin `todo-free`.\n"
        f"Deleted `{INSTALLED}` and its entry in `charter.lock`.\n"
        "Removed `checks.todo-free` from `charter.yaml`.\n"
    )


def test_remove_keeps_the_other_entries_and_their_comments(charter, installed):
    base, _ = installed()
    later = "  # Drafts come later\n  drafts: {source: tools/drafts, enabled: false}\n"
    (base / "charter.yaml").write_text(CONTRACT + f"  todo-free:\n    source: {INSTALLED}\n\n{later}", encoding="utf-8")

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == CONTRACT + f"\n{later}"


def test_remove_reports_settings_that_still_name_the_plugin(charter, installed):
    base, _ = installed()
    with_profile = "profiles:\n  review: {todo-free: warning}\n" + _contract(base)
    (base / "charter.yaml").write_text(with_profile, encoding="utf-8")
    assert charter("validate", cwd=base).exit_code == 1

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert "The contract needs attention" in result.stdout
    assert "profiles.review" in result.stdout
    assert "todo-free: warning" in _contract(base)


def test_remove_keeps_other_locked_plugins(charter, installed, plugin_repo):
    base, _ = installed()
    other = plugin_repo({"charter-plugin.yaml": OTHER_MANIFEST, "x.py": ""})
    charter("plugin", "add", "--from", f"{other.as_posix()}@v1.2.0", cwd=base)

    charter("plugin", "remove", "todo-free", cwd=base)

    assert list(_lock(base)["plugins"]) == ["other"]
    assert (base / ".charter/plugins/other/x.py").exists()
    assert "other:" in _contract(base)


def test_remove_leaves_a_plugin_used_in_place_where_it_is(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n")
    _local(base)

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert "Left `tools/todo-free` in place: charter did not install it." in result.stdout
    assert _contract(base) == CONTRACT
    assert (base / "tools/todo-free/check.py").exists()
    assert not (base / "charter.lock").exists()


def test_remove_deletes_a_locked_plugin_without_a_checks_entry(charter, installed):
    base, _ = installed()
    (base / "charter.yaml").write_text(CONTRACT, encoding="utf-8")

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert not (base / INSTALLED).exists()
    assert _lock(base)["plugins"] == {}
    assert _contract(base) == CONTRACT


def test_remove_fixes_a_contract_the_plugin_made_invalid(charter, kb, plugin_repo):
    base = kb()
    fixture = FIXTURES / "plugins" / "banned-words"
    repo = plugin_repo({path.name: path.read_bytes() for path in fixture.iterdir()})
    assert charter("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0", cwd=base).exit_code == 1

    result = charter("plugin", "remove", "banned-words", cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _contract(base) == CONTRACT
    assert charter("validate", cwd=base).exit_code == 0


def test_remove_of_an_unknown_plugin_is_a_usage_error(charter, installed):
    base, _ = installed()

    result = charter("plugin", "remove", "links", cwd=base)

    assert result.exit_code == 2
    assert "usage/unknown-plugin" in result.stdout
    assert (base / INSTALLED).exists()


def test_remove_changes_nothing_when_the_checks_entry_cannot_be_removed_cleanly(charter, installed):
    base, _ = installed()
    # Removing the entry would remove the anchor the alias refers to.
    contract = CONTRACT + f"  todo-free: &vendored\n    source: {INSTALLED}\n  copy: *vendored\n"
    (base / "charter.yaml").write_text(contract, encoding="utf-8")
    lock = (base / "charter.lock").read_bytes()

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1, result.stdout
    assert "`checks.todo-free` could not be removed from `charter.yaml`" in result.stdout
    assert (_contract(base), (base / "charter.lock").read_bytes()) == (contract, lock)
    assert (base / INSTALLED / "check.py").exists()


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions that bind the current user"
)
def test_remove_changes_nothing_when_the_lock_cannot_be_written(charter, installed):
    base, _ = installed()
    contract, lock = _contract(base), (base / "charter.lock").read_bytes()
    base.chmod(0o555)
    try:
        result = charter("plugin", "remove", "todo-free", cwd=base)
    finally:
        base.chmod(0o755)

    assert result.exit_code == 1
    assert "plugin/write-failed" in result.stdout
    assert (_contract(base), (base / "charter.lock").read_bytes()) == (contract, lock)
    assert sorted(p.name for p in (base / INSTALLED).iterdir()) == ["charter-plugin.yaml", "check.py"]
    assert [p.name for p in (base / ".charter/plugins").iterdir()] == ["todo-free"]


def _listing(base):
    return sorted(path.relative_to(base).as_posix() for path in base.rglob("*"))


def _staging(base):
    plugins = (base / INSTALLED).parent
    return [p for p in plugins.iterdir() if p.name != "todo-free"]


def _inject(monkeypatch, base, *, rename=None, replace=None):
    """Makes the `rename`-th rename inside the plugins directory, or the replace of the file named `replace`,
    do its real work and then raise KeyboardInterrupt. Returns a list that records each firing."""
    real_rename, real_replace = os.rename, os.replace
    plugins, seen, fired = os.fspath((base / INSTALLED).parent), [], []

    def renaming(source, destination):
        result = real_rename(source, destination)
        if os.fspath(source).startswith(plugins):
            seen.append(1)
            if len(seen) == rename:
                fired.append(1)
                raise KeyboardInterrupt
        return result

    def replacing(source, destination):
        result = real_replace(source, destination)
        if os.path.basename(destination) == replace and not fired:
            fired.append(1)
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(os, "rename", renaming)
    monkeypatch.setattr(os, "replace", replacing)
    return fired


# Every step of each sequence, interrupted right after it really happened.
INTERRUPTS = [
    ("add", {"rename": 1}),
    ("add", {"replace": "charter.lock"}),
    ("add", {"replace": "charter.yaml"}),
    ("update", {"rename": 1}),
    ("update", {"rename": 2}),
    ("update", {"replace": "charter.lock"}),
    ("remove", {"rename": 1}),
    ("remove", {"replace": "charter.lock"}),
    ("remove", {"replace": "charter.yaml"}),
]


@pytest.mark.parametrize(
    ("operation", "where"), INTERRUPTS, ids=[f"{o}-{next(iter(w))}-{next(iter(w.values()))}" for o, w in INTERRUPTS]
)
def test_interrupt_right_after_any_step_leaves_the_tree_as_before(
    charter, kb, installed, plugin_repo, monkeypatch, operation, where
):
    if operation == "add":
        base, repo = kb(), plugin_repo()
        # Entries written before the copy deliberately stay (see _install), so start with them in place.
        (base / ".gitignore").write_text("".join(f"{entry}\n" for entry in GITIGNORE_ENTRIES))
        argv = ("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0")
    else:
        base, repo = installed()
        _release(repo, "1.3.0", {"extra.txt": "x\n"})
        argv = ("plugin", "update", "todo-free", "--ref", "v1.3.0") if operation == "update" else ("plugin", "remove", "todo-free")
    before_listing, before_files = _listing(base), _state(base)
    fired = _inject(monkeypatch, base, **where)

    with pytest.raises(KeyboardInterrupt):
        charter(*argv, cwd=base)

    assert fired
    assert _listing(base) == before_listing
    assert _state(base) == before_files


def test_an_interrupt_during_the_undo_does_not_skip_the_other_undo_steps(charter, installed, monkeypatch):
    base, _ = installed()
    lock = (base / "charter.lock").read_bytes()
    real_rename, real_replace = os.rename, os.replace
    plugins, renames = os.fspath((base / INSTALLED).parent), []

    def renaming(source, destination):
        if os.fspath(source).startswith(plugins):
            renames.append(1)
            if len(renames) == 2:  # the first undo step, putting the plugin directory back
                raise KeyboardInterrupt
        return real_rename(source, destination)

    def replacing(source, destination):
        if os.path.basename(destination) == "charter.yaml":
            raise PermissionError(13, "Permission denied")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "rename", renaming)
    monkeypatch.setattr(os, "replace", replacing)

    result = charter("plugin", "remove", "todo-free", cwd=base)

    # The original failure is a refusal, so the undo problems are reported as diagnostics.
    assert result.exit_code == 1
    assert (base / "charter.lock").read_bytes() == lock
    assert len(_staging(base)) == 1


def test_an_interrupt_with_a_failed_undo_names_where_the_previous_copy_is_kept(charter, installed, monkeypatch):
    base, _ = installed()
    real_rename = os.rename
    plugins, renames = os.fspath((base / INSTALLED).parent), []
    interrupt = _inject(monkeypatch, base, replace="charter.lock")
    interrupting_rename = os.rename

    def renaming(source, destination):
        if os.fspath(source).startswith(plugins):
            renames.append(1)
            if len(renames) == 2:  # the undo putting the plugin directory back
                raise PermissionError(13, "Permission denied")
        return interrupting_rename(source, destination)

    monkeypatch.setattr(os, "rename", renaming)

    with pytest.raises(KeyboardInterrupt) as raised:
        charter("plugin", "remove", "todo-free", cwd=base)

    assert interrupt
    [staging] = _staging(base)
    assert any(f"`.charter/plugins/{staging.name}/previous`" in note for note in raised.value.__notes__)
    assert (staging / "previous" / "check.py").exists()


def test_both_directory_undo_steps_failing_gives_one_diagnostic_for_the_path(charter, installed, monkeypatch):
    base, repo = installed()
    _release(repo, "1.3.0", {"extra.txt": "x\n"})
    lock = (base / "charter.lock").read_bytes()
    real_replace, real_rename = os.replace, os.rename
    state = {"failed": False}

    def fake_replace(source, destination):
        if os.path.basename(destination) == "charter.lock" and not state["failed"]:
            state["failed"] = True
            raise PermissionError(13, "Permission denied")
        return real_replace(source, destination)

    def fake_rename(source, destination):
        # Once the change has failed, every directory move fails too, undo steps included.
        if state["failed"]:
            raise PermissionError(13, "Permission denied")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "replace", fake_replace)
    monkeypatch.setattr(os, "rename", fake_rename)

    result = charter("plugin", "update", "todo-free", "--ref", "v1.3.0", cwd=base)

    assert result.exit_code == 1
    reported = [line for line in result.stdout.splitlines() if f"`{INSTALLED}` could not be put back" in line]
    assert len(reported) == 1
    [staging] = _staging(base)
    assert f"`.charter/plugins/{staging.name}/previous`" in result.stdout
    assert (staging / "previous" / "check.py").exists()
    assert (base / "charter.lock").read_bytes() == lock


# --- a rollback leaves a file someone else edited meanwhile ---

EDITED = "charter: 1\nroot: notes\nkinds:\n  entry: {}\n# edited by hand meanwhile\n"


@pytest.fixture
def interrupted(monkeypatch):
    """Makes replacing `name` fail, after `edit` ran on the knowledge base (an editor saving a file); with
    `landed`, the replacement itself happens first and the failure is reported after it."""

    def make(name, edit, landed=False):
        replace = os.replace

        def fake_replace(source, destination):
            if os.path.basename(destination) != name:
                return replace(source, destination)
            if landed:
                replace(source, destination)
            edit()
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(os, "replace", fake_replace)

    return make


def _kept_staging(base):
    return [p for p in (base / ".charter/plugins").iterdir() if p.name != "todo-free"]


@pytest.mark.parametrize(
    ("name", "landed"),
    [("charter.yaml", False), ("charter.yaml", True), ("charter.lock", False), ("charter.lock", True)],
    ids=["contract-before-write", "contract-after-write", "lock-before-write", "lock-after-write"],
)
def test_rollback_leaves_a_file_edited_meanwhile_and_names_it(charter, installed, interrupted, name, landed):
    base, _ = installed()
    lock = (base / "charter.lock").read_bytes()
    interrupted(name, lambda: (base / name).write_bytes(EDITED.encode()), landed)

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert (base / name).read_text(encoding="utf-8") == EDITED
    assert f"`{name}` could not be put back as it was after the failure" in result.stdout
    assert "changed by something else" in result.stdout
    assert (base / INSTALLED / "check.py").exists()
    if name == "charter.yaml":
        assert (base / "charter.lock").read_bytes() == lock
    assert len(_kept_staging(base)) == 1


def test_rollback_leaves_the_contract_edited_before_its_write_when_the_lock_failed(charter, installed, monkeypatch):
    base, _ = installed()
    replace = os.replace

    def fake_replace(source, destination):
        if os.path.basename(destination) == "charter.lock":
            (base / "charter.yaml").write_bytes(EDITED.encode())
            raise PermissionError(13, "Permission denied")
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", fake_replace)

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert _contract(base) == EDITED
    assert "`charter.yaml` could not be put back as it was after the failure" in result.stdout
    assert (base / INSTALLED / "check.py").exists()
    assert len(_kept_staging(base)) == 1


def test_rollback_restores_the_lock_still_holding_what_this_command_wrote(charter, installed, failing):
    base, _ = installed()
    before = _state(base)
    failing("charter.yaml")

    result = charter("plugin", "remove", "todo-free", cwd=base)

    assert result.exit_code == 1
    assert "could not be put back" not in result.stdout
    assert _state(base) == before
    assert _kept_staging(base) == []
