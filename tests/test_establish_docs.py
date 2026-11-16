"""The Establish skill, the README and the example READMEs say the same thing about the same steps.

Skills and READMEs are instruction text, so these tests read them for the sentences a dry run found guessed.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESTABLISH = ROOT / "skills" / "establish"


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


def test_every_readme_path_policy_with_read_only_leaves_untyped_files_allowed():
    policies = re.findall(r"^\s*\"[^\"]+\":\s*\{[^}\n]*edit: read-only[^}\n]*\}", (ROOT / "README.md").read_text("utf-8"), re.M)

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
