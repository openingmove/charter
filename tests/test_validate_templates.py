import pytest
from conftest import FIXTURES


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, kind_yaml, files, top=""):
    contract = f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_yaml}"
    return make_kb({"charter.yaml": contract, **{f"notes/{path}": text for path, text in files.items()}})


def _validate(charter, kb):
    return charter("validate", "--profile", "ci", "--format", "json", cwd=kb)


IGNORE_TEMPLATES = 'paths:\n  "Templates/**": {ignore: true}\n'
ENTRY = (
    "    template: Templates/Entry.md\n"
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      title: {type: string, required: true}\n"
    "      mood: {type: string}\n"
)


def _note(body, **fields):
    lines = "".join(f"{name}: {value}\n" for name, value in {"title": "A", **fields}.items())
    return f"---\nkind: entry\n{lines}---\n{body}"


def test_templates_fixture(charter, golden):
    result = _validate(charter, FIXTURES / "templates")

    assert result.exit_code == 1
    golden("templates", result.json())


def _contract_error(result):
    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    return diagnostic


# --- loading templates ---


def test_a_template_that_names_only_fields_loads(charter, make_kb):
    template = "# {{title}}\n\nWritten {{date}} in a {{ mood }} mood.\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template, "a.md": _note("# A\n")}, IGNORE_TEMPLATES)

    result = _validate(charter, kb)

    assert result.exit_code == 0, result.stdout


def test_a_template_with_frontmatter_is_a_contract_error(charter, make_kb):
    template = "---\nkind: entry\n---\n# {{title}}\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template}, IGNORE_TEMPLATES)

    diagnostic = _contract_error(_validate(charter, kb))

    assert diagnostic["line"] == 7
    assert diagnostic["message"] == (
        "kinds.entry.template: `notes/Templates/Entry.md` has frontmatter; frontmatter belongs in charter.yaml."
    )


def test_a_placeholder_naming_no_field_is_a_contract_error(charter, make_kb):
    template = "# {{title}}\n\nIn a {{mod}} mood.\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template}, IGNORE_TEMPLATES)

    diagnostic = _contract_error(_validate(charter, kb))

    assert diagnostic["message"] == (
        "kinds.entry.template: `{{mod}}` (`notes/Templates/Entry.md` line 3) is not a field of `entry`."
    )
    assert diagnostic["hint"] == "Did you mean `mood`?"


def test_placeholders_in_comments_are_checked_but_not_those_in_code(charter, make_kb):
    template = "<!-- guide: say how {{mod}} it was -->\n\n```\n{{anything}}\n```\nUse `{{literal}}` here.\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template}, IGNORE_TEMPLATES)

    diagnostic = _contract_error(_validate(charter, kb))

    assert "`{{mod}}` (`notes/Templates/Entry.md` line 1)" in diagnostic["message"]


@pytest.mark.parametrize(
    "template, message",
    [
        ("Missing.md", "kinds.entry.template: `notes/Missing.md` does not exist."),
        ("../../x.md", "kinds.entry.template: `../../x.md` is outside the directory holding charter.yaml."),
        ("/tmp/x.md", "kinds.entry.template: `/tmp/x.md` is outside the directory holding charter.yaml."),
    ],
)
def test_a_template_must_be_a_file_inside_the_contract_directory(charter, make_kb, template, message):
    kind = ENTRY.replace("Templates/Entry.md", template)
    kb = _kb(make_kb, kind, {"a.md": _note("")})

    assert _contract_error(_validate(charter, kb))["message"] == message


def test_a_template_that_is_not_utf8_is_a_contract_error(charter, make_kb):
    kb = _kb(make_kb, ENTRY, {}, IGNORE_TEMPLATES)
    (kb / "notes/Templates").mkdir(parents=True)
    (kb / "notes/Templates/Entry.md").write_bytes(b"\xff\xfe# x\n")

    diagnostic = _contract_error(_validate(charter, kb))

    assert diagnostic["message"] == "kinds.entry.template: `notes/Templates/Entry.md` is not valid UTF-8 text."


