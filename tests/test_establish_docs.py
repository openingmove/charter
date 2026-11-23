"""The Establish skill, the user manual and the example READMEs say the same thing about the same steps.

Skills and READMEs are instruction text, so these tests read them for the sentences a dry run found guessed.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESTABLISH = ROOT / "skills" / "establish"


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def test_every_manual_path_policy_with_read_only_leaves_untyped_files_allowed():
    pages = [ROOT / "README.md", *(ROOT / "docs" / "guide").glob("*.md")]
    manual = "\n".join(page.read_text("utf-8") for page in pages)
    policies = re.findall(r"^\s*\"[^\"]+\":\s*\{[^}\n]*edit: read-only[^}\n]*\}", manual, re.M)

    assert policies
    assert all("untyped: allow" in policy for policy in policies), policies


def test_the_interview_table_says_which_policy_never_changes_means():
    rows = [line for line in (ESTABLISH / "interview.md").read_text("utf-8").splitlines() if line.startswith("| never changes")]

    written_once = next(row for row in rows if "create-only" in row)
    assert "read-only" in written_once
    assert any("protected-region" in row and "amendments" in row for row in rows)
    assert not any("an edit policy or" in row for row in rows)


def test_the_install_step_names_claude_md_when_init_creates_one():
    install = _text(ESTABLISH / "SKILL.md").split("## 12. Install")[1].split("## 13.")[0]

    assert "`CLAUDE.md` when init reports creating one" in install


def _example(name):
    return _text(ROOT / "examples" / name / "README.md")


def test_the_sparse_example_hands_off_to_migrate_with_a_plan_and_a_way_back():
    sparse = _example("sparse-history")
    establish, migrate = sparse.split("**Migrate**")

    assert "charter.migration-plan.md" in establish
    assert "installs nothing" in establish
    assert "under git" not in establish
    assert "way back" in migrate
    assert "nothing beyond the expected" not in migrate


def test_the_empty_example_interviews_about_the_domain_not_fields():
    choir = _example("empty-choir")

    assert "never asks about fields" in choir
    assert "have to interview you about" not in choir
    assert "how many singers" not in choir


def test_the_mature_example_compares_titles_the_survey_already_pairs_with_files():
    bakery = _example("mature-bakery")

    assert "pairs each title with an example file" in bakery
    assert "only lists distinct titles" not in bakery
    assert "the draft ignores this README" in bakery


# --- a kind with no path cannot take notes from the section map ---

PATHLESS = "`charter new` cannot create one: it has no path."


def _step(number):
    sections = re.split(r"^## ", (ESTABLISH / "SKILL.md").read_text("utf-8"), flags=re.M)
    section = next(s for s in sections if s.startswith(f"{number}. "))
    return re.sub(r"\s+", " ", section.split("\n", 1)[1])


def test_describe_prints_the_sentence_the_skill_looks_for_on_a_kind_with_no_path(charter, tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "charter: 1\nroot: .\nkinds:\n"
        "  topic:\n    description: A topic, placed anywhere.\n"
        "  story:\n    description: A story.\n    path: \"stories/{title}.md\"\n"
        "    fields:\n      title: {type: string, required: true}\n",
        encoding="utf-8",
    )

    result = charter("describe", cwd=tmp_path)

    assert result.exit_code == 0, result.stderr
    assert result.stdout.count(PATHLESS) == 1


def test_approval_checks_every_kind_the_plan_creates_notes_for_has_a_path_before_the_yes():
    approval = _step(10)

    assert PATHLESS in approval
    assert "When step 11 will hand off to Migrate" in approval
    assert "predict the plan's `Section map` now: it is written only in step 13" in approval
    assert "every kind that the plan's `Section map` will create notes for" in approval
    assert "Migrate creates each of those notes with `charter new`" in approval
    assert "before you ask for the yes" in approval
    assert approval.index(PATHLESS) < approval.index("Ask for a yes")


def test_approval_predicts_the_hand_off_with_both_conditions_of_the_fit_check():
    approval = _step(10)

    assert "Step 11 always hands off to Migrate for a new folder." in approval
    assert "a diagnostic at severity `error` or `warning`, or a note fix on record from step 5" in approval


def test_the_section_map_names_no_target_of_a_kind_with_no_path():
    handoff = _step(13)

    assert "Name no `TARGET` of a kind that has no path" in handoff
    assert "go back to step 10" in handoff


def test_the_interview_table_moves_an_append_only_file_out_of_a_protected_folder():
    rows = [line for line in (ESTABLISH / "interview.md").read_text("utf-8").splitlines() if line.startswith("| ")]

    row = next(row for row in rows if "append" in row.split("|")[1])
    assert "`edit: create-only` or `edit: read-only`" in row
    assert "must move out of that folder" in row
    assert "no `edit:` value lifts the policy for one file" in row
    assert "An `ignore: true` rule for the file would lift it, but the file then stops being a note" in row
