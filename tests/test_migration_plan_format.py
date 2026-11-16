"""The migration plan format and the Migrate skill agree on the lines they both name.

Skills are instruction text, so these tests read the plan format's own example and the Migrate files for what
they must say, and keep the two from drifting apart.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN_FORMAT = ROOT / "skills" / "establish" / "migration-plan.md"
MIGRATE = ROOT / "skills" / "migrate"
EVOLVE = ROOT / "skills" / "evolve"

BRANCH_LINE = re.compile(r"^- \[[ x]\] Way back made: branch `[^`]+` from `[^`]+` at `[0-9a-f]+`$")


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def _template():
    return re.search(r"````markdown\n(.*?)````", PLAN_FORMAT.read_text("utf-8"), re.S).group(1)


def test_the_example_way_back_line_has_every_value_in_backticks():
    line = next(line for line in _template().splitlines() if "Way back made" in line)

    assert BRANCH_LINE.match(line), line


def test_the_filled_in_way_back_line_in_the_skill_files_matches_the_plan_format():
    for path in (PLAN_FORMAT, MIGRATE / "way-back.md"):
        filled = re.findall(r"``(- \[x\] Way back made: .+?)``", path.read_text("utf-8"))
        assert filled, path
        assert all(BRANCH_LINE.match(line.strip()) for line in filled), path


def test_way_back_md_and_the_plan_format_give_the_same_three_shapes():
    for path in (PLAN_FORMAT, MIGRATE / "way-back.md"):
        text = path.read_text("utf-8")
        assert "branch `NAME` from `START` at `COMMIT`" in text, path
        assert "commit `COMMIT` on `START`" in text, path
        assert "snapshot `PATH`, restore with `COMMAND`" in text, path


def test_a_plan_without_a_section_map_still_has_the_agreed_line_and_migrate_ticks_it():
    plan = _text(PLAN_FORMAT)
    skill = _text(MIGRATE / "SKILL.md")

    assert "present in every plan" in plan
    assert "no `Agreed:` line" in plan
    assert "in a plan with no `Section map`, when `Section map agreed` is ticked" in skill
    assert "A plan with no `Section map` has no `Agreed:` line" in skill


def test_a_folder_that_fits_with_no_fix_is_migrate_in_place_never_leave_as_it_is():
    plan = _text(PLAN_FORMAT)

    assert "fits with no fix at all" in plan
    assert "never `leave as it is`" in plan


def test_an_ignored_templates_folder_gets_no_folders_bullet():
    plan = _text(PLAN_FORMAT)

    assert "a templates folder under `\"Templates/**\": {ignore: true}` gets none" in plan


def test_evolve_uses_the_same_backticked_way_back_shape_and_has_no_section_map_line():
    way_back = (EVOLVE / "way-back.md").read_text("utf-8")
    plan = (EVOLVE / "plan.md").read_text("utf-8")

    assert "branch `NAME` from `START` at `COMMIT`" in way_back
    assert "commit `COMMIT` on `START`" in way_back
    assert "snapshot `PATH`, restore with `COMMAND`" in way_back
    filled = re.findall(r"``(- \[x\] Way back made: .+?)``", way_back)
    assert filled
    assert all(BRANCH_LINE.match(line.strip()) for line in filled)
    line = next(line for line in plan.splitlines() if "Way back made" in line and line.startswith("- [ ]"))
    assert BRANCH_LINE.match(line)
    assert "has no `Section map agreed` line" in plan


def test_the_read_only_rule_for_left_folders_skips_the_root():
    skill = _text(MIGRATE / "SKILL.md")

    assert "each `leave as it is` folder except `.`" in skill
    assert "`./**` would match nothing" in skill


def test_moving_offers_retitle_keep_or_drop_when_the_heading_differs_from_the_title():
    moving = _text(MIGRATE / "moving.md")

    assert "differs from the note's title" in moving
    for choice in ("keep the heading line", "retitle", "drop the heading line"):
        assert choice in moving
    assert "row in the `Section map` and its `Created` line, ticked or not, and have the human confirm" in moving
