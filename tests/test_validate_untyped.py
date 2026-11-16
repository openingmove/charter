import pytest

KINDS = "kinds:\n  entry: {fields: {title: {type: string}}}\n"
TYPED = "---\nkind: entry\ntitle: ok\n---\n"


def _codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def _kb(make_kb, notes, top="", root="notes"):
    files = {"charter.yaml": f"charter: 1\nroot: {root}\n{top}{KINDS}"}
    files.update({f"{root}/{path}" if root != "." else path: text for path, text in notes.items()})
    return make_kb(files)


@pytest.mark.parametrize("text", ["Just some prose.\n", "", "# Heading\n\n---\nkind: entry\n---\n"])
def test_markdown_file_without_frontmatter_yields_missing_frontmatter(charter, make_kb, text):
    kb = _kb(make_kb, {"loose.md": text})

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert _codes(result) == [("notes/loose.md", 1, "schema/missing-frontmatter")]
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["severity"] == "error"
    assert "`kind: <kind>`" in diagnostic["hint"]


def test_empty_frontmatter_is_frontmatter_without_a_kind(charter, make_kb):
    kb = _kb(make_kb, {"blank.md": "---\n---\nBody.\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/blank.md", 1, "schema/missing-kind")]


def test_ignored_file_without_frontmatter_is_exempt(charter, make_kb):
    kb = _kb(make_kb, {"Scratch/loose.md": "prose\n"}, top='paths:\n  "Scratch/**": {ignore: true}\n')

    assert charter("validate", cwd=kb).exit_code == 0


def test_untyped_allow_exempts_files_without_frontmatter_but_not_typed_notes(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Inbox/loose.md": "prose\n", "Inbox/typo.md": "---\nkind: entyr\n---\n", "Elsewhere/loose.md": "prose\n"},
        top='paths:\n  "Inbox/**": {untyped: allow}\n',
    )

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [
        ("notes/Elsewhere/loose.md", 1, "schema/missing-frontmatter"),
        ("notes/Inbox/typo.md", 2, "schema/unknown-kind"),
    ]


def test_untyped_allow_composes_with_kinds_on_a_broader_glob(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Research/Raw/loose.md": "prose\n", "Research/Raw/note.md": TYPED},
        top='paths:\n  "Research/**": {kinds: [entry]}\n  "Research/Raw/**": {untyped: allow}\n',
    )

    assert charter("validate", cwd=kb).exit_code == 0


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md", "GEMINI.md"])
def test_default_agent_files_are_exempt_at_any_depth(charter, make_kb, name):
    kb = _kb(make_kb, {name: "Agent guide.\n", f"Deep/Er/{name}": "Folder guide.\n", "note.md": TYPED})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


def test_agent_files_setting_replaces_the_defaults(charter, make_kb):
    kb = _kb(
        make_kb,
        {"AGENTS.md": "Guide.\n", "Deep/HELPERS.md": "Guide.\n"},
        top="agent_files: [HELPERS.md]\n",
    )

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/AGENTS.md", 1, "schema/missing-frontmatter")]


def test_agent_file_name_must_match_exactly(charter, make_kb):
    kb = _kb(make_kb, {"MY-AGENTS.md": "Guide.\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/MY-AGENTS.md", 1, "schema/missing-frontmatter")]


def test_default_generated_rulebook_is_exempt(charter, make_kb):
    kb = _kb(
        make_kb, {"CHARTER.md": "Generated.\n", "Deep/CHARTER.md": "Not generated.\n"}, top="docs: {}\n", root="."
    )

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("Deep/CHARTER.md", 1, "schema/missing-frontmatter")]


def test_configured_rulebook_path_is_exempt_relative_to_the_contract(charter, make_kb):
    kb = _kb(
        make_kb,
        {"Meta/RULES.md": "Generated.\n", "CHARTER.md": "Not generated here.\n"},
        top="docs:\n  output: ./notes/Meta/RULES.md\n",
    )

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [("notes/CHARTER.md", 1, "schema/missing-frontmatter")]


@pytest.mark.parametrize(
    ("path", "top"),
    [
        ("Sub/AGENTS.md", ""),
        ("CLAUDE.md", ""),
        ("Inbox/loose.md", 'paths:\n  "Inbox/**": {untyped: allow}\n'),
        ("Meta/RULES.md", "docs: {output: notes/Meta/RULES.md}\n"),
    ],
)
@pytest.mark.parametrize("text", ["---\ndescription: Tool settings\nmodel: fast\n---\nGuide.\n", "---\n---\nGuide.\n"])
def test_exempt_file_with_frontmatter_but_no_kind_needs_no_kind(charter, make_kb, path, top, text):
    kb = _kb(make_kb, {path: text}, top=top)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


def test_exempt_file_that_declares_a_kind_is_validated_as_that_kind(charter, make_kb):
    kb = _kb(make_kb, {"Sub/AGENTS.md": "---\nkind: entry\ntitle: 3\nstauts: x\n---\n", "CLAUDE.md": "---\nkind: entyr\n---\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert _codes(result) == [
        ("notes/CLAUDE.md", 2, "schema/unknown-kind"),
        ("notes/Sub/AGENTS.md", 3, "schema/type"),
        ("notes/Sub/AGENTS.md", 4, "schema/unknown-field"),
    ]


def test_crlf_frontmatter_is_frontmatter(charter, make_kb):
    kb = _kb(make_kb, {"entry.md": "---\r\nkind: entry\r\ntitle: ok\r\n---\r\n\r\nBody.\r\n"})

    assert charter("validate", cwd=kb).exit_code == 0


@pytest.mark.parametrize(
    ("top", "line"),
    [
        ('paths:\n  "Inbox/**": {untyped: yes}\n', 4),
        ('paths:\n  "Inbox/**": {ignore: true, untyped: allow}\n', 4),
        ("agent_files: AGENTS.md\n", 3),
        ("agent_files: []\n", 3),
        ("docs: CHARTER.md\n", 3),
        ("docs: {output: ''}\n", 3),
        ("docs: {outptu: RULES.md}\n", 3),
        ("docs: {output: ../CHARTER.md}\n", 3),
        ("docs: {output: notes/../../CHARTER.md}\n", 3),
        ("docs: {output: /srv/CHARTER.md}\n", 3),
        ("docs: {output: 'C:\\Rules\\CHARTER.md'}\n", 3),
        ("docs: {output: '\\\\server\\share\\CHARTER.md'}\n", 3),
    ],
)
def test_invalid_untyped_settings_exit_two(charter, make_kb, top, line):
    kb = _kb(make_kb, {"entry.md": TYPED}, top=top)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _codes(result) == [("charter.yaml", line, "contract/invalid")]
