"""Packaging: the published skill and plugin files, read as files (never imported code)."""

import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SKILL_FOLDERS = sorted(p for p in SKILLS.iterdir() if p.is_dir())
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
MARKETPLACE = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8"))


FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def parse_frontmatter(text):
    match = FRONTMATTER.match(text)
    assert match, "no frontmatter"
    return yaml.safe_load(match.group(1))


def frontmatter(path):
    return parse_frontmatter(path.read_text("utf-8"))


def test_frontmatter_parses_crlf_and_stops_at_the_first_closing_rule():
    text = "---\r\nname: x\r\ndisable-model-invocation: true\r\n---\r\nbody\r\n---\r\nnot: meta\r\n"

    assert parse_frontmatter(text) == {"name": "x", "disable-model-invocation": True}


def test_there_is_at_least_one_skill():
    assert SKILL_FOLDERS


@pytest.mark.parametrize("folder", SKILL_FOLDERS, ids=lambda p: p.name)
def test_a_skill_is_user_invoked_for_claude(folder):
    meta = frontmatter(folder / "SKILL.md")

    assert meta["name"] == folder.name
    assert meta["description"]
    assert meta["disable-model-invocation"] is True


@pytest.mark.parametrize("folder", SKILL_FOLDERS, ids=lambda p: p.name)
def test_a_skill_is_user_invoked_for_codex(folder):
    meta = yaml.safe_load((folder / "agents" / "openai.yaml").read_text("utf-8"))

    assert meta["policy"]["allow_implicit_invocation"] is False
    assert meta["interface"]["display_name"]
    assert meta["interface"]["short_description"]


def test_the_skills_never_call_the_knowledge_base_a_vault():
    files = [p for p in SKILLS.rglob("*") if p.is_file()]

    assert files
    assert [p for p in files if re.search(r"\bvaults?\b", p.read_text("utf-8"), re.I)] == []


def test_the_plugin_is_named_charter_and_lists_exactly_the_skill_folders():
    assert PLUGIN["name"] == "charter"
    assert sorted(PLUGIN["skills"]) == [f"./skills/{p.name}" for p in SKILL_FOLDERS]


def test_the_plugin_version_equals_the_package_version():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))

    assert PLUGIN["version"] == pyproject["project"]["version"]


def test_the_version_the_cli_prints_equals_the_package_version():
    # The skills parse `charter --version`; a third copy of the version must not drift.
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    init = (ROOT / "src" / "charter" / "__init__.py").read_text("utf-8")

    assert re.search(r'^__version__ = "([^"]+)"', init, re.M).group(1) == pyproject["project"]["version"]


def test_the_marketplace_offers_the_plugin_from_the_repository_root():
    (entry,) = MARKETPLACE["plugins"]

    assert MARKETPLACE["name"]
    assert entry["name"] == PLUGIN["name"]
    assert (ROOT / entry["source"]).resolve() == ROOT
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


def test_the_retired_claude_code_integration_is_gone():
    assert not (ROOT / "integrations" / "claude-code").exists()
