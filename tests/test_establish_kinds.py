"""Every example kind packaged with the Establish skill loads and validates its own sample notes.

The kinds only inform the skill's proposals, so nothing else keeps them honest: a folder added under
`skills/establish/kinds/` must describe and validate clean through the CLI, as `examples/garden` does.
"""

from pathlib import Path

import pytest

KINDS = Path(__file__).resolve().parent.parent / "skills" / "establish" / "kinds"
KIND_FOLDERS = sorted(p for p in KINDS.iterdir() if p.is_dir())
EXPECTED = {"adr", "decision-record", "concept-note", "meeting-note", "glossary", "research-note"}


def test_the_packaged_kinds_cover_the_six_shapes():
    assert {p.name for p in KIND_FOLDERS} == EXPECTED


@pytest.mark.parametrize("folder", KIND_FOLDERS, ids=lambda p: p.name)
def test_a_kind_describes_its_contract(charter, folder):
    result = charter("describe", "--format", "json", cwd=folder)

    assert result.exit_code == 0, result.stderr
    assert result.json()["kinds"]


@pytest.mark.parametrize("folder", KIND_FOLDERS, ids=lambda p: p.name)
def test_a_kind_validates_its_sample_notes_clean(charter, folder):
    samples = [p for p in folder.rglob("*.md") if "Templates" not in p.relative_to(folder).parts]
    assert samples, "a kind ships at least one sample note"

    result = charter("validate", "--all", "--format", "json", cwd=folder)

    assert result.exit_code == 0, result.stdout
    assert result.json()["diagnostics"] == []
