import pytest
import yaml
from conftest import FIXTURES, run_git, validate_commit_msg
from hostile_names import CATALOGUE, NAMES, can_create, git_can_hold, git_tree_with_paths

from charter.globs import compile_glob
from charter.lock import content_hash

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


@pytest.mark.parametrize("name", NAMES)
def test_every_wildcard_form_matches_the_name(name):
    assert compile_glob("Locked/**").fullmatch(f"Locked/{name}")
    assert compile_glob("Locked/*").fullmatch(f"Locked/{name}")
    assert compile_glob("Locked/" + "?" * len(name)).fullmatch(f"Locked/{name}")


# Not valid UTF-8, and the spelling the output gives it.
BAD_NAME = b"notes/Locked/caf\xe9 \xff"
BAD_NAME_SHOWN = "notes/Locked/caf\\xe9 \\xff"


def _repo_editing(make_kb, paths, *, refused_ok=False):
    """A repository committing NOTE at each of `paths`, with an edit of each staged; returns it and the paths
    git refused (see `git_tree_with_paths`)."""
    kb = make_kb({"charter.yaml": CONTRACT})
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "charter.yaml")
    refused = git_tree_with_paths(kb, paths, NOTE, refused_ok=refused_ok)
    run_git(kb, "commit", "-q", "-m", "base")
    git_tree_with_paths(kb, paths, EDITED, refused_ok=refused_ok)
    return kb, refused


def _repo_holding_every_name(make_kb):
    paths = [f"notes/Locked/{param.values[0]}" for param in NAMES] + [BAD_NAME]
    # Every name git holds here: Git for Windows refuses the control characters and the reserved names.
    kb, refused = _repo_editing(make_kb, paths, refused_ok=True)
    shown = {BAD_NAME: BAD_NAME_SHOWN}
    expected = sorted(shown.get(path, path) for path in paths if path not in refused)
    return kb, expected


def _reported(result):
    assert result.exit_code == 1
    assert "Traceback" not in result.stderr
    return sorted(d["path"] for d in result.json()["diagnostics"] if d["code"] == "paths/read-only")


def test_a_read_only_policy_reports_every_name_in_the_index(charter, make_kb):
    kb, expected = _repo_holding_every_name(make_kb)

    result = validate_commit_msg(charter, kb, "Change\n")

    assert _reported(result) == expected


def test_a_read_only_policy_reports_every_name_in_a_commit_range(charter, make_kb):
    kb, expected = _repo_holding_every_name(make_kb)
    run_git(kb, "commit", "-q", "-m", "edit")

    result = charter("validate", "--range=HEAD~1..HEAD", "--profile", "ci", "--format", "json", cwd=kb)

    assert _reported(result) == expected


# --- Charter-Allow ---

SEPARATORS = {label: name for label, name in CATALOGUE if label in ("u2028", "u0085", "ff", "vt")}


@pytest.mark.parametrize("label", SEPARATORS)
def test_a_trailer_allows_the_path_with_a_line_separator_and_only_that_path(charter, make_kb, label):
    name = f"notes/Locked/{SEPARATORS[label]}"
    other = name.replace(SEPARATORS[label][1], "x")
    kb, _ = _repo_editing(make_kb, [name, other])

    result = validate_commit_msg(charter, kb, f"Fix\n\nCharter-Allow: paths/read-only {name} {chr(0x2014)} typo\n")

    found = {d["path"]: d["severity"] for d in result.json()["diagnostics"] if d["code"] == "paths/read-only"}
    assert found == {name: "warning", other: "error"}


# --- charter new ---

ZONES = """\
charter: 1
root: docs
kinds:
  zone:
    path: "Zones/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""
TOO_LONG = "new/name-too-long"


def _zones_kb(make_kb):
    return make_kb({"charter.yaml": ZONES, "docs/Zones/Old.md": "---\nkind: zone\ntitle: Old\n---\n"})


@pytest.mark.parametrize("dry_run", [[], ["--dry-run"]], ids=["real", "dry-run"])
def test_an_over_long_title_is_refused_and_nothing_is_written(charter, make_kb, tmp_path, dry_run):
    name = dict(CATALOGUE)["long"]
    if can_create(name, tmp_path):
        pytest.skip("this file system holds a name this long")
    kb = _zones_kb(make_kb)

    result = charter("new", "zone", name, *dry_run, "--format", "agent", cwd=kb)

    assert result.exit_code == 1
    assert TOO_LONG in result.stdout
    assert [p.name for p in (kb / "docs" / "Zones").iterdir()] == ["Old.md"]


@pytest.mark.parametrize("name", [param for param in NAMES if param.id != "long"])
def test_a_title_of_ordinary_length_is_never_refused_for_its_length(charter, make_kb, name):
    kb = _zones_kb(make_kb)

    result = charter("new", "zone", name, "--dry-run", "--format", "agent", cwd=kb)

    assert TOO_LONG not in result.stdout
    assert "Traceback" not in result.stderr


# --- plugin add and the content hash ---

PLUGIN_FILES = {
    path.name: path.read_bytes() for path in (FIXTURES / "plugins" / "todo-free").iterdir() if path.is_file()
}


@pytest.mark.parametrize("name", NAMES)
def test_a_plugin_holding_the_name_is_added_and_hashes_the_same_in_the_clone(
    charter, make_kb, plugin_repo, tmp_path, name
):
    if not can_create(name, tmp_path):
        pytest.skip("this file system cannot hold the name")
    if not git_can_hold(name, tmp_path):
        pytest.skip("git on this system refuses the name")
    repo = plugin_repo({**PLUGIN_FILES, f"assets/{name}": b"asset\n"})
    base = make_kb({"charter.yaml": CONTRACT, "notes/a.md": NOTE})

    result = charter("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0", cwd=base)

    assert result.exit_code == 0, result.stdout
    locked = yaml.safe_load((base / "charter.lock").read_text(encoding="utf-8"))["plugins"]["todo-free"]["sha256"]
    assert locked == content_hash(repo) == content_hash(base / ".charter" / "plugins" / "todo-free")
