"""Establish writes templates: prose pins for the skill text, CLI runs of the worked example in templates.md."""

import re
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import commit_files, run_git, write_files
from sparse_support import DRAFT, sparse_kb

ROOT = Path(__file__).resolve().parent.parent
ESTABLISH = ROOT / "skills" / "establish"
MIGRATE = ROOT / "skills" / "migrate"


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def _skill():
    return (ESTABLISH / "SKILL.md").read_text("utf-8")


def _step(number):
    sections = re.split(r"^## ", _skill(), flags=re.M)
    section = next(s for s in sections if s.startswith(f"{number}. "))
    return re.sub(r"\s+", " ", section.split("\n", 1)[1])


# --- the skill no longer contradicts itself ---


def test_the_preamble_lets_establish_write_the_template_files():
    preamble = re.sub(r"\s+", " ", _skill().split("## 1.")[0])

    assert "and the template files of step 9 (`Templates/<Kind>.md`, new files that are Establish's own)" in preamble
    assert "until step 12 or 13" in preamble
    assert "Write only the draft contract, `<folder>/charter.draft.yaml`, until" not in preamble


def test_the_limits_name_the_template_files_and_still_leave_every_note_alone():
    limits = re.sub(r"\s+", " ", _skill().split("## Limits")[1])

    assert "writes the draft, the template files of step 9, the plan and, in step 12, the files `charter init` writes, and no other file" in limits
    assert "new files in the knowledge-base folder, never changes to an existing note" in limits
    assert "never touches an existing note" in limits


def test_the_steps_are_numbered_with_templates_between_the_draft_and_approval():
    headings = re.findall(r"^## (\d+)\. (.+)$", _skill(), re.M)

    assert [(int(n), title) for n, title in headings] == [
        (1, "Check charter"),
        (2, "Pick the folder"),
        (3, "Survey"),
        (4, "Interview"),
        (5, "Put each judgement call to the human"),
        (6, "Propose the contract"),
        (7, "Choose how to write, and confirm"),
        (8, "Write the draft"),
        (9, "Settle the templates"),
        (10, "Get approval"),
        (11, "Check the files against the draft"),
        (12, "Install"),
        (13, "Hand off to Migrate"),
        (14, "Mention the layers"),
    ]


def test_every_step_reference_in_the_skill_points_at_the_step_it_means():
    skill = _text(ESTABLISH / "SKILL.md")

    assert "`charter init` generates the rulebook in step 12" in skill
    assert "fits, go to step 12; otherwise go to step 13" in skill
    assert skill.count("and go to step 14") == 2
    assert "the step 5 answers" in skill
    assert "the files `charter init` writes, and no other file" in skill
    assert "step 8" not in skill  # nothing points at the draft-writing step by number


def test_the_templates_step_asks_writes_shows_pauses_and_reruns_the_description():
    asking, step = _step(6), _step(9)

    assert "[templates.md](templates.md)" in step
    assert "whether its notes share a fixed outline" in asking
    assert '"No template" is a valid answer and is recorded' in asking
    assert "write `Templates/<Kind>.md` for each yes and name it in the kind" in step
    assert "keep the templates folder ignored by a path rule" in step
    assert "make the headings optional when the notes come from loose prose" in step
    assert "show each template as a sample note beside `charter describe --config <draft>`" in step
    assert "pause until the human has read it and edited the file if they wish" in step
    assert "rerun `charter describe --config <draft>` and fix any load error" in step
    assert "never changes an existing note" in step
    assert "the human has said they are done with the templates" in step


def test_templates_are_settled_before_the_cutoff_that_needs_them():
    step = _step(9)

    assert step.index("rerun `charter describe") < step.index("structure_cutoff")
    assert "structure_cutoff" not in _step(8)
    assert "Templates are step 9" in _step(8)


def test_approval_install_and_hand_off_account_for_the_template_files():
    assert "each kind's body outline is its template" in _step(10)
    assert "say in one line which kinds have no template" in _step(10)
    install = _step(12)
    assert "The template files from step 9 stay where they are" in install
    assert "Name the template files written in step 9" in install
    handoff = _step(13)
    assert "the template files from step 9 (`- Templates:`)" in handoff
    assert "no existing file changes before Migrate has made a way back" in handoff
    assert "The template files are new files, already written" in handoff