def test_a_marker_that_follows_no_heading_is_a_contract_error(charter, make_kb):
    template = "Intro text.\n<!-- optional -->\n\n## Notes\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template}, IGNORE_TEMPLATES)

    diagnostic = _contract_error(_validate(charter, kb))

    assert diagnostic["message"] == (
        "kinds.entry.template: `<!-- optional -->` (`notes/Templates/Entry.md` line 2) follows no heading."
    )


VARIANTS = (
    "    template: Templates/Entry.md\n"
    "    fields:\n"
    "      kind: {type: string, required: true}\n"
    "      title: {type: string, required: true}\n"
    "      form: {type: string}\n"
    "    variants:\n"
    "      poem:\n"
    "        set: {form: poem}\n"
    "        template: Templates/Poem.md\n"
    "        fields:\n"
    "          metre: {type: string}\n"
    "      essay:\n"
    "        set: {form: essay}\n"
)


def test_a_variant_template_may_name_the_variants_fields(charter, make_kb):
    files = {"Templates/Entry.md": "# {{title}}\n", "Templates/Poem.md": "# {{title}} in {{metre}}\n"}

    assert _validate(charter, _kb(make_kb, VARIANTS, files, IGNORE_TEMPLATES)).exit_code == 0


def test_a_kind_template_may_not_name_a_variants_field(charter, make_kb):
    files = {"Templates/Entry.md": "# {{metre}}\n", "Templates/Poem.md": "# {{title}}\n"}

    diagnostic = _contract_error(_validate(charter, _kb(make_kb, VARIANTS, files, IGNORE_TEMPLATES)))

    assert diagnostic["message"].startswith("kinds.entry.template: `{{metre}}`")


def test_a_variant_template_is_checked_against_the_variant(charter, make_kb):
    files = {"Templates/Entry.md": "# {{title}}\n", "Templates/Poem.md": "# {{metr}}\n"}

    diagnostic = _contract_error(_validate(charter, _kb(make_kb, VARIANTS, files, IGNORE_TEMPLATES)))

    assert diagnostic["message"] == (
        "kinds.entry.variants.poem.template: `{{metr}}` (`notes/Templates/Poem.md` line 1) "
        "is not a field of `entry/poem`."
    )


# --- structure ---

OUTLINE = (
    "# {{title}}\n"
    "<!-- guide: one line on what happened -->\n"
    "## Context\n"
    "## Details <!-- optional -->\n"
    "## Day {{date}}\n"
    "<!-- repeat -->\n"
    "## Outcome\n"
)


def _structure(charter, make_kb, body, template=OUTLINE):
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": template, "a.md": _note(body)}, IGNORE_TEMPLATES)
    result = _validate(charter, kb)
    return [(d["line"], d["code"]) for d in result.json()["diagnostics"] if d["path"] == "notes/a.md"]


@pytest.mark.parametrize(
    "body",
    [
        "# A\n## Context\n## Details\n## Day 1\n## Day 2\n## Outcome\n",
        "# A\n## Context\n## Outcome\n",
        "# A\nIntro\n## Context\n### Aside\n## Day one\n### Notes\n## Day two\n## Outcome\n## Appendix\n",
        "# A\n## Context <!-- optional -->\n## Outcome\n",
    ],
    ids=["everything", "optional and repeat absent", "extra headings", "comments in headings"],
)
def test_a_note_keeping_the_outline_has_no_structure_findings(charter, make_kb, body):
    assert _structure(charter, make_kb, body) == []


def test_a_missing_required_heading_is_reported(charter, make_kb):
    kb = _kb(
        make_kb, ENTRY, {"Templates/Entry.md": OUTLINE, "a.md": _note("# A\n## Context\n## Day 1\n")}, IGNORE_TEMPLATES
    )

    result = _validate(charter, kb)

    assert result.exit_code == 1
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["path"], diagnostic["line"], diagnostic["code"]) == (
        "notes/a.md",
        None,
        "structure/missing-heading",
    )
    assert diagnostic["message"] == "Heading `## Outcome` from the template `notes/Templates/Entry.md` is missing."
    assert diagnostic["hint"] == "Add `## Outcome` after the `## Day 1` section."


def test_a_heading_at_the_wrong_level_is_missing(charter, make_kb):
    assert _structure(charter, make_kb, "# A\n### Context\n## Outcome\n") == [(None, "structure/missing-heading")]


