import pytest
from conftest import FIXTURES


def _kb(make_kb, tags_yaml, notes):
    contract = (
        "charter: 1\nroot: notes\n"
        f"{tags_yaml}"
        "common_fields: [tags]\n"
        "kinds:\n  entry:\n    fields:\n      kind: {type: string, required: true}\n"
    )
    files = {"charter.yaml": contract}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


def _tagged(diagnostics):
    return [(d["path"], d["line"], d["message"]) for d in diagnostics if d["code"] == "tags/not-allowed"]


def _note(tags=None, body=""):
    front = "---\nkind: entry\n" + (f"tags: {tags}\n" if tags is not None else "") + "---\n"
    return front + body


def test_tags_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "tags")

    assert result.exit_code == 1
    golden("tags", result.json())


def test_frontmatter_tags_outside_the_allowlist_are_reported(charter, make_kb):
    kb = _kb(make_kb, 'tags: {allow: ["cross/*", draft]}\n', {"a.md": _note("[cross/sea, draft, misc, cross]")})

    result = _validate(charter, kb)

    assert result.exit_code == 1
    assert _tagged(result.json()["diagnostics"]) == [
        ("notes/a.md", 3, "Tag `cross` is not allowed; `tags.allow` permits `cross/*`, `draft`."),
        ("notes/a.md", 3, "Tag `misc` is not allowed; `tags.allow` permits `cross/*`, `draft`."),
    ]
    hint = result.json()["diagnostics"][0]["hint"]
    assert hint == "Use an allowed tag, or add a glob matching `cross` to `tags.allow` in charter.yaml."


def test_without_an_allowlist_no_tag_is_reported(charter, make_kb):
    kb = _kb(make_kb, "tags: {inline: true}\n", {"a.md": _note("[anything, at/all]", "Body #whatever\n")})

    result = _validate(charter, kb)

    assert result.exit_code == 0
    assert result.json()["diagnostics"] == []


def test_without_a_tags_section_no_tag_is_reported(charter, make_kb):
    kb = _kb(make_kb, "", {"a.md": _note("[anything]")})

    result = _validate(charter, kb)

    assert result.json()["diagnostics"] == []


@pytest.mark.parametrize(
    ("glob", "tag", "allowed"),
    [
        ("cross/*", "cross/sea", True),
        ("cross/*", "cross/sea/deep", False),
        ("cross/**", "cross/sea/deep", True),
        ("cross/*", "Cross/sea", False),
        ("?ea", "sea", True),
        ("draft", "drafts", False),
    ],
)
def test_globs_match_tags_level_by_level_like_path_globs(charter, make_kb, glob, tag, allowed):
    kb = _kb(make_kb, f'tags: {{allow: ["{glob}"]}}\n', {"a.md": _note(f"[{tag}]")})

    result = _validate(charter, kb)

    assert bool(_tagged(result.json()["diagnostics"])) is not allowed


def test_a_single_tag_value_and_hash_prefixed_values_are_read_as_tags(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: [draft]}\n", {
        "a.md": _note("draft"),
        "b.md": _note('"#draft"'),
        "c.md": _note("misc"),
        "d.md": _note("draft, misc"),
    })

    result = _validate(charter, kb)

    assert [(path, message.split(";")[0]) for path, _, message in _tagged(result.json()["diagnostics"])] == [
        ("notes/c.md", "Tag `misc` is not allowed"),
        ("notes/d.md", "Tag `misc` is not allowed"),
    ]


@pytest.mark.parametrize("tags", ['"draft misc"', '"draft,misc"', '["draft misc"]', '["draft, misc"]'])
def test_text_and_list_values_split_into_tags_alike(charter, make_kb, tags):
    kb = _kb(make_kb, "tags: {allow: [draft]}\n", {"a.md": _note(tags)})

    result = _validate(charter, kb)

    assert [message.split(";")[0] for _, _, message in _tagged(result.json()["diagnostics"])] == [
        "Tag `misc` is not allowed",
    ]


@pytest.mark.parametrize(
    ("tags", "body", "reported"),
    [
        ("[voyage/]", "", "voyage"),
        (None, "Off #voyage/ now\n", "voyage"),
        ("[voyage//north]", "", "voyage//north"),
        (None, "Off #voyage//north now\n", "voyage//north"),
        ("[/north]", "", "/north"),
    ],
)
def test_trailing_slashes_are_dropped_and_empty_levels_never_match(charter, make_kb, tags, body, reported):
    kb = _kb(make_kb, 'tags: {allow: ["voyage/*", "*/*/*", "*/*"], inline: true}\n', {"a.md": _note(tags, body)})

    result = _validate(charter, kb)

    assert [message.split(";")[0] for _, _, message in _tagged(result.json()["diagnostics"])] == [
        f"Tag `{reported}` is not allowed",
    ]


