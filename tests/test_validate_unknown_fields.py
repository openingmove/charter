import pytest


def _kb(make_kb, note, top="", kind_extra=""):
    return make_kb({
        "charter.yaml": (
            f"charter: 1\nroot: notes\n{top}kinds:\n  entry:\n{kind_extra}    fields:\n"
            "      kind: {type: string}\n      status: {type: string}\n      title: {type: string}\n"
        ),
        "notes/entry.md": note,
    })


def _diagnostics(result):
    return [(d["line"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def test_undeclared_field_yields_unknown_field_with_a_did_you_mean_hint(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\nstauts: draft\n---\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["path"], diagnostic["line"], diagnostic["severity"], diagnostic["code"]) == (
        "notes/entry.md", 3, "error", "schema/unknown-field"
    )
    assert "`stauts`" in diagnostic["message"]
    assert diagnostic["hint"] == "Did you mean `status`?"


@pytest.mark.parametrize(("typo", "meant"), [("ttle", "title"), ("kidn", "kind"), ("titel", "title")])
def test_short_typos_get_a_did_you_mean_hint(charter, make_kb, typo, meant):
    kb = _kb(make_kb, f"---\nkind: entry\n{typo}: x\n---\n")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.json()["diagnostics"][0]["hint"] == f"Did you mean `{meant}`?"


def test_two_letter_typo_gets_a_did_you_mean_hint(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: {fields: {id: {type: int}, title: {type: string}}}\n",
        "notes/entry.md": "---\nkind: entry\nix: 3\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.json()["diagnostics"][0]["hint"] == "Did you mean `id`?"


def test_a_short_name_two_edits_away_is_not_suggested(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: {fields: {id: {type: int}}}\n",
        "notes/entry.md": "---\nkind: entry\nab: 3\n---\n",
    })

    result = charter("validate", "--format", "json", cwd=kb)

    assert "Did you mean" not in result.json()["diagnostics"][0]["hint"]


def test_undeclared_field_far_from_any_declared_field_lists_where_to_declare_it(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\nmood: grumpy\n---\n")

    result = charter("validate", "--format", "json", cwd=kb)

    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "schema/unknown-field"
    assert "Did you mean" not in diagnostic["hint"]
    assert "common_fields" in diagnostic["hint"]


def test_each_undeclared_field_is_reported_on_its_own_line(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\ncolour: red\ntitle: ok\nsize: 3\n---\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [(3, "error", "schema/unknown-field"), (5, "error", "schema/unknown-field")]


def test_discriminator_need_not_be_declared_on_the_kind(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nroot: notes\nkinds:\n  entry: {fields: {title: {type: string}}}\n",
        "notes/entry.md": "---\nkind: entry\ntitle: ok\n---\n",
    })

    assert charter("validate", cwd=kb).exit_code == 0


def test_common_fields_are_valid_on_every_kind(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\ntags: [a]\naliases: [b]\n---\n", top="common_fields: [tags, aliases]\n")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout


def test_common_fields_count_as_did_you_mean_candidates(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\ntagz: [a]\n---\n", top="common_fields: [tags]\n")

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.json()["diagnostics"][0]["hint"] == "Did you mean `tags`?"


def test_common_field_may_declare_a_type(charter, make_kb):
    kb = _kb(
        make_kb,
        "---\nkind: entry\ntags: solo\naliases: whatever\n---\n",
        top="common_fields:\n  tags: {type: list, of: string}\n  aliases:\n",
    )

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert _diagnostics(result) == [(3, "error", "schema/type")]


def test_a_kind_declaration_takes_precedence_over_a_common_field(charter, make_kb):
    kb = _kb(make_kb, "---\nkind: entry\ntitle: 12\n---\n", top="common_fields:\n  title: {type: int}\n")

    result = charter("validate", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [(3, "error", "schema/type")]
    assert "must be a string" in result.json()["diagnostics"][0]["message"]


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("error", [(3, "error", "schema/unknown-field")]),
        ("warn", [(3, "warning", "schema/unknown-field")]),
        ("allow", []),
    ],
)
def test_unknown_fields_setting_per_kind(charter, make_kb, setting, expected):
    kb = _kb(make_kb, "---\nkind: entry\nscribble: yes\n---\n", kind_extra=f"    unknown_fields: {setting}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert _diagnostics(result) == expected
    assert result.exit_code == (1 if setting == "error" else 0)


def test_unknown_fields_on_a_crlf_note_report_the_same_lines_as_lf(charter, make_kb):
    kb = _kb(make_kb, "---\r\nkind: entry\r\nstauts: draft\r\n---\r\n\r\nBody.\r\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [(3, "error", "schema/unknown-field")]


@pytest.mark.parametrize(
    ("top", "kind_extra", "line"),
    [
        ("", "    unknown_fields: sometimes\n", 5),
        ("common_fields: tags\n", "", 3),
        ("common_fields: [tags, tags]\n", "", 3),
        ("common_fields:\n  tags: {type: colour}\n", "", 4),
        ("common_fields:\n  tags: {type: list, required_when: {stage: cut}}\n", "", 4),
    ],
)
def test_invalid_unknown_field_settings_exit_two(charter, make_kb, top, kind_extra, line):
    kb = _kb(make_kb, "---\nkind: entry\n---\n", top=top, kind_extra=kind_extra)

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _diagnostics(result) == [(line, "error", "contract/invalid")]
