"""Edge cases of the `.gitignore` entry `plugin add` makes for Python plugins."""

import codecs

from conftest import FIXTURES

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"


def _kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, "notes/a.md": "---\nkind: entry\n---\n# Plans\n"})


def test_a_gitignore_with_a_byte_order_mark_is_not_given_the_entry_twice(charter, make_kb, plugin_repo):
    kb = _kb(make_kb)
    (kb / ".gitignore").write_bytes(codecs.BOM_UTF8 + b"__pycache__/\n")

    result = charter("plugin", "add", "--from", f"{plugin_repo().as_posix()}@v1.2.0", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert (kb / ".gitignore").read_bytes() == codecs.BOM_UTF8 + b"__pycache__/\n"


def test_a_folder_named_like_a_python_file_does_not_make_a_plugin_python(charter, make_kb, plugin_repo):
    kb = _kb(make_kb)
    manifest = (FIXTURES / "plugins" / "todo-free" / "charter-plugin.yaml").read_text(encoding="utf-8")
    manifest = manifest.replace('["uv", "run", "--script", "check.py"]', '["node", "check.js"]')
    repo = plugin_repo({"charter-plugin.yaml": manifest, "check.js": "//\n", "data.py/readme.txt": "not code\n"})

    result = charter("plugin", "add", "--from", f"{repo.as_posix()}@v1.2.0", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert not (kb / ".gitignore").exists()