def test_hashes_followed_only_by_digits_dashes_or_slashes_are_not_tags(charter, make_kb):
    body = "A #- B #-- C #1-2 D #/ E #12/3\n"
    kb = _kb(make_kb, "tags: {allow: [draft], inline: true}\n", {"a.md": _note('["-", "#", "12/3"]', body)})

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == []


def test_non_text_tag_values_are_not_tags(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: [draft]}\n", {"a.md": _note("[draft, 7, null]"), "b.md": _note("{a: b}")})

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == []


def test_inline_tags_are_ignored_unless_enabled(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: [draft]}\n", {"a.md": _note(body="Some #misc text.\n")})

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == []


def test_inline_tags_are_checked_when_enabled(charter, make_kb):
    body = (
        "# Heading is not a tag\n"   # line 4
        "Text #misc and #draft.\n"   # line 5
        "#cross/sea starts a line\n"  # line 6
        "\n"
        "#misc twice\n"               # line 8
    )
    kb = _kb(make_kb, 'tags: {allow: [draft], inline: true}\n', {"a.md": _note(body=body)})

    result = _validate(charter, kb)

    assert [(line, message.split(";")[0]) for _, line, message in _tagged(result.json()["diagnostics"])] == [
        (5, "Tag `misc` is not allowed"),
        (6, "Tag `cross/sea` is not allowed"),
        (8, "Tag `misc` is not allowed"),
    ]


def test_hashes_that_are_not_tags_are_ignored(charter, make_kb):
    body = (
        "See [[Other#Heading]], [x](other.md#part), [[#Local]] and a#b.\n"
        "Issue #123 is a number, \\#escaped is escaped, `#code` is code.\n"
        "<!-- #comment -->\n"
        "```\n#fenced\n```\n"
        "\n    #indented\n"
        "## Heading\n"
    )
    kb = _kb(make_kb, "tags: {allow: [draft], inline: true}\n", {"a.md": _note(body=body)})

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == []


def test_tags_are_checked_on_notes_without_a_kind(charter, make_kb):
    kb = make_kb({
        "charter.yaml": (
            "charter: 1\ntags: {allow: [draft], inline: true}\n"
            "paths: {\"Inbox/**\": {untyped: allow}}\nkinds: {}\n"
        ),
        "Inbox/loose.md": "Loose #misc\n",
    })

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == [
        ("Inbox/loose.md", 1, "Tag `misc` is not allowed; `tags.allow` permits `draft`."),
    ]


def test_an_empty_allowlist_allows_no_tags(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: []}\n", {"a.md": _note("[draft]")})

    result = _validate(charter, kb)

    assert _tagged(result.json()["diagnostics"]) == [
        ("notes/a.md", 3, "Tag `draft` is not allowed; `tags.allow` is empty, so no tags are allowed."),
    ]


def test_file_mode_checks_only_the_targeted_notes(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: [draft]}\n", {"a.md": _note("[misc]"), "b.md": _note("[misc]")})

    result = charter("validate", "--profile", "ci", "--format", "json", "--file", "notes/b.md", cwd=kb)

    assert [path for path, _, _ in _tagged(result.json()["diagnostics"])] == ["notes/b.md"]


@pytest.mark.parametrize(
    ("tags_yaml", "message"),
    [
        ("tags: [draft]\n", "tags: expected a mapping"),
        ("tags: {allow: draft}\n", "tags.allow: expected a list"),
        ("tags: {allow: ['']}\n", "tags.allow.0: must not be empty"),
        ("tags: {allow: [draft, draft]}\n", "tags.allow: must not repeat a value"),
        ("tags: {inline: yes please}\n", "tags.inline: expected true or false"),
        ("tags: {allowed: [draft]}\n", "tags: unknown key `allowed`"),
    ],
)
def test_malformed_tags_settings_are_contract_errors(charter, make_kb, tags_yaml, message):
    kb = _kb(make_kb, tags_yaml, {})

    result = _validate(charter, kb)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    assert diagnostic["line"] == 3
    assert diagnostic["message"].startswith(message)


def test_the_tags_check_can_be_turned_off(charter, make_kb):
    kb = _kb(make_kb, "tags: {allow: [draft]}\nchecks: {agents-include: {enabled: false}, tags: {enabled: false}}\n", {"a.md": _note("[misc]")})

    result = _validate(charter, kb)

    assert result.json()["diagnostics"] == []