def test_a_heading_out_of_template_order_is_reported(charter, make_kb):
    kb = _kb(
        make_kb,
        ENTRY,
        {"Templates/Entry.md": OUTLINE, "a.md": _note("# A\n## Outcome\n## Context\n## Details\n")},
        IGNORE_TEMPLATES,
    )

    diagnostics = _validate(charter, kb).json()["diagnostics"]

    assert [(d["line"], d["code"]) for d in diagnostics] == [
        (7, "structure/heading-order"),
        (8, "structure/heading-order"),
    ]
    assert diagnostics[0]["message"] == "`## Context` is out of order: the template puts it before `## Outcome`."
    assert diagnostics[0]["hint"] == "Move the `## Context` section above `## Outcome` (line 6)."


def test_a_placeholder_heading_out_of_place_is_extra(charter, make_kb):
    assert _structure(charter, make_kb, "# A\n## Context\n## Outcome\n## Day 1\n") == []


def test_diagnostics_show_headings_as_rendered(charter, make_kb):
    template = "# {{title}}\n## Next steps\n"
    files = {"Templates/Entry.md": template, "a.md": _note("# A\n## Next steps\n## Next <!-- x --> steps\n")}

    [repeated] = _validate(charter, _kb(make_kb, ENTRY, files, IGNORE_TEMPLATES)).json()["diagnostics"]

    assert repeated["message"].startswith("`## Next steps` appears more than once;")


def test_a_repeat_heading_must_keep_its_place(charter, make_kb):
    template = "# {{title}}\n## Day\n<!-- repeat -->\n## Outcome\n"
    body = "# A\n## Day\n## Day\n## Outcome\n## Day\n"

    assert _structure(charter, make_kb, body, template) == [(9, "structure/heading-order")]


def test_a_placeholder_heading_matches_once_and_further_headings_are_extra(charter, make_kb):
    template = "# {{title}}\n## Context\n"

    assert _structure(charter, make_kb, "# D\n# Something else\n## Context\n", template) == []


def test_a_placeholder_heading_matches_only_in_sequence(charter, make_kb):
    template = "# {{title}}\n## Intro\n## {{mood}}\n## End\n"
    body = "# T\n## Extra\n## Intro\n## Calm\n## Also extra\n## End\n"

    assert _structure(charter, make_kb, body, template) == []


@pytest.mark.parametrize(
    "body, expected",
    [
        ("# B\n## Summary\n## Summary\n## End\n", [(7, "structure/repeated-heading")]),
        (
            "# B\n## End\n## Summary\n## Summary\n",
            [(7, "structure/heading-order"), (8, "structure/repeated-heading")],
        ),
    ],
    ids=["in place", "after a later section"],
)
def test_a_duplicate_heading_is_repeated_wherever_it_appears(charter, make_kb, body, expected):
    template = "# {{title}}\n## Summary\n## End\n"

    assert _structure(charter, make_kb, body, template) == expected


def test_a_heading_without_repeat_may_appear_once(charter, make_kb):
    diagnostics = _structure(charter, make_kb, "# A\n## Context\n## Context\n## Outcome\n")

    assert diagnostics == [(7, "structure/repeated-heading")]


def test_a_variant_note_keeps_the_variants_outline(charter, make_kb):
    files = {
        "Templates/Entry.md": "# {{title}}\n## Body\n",
        "Templates/Poem.md": "# {{title}}\n## Verses\n",
        "a.md": _note("# A\n## Verses\n", form="poem"),
        "b.md": _note("# B\n## Verses\n", form="essay"),
    }

    result = _validate(charter, _kb(make_kb, VARIANTS, files, IGNORE_TEMPLATES))

    assert _codes(result) == [("notes/b.md", None, "structure/missing-heading")]


def test_notes_of_kinds_without_a_template_have_no_structure(charter, make_kb):
    kind = ENTRY.replace("    template: Templates/Entry.md\n", "")

    assert _validate(charter, _kb(make_kb, kind, {"a.md": _note("## Anything\n")})).exit_code == 0


