"""On a `--file` run, a file-scope plugin is sent the notes a target links to. Their parsed parts (links, headings,
tags) are filled in only when the plugin declares `needs: [body]`; without it those notes' bodies are never parsed.
The targets themselves, and every note of a whole run or of a vault-scope plugin, carry their parsed parts whatever
the `needs`. Everything else in the request is as before."""

import json

import pytest
from plugin_support import plugin_kb, probe

from charter import __version__, index

# The request a file-scope plugin declaring `needs: [body]` received before the payload was narrowed, for
# `plugin run probe --dump-input --file notes/a.md` on plugin_support.LINKED. Compared as text so any change in the
# bytes shows; only the running charter's version is filled in.
LEGACY_BODY_REQUEST = (
    '{"protocol": "charter-plugin/1", "charter_version": "' + __version__ + '", "plugin": {"id": "probe", "version": "2.0.1"}, '
    '"params": {}, "mode": "file", "root": "notes", "targets": ["a.md"], "today": "2024-03-05", '
    '"index": {"notes": [{"path": "a.md", "kind": "entry", "variant": null, "frontmatter": {"kind": "entry"}, '
    '"links": [{"raw": "[[b]]", "target": "b.md", "field": null, "line": 8}], '
    '"headings": [{"level": 1, "text": "Plans", "line": 4}, {"level": 2, "text": "A secret step", "line": 6}], '
    '"tags": [], "body": "# Plans\\n\\n## A secret step\\n\\nSee [[b]].\\n"}, '
    '{"path": "b.md", "kind": "entry", "variant": null, "frontmatter": {"kind": "entry"}, "links": [], '
    '"headings": [{"level": 1, "text": "Secret notes", "line": 4}], "tags": [], "body": "# Secret notes\\n"}]}}'
)
LEGACY_NOTES = json.loads(LEGACY_BODY_REQUEST)["index"]["notes"]


@pytest.fixture
def kb(make_kb):
    return plugin_kb(make_kb)


def _without_body(note):
    return {key: value for key, value in note.items() if key != "body"}


@pytest.fixture
def parsed(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(index, "_body_parsed", seen.append)
    return seen


def _dump(charter, base, monkeypatch, *argv):
    monkeypatch.setenv("CHARTER_TODAY", "2024-03-05")
    return charter("plugin", "run", "probe", "--dump-input", *argv, cwd=base).stdout.strip()


def test_a_plugin_that_needs_the_body_gets_the_same_request_as_before(charter, kb, monkeypatch):
    base = probe(kb, scope="file", needs="[body]")

    assert _dump(charter, base, monkeypatch, "--file", "notes/a.md") == LEGACY_BODY_REQUEST


def test_needing_the_earlier_version_as_well_leaves_the_notes_as_they_were(charter, kb, monkeypatch):
    base = probe(kb, scope="file", needs="[body, before]")

    request = json.loads(_dump(charter, base, monkeypatch, "--file", "notes/a.md"))

    assert request["index"]["notes"] == LEGACY_NOTES


def test_without_the_body_a_linked_note_keeps_its_keys_but_none_of_its_parsed_parts(charter, kb, monkeypatch):
    base = probe(kb, scope="file")

    request = json.loads(_dump(charter, base, monkeypatch, "--file", "notes/a.md"))

    target, linked = request["index"]["notes"]
    # The target is parsed for the run anyway, so it is sent whole; the body text waits for `needs: body`.
    assert target == _without_body(LEGACY_NOTES[0])
    assert linked == {**_without_body(LEGACY_NOTES[1]), "links": [], "headings": [], "tags": []}


def test_without_the_body_a_linked_note_is_not_parsed(charter, kb, monkeypatch, parsed):
    base = probe(kb, scope="file")

    _dump(charter, base, monkeypatch, "--file", "notes/a.md")

    assert parsed == ["notes/a.md"]


def test_validate_does_not_parse_a_linked_note_for_a_plugin_that_does_not_need_the_body(charter, kb, parsed):
    base = probe(kb, scope="file")

    result = charter("validate", "--format", "json", "--file", "notes/a.md", cwd=base)

    assert result.exit_code == 0
    assert parsed == ["notes/a.md"]


def test_a_file_run_is_sent_every_note_whole_by_a_vault_scope_plugin(charter, kb, monkeypatch):
    base = probe(kb, scope="vault")

    request = json.loads(_dump(charter, base, monkeypatch, "--file", "notes/a.md"))

    assert request["mode"] == "vault"
    assert request["index"]["notes"][2]["headings"] == [{"level": 1, "text": "Secret notes", "line": 4}]


def test_a_whole_run_sends_a_file_scope_plugin_every_note_whole(charter, kb, monkeypatch):
    base = probe(kb, scope="file")

    request = json.loads(_dump(charter, base, monkeypatch))

    assert request["mode"] == "vault"
    by_path = {note["path"]: note for note in request["index"]["notes"]}
    assert by_path["b.md"]["headings"] == [{"level": 1, "text": "Secret notes", "line": 4}]
    assert by_path["d.md"]["links"][0]["target"] == "a.md"
