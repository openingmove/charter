import json
import os
import shutil

import pytest

from conftest import FIXTURES, write_files

GARDEN = FIXTURES / "survey" / "garden"
IGNORED = "---\nkind: ignored\n---\nVersion-control state.\n"


@pytest.fixture
def garden(tmp_path):
    """The fixture knowledge base copied somewhere with no contract above it, plus the `.git` a fixture cannot hold."""
    kb = tmp_path / "garden"
    shutil.copytree(GARDEN, kb)
    write_files(kb, {".git/ignored.md": IGNORED})
    return kb


def _snapshot(folder):
    return {
        path.relative_to(folder).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_json_survey_matches_golden(charter, golden, garden):
    result = charter("survey", str(garden), "--format", "json", cwd=garden.parent)

    assert result.exit_code == 0
    assert result.stderr == ""
    assert next(iter(result.json())) == "format"
    golden("survey", result.json())


def test_output_is_deterministic_and_machine_independent(charter, garden):
    first = charter("survey", str(garden), "--format", "json", cwd=garden.parent)
    second = charter("survey", ".", "--format", "json", cwd=garden)

    assert first.stdout == second.stdout
    assert str(garden) not in first.stdout
    assert "\\" not in first.stdout.replace("\\n", "")


def test_survey_surfaces_drift_and_partial_fields(charter, garden):
    survey = charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()

    status = survey["fields"]["status"]
    assert status["values"] == [
        {"value": "active", "count": 2, "files": ["plants/Fern.md", "plants/Monstera.md"]},
        {"value": "actve", "count": 1, "files": ["plants/Basil.md"]},
    ]
    assert status["files"] == 3
    assert survey["fields"]["planted"]["files"] == 1
    assert survey["fields"]["height"]["types"] == {"number": 2, "string": 1}
    assert survey["fields"]["flag"]["values"] == [
        {"value": True, "count": 1, "files": ["notes/nested/deep/greenhouse.md"]}
    ]
    assert survey["fields"]["empty"]["types"] == {"null": 1}
    assert survey["fields"]["helpers"]["types"] == {"mapping": 1}
    assert survey["fields"]["tags"]["distinct"] == 3


def test_survey_reports_files_without_frontmatter_and_malformed_frontmatter(charter, garden):
    survey = charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()
    files = {file["path"]: file for file in survey["files"]}

    assert files["plants/Mint.md"]["has_frontmatter"] is False
    assert files["plants/Mint.md"]["frontmatter_error"] is None
    broken = files["notes/broken.md"]
    assert broken["has_frontmatter"] is True
    assert broken["frontmatter_error"].startswith("Invalid YAML in frontmatter")
    assert broken["fields"] == {}
    assert survey["totals"]["files"] == len(files)


def test_survey_counts_link_styles_outside_code_and_urls(charter, garden):
    links = charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()["links"]

    # Monstera 1, Fern 2, journal watering 1 body + 1 frontmatter, pruning 1 frontmatter.
    assert links["wikilink"] == {"links": 6, "files": 4}
    assert links["markdown"] == {"links": 1, "files": 1}


def test_survey_finds_agent_files_and_rulebooks(charter, garden):
    survey = charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()

    assert survey["agent_files"] == ["AGENTS.md", "CLAUDE.md"]
    assert survey["rulebooks"] == [{"path": "house-rules.md", "reason": "filename"}]


def test_survey_finds_a_rulebook_by_heading(charter, tmp_path):
    write_files(tmp_path, {"guide.md": "# Style guide for notes\n", "plain.md": "# Plain\n"})

    survey = charter("survey", str(tmp_path), "--format", "json", cwd=tmp_path).json()

    assert survey["rulebooks"] == [{"path": "guide.md", "reason": "heading"}]


def test_survey_describes_folders(charter, garden):
    folders = {f["folder"]: f for f in charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()["folders"]}

    assert folders["journal"]["filename_shapes"] == {"NNNN-NN-NN-word.md": 2}
    assert folders["journal"]["outline"] == {"headings": ["# {{title}}"], "files": 2}
    assert folders["plants"]["outline"] == {"headings": ["# {{title}}", "## Care", "## History"], "files": 3}
    assert folders["plants"]["filename_shapes"] == {"Title.md": 4}
    assert folders["notes/nested/deep"]["files"] == 1
    assert ".obsidian" not in folders
    assert ".git" not in folders


def test_filename_shapes(charter, tmp_path):
    names = ["0007-use-postgres.md", "snake_case_note.md", "Monstera Deliciosa.md", "index.md"]
    write_files(tmp_path, {name: "# Note\n" for name in names})

    folder = charter("survey", ".", "--format", "json", cwd=tmp_path).json()["folders"][0]

    assert folder["filename_shapes"] == {
        "NNNN-kebab-title.md": 1,
        "snake_title.md": 1,
        "Title.md": 1,
        "word.md": 1,
    }


def test_values_name_example_files_up_to_three(charter, tmp_path):
    files = {f"n{i}.md": "---\nstatus: open\n---\n" for i in range(5)}
    files["odd.md"] = "---\nstatus: opne\n---\n"
    write_files(tmp_path, files)

    status = charter("survey", ".", "--format", "json", cwd=tmp_path).json()["fields"]["status"]

    assert status["values"] == [
        {"value": "open", "count": 5, "files": ["n0.md", "n1.md", "n2.md"]},
        {"value": "opne", "count": 1, "files": ["odd.md"]},
    ]


def test_folders_report_which_fields_their_files_carry(charter, garden):
    folders = {f["folder"]: f for f in charter("survey", str(garden), "--format", "json", cwd=garden.parent).json()["folders"]}

    assert folders["plants"]["fields"] == [
        {"name": "height", "files": 3},
        {"name": "kind", "files": 3},
        {"name": "light", "files": 3},
        {"name": "planted", "files": 1},
        {"name": "status", "files": 3},
        {"name": "tags", "files": 3},
    ]
    assert folders["."]["fields"] == []


def test_crlf_and_bom_frontmatter_is_read(charter, tmp_path):
    write_files(
        tmp_path,
        {
            "crlf.md": b"---\r\nstatus: open\r\n---\r\n# Title\r\n",
            "bom.md": b"\xef\xbb\xbf---\nstatus: open\n---\n# Title\n",
        },
    )

    survey = charter("survey", ".", "--format", "json", cwd=tmp_path).json()

    assert survey["totals"]["with_frontmatter"] == 2
    assert survey["fields"]["status"]["values"] == [{"value": "open", "count": 2, "files": ["bom.md", "crlf.md"]}]
    assert survey["folders"][0]["outline"] == {"headings": ["# {{title}}"], "files": 2}


def test_singular_forms_in_text(charter, tmp_path):
    write_files(tmp_path, {"only.md": "# Only\n"})

    result = charter("survey", ".", cwd=tmp_path)

    assert result.stdout.startswith("Surveyed 1 Markdown file in 1 folder; 0 with frontmatter.\n")
    assert "Agent files:\n  none" in result.stdout


def test_distinct_values_are_capped_with_a_total(charter, tmp_path):
    files = {f"n{i:02d}.md": f"---\ncode: v{i:02d}\n---\n" for i in range(25)}
    write_files(tmp_path, files)

    code = charter("survey", str(tmp_path), "--format", "json", cwd=tmp_path).json()["fields"]["code"]

    assert code["distinct"] == 25
    assert code["truncated"] is True
    assert len(code["values"]) == 20


def test_unreadable_and_empty_files_do_not_stop_the_survey(charter, tmp_path):
    write_files(tmp_path, {"binary.md": b"\xff\xfe\x00bad", "empty.md": b"", "ok.md": "---\na: 1\n---\n"})

    result = charter("survey", str(tmp_path), "--format", "json", cwd=tmp_path)
    files = {file["path"]: file for file in result.json()["files"]}

    assert result.exit_code == 0
    assert files["binary.md"]["problem"] == "not valid UTF-8"
    assert files["empty.md"]["has_frontmatter"] is False
    assert files["empty.md"]["problem"] is None
    assert files["ok.md"]["fields"] == {"a": "number"}


def test_symlinks_do_not_escape_or_loop(charter, tmp_path):
    outside = tmp_path / "outside"
    kb = tmp_path / "kb"
    write_files(outside, {"secret.md": "---\nsecret: yes\n---\n"})
    write_files(kb, {"inside.md": "# In\n"})
    try:
        os.symlink(outside, kb / "linked-dir", target_is_directory=True)
        os.symlink(outside / "secret.md", kb / "linked-file.md")
        os.symlink(kb, kb / "loop", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")

    survey = charter("survey", str(kb), "--format", "json", cwd=tmp_path).json()

    assert [file["path"] for file in survey["files"]] == ["inside.md"]
    assert "secret" not in survey["fields"]


def test_survey_writes_nothing(charter, garden):
    before = _snapshot(garden)
    tree = sorted(p.relative_to(garden).as_posix() for p in garden.rglob("*"))

    charter("survey", str(garden), cwd=garden.parent)
    charter("survey", str(garden), "--format", "json", cwd=garden.parent)

    assert _snapshot(garden) == before
    assert sorted(p.relative_to(garden).as_posix() for p in garden.rglob("*")) == tree


def test_survey_needs_no_contract(charter, garden):
    assert not (garden / "charter.yaml").exists()

    result = charter("survey", ".", "--format", "json", cwd=garden)

    assert result.exit_code == 0
    assert "contract/not-found" not in result.stdout + result.stderr


def test_survey_ignores_a_contract_in_or_above_the_folder(charter, garden):
    plain = charter("survey", str(garden), "--format", "json", cwd=garden.parent).stdout
    write_files(garden.parent, {"charter.yaml": "charter: 1\nroot: nowhere\nkinds: {}\n"})
    write_files(garden, {"charter.yaml": "this: [is not a contract\n"})

    with_contracts = charter("survey", str(garden), "--format", "json", cwd=garden)

    assert with_contracts.exit_code == 0
    survey = json.loads(with_contracts.stdout)
    # The contract files are not Markdown, so the survey of the notes is unchanged.
    assert survey == json.loads(plain)
    assert with_contracts.stderr == ""


def test_text_format_is_a_readable_summary(charter, garden):
    result = charter("survey", str(garden), cwd=garden.parent)

    assert result.exit_code == 0
    assert result.stdout.startswith("Surveyed 11 Markdown files in 5 folders; 7 with frontmatter.\n")
    for expected in (
        "plants: 4 files (Title.md x4)",
        "common outline (3 files): # {{title}} / ## Care / ## History",
        "status: in 3 files, string x3",
        "values (2 distinct): active x2, actve x1",
        "wikilink: 6 links in 4 files",
        "markdown: 1 link in 1 file",
        "notes/broken.md: Invalid YAML in frontmatter",
        "Agent files:\n  AGENTS.md\n  CLAUDE.md",
        "Rulebook-like documents:\n  house-rules.md (by filename)",
    ):
        assert expected in result.stdout


def test_missing_folder_is_a_usage_error(charter, tmp_path):
    result = charter("survey", "nowhere", cwd=tmp_path)

    assert result.exit_code == 2
    assert "usage/folder-not-found" in result.stdout


def test_missing_folder_reports_json_diagnostics_when_asked(charter, tmp_path):
    result = charter("survey", "nowhere", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert result.json()["diagnostics"][0]["code"] == "usage/folder-not-found"


def test_a_file_is_not_a_folder(charter, tmp_path):
    write_files(tmp_path, {"note.md": "# Note\n"})

    assert charter("survey", "note.md", cwd=tmp_path).exit_code == 2


def test_folder_without_markdown_is_an_empty_survey(charter, tmp_path):
    write_files(tmp_path, {"data.csv": "a,b\n"})

    result = charter("survey", ".", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.json() == {
        "format": "charter-survey/1",
        "totals": {"files": 0, "folders": 0, "with_frontmatter": 0},
        "files": [],
        "folders": [],
        "fields": {},
        "links": {"markdown": {"links": 0, "files": 0}, "wikilink": {"links": 0, "files": 0}},
        "agent_files": [],
        "rulebooks": [],
    }
    text = charter("survey", ".", cwd=tmp_path)
    assert text.exit_code == 0
    assert text.stdout.startswith("Surveyed 0 Markdown files in 0 folders; 0 with frontmatter.\n")
