"""A per-edit run loads only what it uses. Each case is a fresh interpreter, because imports are process-wide."""

import json
import shutil
import subprocess
import sys

import pytest
from conftest import FIXTURES

from charter import cli, description, inventory, survey, sweep

# Runs the CLI in-process and reports, after it, which modules are loaded.
_HARNESS = """
import json, sys
from charter.cli import main
try:
    main(sys.argv[1:])
except SystemExit:
    pass
sys.stderr.write("\\nLOADED " + json.dumps(sorted(sys.modules)))
"""

JSONSCHEMA = "jsonschema"
DESCRIPTION = "charter.description"
LOADED_ONLY_WHEN_USED = (
    JSONSCHEMA, DESCRIPTION, "charter.docs", "charter.sweep", "charter.survey", "charter.install", "charter.inventory",
    "charter.snapshot", "charter.init", "charter.agent_files",
)

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n      title: {type: string, required: true}\n"
NOTE = "---\nkind: entry\ntitle: A\n---\n# A\n"


def _loaded(cwd, *argv):
    result = subprocess.run(
        [sys.executable, "-c", _HARNESS, *argv], cwd=cwd, capture_output=True, text=True, check=False
    )
    marker = result.stderr.rindex("\nLOADED ")
    return set(json.loads(result.stderr[marker + len("\nLOADED ") :])), result


@pytest.fixture
def plain_kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, "notes/a.md": NOTE})


def test_a_single_file_run_on_a_knowledge_base_without_plugins_loads_neither_jsonschema_nor_the_description(plain_kb):
    loaded, result = _loaded(plain_kb, "validate", "--file", "notes/a.md")

    assert result.returncode == 0, result.stdout
    assert loaded.isdisjoint(LOADED_ONLY_WHEN_USED)


def test_a_single_file_run_with_the_agent_layer_on_loads_the_description_only_for_the_rulebook(make_kb):
    kb = make_kb(
        {"charter.yaml": CONTRACT + "docs: {}\nagents: {}\n", "notes/a.md": NOTE, "AGENTS.md": "x\n", "CHARTER.md": "old\n"},
        agents_include=True,
    )

    loaded, result = _loaded(kb, "validate", "--file", "notes/a.md")

    assert result.returncode == 0, result.stdout
    assert loaded.isdisjoint(LOADED_ONLY_WHEN_USED)

    loaded, result = _loaded(kb, "validate", "--file", "CHARTER.md")

    assert "agents-include/stale" in result.stdout
    assert DESCRIPTION in loaded


def test_a_contract_with_a_mistake_loads_jsonschema_for_its_wording(make_kb):
    kb = make_kb({"charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: 5\n", "notes/a.md": NOTE})

    loaded, result = _loaded(kb, "validate", "--file", "notes/a.md")

    assert "contract/invalid" in result.stdout
    assert JSONSCHEMA in loaded


def test_a_plugin_with_a_config_schema_loads_jsonschema(make_kb):
    kb = make_kb({
        "charter.yaml": CONTRACT
        + "checks:\n  agents-include: {enabled: false}\n  banned-words:\n    source: tools/banned-words\n"
        "    with: {words: [secret]}\n",
        "notes/a.md": NOTE,
    })
    shutil.copytree(FIXTURES / "plugins" / "banned-words", kb / "tools" / "banned-words")

    loaded, result = _loaded(kb, "validate", "--file", "notes/a.md")

    assert result.returncode == 0, result.stdout
    assert JSONSCHEMA in loaded


@pytest.mark.parametrize(
    ("argv", "module"),
    [
        (("describe",), DESCRIPTION),
        (("docs", "--check"), DESCRIPTION),
        (("sweep", "notes/a.md"), "charter.sweep"),
        (("survey", "."), "charter.survey"),
        (("plugin", "list"), "charter.inventory"),
        (("snapshot", "."), "charter.snapshot"),
    ],
)
def test_a_command_loads_the_module_it_needs(plain_kb, argv, module):
    loaded, _ = _loaded(plain_kb, *argv)

    assert module in loaded


def test_command_formats_match_their_modules():
    assert cli.DESCRIBE_FORMATS == description.FORMATS
    assert cli.SWEEP_FORMATS == sweep.FORMATS
    assert cli.SURVEY_FORMATS == survey.FORMATS
    assert cli.LISTING_FORMATS == inventory.FORMATS
