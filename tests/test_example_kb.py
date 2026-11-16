"""The shipped example knowledge base stays valid, documented and scaffoldable."""

import shutil
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "garden"

NEW_NOTES = [
    (["grower", "Ash Keller"], "notes/Growers/Ash Keller.md"),
    (["plot", "Raised Bed"], "notes/Plots/Raised Bed.md"),
    (["crop", "Kale", "--set", "season=autumn", "--set", "plot=Sunny Bed"], "notes/Crops/Kale.md"),
    (
        ["crop/perennial", "Thyme", "--set", "season=spring", "--set", "plot=Herb Spiral", "--set", "years_to_harvest=1"],
        "notes/Crops/Perennials/Thyme.md",
    ),
    (["entry", "Seeds ordered"], "notes/Journal/3 Seeds ordered.md"),
]


@pytest.fixture
def garden(tmp_path):
    copy = tmp_path / "garden"
    shutil.copytree(EXAMPLE, copy)
    return copy


def test_the_example_validates_clean(charter):
    result = charter("validate", "--all", "--format", "json", cwd=EXAMPLE)

    assert result.exit_code == 0
    assert result.json()["diagnostics"] == []


def test_the_example_rulebook_is_up_to_date(charter):
    result = charter("docs", "--check", cwd=EXAMPLE)

    assert result.exit_code == 0


def test_the_example_agents_file_links_the_rulebook():
    assert "(CHARTER.md)" in (EXAMPLE / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("argv", "path"), NEW_NOTES, ids=[argv[0] for argv, _ in NEW_NOTES])
def test_new_creates_a_valid_note_of_every_kind(charter, garden, argv, path):
    created = charter("new", *argv, cwd=garden)

    assert created.exit_code == 0, created.stdout + created.stderr
    assert (garden / path).is_file()
    validated = charter("validate", "--all", "--format", "json", cwd=garden)
    codes = [d["code"] for d in validated.json()["diagnostics"] if d["severity"] != "info"]
    # A fresh scaffold still carries its template's guide comments; that is expected, not a defect.
    assert set(codes) <= {"residue/guide"}
