import json
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from charter.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
# Most test knowledge bases are about something other than the agent rulebook; their contracts opt out of
# the `agents-include` check so that a contract which does declare `agents:` doesn't report a missing
# AGENTS.md or CHARTER.md in every result. (Without `agents:` the check is off anyway.)
AGENTS_INCLUDE_OFF = "checks: {agents-include: {enabled: false}}\n"


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        help="rewrite expected.json files from actual output instead of comparing",
    )


@dataclass(frozen=True)
class Result:
    exit_code: int
    stdout: str
    stderr: str

    def json(self):
        return json.loads(self.stdout)


@pytest.fixture
def charter(capsys, monkeypatch):
    """Run the charter CLI in-process from `cwd`, capturing its streams."""
    for var in ("NO_COLOR", "CI", "CHARTER_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    def run(*argv, cwd):
        monkeypatch.chdir(cwd)
        exit_code = main(list(argv))
        captured = capsys.readouterr()
        return Result(exit_code, captured.out, captured.err)

    return run


@pytest.fixture
def make_kb(tmp_path):
    """Write a small knowledge base from {relative path: text} and return its directory.

    Unless `agents_include` is set, a contract without its own `checks:` gets AGENTS_INCLUDE_OFF appended
    after its last line, so line numbers stay put; a contract with `checks:` opts out itself.
    """

    def make(files, agents_include=False):
        if not agents_include:
            files = {
                relative: _without_agents_include(text) if Path(relative).name == "charter.yaml" else text
                for relative, text in files.items()
            }
        for relative, text in files.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="")
        return tmp_path

    return make


def _without_agents_include(contract):
    try:
        data = yaml.safe_load(contract)
    # PyYAML raises many exception types for odd values; an unloadable contract is the test's subject.
    except Exception:  # noqa: BLE001
        return contract
    if not isinstance(data, dict) or "checks" in data:
        return contract
    return contract + ("" if contract.endswith("\n") else "\n") + AGENTS_INCLUDE_OFF


def run_git(cwd, *args, input=None):
    settings = ["user.name=Test", "user.email=test@example.com", "commit.gpgsign=false", "core.autocrlf=false"]
    # autocrlf off: commit the fixtures' bytes as they are, whatever this machine's git would convert.
    options = [option for setting in settings for option in ("-c", setting)]
    # Bytes in, bytes out: a path that is not valid UTF-8 cannot travel as text.
    text = not isinstance(input, bytes)
    finished = subprocess.run(["git", *options, *args], cwd=cwd, check=True, capture_output=True, text=text, input=input)
    return finished.stdout.strip()


def delete_git_object(repo, object_id):
    """Deletes a loose object, so git cannot read it. Git writes objects read-only, and Windows refuses to delete a
    read-only file, so the file is made writable first."""
    path = Path(repo) / ".git" / "objects" / object_id[:2] / object_id[2:]
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.unlink()


def write_files(directory, files):
    for relative, content in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def commit_files(repo, files, message="change"):
    write_files(repo, files)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    return run_git(repo, "rev-parse", "HEAD")


COMMIT_MSG = ".git/COMMIT_EDITMSG"


def validate_commit_msg(charter, kb, message, *argv):
    """`validate --staged --commit-msg` under the `ci` profile as JSON, with `message` (text or bytes) where git
    writes it for the commit-msg hook."""
    write_files(kb, {COMMIT_MSG: message})
    return charter(
        "validate", "--staged", "--commit-msg", COMMIT_MSG, "--profile", "ci", "--format", "json", *argv, cwd=kb
    )


@pytest.fixture
def plugin_repo(tmp_path_factory):
    """A local git repository holding a plugin (the todo-free fixture unless `files` are given), tagged `tag`."""

    def make(files=None, tag="v1.2.0"):
        repo = tmp_path_factory.mktemp("plugin-repo")
        run_git(repo, "init", "-q", "--initial-branch=main")
        if files is None:
            shutil.copytree(FIXTURES / "plugins" / "todo-free", repo, dirs_exist_ok=True)
        commit_files(repo, files or {}, "plugin")
        if tag:
            run_git(repo, "tag", tag)
        return repo

    return make


@pytest.fixture
def golden(request):
    """Compare output with tests/fixtures/<case>/<name>: a JSON document, or text compared exactly."""
    update = request.config.getoption("--update-golden")

    def check(case, actual, name="expected.json"):
        expected_path = FIXTURES / case / name
        text = actual if isinstance(actual, str) else json.dumps(actual, indent=2) + "\n"
        if update:
            expected_path.write_text(text, encoding="utf-8", newline="\n")
        expected = expected_path.read_text(encoding="utf-8")
        if isinstance(actual, str):
            assert actual == expected
        else:
            assert actual == json.loads(expected)

    return check
