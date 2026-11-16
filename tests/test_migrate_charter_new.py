"""Migrate makes every new note with `charter new`: prose pins, and what `charter new` does on the sparse example, run through the CLI."""

import re
from pathlib import Path

import pytest
from sparse_support import DRAFT, sparse_kb

MIGRATE = Path(__file__).resolve().parent.parent / "skills" / "migrate"


def _section(path, heading):
    sections = re.split(r"^## ", path.read_text("utf-8"), flags=re.M)
    section = next(s for s in sections if s.split("\n", 1)[0] == heading)
    return re.sub(r"\s+", " ", section)


# --- the rule is where an agent reads first ---


def test_step_5_says_every_new_note_is_made_with_charter_new_and_prose_comes_after():
    step = _section(MIGRATE / "SKILL.md", "5. Move the content")

    assert 'Make every new note with `charter new --config <draft> KIND "TITLE"`' in step
    assert "never by writing the file yourself" in step
    assert "Add the prose after what it wrote" in step


def test_the_limits_forbid_a_hand_written_created_note_but_not_note_fixes_or_renames():
    limits = _section(MIGRATE / "SKILL.md", "Limits")

    assert "never writes a new note for a `Created` line other than with `charter new`" in limits
    assert "never overwrites a file at a `Created` line's target that `charter new` did not make" in limits
    assert "Note fixes and the rename move of an existing note are not new notes; they follow moving.md" in limits


# --- the moving reference ---


def test_a_created_line_is_ticked_only_after_charter_new_printed_the_target_or_reported_new_exists():
    created = _section(MIGRATE / "moving.md", "`Created TARGET`")

    assert "Done when `charter new` printed `TARGET` (or reported `new/exists` for it on resume" in created
    assert "Tick the line only then: a note you wrote any other way does not count" in created


def test_a_file_charter_new_did_not_make_is_compared_by_validation_and_never_overwritten():
    created = _section(MIGRATE / "moving.md", "`Created TARGET`")

    assert "reports `new/exists` (it exits 1), run `charter validate --config <draft> --file TARGET`" in created
    assert "A file with a `schema` or `filenames` finding" in created
    assert "was not made by `charter new` from this draft, or was broken after it did: tell the human what the validation reports and do not overwrite, move or delete it" in created
    assert "leave the line unticked" in created


def test_validation_cannot_prove_who_wrote_a_file_so_a_resumed_body_is_checked_against_the_template():
    created = _section(MIGRATE / "moving.md", "`Created TARGET`")

    assert "validation cannot prove who wrote it" in created
    assert "when its body is not the template's body plus the prose of the earlier parts, tell the human and ask before adding anything" in created


# --- what `charter new` and single-file validation do on the sparse example (the facts the skill text relies on) ---


@pytest.fixture
def kb(tmp_path):
    return sparse_kb(tmp_path)


def _codes(charter, kb, target):
    result = charter("validate", "--config", DRAFT, "--file", target, "--format", "json", cwd=kb)
    assert result.exit_code in (0, 1), result.stderr
    return [d["code"] for d in result.json()["diagnostics"] if d["path"] == target]


def test_charter_new_prints_the_path_the_created_line_is_ticked_against(charter, kb):
    result = charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)

    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("Created `stories/The founding.md` (story).")


def test_a_created_story_is_clean_once_its_guide_comment_is_followed_and_removed(charter, kb):
    target = "stories/The founding.md"
    charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)
    note = kb / target

    assert _codes(charter, kb, target) == ["residue/guide"]
    filled = note.read_text("utf-8").replace("## What happened <!-- optional -->\n", "## What happened <!-- optional -->\nThe mill opened.\n")
    note.write_text(re.sub(r"<!-- guide:.*-->\n", "", filled), encoding="utf-8")

    assert _codes(charter, kb, target) == []


def test_a_second_run_reports_new_exists_with_exit_1_and_leaves_the_note_as_it_was(charter, kb):
    charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)
    note = kb / "stories" / "The founding.md"
    note.write_text(note.read_text("utf-8") + "Half moved.\n", encoding="utf-8")
    before = note.read_bytes()

    again = charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)

    assert again.exit_code == 1
    assert "new/exists" in again.stdout
    assert note.read_bytes() == before


@pytest.mark.parametrize(
    ("target", "text", "code"),
    [
        ("stories/The founding.md", "Written by hand, no frontmatter.\n", "schema/missing-frontmatter"),
        ("stories/Sideways.md", "---\nkind: person\ntitle: Sideways\n---\nWritten by hand.\n", "filenames/path"),
    ],
    ids=["no frontmatter", "another kind"],
)
def test_an_unknown_existing_file_is_untouched_and_validation_names_the_mismatch(charter, kb, target, text, code):
    path = kb / target
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    title = Path(target).stem

    result = charter("new", "--config", DRAFT, "story", title, cwd=kb)

    assert result.exit_code == 1
    assert "new/exists" in result.stdout
    assert path.read_text("utf-8") == text
    assert code in _codes(charter, kb, target)


def test_a_hand_written_file_with_matching_frontmatter_passes_validation_so_only_the_body_check_can_tell_it_apart(charter, kb):
    target = "people/Edmund Tarrow.md"
    text = "---\nkind: person\ntitle: Edmund Tarrow\n---\nWritten by hand, not by charter new.\n"
    (kb / "people").mkdir()
    (kb / target).write_text(text, encoding="utf-8")

    result = charter("new", "--config", DRAFT, "person", "Edmund Tarrow", cwd=kb)

    assert result.exit_code == 1
    assert "new/exists" in result.stdout
    assert (kb / target).read_text("utf-8") == text
    assert _codes(charter, kb, target) == []
