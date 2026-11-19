"""Establish owns the git decision, confirms before writing and offers a new folder.

Skills are instruction text, so these tests read the skill and plan-format files for what they must say. The
real run committed to main because the skill was silent about git and the agent fell back on the repository's
own CLAUDE.md; the scanner below keeps every history-changing command out of the skill files except the one
step where the human chose it.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ESTABLISH = ROOT / "skills" / "establish"
MIGRATE = ROOT / "skills" / "migrate"
PLAN_FORMAT = ESTABLISH / "migration-plan.md"


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def _step(number):
    sections = re.split(r"^## ", (ESTABLISH / "SKILL.md").read_text("utf-8"), flags=re.M)
    section = next(s for s in sections if s.startswith(f"{number}. "))
    return re.sub(r"\s+", " ", section.split("\n", 1)[1])


def _plan_section(name):
    parts = re.split(r"^## (.+)$", PLAN_FORMAT.read_text("utf-8"), flags=re.M)
    return re.sub(r"\s+", " ", dict(zip(parts[1::2], parts[2::2], strict=True))[name])


# --- no skill file changes history outside the git question ---

# Commands that write history or move it. Reads (`git status`, `git rev-parse`, `git remote`, `git branch
# --show-current`) and `git switch` (a branch the human agreed to) are not here. Wording that merely avoids the
# literal command ("the human pushes it themselves") is how Migrate talks about it.
# Git's global flags may sit between `git` and the verb (`git -C dir commit`, `git -c k=v commit`,
# `git --no-pager push`), so the pattern skips them.
HISTORY = re.compile(
    r"\bgit(?:\s+(?:-[cC]\s+\S+|--[a-z][a-z-]*(?:=\S+)?))*\s+"
    r"(?:commit|push|add|merge|rebase|reset|tag|cherry-pick|stash|am|revert)\b|--amend\b",
    re.IGNORECASE,
)


def _skill_files():
    return sorted(p for d in (ESTABLISH, MIGRATE) for p in d.rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "instruction",
    [
        "Run `git commit -m message`.",
        "then git push -u origin branch",
        "run git\n  commit afterwards",  # a line break inside the command
        "Run `git add -- file` first.",
        "git commit --amend",
        "git rebase main",
        "git reset --hard",
        "GIT PUSH",
        "git -C kb commit -m x",
        "git -c user.name=x commit -m y",
        "git --no-pager push",
        "git --git-dir=.git -C kb add -- f",
    ],
)
def test_the_history_detector_catches_history_changing_commands(instruction):
    assert HISTORY.search(re.sub(r"\s+", " ", instruction))


@pytest.mark.parametrize(
    "fine",
    [
        "Run `git rev-parse --is-inside-work-tree`.",
        "git status --porcelain --ignored",
        "git remote lists the remotes",
        "run `git switch -c <name>`",
        "Commit nothing for them.",
        "the human pushes it themselves",
        "a commit hash from git rev-parse HEAD",
        "git branch --show-current",
        "git -C kb status --porcelain",
        "git --no-pager log",
    ],
)
def test_the_history_detector_leaves_reads_and_plain_words_alone(fine):
    assert not HISTORY.search(fine)


def test_the_git_step_is_the_only_place_a_skill_file_changes_history():
    skill = (ESTABLISH / "SKILL.md").read_text("utf-8")
    # Cut out only the paragraph that carries out the human's chosen option, so what is left of every skill
    # file, the rest of step 7 included, must hold no history command at all.
    without_git_step = re.sub(r"^After the yes, .*?(?=^## 8\. )", "", skill, flags=re.M | re.S)
    assert without_git_step != skill  # the step was found and cut out
    found = []
    for path in _skill_files():
        raw = without_git_step if path == ESTABLISH / "SKILL.md" else path.read_text("utf-8")
        found += [f"{path.relative_to(ROOT)}: {m.group(0)!r}" for m in HISTORY.finditer(re.sub(r"\s+", " ", raw))]

    assert not found, "A history-changing git command sits outside Establish's git step:\n" + "\n".join(found)
    assert HISTORY.search(_step(7)), "the git step is where the human's chosen commit and push are written"
    chosen = re.search(r"^After the yes, .*?(?=^## 8\. )", skill, flags=re.M | re.S).group(0)
    assert chosen.startswith("After the yes, create the new directory")
    assert HISTORY.search(re.sub(r"\s+", " ", chosen))


def test_the_skill_owns_the_git_decision_and_the_repository_instructions_do_not_apply():
    skill = _text(ESTABLISH / "SKILL.md").split("## 1.")[0]

    assert "makes no commit and no push unless the human picked one in step 7" in skill
    assert "`CLAUDE.md` or `AGENTS.md`" in skill
    assert "does not apply to this skill's files" in skill


# --- step 7: the git question and the confirmation, before anything is written ---


def test_the_git_step_detects_with_read_only_commands_and_offers_four_options_with_no_default():
    step = _step(7)

    assert "`git rev-parse --is-inside-work-tree`" in step
    assert "`git remote`" in step
    assert "(a) a new local branch only" in step
    assert "(b) a new branch pushed to the remote, offered only when a remote is configured" in step
    assert "(c) write the files and leave them uncommitted" in step
    assert "(d) commit to the current branch" in step
    assert "never a default" in step
    assert "never recommend" in step


def test_without_a_repository_the_question_is_skipped_and_nothing_is_committed():
    step = _step(7)

    assert "Not in a repository: skip the question" in step
    assert "nothing is committed anywhere" in step


def test_the_git_step_commits_and_pushes_only_what_the_human_picked():
    step = _step(7)

    assert "(a) and (c) commit nothing" in step
    assert "(b) commits the listed files on the new branch only and pushes that branch" in step
    assert "(d) commits the listed files on the current branch and pushes nothing" in step
    assert "stage only the listed files that exist at that moment" in step
    assert "the draft deleted in step 12 was never tracked" in step
    assert "the alternative not taken was never written" in step


def test_the_confirmation_lists_every_file_with_its_path_and_waits_for_a_yes_before_any_write():
    step = _step(7)

    assert "list every file this run will create, with its path" in step
    assert "`charter.draft.yaml`" in step
    assert "`Templates/<Kind>.md`" in step
    assert "`charter.migration-plan.md`" in step
    assert "`charter.yaml`" in step and "`CHARTER.md`" in step and "`AGENTS.md`" in step
    assert "together with the git answer" in step
    assert "wait for the human's yes" in step
    assert "A no, or no answer, stops the run with nothing written" in step
    assert "no directory and no branch" in step


def test_the_confirmation_step_comes_before_every_step_that_writes():
    headings = re.findall(r"^## (\d+)\. (.+)$", (ESTABLISH / "SKILL.md").read_text("utf-8"), re.M)
    titles = {int(n): title for n, title in headings}

    assert titles[6] == "Propose the contract"
    assert titles[7] == "Choose how to write, and confirm"
    assert titles[8] == "Write the draft"
    assert titles[9] == "Settle the templates"
    assert "write no file yet" in _step(6)
    assert "the template question" in _step(6) and "which fixes the list of files step 7 shows" in _step(6)


def test_the_preamble_writes_nothing_before_the_yes():
    preamble = _text(ESTABLISH / "SKILL.md").split("## 1.")[0]

    assert "Write nothing before the human's yes in step 7" in preamble


# --- step 2: the new-folder question ---


def test_step_two_asks_existing_folder_or_a_new_one_and_leaves_the_existing_documents_alone():
    step = _step(2)

    assert "build the knowledge base in the existing folder, or in a NEW folder, leaving the existing documents where they are" in step
    assert "Ask for its name" in step
    assert "read-only source" in step
    assert "step 7 creates the new directory after the human's yes" in step
    assert "ask for another" in step


def test_the_new_folder_question_says_a_plan_carries_the_old_documents_in_and_the_existing_folder_is_never_changed():
    step = _step(2)

    assert "In a new folder, Establish writes a plan that sends the old documents you pick into the new folder" in step
    assert "`/charter:migrate` carries it out by copying them into notes; the existing folder is never changed" in step
    assert "If the human wants nothing brought in, the plan holds only the install lines" in step
    assert "not automated" not in step


def test_the_survey_reads_the_existing_folder_even_when_the_knowledge_base_is_new():
    step = _step(3)

    assert "charter survey <source> --format json" in step
    assert "the existing folder" in step


def test_a_new_folder_always_writes_a_plan_and_never_installs_directly():
    assert "A new folder always goes to step 13, even with nothing to bring in, because the plan carries the install." in _step(11)
    assert "A new folder always takes the second alternative: its old documents are what the plan carries over." in _step(7)
    install = _step(12)
    assert "new folder" not in install
    assert "no plan is written" not in install
    assert "Migrate does not do yet" not in _text(ESTABLISH / "SKILL.md")


def test_the_hand_off_for_a_new_folder_records_the_source_and_leaves_the_existing_folder_read_only():
    handoff = _step(13)

    assert "`- Git:`" in handoff
    assert "For a new folder, the plan's `Draft contract` also holds `- Source:`, the existing folder as a path from `<folder>`" in handoff
    assert "The plan has no `migrate in place` folder and no `Note fixes`" in handoff
    assert "the existing folder stays untouched as a read-only source, which Migrate reads and never changes" in handoff


def test_install_and_hand_off_make_the_commit_only_when_step_seven_says_so():
    assert "the commit step 7 describes" in _step(12)
    assert "the commit step 7 describes" in _step(13)
    limits = _text(ESTABLISH / "SKILL.md").split("## Limits")[1]
    assert "no commit and no push beyond the human's answer in step 7" in limits
    assert "never writes into the existing folder when the human chose a new one" in limits


# --- the plan grammar ---


def test_the_plan_example_shows_the_git_bullet_under_draft_contract():
    example = re.search(r"````markdown\n(.*?)````", PLAN_FORMAT.read_text("utf-8"), re.S).group(1)
    draft_contract = example.split("## Draft contract")[1].split("## Folders")[0]

    assert "- Git: new branch" in draft_contract
    assert "Target" not in draft_contract


def test_the_plan_grammar_documents_the_git_bullet_with_its_five_values():
    section = _plan_section("`## Draft contract`")

    assert "`- Git: `" in section
    for value in ("`new branch`", "`new branch pushed`", "`uncommitted`", "`commit to current branch`", "`no repository`"):
        assert value in section, value
    assert "A plan without a `Git` bullet" in section and "means ask now" in section
    assert "Establish has already created and switched to that branch" in section


# --- Migrate follows the recorded answer ---


def test_migrate_reads_the_recorded_git_answer_and_does_not_ask_the_branch_question_again():
    skill = _text(MIGRATE / "SKILL.md").split("## 3. Make a way back")[1].split("## 4.")[0]
    way_back = _text(MIGRATE / "way-back.md")

    assert "`- Git:` bullet" in skill
    assert "so do not ask the branch question again" in way_back
    for value in ("`new branch` or `new branch pushed`", "`uncommitted`", "`commit to current branch`", "`no repository`"):
        assert value in way_back, value


def test_migrate_stays_on_the_branch_establish_made_and_creates_no_second_one():
    way_back = _text(MIGRATE / "way-back.md")

    assert "Establish already made that branch and switched to it, so the current branch is the one to stay on" in way_back
    assert "Create no second branch and ask for no name" in way_back
    assert "Fill in the line as `` branch `NAME` from `START` at `COMMIT` ``, with NAME the current branch and START and COMMIT the values the bullet gives after `from` and `at`" in way_back
    assert "A bullet without them (an older plan) gives `` commit `COMMIT` on `START` `` instead, with START the current branch" in way_back
    assert "Git, on a new branch (Migrate's own, or Establish's, per the plan's `Git` bullet): `git switch <starting branch>`" in way_back
    assert "asking the human only for the name" not in way_back
    assert "Target" not in _text(MIGRATE / "SKILL.md")


def test_migrate_commits_and_pushes_nothing_whatever_the_recorded_answer_is():
    way_back = _text(MIGRATE / "way-back.md")
    skill = _text(MIGRATE / "SKILL.md")

    assert "In every case Migrate commits nothing and pushes nothing" in way_back
    assert "creates a branch only when the human said yes to the offer (a recorded `new branch` or `new branch pushed` means Establish already made it)" in skill


def test_a_plan_with_no_git_bullet_still_works_because_migrate_asks_now():
    way_back = _text(MIGRATE / "way-back.md")

    assert "No `Git` bullet (a plan from an older run): offer a new branch for the migration and let the human name it or decline" in way_back


def test_the_manual_describes_the_new_folder_question_the_git_question_and_the_confirmation():
    skills = _text(ROOT / "docs" / "guide" / "Skills.md")
    establish = skills.split("- **Establish** (`/charter:establish`)")[1].split("- **Migrate**")[0]

    assert "in the existing folder or a new one" in establish
    assert "never a default" in establish
    assert "waiting for your yes" in establish
    assert "lists every file it will create, waiting for your yes" in establish

