import pytest
from conftest import FIXTURES

from links_support import KINDS, PAGE, codes as _codes, kb as _kb, validate as _validate  # noqa: F401


def test_links_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "links")

    assert result.exit_code == 1
    golden("links", result.json())


# --- markdown links ---


def test_markdown_links_resolve_relative_to_the_note_with_md_optional(charter, make_kb):
    kb = _kb(make_kb, {
        "Places/Harbour.md": PAGE,
        "Places/Old Mill.md": PAGE,
        "Index.md": PAGE + (
            "[a](Places/Harbour.md) [b](Places/Harbour) [c](<Places/Old Mill.md>) [d](Places/Old%20Mill)\n"
            '[e](./Places/Harbour.md "title")\n'
        ),
        "Places/Sub/Deep.md": PAGE + "[up](../Harbour.md) [root](../../Index)\n",
    })

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_broken_markdown_link_is_unresolved_at_its_line(charter, make_kb):
    kb = _kb(make_kb, {
        "Places/Harbour.md": PAGE,
        "Index.md": PAGE
        + "\nIntro.\n[ok](Places/Harbour.md) and [broken](Places/Harbor.md)\n[out](../../elsewhere.md)\n",
    })

    result = _validate(charter, kb)

    assert result.exit_code == 1
    assert _codes(result) == [("notes/Index.md", 6, "links/unresolved"), ("notes/Index.md", 7, "links/unresolved")]
    first = result.json()["diagnostics"][0]
    assert "`[broken](Places/Harbor.md)`" in first["message"]


def test_unresolved_message_quotes_a_code_span_link_text_as_written(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "See [`foo`](missing.md) and [a `b` c](nowhere.md).\n"})

    messages = [d["message"] for d in _validate(charter, kb).json()["diagnostics"]]

    assert messages == [
        "Link `` [`foo`](missing.md) `` does not resolve to a file.",
        "Link `` [a `b` c](nowhere.md) `` does not resolve to a file.",
    ]


# Text before the link that shortens or lengthens lines in the blanked view: the quote must still be the note's own.
BEFORE = {
    "fence": "```\ncode line one\ncode line two ``\n```\n",
    "indented": "    indented code\n    more code\n\n",
    "comment": "<!-- a comment\nspanning lines -->\n",
    "crlf-multibyte": "Zażółć 値 `x`\t text\n",
    "nothing": "",
}


@pytest.mark.parametrize("before", BEFORE.values(), ids=BEFORE.keys())
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_messages_quote_links_as_written_after_code_and_comments(charter, make_kb, before, newline):
    plain, spanned, anchored, plain_anchor = "[plain](x.md)", "[`foo` bar](missing.md)", "[a `b`](Target.md#nope)", "[[Target#nope]]"
    body = f"{before}A `code` and {plain} then {spanned} and {anchored} {plain_anchor} [[Dup]] end"
    kb = _kb(
        make_kb,
        {
            "Target.md": PAGE + "# Target\n",
            "One/Dup.md": PAGE,
            "Two/Dup.md": PAGE,
            "Index.md": (PAGE + body).replace("\n", newline),
        },
        top="links: {check_anchors: true}\n",
    )

    diagnostics = _validate(charter, kb).json()["diagnostics"]
    messages = {d["code"]: [] for d in diagnostics}
    for d in diagnostics:
        messages[d["code"]].append(d["message"])

    assert messages["links/unresolved"] == [
        "Link `[plain](x.md)` does not resolve to a file.",
        "Link `` [`foo` bar](missing.md) `` does not resolve to a file.",
    ]
    assert sorted(m.split(", which")[0] for m in messages["links/missing-anchor"]) == sorted([
        "Link `` [a `b`](Target.md#nope) `` points at heading `nope`",
        "Link `[[Target#nope]]` points at heading `nope`",
    ])
    assert messages["links/ambiguous"][0].startswith("Link `[[Dup]]` is ambiguous")


