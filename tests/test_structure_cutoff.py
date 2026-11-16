import shutil

import pytest
from conftest import FIXTURES, commit_files, run_git

CUTOFF = FIXTURES / "structure-cutoff"
STRUCTURE = "structure/missing-heading"
LEGACY = ["notes/Legacy.md", "notes/Legacy link.md"]
JUDGED = ["notes/On the day.md", "notes/Undated.md"]


def _found(result):
    return sorted((d["path"], d["code"]) for d in result.json()["diagnostics"])


def _structure(result):
    return sorted(path for path, code in _found(result) if code.startswith("structure/"))


def _validate(charter, kb, *argv):
    return charter("validate", "--profile", "ci", "--format", "json", *argv, cwd=kb)


@pytest.fixture
def kb(tmp_path):
    copy = tmp_path / "kb"
    shutil.copytree(CUTOFF, copy)
    return copy


# --- judging notes ---


def test_the_fixture_matches_the_golden(charter, golden):
    result = _validate(charter, CUTOFF)

    assert result.exit_code == 1
    golden("structure-cutoff", result.json())


def test_only_notes_dated_on_or_after_the_cutoff_are_judged_on_structure(charter):
    result = _validate(charter, CUTOFF)

    # "Later" has no Details heading either; "Complete" keeps the template.
    assert _structure(result) == sorted([*JUDGED, "notes/Later.md"])


def test_a_legacy_note_is_still_judged_on_everything_else(charter):
    found = _found(_validate(charter, CUTOFF))

    assert ("notes/Legacy link.md", "links/unresolved") in found
    assert not [item for item in found if item[0] == "notes/Legacy.md"]


def test_an_undated_note_gets_the_schema_error_and_structure_findings(charter):
    found = [item for item in _found(_validate(charter, CUTOFF)) if item[0] == "notes/Undated.md"]

    assert found == [("notes/Undated.md", "schema/required"), ("notes/Undated.md", STRUCTURE)]


@pytest.mark.parametrize("value", ["2025-12-31T23:00:00", "2025-12-31T23:00:00+02:00", '"2025-12-31"', "yesterday"])
def test_a_value_that_is_not_a_date_is_judged_even_before_the_cutoff(charter, kb, value):
    note = kb / "notes" / "Legacy.md"
    text = note.read_text()
    assert "created: 2025-12-31" in text
    note.write_text(text.replace("created: 2025-12-31", f"created: {value}"), encoding="utf-8")

    found = _found(_validate(charter, kb))

    assert ("notes/Legacy.md", "schema/type") in found
    assert ("notes/Legacy.md", STRUCTURE) in found


def test_a_note_on_the_cutoff_day_that_keeps_the_template_is_clean(charter, kb):
    note = kb / "notes" / "On the day.md"
    note.write_text(note.read_text() + "\n## Details\n", encoding="utf-8")

    assert "notes/On the day.md" not in _structure(_validate(charter, kb))


# --- the same answer everywhere ---


def test_single_file_runs_agree(charter):
    for path in [*LEGACY, *JUDGED]:
        result = _validate(charter, CUTOFF, "--file", path)
        assert (path in _structure(result)) == (path in JUDGED), path


def test_staged_runs_agree(charter, kb):
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "-A")

    result = _validate(charter, kb, "--staged")

    assert _structure(result) == sorted([*JUDGED, "notes/Later.md"])
    assert ("notes/Legacy link.md", "links/unresolved") in _found(result)


def test_range_runs_judge_no_structure_at_all(charter, kb):
    # `--range` checks history only (edit policies, updated-date, protected-region), so a cutoff changes nothing.
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "commit", "-q", "--allow-empty", "-m", "base")
    commit_files(kb, {}, "notes")

    result = _validate(charter, kb, "--range=HEAD~1..HEAD")

    assert result.exit_code == 0
    assert _structure(result) == []


def test_the_cutoff_works_without_version_control(charter, kb):
    assert not (kb / ".git").exists()

    assert "notes/Legacy.md" not in _structure(_validate(charter, kb))


def test_new_accepts_an_old_date(charter, kb):
    result = charter("new", "log", "Backfilled", "--set", "created=2024-05-01", cwd=kb)

    assert result.exit_code == 0, result.stdout + result.stderr


# --- describe and the rulebook ---


def test_describe_shows_the_cutoff(charter, golden):
    result = charter("describe", cwd=CUTOFF)

    assert result.exit_code == 0
    assert "before 2026-01-01" in result.stdout
    golden("structure-cutoff", result.stdout, "describe.md")


def test_describe_json_has_the_cutoff_for_a_kind_that_declares_one(charter):
    [log] = charter("describe", "log", "--format", "json", cwd=CUTOFF).json()["kinds"]

    assert log["structure_cutoff"] == {"field": "created", "date": "2026-01-01"}


