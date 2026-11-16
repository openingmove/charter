"""`plugin add` ignores the bytecode a Python plugin leaves behind, the first time it vendors one."""

import pytest
from conftest import FIXTURES

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"


@pytest.fixture
def kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, "notes/a.md": "---\nkind: entry\n---\n# Plans\n"})


def _from(repo):
    return f"{repo.as_posix()}@v1.2.0"


def test_adding_a_python_plugin_ignores_bytecode_in_gitignore(charter, kb, plugin_repo):
    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert (kb / ".gitignore").read_text(encoding="utf-8") == "__pycache__/\n"
    assert "Added `__pycache__/` to `.gitignore`" in result.stdout


def test_the_bytecode_entry_keeps_the_gitignores_lines_and_line_endings(charter, kb, plugin_repo):
    (kb / ".gitignore").write_bytes(b".venv/\r\n*.log")

    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=kb)

    assert (kb / ".gitignore").read_bytes() == b".venv/\r\n*.log\r\n__pycache__/\r\n"


def test_the_bytecode_entry_is_never_added_twice(charter, kb, plugin_repo):
    (kb / ".gitignore").write_text(".venv/\n__pycache__/\n", encoding="utf-8")
    repo = plugin_repo()

    first = charter("plugin", "add", "--from", _from(repo), cwd=kb)
    second = charter("plugin", "add", "--from", _from(repo), cwd=kb)

    assert (first.exit_code, second.exit_code) == (0, 0)
    assert (kb / ".gitignore").read_text(encoding="utf-8") == ".venv/\n__pycache__/\n"
    assert ".gitignore" not in first.stdout


def test_adding_the_same_plugin_again_does_not_repeat_the_entry(charter, kb, plugin_repo):
    repo = plugin_repo()

    charter("plugin", "add", "--from", _from(repo), cwd=kb)
    second = charter("plugin", "add", "--from", _from(repo), cwd=kb)

    assert (kb / ".gitignore").read_text(encoding="utf-8") == "__pycache__/\n"
    assert ".gitignore" not in second.stdout


def test_a_plugin_that_is_not_python_leaves_gitignore_alone(charter, kb, plugin_repo):
    manifest = (FIXTURES / "plugins" / "todo-free" / "charter-plugin.yaml").read_text(encoding="utf-8")
    manifest = manifest.replace('["uv", "run", "--script", "check.py"]', '["node", "check.js"]')
    repo = plugin_repo({"charter-plugin.yaml": manifest, "check.js": "//\n"})

    result = charter("plugin", "add", "--from", _from(repo), cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert not (kb / ".gitignore").exists()


def test_an_unwritable_gitignore_refuses_the_add_and_installs_nothing(charter, kb, plugin_repo):
    (kb / ".gitignore").mkdir()

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=kb)

    assert result.exit_code == 1
    assert "plugin/write-failed" in result.stdout
    assert not (kb / ".charter").exists()
    assert not (kb / "charter.lock").exists()