def test_the_template_reference_covers_ask_write_show_pause_rerun_and_the_hand_off():
    text = _text(ESTABLISH / "templates.md")

    for phrase in (
        "Ask it even when the survey found no outline",
        "\"No template\" is a valid answer",
        "Record it as a YAML comment above the kind in the draft, `# template: none, the notes share no outline`",
        "write `Templates/<Kind>.md` in the knowledge-base folder",
        "add `\"Templates/**\": {ignore: true}` under `paths:` once",
        "Make the headings optional when the notes come from loose prose",
        "Show each template to the human as a sample note",
        "do not run `charter new` to render it",
        "Then stop and wait until they say they are done",
        "Rerun until it exits 0",
        "Establish never applies a template to an existing note",
    ):
        assert phrase in text, phrase
    for cause in ("has frontmatter", "is not a field of", "follows no heading", "does not exist"):
        assert f"| `{cause}` |" in text, cause


def test_the_survey_guidance_asks_the_template_question_even_without_an_outline():
    survey = _text(ESTABLISH / "survey.md")

    assert "ask the template question for every kind even when `outline` is empty" in survey
    assert "[templates.md](templates.md)" in survey


def test_the_plan_lists_the_template_files_and_leaves_the_section_to_migrate():
    plan = _text(ESTABLISH / "migration-plan.md")
    example = re.search(r"````markdown\n(.*?)````", (ESTABLISH / "migration-plan.md").read_text("utf-8"), re.S).group(1)

    assert "- Templates: `Templates/Story.md`, `Templates/Place.md`" in example
    assert "only when step 9 of Establish wrote template files, a `- Templates: ` bullet" in plan
    assert "Migrate's clean-state check does not count them as uncommitted work" in plan
    assert "The plan does not say which template section each part of the `Section map` lands in. Migrate decides that at move time from the template" in plan


def test_migrate_treats_the_template_files_as_establishs_own_in_the_clean_state_check():
    way_back = _text(MIGRATE / "way-back.md")

    assert "git status --porcelain --ignored --untracked-files=all -- <folder>" in way_back
    assert "the plan, the draft and the template files the plan's `Templates` bullet lists" in way_back
    assert "so a file in the templates folder that Establish did not write cannot hide" in way_back


def test_migrate_sends_the_human_back_to_establish_when_a_kind_needs_a_template_and_has_none():
    step = _text(MIGRATE / "SKILL.md").split("## 2. Open the plan")[1].split("## 3.")[0]

    assert "a kind clearly needs a template and has none" in step
    assert "go back to `/charter:establish`" in step
    assert ", unless the draft records `# template: none` above that kind (the human already decided)" in step


# --- the claims, against the real CLI ---


@pytest.fixture
def kb(tmp_path):
    return sparse_kb(tmp_path)


def test_the_sparse_walkthrough_ends_with_a_template_the_draft_names_and_the_contract_loads(charter, kb):
    story = yaml.safe_load((kb / DRAFT).read_text("utf-8"))["kinds"]["story"]

    assert story["template"] == "Templates/Story.md"
    assert (kb / story["template"]).is_file()
    assert yaml.safe_load((kb / DRAFT).read_text("utf-8"))["paths"]["Templates/**"] == {"ignore": True}

    result = charter("describe", "--config", DRAFT, "story", cwd=kb)

    assert result.exit_code == 0, result.stderr
    assert "Template: `Templates/Story.md`" in result.stdout
    assert "- `## What happened` (optional)" in result.stdout


def test_charter_new_fills_the_template(charter, kb):
    result = charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)

    assert result.exit_code == 0, result.stderr
    note = (kb / "stories" / "The founding.md").read_text("utf-8")
    assert note.startswith("---\nkind: story\ntitle: The founding\n---\n# The founding\n")
    assert "## What happened <!-- optional -->" in note
    assert "{{title}}" not in note


def test_the_templates_folder_is_not_validated_as_notes(charter, kb):
    result = charter("validate", "--config", DRAFT, "--all", "--format", "json", cwd=kb)

    assert not [d for d in result.json()["diagnostics"] if d["path"].startswith("Templates/")]


def test_a_human_edit_to_the_template_reaches_the_description_and_new_notes(charter, kb):
    template = kb / "Templates" / "Story.md"
    template.write_text(template.read_text("utf-8") + "\n## Where it happened <!-- optional -->\n", encoding="utf-8")

    described = charter("describe", "--config", DRAFT, "story", cwd=kb)
    created = charter("new", "--config", DRAFT, "story", "The founding", cwd=kb)

    assert described.exit_code == 0 and created.exit_code == 0
    assert "- `## Where it happened` (optional)" in described.stdout
    assert "## Where it happened" in (kb / "stories" / "The founding.md").read_text("utf-8")