def test_external_urls_and_attachments_are_not_broken(charter, make_kb):
    kb = _kb(make_kb, {
        "Index.md": PAGE + (
            "[web](https://example.com/a.md) [mail](mailto:someone@example.com) ![img](media/map.png)\n"
            "![[map.png]] [[media/map.png]]\n"
        ),
        "media/map.png": "binary-ish",
    })

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_missing_attachment_is_unresolved(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "![img](media/map.png)\n"})

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 4, "links/unresolved")]


def test_markdown_link_to_an_ignored_note_by_path_resolves(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Index.md": PAGE + "[template](Templates/Page.md)\n", "Templates/Page.md": "Template body.\n"},
        top='paths:\n  "Templates/**": {ignore: true}\n',
    )

    assert _validate(charter, kb).exit_code == 0


# --- wikilinks ---


def test_wikilinks_resolve_by_path_basename_and_alias(charter, make_kb):
    kb = _kb(make_kb, {
        "Places/Harbour.md": "---\nkind: page\naliases: [The Docks]\n---\n",
        "Index.md": PAGE + "[[Harbour]] [[Places/Harbour]] [[Places/Harbour.md]] [[Harbour|the harbour]]\n"
        "[[The Docks]] [[Harbour#Top]] | [[Harbour\\|in a table]] |\n",
    })

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_unresolved_wikilink_suggests_a_close_name(charter, make_kb):
    kb = _kb(make_kb, {"Places/Harbour.md": PAGE, "Index.md": PAGE + "[[Harbor]]\n"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/unresolved")]
    assert "`Harbour`" in result.json()["diagnostics"][0]["hint"]


def test_ambiguous_basename_is_its_own_diagnostic(charter, make_kb):
    kb = _kb(make_kb, {
        "Places/Canal.md": PAGE,
        "Zones/Canal.md": PAGE,
        "Index.md": PAGE + "[[Canal]] [[Zones/Canal]]\n",
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/ambiguous")]
    message = result.json()["diagnostics"][0]["message"]
    assert "`notes/Places/Canal.md`" in message and "`notes/Zones/Canal.md`" in message


def test_ambiguous_alias(charter, make_kb):
    kb = _kb(make_kb, {
        "A.md": "---\nkind: page\naliases: [Twin]\n---\n",
        "B.md": "---\nkind: page\naliases: Twin\n---\n",
        "Index.md": PAGE + "[[Twin]]\n",
    })

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 4, "links/ambiguous")]


def test_resolution_order_decides_before_ambiguity(charter, make_kb):
    notes = {
        "Canal.md": PAGE,
        "Zones/Canal.md": PAGE,
        "Index.md": PAGE + "[[Canal]]\n",
    }
    in_order = _kb(make_kb, notes)

    assert _validate(charter, in_order).exit_code == 0


def test_resolve_setting_limits_the_strategies(charter, make_kb):
    kb = _kb(
        make_kb,
        {
            "Places/Harbour.md": "---\nkind: page\naliases: [Docks]\n---\n",
            "Index.md": PAGE + "[[Harbour]]\n[[Places/Harbour]]\n[[Docks]]\n",
        },
        top="links: {resolve: [basename]}\n",
    )

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 5, "links/unresolved"), ("notes/Index.md", 6, "links/unresolved")]


def test_heading_only_wikilink_points_at_its_own_note(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Index.md": PAGE + "## Here\n[[#Here]] [[#Gone]] [x](#here)\n"},
        top="links: {check_anchors: true}\n",
    )

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 5, "links/missing-anchor")]


# --- anchors ---


