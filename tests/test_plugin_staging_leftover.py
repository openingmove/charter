"""A `.staging-*` folder that an interrupted plugin commit left in `.charter/plugins/` is reported by `plugin list`
and `validate` as a warning on stderr. Their output and exit code stay as they were, and charter never deletes the
folder: it may hold the only copy of a plugin's previous directory."""

import pytest
from conftest import FIXTURES

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
NOTES = {"notes/a.md": "---\nkind: entry\n---\n# Plans\n"}
PLUGIN = str(FIXTURES / "plugins" / "todo-free")
LEFTOVER = ".charter/plugins/.staging-x"
CODE = "plugin/leftover-staging"


@pytest.fixture
def kb(make_kb, charter):
    base = make_kb({"charter.yaml": CONTRACT, **NOTES})
    assert charter("plugin", "add", "--dev", PLUGIN, cwd=base).exit_code == 0
    return base


def _leave_staging(base):
    previous = base / LEFTOVER / "previous"
    previous.mkdir(parents=True)
    (previous / "check.py").write_text("old\n", encoding="utf-8")
    return previous


@pytest.mark.parametrize(
    "argv",
    [
        ("plugin", "list"),
        ("plugin", "list", "--format", "json"),
        ("validate",),
        ("validate", "--format", "json"),
        ("validate", "--file", "notes/a.md"),
    ],
)
def test_a_leftover_staging_folder_is_a_warning_and_output_and_exit_code_stay_the_same(charter, kb, argv):
    clean = charter(*argv, cwd=kb)
    previous = _leave_staging(kb)

    result = charter(*argv, cwd=kb)

    assert (result.exit_code, result.stdout) == (clean.exit_code, clean.stdout)
    assert clean.stderr == ""
    assert CODE in result.stderr
    assert "warning" in result.stderr
    assert f"`{LEFTOVER}`" in result.stderr
    assert "previous/" in result.stderr
    assert previous.joinpath("check.py").is_file()


def test_each_leftover_staging_folder_is_named(charter, kb):
    _leave_staging(kb)
    (kb / ".charter/plugins/.staging-y").mkdir()

    result = charter("plugin", "list", cwd=kb)

    assert result.stderr.count(CODE) == 2
    assert f"`{LEFTOVER}`" in result.stderr
    assert "`.charter/plugins/.staging-y`" in result.stderr


def test_a_plugin_directory_is_not_a_leftover(charter, kb):
    result = charter("validate", cwd=kb)

    assert CODE not in result.stderr


def test_without_a_plugins_folder_nothing_is_reported(charter, make_kb):
    base = make_kb({"charter.yaml": CONTRACT, **NOTES})

    assert charter("validate", cwd=base).stderr == ""
    assert charter("plugin", "list", cwd=base).stderr == ""


def test_a_stray_file_named_like_a_staging_folder_is_not_a_leftover(charter, kb):
    (kb / LEFTOVER).write_text("stray\n", encoding="utf-8")

    result = charter("validate", cwd=kb)

    assert CODE not in result.stderr
