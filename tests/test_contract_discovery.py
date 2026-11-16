import os
import shutil
from pathlib import Path

import pytest
from conftest import FIXTURES

REPO = FIXTURES / "discovery"
NARRATIVE = REPO / "narrative"
TECHNICAL = REPO / "technical"


def _copy_contract(folder):
    folder.mkdir(parents=True, exist_ok=True)
    contract = (TECHNICAL / "charter.yaml").read_text(encoding="utf-8")
    (folder / "charter.yaml").write_text(contract, encoding="utf-8")


def _paths(result):
    return [(d["path"], d["code"]) for d in result.json()["diagnostics"]]


def test_validate_from_a_subfolder_uses_the_contract_above(charter):
    result = charter("validate", "--format", "json", cwd=NARRATIVE / "notes" / "sub")

    assert result.exit_code == 0, result.stdout


def test_diagnostic_paths_are_relative_to_the_contract_not_the_working_directory(charter):
    result = charter("validate", "--format", "json", cwd=TECHNICAL / "notes")

    assert result.exit_code == 1
    assert _paths(result) == [("notes/broken.md", "schema/required")]


def test_each_knowledge_base_in_a_repository_uses_its_own_contract(charter):
    assert charter("validate", "--format", "json", cwd=NARRATIVE).exit_code == 0
    assert charter("validate", "--format", "json", cwd=TECHNICAL).exit_code == 1


def test_validate_file_searches_from_the_files_folder(charter):
    result = charter("validate", "--file", "technical/notes/broken.md", "--format", "json", cwd=REPO)

    assert result.exit_code == 1
    assert _paths(result) == [("notes/broken.md", "schema/required")]


def test_validate_file_of_several_files_in_one_knowledge_base(charter):
    result = charter(
        "validate", "--file", "technical/notes/fine.md", "technical/notes/broken.md", "--format", "json", cwd=REPO
    )

    assert _paths(result) == [("notes/broken.md", "schema/required")]


