"""A single-file run parses a note's body only when something reads it: the targets, notes a target links to with an
anchor to check, and notes a plugin is sent. Frontmatter, paths and aliases are indexed for every note."""

import shutil

import pytest
from conftest import FIXTURES

from charter import index
from charter.validate import contract_at

CONTRACT = "charter: 1\nroot: notes\n{top}kinds:\n  entry: {{}}\n{checks}"
HEAD = "---\nkind: entry\n---\n"
NOTES = {
    "a.md": HEAD + "See [[b]].\n",
    "b.md": HEAD + "# Intro\n\nBack to [[c]].\n",
    "c.md": HEAD + "# Elsewhere\n",
    "d.md": HEAD + "Points at [[a]].\n",
}
ANCHORED = {**NOTES, "a.md": HEAD + "See [[b#Intro]].\n"}


@pytest.fixture
def parsed(monkeypatch):
    """The paths of the notes whose bodies were parsed, in order."""
    seen: list[str] = []
    monkeypatch.setattr(index, "_body_parsed", seen.append)
    return seen


def _kb(make_kb, notes, top="", checks=""):
    files = {"charter.yaml": CONTRACT.format(top=top, checks=checks)}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _file(charter, base, *paths):
    return charter("validate", "--format", "json", "--file", *paths, cwd=base)


def _codes(result):
    return [(d["path"], d["code"]) for d in result.json()["diagnostics"]]


def test_only_the_target_is_parsed_when_nothing_else_needs_a_body(charter, make_kb, parsed):
    base = _kb(make_kb, NOTES)

    result = _file(charter, base, "notes/a.md")

    assert result.exit_code == 0
    assert parsed == ["notes/a.md"]


def test_every_target_is_parsed_and_no_other_note(charter, make_kb, parsed):
    base = _kb(make_kb, NOTES)

    _file(charter, base, "notes/a.md", "notes/c.md")

    assert sorted(parsed) == ["notes/a.md", "notes/c.md"]


def test_a_whole_run_parses_every_note(charter, make_kb, parsed):
    base = _kb(make_kb, NOTES)

    charter("validate", "--format", "json", cwd=base)

    assert sorted(parsed) == [f"notes/{name}" for name in NOTES]


def test_a_linked_note_is_parsed_for_an_anchor_when_anchors_are_checked(charter, make_kb, parsed):
    base = _kb(make_kb, ANCHORED, top="links: {check_anchors: true}\n")

    result = _file(charter, base, "notes/a.md")

    assert result.exit_code == 0
    assert sorted(parsed) == ["notes/a.md", "notes/b.md"]


def test_a_missing_anchor_is_still_reported_from_the_lazily_parsed_target(charter, make_kb, parsed):
    notes = {**ANCHORED, "a.md": HEAD + "See [[b#Nowhere]].\n"}
    base = _kb(make_kb, notes, top="links: {check_anchors: true}\n")

    result = _file(charter, base, "notes/a.md")

    assert _codes(result) == [("notes/a.md", "links/missing-anchor")]
    assert "notes/b.md" in parsed


@pytest.mark.parametrize(
    ("top", "note"),
    [
        ("", HEAD + "See [[b#Intro]].\n"),
        ("links: {check_anchors: true}\n", HEAD + "See [[b]].\n"),
        ("links: {check_anchors: true}\n", HEAD + "See [[b#^block]].\n"),
    ],
    ids=["anchors-unchecked", "link-without-anchor", "block-anchor"],
)
def test_a_linked_note_is_not_parsed_without_an_anchor_to_check(charter, make_kb, parsed, top, note):
    base = _kb(make_kb, {**NOTES, "a.md": note}, top=top)

    _file(charter, base, "notes/a.md")

    assert parsed == ["notes/a.md"]


def _plugin_kb(make_kb, *, scope, needs):
    base = _kb(make_kb, NOTES, checks="checks:\n  probe:\n    source: tools/probe\n")
    plugin = base / "tools" / "probe"
    shutil.copytree(FIXTURES / "plugins" / "probe", plugin)
    manifest = plugin / "charter-plugin.yaml"
    extra = f"scope: {scope}\n" + (f"needs: [{needs}]\n" if needs else "")
    manifest.write_text(manifest.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return base


def test_a_file_scope_plugin_that_needs_the_body_gets_the_target_and_its_links_parsed(charter, make_kb, parsed):
    base = _plugin_kb(make_kb, scope="file", needs="body")

    result = _file(charter, base, "notes/a.md")

    assert result.exit_code == 0
    assert sorted(parsed) == ["notes/a.md", "notes/b.md"]


def test_a_vault_scope_plugin_is_sent_every_note_so_every_body_is_parsed(charter, make_kb, parsed):
    base = _plugin_kb(make_kb, scope="vault", needs="body")

    _file(charter, base, "notes/a.md")

    assert sorted(parsed) == [f"notes/{name}" for name in NOTES]


def test_a_note_body_is_parsed_once_however_often_it_is_read(charter, make_kb, parsed):
    base = _kb(make_kb, ANCHORED, top="links: {check_anchors: true}\n", checks="")

    _file(charter, base, "notes/a.md", "notes/b.md")

    assert sorted(parsed) == ["notes/a.md", "notes/b.md"]


def test_notes_with_equal_frontmatter_and_different_bodies_differ_without_parsing(make_kb, parsed):
    base = _kb(make_kb, {"a.md": HEAD + "One.\n", "b.md": HEAD + "Two.\n"})
    first, second = index.build_index(contract_at(base / "charter.yaml")).notes

    assert first.frontmatter == second.frontmatter
    assert first != second
    assert first == first
    assert parsed == []