def test_the_rulebook_shows_the_cutoff_and_stays_in_sync(charter, kb, golden):
    assert charter("docs", cwd=kb).exit_code == 0

    golden("structure-cutoff", (kb / "CHARTER.md").read_text(encoding="utf-8"), "CHARTER.golden.md")
    assert charter("docs", "--check", cwd=kb).exit_code == 0


# --- loading the contract ---

BASE = """\
charter: 1
root: notes
paths:
  "Templates/**": {{ignore: true}}
{top}kinds:
  log:
{kind}    path: "{{title}}.md"
    fields:
      kind: {{type: string, required: true}}
      title: {{type: string, required: true}}
{fields}"""
TEMPLATE = "    template: Templates/Log.md\n"
CUTOFF_OK = "    structure_cutoff: {field: created, date: 2026-01-01}\n"
CREATED = "      created: {type: date, required: true}\n"


def _contract(kind=TEMPLATE + CUTOFF_OK, fields=CREATED, top=""):
    return BASE.format(kind=kind, fields=fields, top=top)


def _load(charter, make_kb, contract):
    kb = make_kb({"charter.yaml": contract, "notes/Templates/Log.md": "# {{title}}\n"})
    result = charter("validate", "--format", "json", cwd=kb)
    return result, [(d["line"], d["code"], d["message"], d["hint"]) for d in result.json()["diagnostics"]]


def test_a_valid_cutoff_loads(charter, make_kb):
    result, found = _load(charter, make_kb, _contract())

    assert result.exit_code == 0, found


def test_a_common_field_can_be_the_date(charter, make_kb):
    contract = _contract(fields="", top="common_fields:\n  created: {type: date, required: true}\n")

    result, found = _load(charter, make_kb, contract)

    assert result.exit_code == 0, found


@pytest.mark.parametrize(
    ("fields", "top", "words"),
    [
        ("      created: {type: string, required: true}\n", "", "holds `string`"),
        ("      created: {type: date}\n", "", "not required"),
        ("      created: {type: date, required_when: {kind: log}}\n", "", "not required"),
        ("", "", "not a field of this kind"),
        ("", "common_fields: [created]\n", "not a field of this kind"),
        ("", "common_fields:\n  created: {type: date}\n", "not required"),
    ],
)
def test_the_cutoff_field_must_be_a_required_date_the_kind_declares(charter, make_kb, fields, top, words):
    result, found = _load(charter, make_kb, _contract(fields=fields, top=top))

    assert result.exit_code == 2
    [(line, code, message, _)] = found
    assert code == "contract/invalid"
    assert words in message
    assert message.startswith("kinds.log.structure_cutoff")


def test_the_cutoff_needs_a_template(charter, make_kb):
    result, found = _load(charter, make_kb, _contract(kind=CUTOFF_OK))

    assert result.exit_code == 2
    [(line, code, message, hint)] = found
    assert (line, code) == (7, "contract/invalid")
    assert "no template" in message


def test_a_field_only_a_variant_declares_is_not_on_every_note(charter, make_kb):
    kind = (
        TEMPLATE
        + CUTOFF_OK
        + "    variant_by: size\n    variants:\n      big:\n        fields:\n"
        + "          created: {type: date, required: true}\n"
    )
    result, found = _load(charter, make_kb, _contract(kind=kind, fields=""))

    assert result.exit_code == 2
    [(_, code, message, hint)] = found
    assert code == "contract/invalid"
    assert "not a field of this kind" in message
    assert "variant `big`" in hint


def test_a_variant_may_not_weaken_the_cutoff_field(charter, make_kb):
    kind = (
        TEMPLATE
        + CUTOFF_OK
        + "    variant_by: size\n    variants:\n      big:\n        fields:\n"
        + "          created: {type: date}\n"
    )
    result, found = _load(charter, make_kb, _contract(kind=kind))

    assert result.exit_code == 2
    [(line, code, message, _)] = found
    assert code == "contract/invalid"
    assert "not required in variant `big`" in message


@pytest.mark.parametrize(
    "cutoff",
    [
        "structure_cutoff: {field: created}",
        "structure_cutoff: {date: 2026-01-01}",
        "structure_cutoff: {field: created, date: 2026-01-01, extra: 1}",
        "structure_cutoff: {field: created, date: '2026-01-01'}",
        "structure_cutoff: {field: created, date: 2026-01-01T10:00:00}",
        "structure_cutoff: {field: created, date: 20260101}",
        "structure_cutoff: 2026-01-01",
        "structure_cutoff: [created, 2026-01-01]",
        "structure_cutoff: null",
        "structure_cutoff: {field: 3, date: 2026-01-01}",
    ],
)
def test_a_malformed_cutoff_is_contract_invalid(charter, make_kb, cutoff):
    result, found = _load(charter, make_kb, _contract(kind=TEMPLATE + f"    {cutoff}\n"))

    assert result.exit_code == 2
    assert {code for _, code, _, _ in found} == {"contract/invalid"}
    assert all(message.startswith("kinds.log.structure_cutoff") for _, _, message, _ in found)

