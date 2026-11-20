"""The CI classifier that decides whether a pull request changes only documentation."""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".github" / "scripts" / "docs_only.py"


def classify(paths: list[str]) -> str:
    """Run the classifier as CI runs it: NUL-separated paths on stdin, as `git diff -z` writes them."""
    stdin = "".join(p + "\0" for p in paths).encode()
    result = subprocess.run([sys.executable, str(SCRIPT)], input=stdin, capture_output=True, check=True)
    return result.stdout.decode().strip()


@pytest.mark.parametrize(
    "paths",
    [
        ["docs/guide/Install.md"],
        ["images/logo.png"],
        ["README.md"],
        ["CHANGELOG.md", "docs/guide/Plugins.md", "images/a.png"],
        ["docs/guide/café.md"],
        ["docs/guide/a file with spaces.md"],
    ],
)
def test_documentation_only(paths):
    assert classify(paths) == "true"


@pytest.mark.parametrize(
    "paths",
    [
        ["src/charter/cli.py"],
        ["pyproject.toml"],
        [".github/workflows/ci.yml"],
        ["tests/README.md"],
        ["docsx/a.md"],
        ["NOTES.MD"],
        ["docs/guide/Install.md", "src/charter/cli.py"],
        [],
    ],
)
def test_anything_else(paths):
    assert classify(paths) == "false"