def test_structure_findings_are_warnings_while_editing(charter, make_kb):
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": OUTLINE, "a.md": _note("# A\n")}, IGNORE_TEMPLATES)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0
    assert {d["severity"] for d in result.json()["diagnostics"]} == {"warning"}


# --- residue ---

PLAIN = "# {{title}}\n"


def test_leftover_guidance_and_placeholders_are_reported(charter, make_kb):
    body = "# A\n<!-- guide: one line on\nwhat happened -->\nIt was {{mood}}, on {{ date }}.\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": PLAIN, "a.md": _note(body)}, IGNORE_TEMPLATES)

    result = _validate(charter, kb)

    assert result.exit_code == 1
    diagnostics = result.json()["diagnostics"]
    assert [(d["line"], d["code"]) for d in diagnostics] == [
        (6, "residue/guide"),
        (8, "residue/placeholder"),
        (8, "residue/placeholder"),
    ]
    assert diagnostics[0]["message"] == "Guide comment left in the note: `one line on what happened`."
    assert diagnostics[0]["hint"] == "Follow the guidance, then delete the comment."
    assert diagnostics[2]["message"] == "Placeholder `{{mood}}` left in the note."
    assert diagnostics[1]["hint"] == "Replace it with the note's own text."


def test_residue_ignores_code_and_other_comments(charter, make_kb):
    body = "# A\nUse `{{mood}}` or <!-- {{mood}} -->.\n```\n<!-- guide: x -->\n{{mood}}\n```\n<!-- guidebook -->\n"
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": PLAIN, "a.md": _note(body)}, IGNORE_TEMPLATES)

    assert _validate(charter, kb).exit_code == 0


def test_residue_is_reported_in_every_note(charter, make_kb):
    kind = ENTRY.replace("    template: Templates/Entry.md\n", "")
    files = {"a.md": _note("{{mood}} <!-- guide: x -->\n"), "Inbox/b.md": "Left: {{mood}}\n"}
    kb = _kb(make_kb, kind, files, 'paths:\n  "Inbox/**": {untyped: allow}\n')

    assert _codes(_validate(charter, kb)) == [
        ("notes/Inbox/b.md", 1, "residue/placeholder"),
        ("notes/a.md", 5, "residue/guide"),
        ("notes/a.md", 5, "residue/placeholder"),
    ]


@pytest.mark.parametrize("key", ["structure", "residue", "structure/heading-order", "residue/guide"])
def test_profiles_and_checks_may_name_the_template_checks(charter, make_kb, key):
    check = key.split("/")[0]
    top = IGNORE_TEMPLATES + (
        f"checks:\n  agents-include: {{enabled: false}}\n  {check}: {{severity: info}}\nprofiles:\n  ci: {{{key}: off}}\n"
    )
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": PLAIN, "a.md": _note("# A\n")}, top)

    assert _validate(charter, kb).exit_code == 0


# --- placeholders inside code spans are literal ---

CODE_SPAN_TEMPLATE = "# {{title}}\n## `{{title}}` Z\n"


def test_a_code_span_placeholder_heading_matches_literally(charter, make_kb):
    assert _structure(charter, make_kb, "# A\n## `{{title}}` Z\n", CODE_SPAN_TEMPLATE) == []


def test_a_code_span_placeholder_heading_is_not_a_wildcard(charter, make_kb):
    kb = _kb(
        make_kb,
        ENTRY,
        {"Templates/Entry.md": CODE_SPAN_TEMPLATE, "a.md": _note("# A\n## `x` Z\n")},
        IGNORE_TEMPLATES,
    )

    [diagnostic] = _validate(charter, kb).json()["diagnostics"]

    assert diagnostic["code"] == "structure/missing-heading"
    assert diagnostic["message"] == (
        "Heading `` ## `{{title}}` Z `` from the template `notes/Templates/Entry.md` is missing."
    )
    assert diagnostic["hint"] == "Add `` ## `{{title}}` Z `` after the `# A` section."


def test_a_code_span_placeholder_is_not_checked_as_a_field(charter, make_kb):
    kb = _kb(make_kb, ENTRY, {"Templates/Entry.md": "# {{title}}\n## `{{nope}}` Z\n"}, IGNORE_TEMPLATES)

    assert _validate(charter, kb).exit_code == 0
