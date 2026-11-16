"""The three skill-walkthrough example knowledge bases hold the facts their walkthroughs rely on.

They have no contract on purpose (Establish derives one), so they are checked through `charter survey`
and by scanning their files, never by loading a contract.
"""

import re
import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EMPTY = EXAMPLES / "empty-choir"
SPARSE = EXAMPLES / "sparse-history"
MATURE = EXAMPLES / "mature-bakery"
ALL = [EMPTY, SPARSE, MATURE]


def _survey(charter, folder, tmp_path):
    # Surveyed from a copy so a test can never touch the shipped example.
    copy = tmp_path / folder.name
    shutil.copytree(folder, copy)
    result = charter("survey", str(copy), "--format", "json", cwd=tmp_path)
    assert result.exit_code == 0, result.stderr
    return result.json()


def _field(survey, name):
    return survey["fields"][name]


def _value(survey, field, value):
    return next(item for item in _field(survey, field)["values"] if item["value"] == value)


def test_the_empty_example_holds_only_a_readme(charter, tmp_path):
    survey = _survey(charter, EMPTY, tmp_path)

    assert [entry["path"] for entry in survey["files"]] == ["README.md"]
    assert survey["totals"]["with_frontmatter"] == 0
    assert survey["fields"] == {}
    assert survey["agent_files"] == []
    assert survey["rulebooks"] == []
    assert sorted(path.name for path in EMPTY.rglob("*") if path.is_file()) == ["README.md"]


def test_the_sparse_example_has_prose_and_no_frontmatter(charter, tmp_path):
    survey = _survey(charter, SPARSE, tmp_path)

    assert survey["totals"] == {"files": 6, "folders": 2, "with_frontmatter": 0}
    assert survey["fields"] == {}
    folders = {folder["folder"]: folder["files"] for folder in survey["folders"]}
    assert folders == {".": 4, "archive": 2}
    assert survey["agent_files"] == []
    assert survey["rulebooks"] == []
    for name in ("town-history.md", "oral-histories.md", "walking-tour.md"):
        assert len((SPARSE / name).read_text(encoding="utf-8").split()) >= 400


def test_the_mature_example_is_a_consistent_vault(charter, tmp_path):
    survey = _survey(charter, MATURE, tmp_path)

    assert survey["totals"]["files"] == 26
    assert survey["totals"]["with_frontmatter"] == 23
    kinds = {item["value"]: item["count"] for item in _field(survey, "kind")["values"]}
    assert kinds == {"recipe": 7, "ingredient": 6, "supplier": 3, "bake": 3, "equipment": 2, "decision": 2}
    assert set(survey["links"]) == {"markdown", "wikilink"}
    assert survey["agent_files"] == ["AGENTS.md"]
    assert [rulebook["path"] for rulebook in survey["rulebooks"]] == ["Kitchen Rules.md"]


def _all_files_with(folder, line):
    return [
        path.relative_to(folder).as_posix()
        for path in sorted(folder.rglob("*.md"))
        if line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_the_mature_example_has_a_vocabulary_value_to_split_and_a_typo(charter, tmp_path):
    survey = _survey(charter, MATURE, tmp_path)

    draft = _value(survey, "status", "draft")
    assert draft["count"] == 4
    assert {path.split("/")[0] for path in _all_files_with(MATURE, "status: draft")} == {"recipes", "decisions"}
    typo = _value(survey, "status", "tesetd")
    assert typo["count"] == 1
    assert typo["files"] == ["recipes/Plain Baguette.md"]


def test_the_mature_example_has_undeclared_fields(charter, tmp_path):
    survey = _survey(charter, MATURE, tmp_path)

    assert _field(survey, "oven_temp_f")["files"] == 2
    assert {item["files"][0] for item in _field(survey, "oven_temp_f")["values"]} == {
        "recipes/Focaccia.md",
        "recipes/Sourdough Boule.md",
    }
    assert _field(survey, "rating")["files"] == 1


def test_the_mature_example_has_a_title_that_differs_from_its_filename(charter, tmp_path):
    survey = _survey(charter, MATURE, tmp_path)

    assert _value(survey, "title", "Rye Bread")["files"] == ["recipes/Rye Loaf.md"]
    assert "Rye Loaf" not in {item["value"] for item in _field(survey, "title")["values"]}


def test_the_split_value_is_shared_by_ordinary_and_protected_notes():
    carriers = _all_files_with(MATURE, "status: draft")

    assert len([path for path in carriers if path.startswith("recipes/")]) == 3
    protected = [path for path in carriers if path.startswith("decisions/")]
    assert protected == ["decisions/Test new recipes on Mondays.md"]
    assert "\n## Amendments (append-only)" in (MATURE / protected[0]).read_text(encoding="utf-8")


def test_the_mature_example_has_protected_decisions():
    decisions = sorted((MATURE / "decisions").glob("*.md"))

    assert len(decisions) == 2
    for decision in decisions:
        assert "\n## Amendments (append-only)" in decision.read_text(encoding="utf-8")
    assert "Amendments (append-only)" in (MATURE / "Kitchen Rules.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("folder", ALL, ids=lambda folder: folder.name)
def test_no_example_ships_a_contract(folder):
    assert not list(folder.rglob("charter.yaml"))


@pytest.mark.parametrize("folder", ALL, ids=lambda folder: folder.name)
def test_validate_without_a_contract_is_a_usage_error(charter, tmp_path, folder):
    copy = tmp_path / folder.name
    shutil.copytree(folder, copy)

    result = charter("validate", "--all", "--format", "json", cwd=copy)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["contract/not-found"]


# The examples are public: nothing in them may point at a private place. A generic check, not a deny list,
# so the check itself names nothing.
URL = re.compile(r"https?://[^\s)>\]\"']+", re.IGNORECASE)
ALLOWED_URL_HOSTS = {"example.com", "example.org"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ABSOLUTE_PATH = re.compile(r"(?<![\w.~)\]/-])(?:/(?:Users|home|var|etc|tmp|opt|mnt|srv|root)/|[A-Za-z]:[\\/])")


def _example_files():
    return sorted(path for folder in ALL for path in folder.rglob("*") if path.is_file())


@pytest.mark.parametrize("path", _example_files(), ids=lambda path: str(path.relative_to(EXAMPLES)))
def test_example_files_are_extraction_clean(path):
    text = path.read_text(encoding="utf-8")

    for url in URL.findall(text):
        host = url.split("//", 1)[1].split("/", 1)[0].lower()
        assert host in ALLOWED_URL_HOSTS, f"{path}: URL {url}"
    assert not EMAIL.search(text), f"{path}: email address"
    assert not ABSOLUTE_PATH.search(text), f"{path}: absolute filesystem path"
