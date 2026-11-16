"""Every tracked path must be classified in the extraction manifest, when the repository has one."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "PUBLIC-SURFACE.md"
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(public|private)\s*\|", re.MULTILINE)


def _tracked_paths():
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )
    if listing.returncode != 0:
        pytest.skip("not a git checkout")
    return [path for path in listing.stdout.split("\0") if path]


@pytest.mark.skipif(not MANIFEST.exists(), reason="no extraction manifest in this repository")
def test_every_tracked_path_has_a_classification_row():
    rows = [path.rstrip("/") for path, _ in ROW.findall(MANIFEST.read_text(encoding="utf-8"))]

    def covered(path):
        return any(path == row or path.startswith(row + "/") for row in rows)

    unclassified = sorted({path for path in _tracked_paths() if not covered(path)})

    assert unclassified == [], "add these paths to PUBLIC-SURFACE.md"