def test_files_in_different_knowledge_bases_are_a_usage_error_naming_each(charter):
    result = charter(
        "validate", "--file", "narrative/notes/one.md", "technical/notes/fine.md", "--format", "json", cwd=REPO
    )

    assert result.exit_code == 2
    assert [(d["path"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("narrative/notes/one.md", "usage/mixed-contracts"),
        ("technical/notes/fine.md", "usage/mixed-contracts"),
    ]
    messages = " ".join(d["message"] for d in result.json()["diagnostics"])
    assert "narrative" in messages and "technical" in messages and "charter.yaml" in messages


def test_config_overrides_discovery(charter):
    result = charter("validate", "--config", str(NARRATIVE / "charter.yaml"), "--format", "json", cwd=TECHNICAL)

    assert result.exit_code == 0, result.stdout


def test_config_overrides_discovery_for_files_of_other_knowledge_bases(charter):
    result = charter(
        "validate",
        "--config",
        str(NARRATIVE / "charter.yaml"),
        "--file",
        "narrative/notes/one.md",
        "technical/notes/fine.md",
        "--format",
        "json",
        cwd=REPO,
    )

    assert result.exit_code == 0, result.stdout


def test_no_contract_is_a_usage_error_with_a_hint(charter, tmp_path):
    result = charter("validate", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/not-found"
    assert "charter init" in diagnostic["hint"] and "--config" in diagnostic["hint"]


def test_file_with_no_contract_above_is_a_usage_error(charter, tmp_path):
    (tmp_path / "loose.md").write_text("# Loose\n", encoding="utf-8")

    result = charter("validate", "--file", "loose.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("loose.md", "contract/not-found")]


def test_every_command_finds_the_contract_upward(charter):
    sub = TECHNICAL / "notes"

    assert "spec" in charter("describe", cwd=sub).stdout
    docs_check = charter("docs", "--check", cwd=sub)
    assert docs_check.exit_code == 1 and "`CHARTER.md` does not exist" in docs_check.stdout
    assert charter("sweep", "broken.md", cwd=sub).exit_code == 0
    assert charter("plugin", "list", cwd=sub).exit_code == 0
    assert charter("new", "spec", "Dry", "--dry-run", "--set", "status=draft", cwd=sub).exit_code == 0


def test_new_writes_relative_to_the_contract_found_above(charter, tmp_path):
    (tmp_path / "kb" / "notes" / "inner").mkdir(parents=True)
    _copy_contract(tmp_path / "kb")

    result = charter("new", "spec", "Made", "--set", "status=draft", cwd=tmp_path / "kb" / "notes" / "inner")

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "kb" / "notes" / "Made.md").is_file()
    assert not (tmp_path / "kb" / "notes" / "inner" / "Made.md").exists()


def test_init_does_not_search_for_a_contract(charter, tmp_path):
    (tmp_path / "kb").mkdir()
    _copy_contract(tmp_path / "kb")
    (tmp_path / "kb" / "inner").mkdir()

    result = charter("init", cwd=tmp_path / "kb" / "inner")

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "kb" / "inner" / "charter.yaml").is_file()


def test_dotdot_in_a_file_path_resolves_to_the_contract_of_the_named_file(charter):
    result = charter("validate", "--file", "narrative/notes/sub/../one.md", "--format", "json", cwd=REPO)

    assert result.exit_code == 0, result.stdout
    assert result.json()["diagnostics"] == []


def test_no_contract_for_a_file_reads_as_above_the_file(charter, tmp_path):
    (tmp_path / "loose.md").write_text("# Loose\n", encoding="utf-8")

    result = charter("validate", "--file", "loose.md", "--format", "json", cwd=tmp_path)

    assert "any folder above `loose.md`" in result.json()["diagnostics"][0]["message"]


def _two_knowledge_bases(root):
    for name in ("a", "b"):
        _copy_contract(root / name)
        (root / name / "n.md").write_text("# N\n", encoding="utf-8")


def test_mixed_contracts_message_shows_both_paths_relative_to_the_working_directory(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter("validate", "--file", "a/n.md", "b/n.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    diagnostics = result.json()["diagnostics"]
    assert [(d["path"], d["code"]) for d in diagnostics] == [
        ("a/n.md", "usage/mixed-contracts"),
        ("b/n.md", "usage/mixed-contracts"),
    ]
    assert diagnostics[0]["message"].startswith("`a/n.md` belongs to the contract `a/charter.yaml`;")
    assert diagnostics[1]["message"].startswith("`b/n.md` belongs to the contract `b/charter.yaml`;")
    assert str(tmp_path) not in result.stdout


def test_mixed_contracts_message_in_text_output_uses_the_same_base(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter("validate", "--file", "a/n.md", "b/n.md", cwd=tmp_path)

    assert result.exit_code == 2
    assert "`a/n.md` belongs to the contract `a/charter.yaml`" in result.stdout
    assert str(tmp_path) not in result.stdout


def test_mixed_contracts_uses_dotdot_for_a_contract_outside_the_working_directory(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter("validate", "--file", "../a/n.md", "../b/n.md", "--format", "json", cwd=tmp_path / "a")

    assert result.exit_code == 2
    messages = [d["message"] for d in result.json()["diagnostics"]]
    assert messages[0].startswith("`../a/n.md` belongs to the contract `charter.yaml`;")
    assert messages[1].startswith("`../b/n.md` belongs to the contract `../b/charter.yaml`;")


def test_mixed_contracts_shows_an_absolute_file_relative_to_the_working_directory(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter(
        "validate", "--file", str(tmp_path / "a" / "n.md"), "b/n.md", "--format", "json", cwd=tmp_path
    )

    assert result.exit_code == 2
    assert result.json()["diagnostics"][0]["message"].startswith(
        "`a/n.md` belongs to the contract `a/charter.yaml`;"
    )


def test_a_missing_file_is_reported_before_the_missing_contract(charter, tmp_path):
    result = charter("validate", "--file", "ghost.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("ghost.md", "usage/file-not-found")]


def test_a_missing_file_is_reported_as_text_before_the_missing_contract(charter, tmp_path):
    result = charter("validate", "--file", "ghost.md", cwd=tmp_path)

    assert result.exit_code == 2
    assert "usage/file-not-found" in result.stdout and "contract/not-found" not in result.stdout


def test_a_missing_file_with_a_contract_above_is_still_a_file_error(charter, tmp_path):
    _copy_contract(tmp_path)

    result = charter("validate", "--file", "ghost.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("ghost.md", "usage/file-not-found")]


def test_a_missing_file_among_existing_ones_is_the_only_report(charter, tmp_path):
    (tmp_path / "loose.md").write_text("# Loose\n", encoding="utf-8")

    result = charter("validate", "--file", "loose.md", "ghost.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("ghost.md", "usage/file-not-found")]


def test_a_missing_file_wins_over_files_of_different_contracts(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter("validate", "--file", "a/n.md", "b/n.md", "b/ghost.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("ghost.md", "usage/file-not-found")]  # contract-relative


def test_a_directory_given_as_a_file_is_not_an_existing_file(charter, tmp_path):
    (tmp_path / "folder").mkdir()

    result = charter("validate", "--file", "folder", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("folder", "usage/file-not-found")]


def test_an_existing_file_outside_any_contract_is_still_not_found_contract(charter, tmp_path):
    (tmp_path / "loose.md").write_text("# Loose\n", encoding="utf-8")

    result = charter("validate", "--file", "loose.md", "--format", "json", cwd=tmp_path)

    assert result.exit_code == 2
    assert _paths(result) == [("loose.md", "contract/not-found")]


def test_config_given_with_a_missing_file_reports_the_file(charter, tmp_path):
    result = charter(
        "validate", "--config", str(NARRATIVE / "charter.yaml"), "--file", "ghost.md", "--format", "json",
        cwd=tmp_path,
    )

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/file-not-found"]


def _narrative_copy(tmp_path):
    kb = tmp_path / "kb"
    shutil.copytree(NARRATIVE, kb)
    return kb


def _symlink_or_skip(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")


@pytest.mark.parametrize("with_config", [False, True])
@pytest.mark.parametrize("as_text", [False, True])
@pytest.mark.parametrize("kind", ["absolute", "dotdot", "symlink"])
def test_a_missing_file_shows_the_contract_relative_path(charter, tmp_path, kind, as_text, with_config):
    kb = _narrative_copy(tmp_path)
    cwd = kb / "notes" / "sub"
    if kind == "absolute":
        typed = str(kb / "notes" / "nope.md")
    elif kind == "dotdot":
        typed = "../nope.md"
    else:
        _symlink_or_skip(tmp_path / "link", kb)
        typed = str(tmp_path / "link" / "notes" / "nope.md")
    args = ["validate", "--file", typed]
    if with_config:
        args += ["--config", str(kb / "charter.yaml")]
    args += [] if as_text else ["--format", "json"]

    result = charter(*args, cwd=cwd)

    assert result.exit_code == 2
    if as_text:
        assert "notes/nope.md" in result.stdout and "usage/file-not-found" in result.stdout
    else:
        assert _paths(result) == [("notes/nope.md", "usage/file-not-found")]


@pytest.mark.parametrize("config", [None, "real", "relative", "through-the-parent-link"])
@pytest.mark.parametrize("parent_link", [False, True])
def test_a_missing_file_through_a_link_to_the_contract_folder_shows_the_same_path(
    charter, tmp_path, parent_link, config
):
    # Built here, not taken from the OS temp directory (which is itself a symlink on macOS), so the layers are known.
    home = Path(os.path.realpath(tmp_path))
    (home / "real").mkdir()
    kb = _narrative_copy(home / "real")
    _symlink_or_skip(kb / "link", kb)  # kb/link -> kb: the contract is reachable twice, at kb and at kb/link
    typed_kb = kb
    if parent_link:
        _symlink_or_skip(home / "via", home / "real")  # a second layer: a symlinked parent of the knowledge base
        typed_kb = home / "via" / "kb"
    args = ["validate", "--file", str(typed_kb / "link" / "notes" / "nope.md"), "--format", "json"]
    if config:
        args += ["--config", {"real": str(kb / "charter.yaml"), "relative": "../charter.yaml",
                              "through-the-parent-link": str(typed_kb / "charter.yaml")}[config]]

    result = charter(*args, cwd=kb / "notes")

    assert result.exit_code == 2
    assert _paths(result) == [("link/notes/nope.md", "usage/file-not-found")]


def test_mixed_contracts_paths_are_short_when_the_working_directory_is_a_symlink(charter, tmp_path):
    _two_knowledge_bases(tmp_path / "real")
    _symlink_or_skip(tmp_path / "via", tmp_path / "real")

    result = charter(
        "validate", "--file", str(tmp_path / "via" / "a" / "n.md"), str(tmp_path / "via" / "b" / "n.md"),
        "--format", "json", cwd=tmp_path / "via",
    )

    assert result.exit_code == 2
    assert result.json()["diagnostics"][0]["message"].startswith("`a/n.md` belongs to the contract `a/charter.yaml`;")


def test_mixed_contracts_with_absolute_tmp_path_files_are_short(charter, tmp_path):
    _two_knowledge_bases(tmp_path)

    result = charter(
        "validate", "--file", str(tmp_path / "a" / "n.md"), str(tmp_path / "b" / "n.md"), "--format", "json",
        cwd=tmp_path,
    )

    assert result.json()["diagnostics"][1]["message"].startswith("`b/n.md` belongs to the contract `b/charter.yaml`;")