def test_anchors_are_checked_only_when_enabled(charter, make_kb):
    notes = {
        "Harbour.md": PAGE + "# Harbour\n## Opening Hours\n```\n## Not a heading\n```\n",
        "Index.md": PAGE + (
            "[a](Harbour.md#opening-hours) [b](Harbour#harbour) [[Harbour#Opening Hours]]\n"
            "[c](Harbour.md#closing-hours)\n"
            "[[Harbour#Not a heading]]\n"
            "[[Harbour#^block-id]]\n"
        ),
    }

    assert _validate(charter, _kb(make_kb, notes)).exit_code == 0

    checked = _kb(make_kb, notes, top="links: {check_anchors: true}\n")
    result = _validate(charter, checked)
    assert _codes(result) == [
        ("notes/Index.md", 5, "links/missing-anchor"),
        ("notes/Index.md", 6, "links/missing-anchor"),
    ]
    assert "`opening-hours`" in result.json()["diagnostics"][0]["hint"]


def test_anchors_name_headings_as_rendered_without_comments(charter, make_kb):
    notes = {
        "Harbour.md": PAGE + "## Tides <!-- optional -->\n<!--\n## Hidden\n-->\n",
        "Index.md": PAGE + "[[Harbour#Tides]]\n[[Harbour#Hidden]]\n",
    }

    result = _validate(charter, _kb(make_kb, notes, top="links: {check_anchors: true}\n"))

    assert _codes(result) == [("notes/Index.md", 5, "links/missing-anchor")]


# --- styles and code ---


def test_only_configured_styles_count(charter, make_kb):
    notes = {"Index.md": PAGE + "[[Missing]]\n[gone](Missing.md)\n"}

    wikilinks_only = _validate(charter, _kb(make_kb, notes, top="links: {styles: [wikilink]}\n"))
    assert _codes(wikilinks_only) == [("notes/Index.md", 4, "links/unresolved")]

    markdown_only = _validate(charter, _kb(make_kb, notes, top="links: {styles: [markdown]}\n"))
    assert _codes(markdown_only) == [("notes/Index.md", 5, "links/unresolved")]


def test_links_in_code_are_ignored(charter, make_kb):
    kb = _kb(make_kb, {
        "Index.md": PAGE + (
            "Use `[[Missing]]` or ``[x](missing.md)`` inline.\n"
            "```markdown\n[[Missing]]\n[x](missing.md)\n```\n"
            "~~~~\n```\n[[Missing]]\n~~~~\n"
            "After the fence: [[Gone]]\n"
        ),
    })

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 13, "links/unresolved")]


def test_crlf_note_links_resolve(charter, make_kb):
    kb = _kb(make_kb, {"A.md": PAGE, "Index.md": "---\r\nkind: page\r\n---\r\n[[A]] [a](A.md)\r\n[[B]]\r\n"})

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 5, "links/unresolved")]


def test_escaped_brackets_are_not_links(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "\\[x](nope.md) and \\[[Nope]]\n"})

    assert _validate(charter, kb).exit_code == 0


def test_destinations_may_hold_balanced_parentheses_or_angle_brackets(charter, make_kb):
    kb = _kb(make_kb, {
        "Places/foo(1).md": PAGE,
        "Places/a (b).md": PAGE,
        "Index.md": PAGE + "[p](Places/foo(1).md) [q](<Places/a (b).md>) [r](Places/foo(2).md \"t\")\n",
    })

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/unresolved")]
    assert "`[r](Places/foo(2).md \"t\")`" in result.json()["diagnostics"][0]["message"]


