"""The composite action's entry point, run as GitHub runs it: a script reading the event payload, driving charter."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import AGENTS_INCLUDE_OFF, commit_files, run_git, write_files

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "action" / "run.py"
ZEROS = "0" * 40
CONTRACT = """\
charter: 1
root: notes
docs: {output: CHARTER.md}
paths:
  "Archive/**": {edit: read-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git on PATH")


@pytest.fixture
def kb(make_kb, charter, monkeypatch):
    scripts = Path(sys.executable).parent
    if not (scripts / ("charter.exe" if os.name == "nt" else "charter")).exists():
        pytest.skip("the charter console script is not installed next to this interpreter")
    monkeypatch.setenv("PATH", str(scripts) + os.pathsep + os.environ["PATH"])
    directory = make_kb({"charter.yaml": CONTRACT, "notes/Archive/old.md": NOTE, "notes/free.md": NOTE})
    assert charter("docs", cwd=directory).exit_code == 0
    run_git(directory, "init", "-q", "--initial-branch=main")
    commit_files(directory, {}, "base")
    return directory


def _head(kb):
    return run_git(kb, "rev-parse", "HEAD")


def _run(kb, event_name, event, tmp_path, **env):
    payload = tmp_path / "event.json"
    payload.write_text(json.dumps(event), encoding="utf-8")
    environment = {
        **os.environ,
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": str(payload),
        "CHARTER_TODAY": "2026-10-16",
        **env,
    }
    environment.pop("CI", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=kb, env=environment, capture_output=True, text=True, encoding="utf-8"
    )


def _push(before, after):
    return {"before": before, "after": after, "repository": {"default_branch": "main"}}


def _pull_request(base, head):
    return {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}


def test_a_clean_push_passes_every_check(kb, tmp_path):
    base = _head(kb)
    after = commit_files(kb, {"notes/free.md": EDITED}, "Edit a free note")

    result = _run(kb, "push", _push(base, after), tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "charter validate --all --profile ci" in result.stdout
    assert f"charter validate --range={base}..{after} --profile ci" in result.stdout
    assert "charter docs --check" in result.stdout


def test_a_push_that_edits_a_read_only_note_fails(kb, tmp_path):
    base = _head(kb)
    after = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit the archive")

    result = _run(kb, "push", _push(base, after), tmp_path)

    assert result.returncode == 1
    assert "paths/read-only" in result.stdout


def test_a_charter_allow_trailer_in_the_pushed_commit_is_honoured(kb, tmp_path):
    base = _head(kb)
    message = "Fix a typo\n\nCharter-Allow: paths/read-only notes/Archive/old.md — typo\n"
    after = commit_files(kb, {"notes/Archive/old.md": EDITED}, message)

    assert _run(kb, "push", _push(base, after), tmp_path).returncode == 0


def test_a_pull_request_checks_the_range_from_its_base_to_its_head(kb, tmp_path):
    base = _head(kb)
    head = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit the archive")

    result = _run(kb, "pull_request", _pull_request(base, head), tmp_path)

    assert result.returncode == 1
    assert f"--range={base}..{head}" in result.stdout
    assert "paths/read-only" in result.stdout


def test_a_push_that_creates_a_branch_is_checked_against_the_default_branch(kb, tmp_path):
    base = _head(kb)
    run_git(kb, "update-ref", "refs/remotes/origin/main", base)
    after = commit_files(kb, {"notes/Archive/old.md": EDITED}, "Edit the archive")

    result = _run(kb, "push", _push(ZEROS, after), tmp_path)

    assert result.returncode == 1
    assert f"--range=origin/main..{after}" in result.stdout
    assert "paths/read-only" in result.stdout


def test_a_stale_rulebook_fails_even_when_the_range_is_clean(kb, tmp_path):
    base = _head(kb)
    wider = CONTRACT + "      title: {type: string}\n"
    after = commit_files(kb, {"charter.yaml": wider}, "Add a field")

    result = _run(kb, "push", _push(base, after), tmp_path)

    assert result.returncode == 1
    assert "docs/stale" in result.stdout


def test_every_check_runs_even_after_one_fails(kb, tmp_path):
    base = _head(kb)
    after = commit_files(kb, {"notes/Archive/old.md": "---\nkind: [x]\n---\n"}, "Break a note")

    result = _run(kb, "push", _push(base, after), tmp_path)

    assert result.returncode == 1
    assert "schema/unknown-kind" in result.stdout
    assert "paths/read-only" in result.stdout
    assert "charter docs --check" in result.stdout


def test_an_event_without_commits_skips_only_the_range(kb, tmp_path):
    result = _run(kb, "workflow_dispatch", {}, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "::notice::" in result.stdout
    assert "charter validate --all" in result.stdout
    assert "charter docs --check" in result.stdout
    assert "charter validate --range" not in result.stdout


def test_a_deleted_branch_has_nothing_to_check(kb, tmp_path):
    result = _run(kb, "push", _push(_head(kb), ZEROS), tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping --range" in result.stdout


def test_a_shallow_clone_is_refused_rather_than_passed(kb, tmp_path):
    base = _head(kb)
    after = commit_files(kb, {"notes/free.md": EDITED}, "Edit a free note")
    shallow = tmp_path / "shallow"
    run_git(tmp_path, "clone", "-q", "--depth=1", kb.as_uri(), str(shallow))

    result = _run(shallow, "push", _push(base, after), tmp_path)

    assert result.returncode == 2
    assert "usage/shallow-history" in result.stdout


def test_the_config_input_selects_the_contract_to_check(kb, charter, tmp_path):
    base = _head(kb)
    sibling = {"other/charter.yaml": CONTRACT + AGENTS_INCLUDE_OFF, "other/notes/a.md": NOTE, "notes/free.md": "---\nkind: [x]\n---\n"}
    write_files(kb, sibling)
    assert charter("docs", "--config", "other/charter.yaml", cwd=kb).exit_code == 0
    after = commit_files(kb, {})
    event = _push(base, after)

    assert _run(kb, "push", event, tmp_path).returncode == 1
    selected = _run(kb, "push", event, tmp_path, CHARTER_CONFIG="other/charter.yaml")
    assert selected.returncode == 0, selected.stdout


def test_a_push_payload_without_its_commits_is_a_one_line_error(kb, tmp_path):
    result = _run(kb, "push", {"repository": {"default_branch": "main"}}, tmp_path)

    assert result.returncode == 2
    assert result.stderr.strip().count("\n") == 0
    assert "::error::" in result.stderr


def test_action_yml_installs_charter_from_its_inputs_through_the_environment():
    action = yaml.safe_load((REPO / "action.yml").read_text(encoding="utf-8"))

    assert action["runs"]["using"] == "composite"
    setup, install, run = action["runs"]["steps"]
    assert setup["uses"].startswith("astral-sh/setup-uv@")
    assert "${{" not in install["run"]
    assert install["env"] == {"CHARTER_SOURCE": "${{ inputs.source }}", "CHARTER_REF": "${{ inputs.ref }}"}
    assert "action/run.py" in run["run"]
    assert {"ref", "source", "config"} <= set(action["inputs"])


def test_the_action_recognises_the_code_charter_docs_reports_for_no_rulebook():
    from charter import docs

    assert f'NO_RULEBOOK = "{docs.NO_RULEBOOK}"' in SCRIPT.read_text(encoding="utf-8")


def test_a_contract_with_no_rulebook_skips_only_the_rulebook_check(kb, tmp_path):
    base = _head(kb)
    standalone = CONTRACT.replace("docs: {output: CHARTER.md}\n", "")
    after = commit_files(kb, {"charter.yaml": standalone, "notes/free.md": EDITED}, "Drop the rulebook")

    result = _run(kb, "push", _push(base, after), tmp_path)

    assert result.returncode == 0, result.stdout
    assert "skipping the rulebook check" in result.stdout


def test_non_ascii_charter_output_survives_a_non_utf8_locale(kb, tmp_path):
    # PYTHONIOENCODING=cp1252 with UTF-8 mode off is the Windows runner's code page; see test_cli_encoding.py.
    base = _head(kb)
    after = commit_files(kb, {"charter.yaml": CONTRACT.replace("CHARTER.md", "規則.md")}, "Rename the rulebook")

    result = _run(kb, "push", _push(base, after), tmp_path, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")

    assert result.returncode == 1
    assert "UnicodeEncodeError" not in result.stderr
    assert "規則.md" in result.stdout
