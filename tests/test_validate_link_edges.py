"""Edge cases of the `links` check: the wording of its messages, and which files the index reads for it."""

from pathlib import Path

import pytest
from links_support import PAGE, codes as _codes, kb as _kb, validate as _validate


def _messages(result):
    return [(d["path"], d["code"], d["message"], d["hint"]) for d in result.json()["diagnostics"]]


def test_field_link_to_an_unparseable_note_says_it_has_no_valid_kind(charter, make_kb):
    kb = _kb(make_kb, {
        "Broken.md": "---\nkind: zone\nname: [unclosed\n---\n",
        "Rock.md": "---\nkind: thing\nzone: '[[Broken]]'\n---\n",
    })

    findings = [m for m in _messages(_validate(charter, kb)) if m[1] == "links/wrong-kind"]

    assert findings == [(
        "notes/Rock.md",
        "links/wrong-kind",
        "Field `zone` links to `notes/Broken.md`, which has no valid kind"
        " (it could not be read as a note; see its own findings); it must link to a note of kind `zone`.",
        "Link to a note of kind `zone`, or change `to` for this field in charter.yaml.",
    )]


def test_field_link_to_an_attachment_still_says_it_is_not_a_note(charter, make_kb):
    kb = _kb(make_kb, {"map.png": "x", "Rock.md": "---\nkind: thing\nzone: '[[map.png]]'\n---\n"})

    messages = [m[2] for m in _messages(_validate(charter, kb)) if m[1] == "links/wrong-kind"]

    assert messages == [
        "Field `zone` links to `notes/map.png`, which is not a note; it must link to a note of kind `zone`."
    ]


@pytest.mark.parametrize("value", ["''", "'   '"])
def test_empty_link_field_value_is_absent(charter, make_kb, value):
    kb = _kb(make_kb, {"Rock.md": f"---\nkind: thing\nzone: {value}\nrequires: [{value}]\n---\n"})

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_empty_required_link_field_is_reported_as_empty_only(charter, make_kb):
    kb = _kb(make_kb, {"Rock.md": "---\nkind: thing\nzone: ''\n---\n"})
    contract = kb / "charter.yaml"
    contract.write_text(
        contract.read_text().replace("zone: {type: link, to: zone}", "zone: {type: link, to: zone, required: true}")
    )

    assert _codes(_validate(charter, kb)) == [("notes/Rock.md", 3, "schema/required")]


def _ambiguous_hint(charter, make_kb, top):
    kb = _kb(make_kb, {"a/Twin.md": PAGE, "b/Twin.md": PAGE, "Index.md": PAGE + "[[Twin]]\n"}, top=top)
    result = _validate(charter, kb)
    assert [d["code"] for d in result.json()["diagnostics"]] == ["links/ambiguous"]
    return result.json()["diagnostics"][0]["hint"]


def test_ambiguous_hint_suggests_a_path_link_when_path_resolution_is_on(charter, make_kb):
    assert _ambiguous_hint(charter, make_kb, "") == "Link by path to name one note, e.g. `[[a/Twin]]`."


def test_ambiguous_hint_suggests_a_markdown_link_without_path_resolution(charter, make_kb):
    hint = _ambiguous_hint(charter, make_kb, "links: {resolve: [basename]}\n")

    assert hint == "Link with a Markdown link to name one note, e.g. `[Twin](a/Twin.md)`."


def test_ambiguous_hint_offers_no_unaccepted_form(charter, make_kb):
    hint = _ambiguous_hint(charter, make_kb, "links: {resolve: [basename], styles: [wikilink]}\n")

    assert hint == "Make the name unique, or add `path` to `links.resolve` in charter.yaml to link by path."


def test_wikilink_value_in_a_markdown_only_contract_says_the_syntax_is_off(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Home.md": PAGE, "Rock.md": "---\nkind: thing\nanywhere: '[[Home]]'\n---\n"},
        top="links: {styles: [markdown]}\n",
    )

    assert _messages(_validate(charter, kb)) == [(
        "notes/Rock.md",
        "links/unresolved",
        "Link `[[Home]]` uses wikilink syntax, which `links.styles` does not enable.",
        "Write a Markdown link such as `[Home](Home.md)`, or add `wikilink` to `links.styles` in charter.yaml.",
    )]


def test_bare_name_in_a_markdown_only_contract_still_resolves(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Home.md": PAGE, "Rock.md": "---\nkind: thing\nanywhere: Home\n---\n"},
        top="links: {styles: [markdown]}\n",
    )

    assert _validate(charter, kb).exit_code == 0


# --- bare names of files that are not notes ---

STYLES = {
    "wikilink": "links: {styles: [wikilink]}\n",
    "markdown": "links: {styles: [markdown]}\n",
    "both": "",
}
PLAIN_FILES = {"Makefile": "x", "LICENSE": "x", ".gitignore": "x"}