def test_a_kind_with_no_template_validates_and_charter_new_still_works(charter, kb):
    created = charter("new", "--config", DRAFT, "person", "Edmund Tarrow", cwd=kb)

    assert created.exit_code == 0, created.stderr
    assert (kb / "people" / "Edmund Tarrow.md").read_text("utf-8") == "---\nkind: person\ntitle: Edmund Tarrow\n---\n"
    validated = charter("validate", "--config", DRAFT, "--file", "people/Edmund Tarrow.md", "--format", "json", cwd=kb)
    assert validated.exit_code == 0, validated.stdout
    assert validated.json()["diagnostics"] == []
    assert "Template:" not in charter("describe", "--config", DRAFT, "person", cwd=kb).stdout


def test_the_recorded_no_template_comment_survives_into_the_installed_contract(charter, kb):
    draft = (kb / DRAFT).read_text("utf-8")
    assert "# template: none, the notes share no outline" in draft

    result = charter("init", ".", "--from", DRAFT, cwd=kb)

    assert result.exit_code == 0, result.stderr
    assert (kb / "charter.yaml").read_text("utf-8") == draft


BROKEN = {
    "frontmatter": ("---\nkind: story\n---\n# {{title}}\n", "has frontmatter"),
    "unknown placeholder": ("# {{title}}\n\n## Who {{nope}}\n", "`{{nope}}`"),
    "stray marker": ("<!-- optional -->\n# {{title}}\n", "follows no heading"),
}


@pytest.mark.parametrize("name", list(BROKEN))
def test_a_template_that_breaks_loading_is_caught_by_the_describe_rerun(charter, kb, name):
    text, complaint = BROKEN[name]
    (kb / "Templates" / "Story.md").write_text(text, encoding="utf-8")

    result = charter("describe", "--config", DRAFT, cwd=kb)

    assert result.exit_code == 2
    assert "contract/invalid" in result.stdout and "kinds.story.template" in result.stdout
    assert complaint in result.stdout


def test_a_missing_template_file_is_caught_by_the_describe_rerun(charter, kb):
    (kb / "Templates" / "Story.md").unlink()

    result = charter("describe", "--config", DRAFT, cwd=kb)

    assert result.exit_code == 2
    assert "`Templates/Story.md` does not exist" in result.stdout


def test_optional_headings_keep_loose_prose_notes_clean_and_required_ones_do_not(charter, kb):
    prose = kb / "stories" / "Prose.md"
    prose.parent.mkdir()
    prose.write_text("---\nkind: story\ntitle: Prose\n---\n# Prose\n\nJust some prose.\n", encoding="utf-8")

    optional = charter("validate", "--config", DRAFT, "--file", "stories/Prose.md", "--format", "json", cwd=kb)
    (kb / "Templates" / "Story.md").write_text("# {{title}}\n\n## What happened\n", encoding="utf-8")
    required = charter("validate", "--config", DRAFT, "--file", "stories/Prose.md", "--format", "json", cwd=kb)

    assert optional.json()["diagnostics"] == []
    assert [d["code"] for d in required.json()["diagnostics"]] == ["structure/missing-heading"]


# --- the clean-state check Migrate runs ---


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git on PATH")
def test_git_shows_a_new_templates_folder_as_one_line_unless_each_file_is_asked_for(tmp_path):
    # way-back.md passes --untracked-files=all for this reason: one folder line cannot say which files are Establish's.
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "--initial-branch=main")
    commit_files(repo, {"kb/a.md": "x\n"}, "start")
    write_files(repo, {"kb/Templates/Story.md": "# {{title}}\n", "kb/Templates/Stray.md": "# {{title}}\n", "kb/charter.draft.yaml": "charter: 1\n"})

    plain = run_git(repo, "status", "--porcelain", "--ignored", "--", "kb").splitlines()
    each = run_git(repo, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", "kb").splitlines()

    assert "?? kb/Templates/" in plain and "?? kb/Templates/Stray.md" not in plain
    assert "?? kb/Templates/Stray.md" in each and "?? kb/Templates/Story.md" in each