def test_linked_image_checks_both_links(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "[![i](media/a.png)](Nope.md)\n"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/unresolved")] * 2
    messages = " ".join(d["message"] for d in result.json()["diagnostics"])
    assert "`![i](media/a.png)`" in messages and "`[![i](media/a.png)](Nope.md)`" in messages


def test_ambiguous_attachment_hint_names_a_path_that_resolves(charter, make_kb):
    kb = _kb(make_kb, {"a/map.png": "x", "b/map.png": "x", "Index.md": PAGE + "![[map.png]]\n"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Index.md", 4, "links/ambiguous")]
    assert "`[[a/map.png]]`" in result.json()["diagnostics"][0]["hint"]


def test_ignored_files_are_not_matched_by_name(charter, make_kb):
    kb = _kb(
        make_kb,
        {"media/pic.png": "x", ".obsidian/pic.png": "x", "Index.md": PAGE + "![[pic.png]] [x](.obsidian/pic.png)\n"},
        top='paths:\n  ".obsidian/**": {ignore: true}\n',
    )

    assert _validate(charter, kb).exit_code == 0


def test_code_spans_may_cross_a_line_break(charter, make_kb):
    kb = _kb(make_kb, {"Index.md": PAGE + "Use `code\n[[Nope]]` here.\n\n`unclosed\n\n[[Gone]]`\n"})

    assert _codes(_validate(charter, kb)) == [("notes/Index.md", 9, "links/unresolved")]


def test_indented_code_and_html_comments_are_ignored(charter, make_kb):
    kb = _kb(make_kb, {
        "Index.md": PAGE + (
            "Para.\n"  # 4
            "\n"
            "    [[Nope]]\n"  # 6: indented code
            "\tNope [x](nope.md)\n"
            "\n"
            "<!-- link like [[Example]]\n"  # 9
            "and [x](y.md) -->\n"
            "Text <!-- [[Inline]] --> [[Gone]]\n"  # 11
            "- item\n"
            "\n"
            "    [[Also Gone]]\n"  # 14: list continuation, not code
        ),
    })

    assert _codes(_validate(charter, kb)) == [
        ("notes/Index.md", 11, "links/unresolved"),
        ("notes/Index.md", 14, "links/unresolved"),
    ]


def test_git_directory_is_not_part_of_the_knowledge_base(charter, make_kb):
    kb = make_kb({
        "charter.yaml": f"charter: 1\nroot: .\n{KINDS}",
        ".git/NOTES.md": "Not a note.\n",
        "Index.md": PAGE + "[[NOTES]]\n",
    })

    assert _codes(_validate(charter, kb)) == [("Index.md", 4, "links/unresolved")]


# --- link fields ---


@pytest.mark.parametrize("value", ["'[x](https://example.com/zone)'", "https://example.com/zone"])
def test_link_field_with_a_target_kind_rejects_urls(charter, make_kb, value):
    kb = _kb(make_kb, {"Things/Key.md": f"---\nkind: thing\nzone: {value}\nanywhere: {value}\n---\n"})

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Things/Key.md", 3, "links/wrong-kind")]
    assert "URL" in result.json()["diagnostics"][0]["message"]



def test_link_fields_must_point_at_their_target_kinds(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": "---\nkind: zone\n---\n",
        "People/Ada.md": "---\nkind: npc\n---\n",
        "Things/Key.md": "---\nkind: thing\nzone: '[[Canal]]'\n---\n",
        "Readme.md": "No frontmatter.\n",
        "Things/Lamp.md": (
            "---\n"
            "kind: thing\n"
            "zone: '[[Ada]]'\n"
            "requires: ['[[Key]]', '[[Ada]]', '[[Canal]]', '[[Nowhere]]']\n"
            "anywhere: '[Readme](../Readme.md)'\n"
            "---\n"
        ),
    }, top='paths:\n  "Readme.md": {untyped: allow}\n')

    result = _validate(charter, kb)

    assert _codes(result) == [
        ("notes/Things/Lamp.md", 3, "links/wrong-kind"),
        ("notes/Things/Lamp.md", 4, "links/unresolved"),
        ("notes/Things/Lamp.md", 4, "links/wrong-kind"),
    ]
    wrong = result.json()["diagnostics"][0]
    assert "`notes/People/Ada.md`" in wrong["message"] and "`npc`" in wrong["message"] and "`zone`" in wrong["message"]


def test_link_field_with_a_bare_name_resolves_like_a_wikilink(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": "---\nkind: zone\n---\n",
        "Things/Key.md": "---\nkind: thing\nzone: Canal\n---\n",
        "Things/Lamp.md": "---\nkind: thing\nzone: Canals\n---\n",
    })

    assert _codes(_validate(charter, kb)) == [("notes/Things/Lamp.md", 3, "links/unresolved")]


def test_link_field_to_an_untyped_note_is_the_wrong_kind(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Inbox/Loose.md": "prose\n", "Things/Key.md": "---\nkind: thing\nzone: '[[Loose]]'\n---\n"},
        top='paths:\n  "Inbox/**": {untyped: allow}\n',
    )

    result = _validate(charter, kb)

    assert _codes(result) == [("notes/Things/Key.md", 3, "links/wrong-kind")]
    assert "has no kind" in result.json()["diagnostics"][0]["message"]


def test_non_text_link_field_is_only_a_schema_problem(charter, make_kb):
    kb = _kb(make_kb, {"Things/Key.md": "---\nkind: thing\nzone: 3\n---\n"})

    assert _codes(_validate(charter, kb)) == [("notes/Things/Key.md", 3, "schema/type")]


# --- which notes are checked ---


def test_links_skip_policy_and_untyped_notes(charter, make_kb):
    kb = _kb(
        make_kb,
        {
            "Templates/Page.md": PAGE + "[[{{zone}}]]\n",
            "AGENTS.md": "See [[Missing Guide]].\n",
            "Inbox/Loose.md": "See [gone](gone.md).\n",
        },
        top='paths:\n  "Templates/**": {links: skip}\n  "Inbox/**": {untyped: allow}\n',
    )

    result = _validate(charter, kb)

    assert [found for found in _codes(result) if found[2].startswith("links/")] == [
        ("notes/AGENTS.md", 1, "links/unresolved"),
        ("notes/Inbox/Loose.md", 1, "links/unresolved"),
    ]


def test_skipped_notes_are_still_link_targets(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Templates/Page.md": PAGE, "Index.md": PAGE + "[[Page]]\n"},
        top='paths:\n  "Templates/**": {links: skip}\n',
    )

    assert _validate(charter, kb).exit_code == 0


def test_file_mode_checks_only_the_named_notes_but_resolves_against_all(charter, make_kb):
    kb = _kb(make_kb, {
        "A.md": PAGE + "[[B]] [[Missing]]\n",
        "B.md": PAGE + "[[Also Missing]]\n",
    })

    result = _validate(charter, kb, "--file", "notes/A.md")

    assert _codes(result) == [("notes/A.md", 4, "links/unresolved")]


def test_links_check_can_be_disabled(charter, make_kb):
    kb = _kb(make_kb, {"A.md": PAGE + "[[Missing]]\n"}, top="checks: {agents-include: {enabled: false}, links: {enabled: false}}\n")

    assert _validate(charter, kb).exit_code == 0


# --- contract ---


@pytest.mark.parametrize(
    ("top", "kinds", "line"),
    [
        ("links: {styles: [wiki]}\n", "", 3),
        ("links: {styles: []}\n", "", 3),
        ("links: {resolve: [path, path]}\n", "", 3),
        ("links: {resolve: [title]}\n", "", 3),
        ("links: {check_anchors: maybe}\n", "", 3),
        ("links: {stlyes: [markdown]}\n", "", 3),
        ('paths:\n  "T/**": {links: off}\n', "", 4),
        ("", "  x: {fields: {f: {type: string, to: zone}}}\n", 5),
        ("", "  x: {fields: {f: {type: list, of: int, to: zone}}}\n", 5),
        ("", "  x: {fields: {f: {type: link, to: zoen}}}\n", 5),
        ("", "  x: {fields: {f: {type: list, of: link, to: [zone, nobody]}}}\n", 5),
        ("", "  x: {fields: {f: {type: link, to: []}}}\n", 5),
    ],
)
def test_invalid_link_settings_exit_two(charter, make_kb, top, kinds, line):
    kb = make_kb({"charter.yaml": f"charter: 1\nroot: notes\n{top}kinds:\n  zone: {{}}\n{kinds}", "notes/A.md": PAGE})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2, result.stdout
    assert [(d["line"], d["code"]) for d in result.json()["diagnostics"]] == [(line, "contract/invalid")]