@pytest.mark.parametrize("styles", STYLES)
@pytest.mark.parametrize("link", ["[[Makefile]]", "[[LICENSE]]", "[[.gitignore]]", "![[Makefile]]"])
def test_wikilink_to_an_extensionless_or_dotfile_resolves(charter, make_kb, link, styles):
    kb = _kb(make_kb, {**PLAIN_FILES, "Index.md": PAGE + f"{link}\n"}, top=STYLES[styles])

    result = _validate(charter, kb)

    # Under markdown-only styles a bare name in a body is plain text, not a link.
    assert _codes(result) == [], result.stdout


@pytest.mark.parametrize("styles", STYLES)
@pytest.mark.parametrize("link", ["[m](Makefile)", "[m](.gitignore)", "[m](LICENSE)"])
def test_markdown_link_to_an_extensionless_or_dotfile_resolves(charter, make_kb, link, styles):
    kb = _kb(make_kb, {**PLAIN_FILES, "Index.md": PAGE + f"{link}\n"}, top=STYLES[styles])

    result = _validate(charter, kb)

    assert _codes(result) == [], result.stdout


@pytest.mark.parametrize("styles", ["wikilink", "both"])
def test_a_note_and_a_file_with_the_same_bare_name_are_ambiguous(charter, make_kb, styles):
    # By path alone the file wins; by name the two clash.
    top = STYLES[styles].replace("links: {", "links: {resolve: [basename], ") or "links: {resolve: [basename]}\n"
    kb = _kb(make_kb, {"Makefile": "x", "Makefile.md": PAGE, "Index.md": PAGE + "[[Makefile]]\n"}, top=top)

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/ambiguous")]
    assert "`notes/Makefile`, `notes/Makefile.md`" in result.json()["diagnostics"][0]["message"]


def test_a_broken_symlink_is_not_a_file_a_link_can_name(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "[[Ghost]] [g](Ghost)\n"})
    try:
        (kb / "notes" / "Ghost").symlink_to(kb / "notes" / "nowhere")
    except OSError:
        pytest.skip("symbolic links are not available")

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 4, "links/unresolved")] * 2


def test_resolution_does_not_depend_on_the_order_of_links(charter, make_kb):
    notes = {"blobs/1.dat": "x", "Makefile": "x", "other.png": "x"}
    first = "[[nope]] ![[blobs/1.dat]] [[Makefile]] [[other.png]] [[Nope Two]]\n"
    second = "[[Nope Two]] [[other.png]] [[Makefile]] ![[blobs/1.dat]] [[nope]]\n"

    one = _validate(charter, _kb(make_kb, {**notes, "Index.md": PAGE + first}))
    two = _validate(charter, _kb(make_kb, {**notes, "Index.md": PAGE + second}))

    assert sorted(d["message"] for d in one.json()["diagnostics"]) == sorted(
        d["message"] for d in two.json()["diagnostics"]
    )
    assert len(one.json()["diagnostics"]) == 2


def test_wikilink_to_a_note_with_its_extension_in_a_markdown_only_contract_has_a_clean_hint(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Home.md": PAGE, "Rock.md": "---\nkind: thing\nanywhere: '[[Home.md]]'\n---\n"},
        top=STYLES["markdown"],
    )

    hint = _messages(_validate(charter, kb))[0][3]

    assert hint == "Write a Markdown link such as `[Home](Home.md)`, or add `wikilink` to `links.styles` in charter.yaml."


# --- listing attachments without checking each ---


def _watch_attachment_checks(monkeypatch):
    """The names of `.dat` files the run asked the file system about."""
    seen = []
    real = Path.is_file

    def counting(self, *args, **kwargs):
        if self.suffix == ".dat":
            seen.append(self.name)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", counting)
    return seen


def _bulky_kb(make_kb, note):
    notes = {f"blobs/{n}.dat": "x" for n in range(40)}
    notes["Index.md"] = note
    kb = _kb(make_kb, notes)
    assert len(list((kb / "notes" / "blobs").iterdir())) == 40
    return kb


def test_attachments_are_not_checked_when_no_link_reaches_one(charter, make_kb, monkeypatch):
    kb = _bulky_kb(make_kb, PAGE + "[[Index]] [self](Index.md) [[#Top]]\n")
    seen = _watch_attachment_checks(monkeypatch)

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout
    assert seen == []


def test_only_the_attachments_a_link_names_are_checked(charter, make_kb, monkeypatch):
    kb = _bulky_kb(make_kb, PAGE + "![[blobs/3.dat]] [b](blobs/4.dat) [[7.dat]]\n")
    seen = _watch_attachment_checks(monkeypatch)

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout
    assert sorted(set(seen)) == ["3.dat", "4.dat", "7.dat"]
