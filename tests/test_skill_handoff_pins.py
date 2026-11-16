"""The Establish to Migrate handoff rules the skill text must keep saying.

Skills are instruction text, so a few load-bearing sentences are pinned here, one per decision or hand-off rule.
The behaviour they rely on is in test_skill_handoff_cli_facts.py.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
ESTABLISH = SKILLS / "establish"
MIGRATE = SKILLS / "migrate"
PLAN_FORMAT = ESTABLISH / "migration-plan.md"


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def _step(path, number):
    sections = re.split(r"^## ", path.read_text("utf-8"), flags=re.M)
    section = next(s for s in sections if s.startswith(f"{number}. "))
    return re.sub(r"\s+", " ", section.split("\n", 1)[1])


def _examples():
    return re.findall(r"````markdown\n(.*?)````", PLAN_FORMAT.read_text("utf-8"), re.S)


# --- structure of the example plans ---


def test_the_example_plan_has_a_created_line_per_target_and_a_source_line_per_source():
    example = _examples()[0]
    map_part = example.split("## Section map")[1].split("## Progress")[0]
    progress = example.split("## Progress")[1]

    sources = re.findall(r"^### `(.+?)`", map_part, re.M)
    targets = set(re.findall(r"^- `.+?` -> `.+?`: `(.+?)`", map_part, re.M))
    assert sources and targets and "Agreed: no" in map_part
    assert all(f"Source `{source}` checked complete" in progress for source in sources)
    assert all(f"Created `{target}`" in progress for target in targets)


def test_the_example_plan_puts_the_frontmatter_fix_before_the_dates_and_both_git_lines_record_a_start():
    examples = _examples()
    progress = examples[0].split("## Progress")[1]

    assert progress.index("add frontmatter `recipe`") < progress.index("- [ ] Date ")
    assert len(examples) == 2 and "- Source: `../docs`" in examples[1]
    for example in examples:
        assert re.search(r"^- Git: new branch from \S+ at [0-9a-f]+$", example, re.M)


# --- D1 to D4 and the hand-off rules ---


def test_establish_drafts_the_whole_plan_and_migrate_only_reviews_it():
    assert "Put `Agreed: no` on its own line" in _step(ESTABLISH / "SKILL.md", 13)
    assert "**Owner**: Establish drafts the whole plan" in _text(PLAN_FORMAT)
    assert "this step reviews and corrects them with the human" in _step(MIGRATE / "SKILL.md", 4)


def test_in_place_frontmatter_fixes_keep_the_old_text_untouched_below_the_new_block():
    plan = _text(PLAN_FORMAT)
    moving = _text(MIGRATE / "moving.md")

    assert "| add frontmatter |" in plan and "| set a field |" in plan
    assert "the completeness rule is its own: **the note's old text survives untouched below the new block.**" in moving
    assert "stop: the plan is stale, so tell the human and change nothing" in moving


def test_the_adopt_gate_reads_a_strict_run_and_the_adopted_plan_leaves_the_install_line_for_migrate():
    step2 = _step(ESTABLISH / "SKILL.md", 2)
    adopt = _text(ESTABLISH / "adopt.md")
    install = _step(MIGRATE / "SKILL.md", 7)

    assert "--all --strict --format json" in step2
    assert "never the plain exit code" in step2
    assert "Leave `Contract installed with ...` unticked" in adopt
    assert "Check that `charter.yaml` equals the draft apart from the plan-ignore line" in install
    assert "run no `charter init`" in install


def test_a_new_folder_always_writes_a_plan_whose_source_stays_read_only():
    assert "A new folder always goes to step 13" in _step(ESTABLISH / "SKILL.md", 11)
    plan = _text(PLAN_FORMAT).split("## New folder: the Source bullet")[1]
    assert "It never edits, moves or deletes anything under the source root" in plan
    assert "always ends as kept, with no question to the human" in plan
    assert "never change anything there" in _text(MIGRATE / "SKILL.md")


def test_an_existing_plan_stops_establish_before_the_adopt_offer():
    step = _step(ESTABLISH / "SKILL.md", 2)

    assert step.index("charter.migration-plan.md` exists") < step.index("charter.yaml` exists")
    assert "Establish never overwrites it" in step


def test_the_starting_point_is_recorded_and_an_undo_can_be_resumed():
    assert "read the starting point before anything switches" in _step(ESTABLISH / "SKILL.md", 7)
    way_back = _text(MIGRATE / "way-back.md")
    assert "with NAME the current branch and START and COMMIT the values the bullet gives after `from` and `at`" in way_back
    assert "Untick every line after `Section map agreed`" in way_back


def test_install_conflicts_are_settled_before_init_runs():
    establish = ESTABLISH / "SKILL.md"

    assert "`charter init` never overwrites (`init/exists`)" in _step(establish, 5)
    assert "a way back must exist before the edit:" in _step(establish, 12)
    assert "Never list the contract or the rulebook as overwritten" in _step(establish, 7)


def test_the_commit_route_is_the_two_commit_order_or_a_trailer_for_an_adopted_plan():
    step = _step(MIGRATE / "SKILL.md", 6)

    assert "commit the migrated notes first, without `charter.yaml`" in step
    assert "only route is a `Charter-Allow` trailer" in step
    assert "you never add one" in step
    assert "`usage/contract-not-staged`" in step
    assert "Never suggest bypassing a hook" in step
    assert "only route is a `Charter-Allow` trailer" in _text(ESTABLISH / "adopt.md")


# --- the minimum charter version is tied to the package ---


def test_the_minimum_version_the_skills_ask_for_is_one_the_package_can_meet():
    package = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))["version"]
    names = ["establish", "migrate", "evolve"]
    asked = {n: set(re.findall(r"needs (\d+\.\d+\.\d+) or newer", _text(SKILLS / n / "SKILL.md"))) for n in names}
    reported = {n: set(re.findall(r"reports (\d+\.\d+\.\d+) or newer", _text(SKILLS / n / "SKILL.md"))) for n in names}

    def numbers(version):
        return tuple(int(part) for part in version.split("."))

    assert package == plugin
    assert all(len(asked[n]) == 1 and asked[n] == reported[n] for n in names)
    assert len({next(iter(v)) for v in asked.values()}) == 1, "the three skills ask for different versions"
    assert all(numbers(next(iter(v))) <= numbers(package) for v in asked.values())
