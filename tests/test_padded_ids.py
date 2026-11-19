"""An `int` field with `width` renders zero padded wherever its value becomes text."""

import shutil

import pytest
from conftest import FIXTURES, write_files


@pytest.fixture
def adr_kb(tmp_path):
    """The padded-ids fixture, copied so a test may add notes; `notes` maps a path under `docs/adr/` to its id."""

    def make(notes=None):
        kb = tmp_path / "kb"
        shutil.copytree(FIXTURES / "padded-ids", kb)
        write_files(kb, {f"docs/adr/{name}": f"---\nkind: adr\nid: {note_id}\ntitle: X\n---\n# ADR {note_id}: X\n"
                         for name, note_id in (notes or {}).items()})
        return kb

    return make


def _validate(charter, kb):
    return charter("validate", "--all", "--profile", "ci", "--format", "json", cwd=kb)


def _codes(result):
    return [(d["path"], d["code"]) for d in result.json()["diagnostics"]]


def test_new_writes_the_padded_file_name_and_the_integer_id(charter, adr_kb):
    kb = adr_kb()

    result = charter("new", "adr", "Some Decision", cwd=kb)

    assert result.exit_code == 0, result.stdout + result.stderr
    written = kb / "docs" / "adr" / "0001 Some Decision.md"
    assert written.read_text(encoding="utf-8") == (
        "---\nkind: adr\nid: 1\ntitle: Some Decision\n---\n# ADR 0001: Some Decision\n"
    )


def test_new_fills_the_next_free_id_after_existing_padded_notes(charter, adr_kb):
    kb = adr_kb({"0001 X.md": 1, "0002 Y.md": 2})

    result = charter("new", "adr", "Third", cwd=kb)

    assert result.exit_code == 0, result.stdout + result.stderr
    written = kb / "docs" / "adr" / "0003 Third.md"
    assert written.read_text(encoding="utf-8") == "---\nkind: adr\nid: 3\ntitle: Third\n---\n# ADR 0003: Third\n"


def test_validate_passes_a_note_under_its_padded_name(charter, adr_kb):
    result = _validate(charter, adr_kb({"0001 X.md": 1}))

    assert result.exit_code == 0, result.stdout
    assert _codes(result) == []


def test_validate_reports_an_unpadded_name_as_misplaced(charter, adr_kb):
    result = _validate(charter, adr_kb({"1 X.md": 1}))

    assert _codes(result) == [("docs/adr/1 X.md", "filenames/matches-filename")]
    diagnostic = result.json()["diagnostics"][0]
    assert diagnostic["message"] == "`id` is `1`, written `0001` at `width: 4`, but the filename has `1`."
    assert diagnostic["hint"] == "Rename the file to `docs/adr/0001 X.md`."


def test_a_padded_name_holding_another_number_offers_that_number(charter, adr_kb):
    result = _validate(charter, adr_kb({"0010 X.md": 1}))

    assert result.json()["diagnostics"][0]["hint"] == "Rename the file to `docs/adr/0001 X.md`, or set `id` to `10`."


def test_a_padded_negative_name_holding_another_number_offers_that_number(charter, adr_kb):
    result = _validate(charter, adr_kb({"-0010 X.md": -1}))

    assert result.json()["diagnostics"][0]["hint"] == "Rename the file to `docs/adr/-0001 X.md`, or set `id` to `-10`."


@pytest.mark.parametrize(
    ("declared", "message", "hint"),
    [
        (
            "{type: string, width: 4}",
            "`width` pads `int` values, not `string`.",
            "Declare the field with `type: int`, or remove `width`.",
        ),
        (
            "{type: list, of: int, width: 4}",
            "`width` pads `int` values, not `list`.",
            "Declare the field with `type: int`, or remove `width`.",
        ),
        *(
            (
                f"{{type: int, width: {width}}}",
                f"`width` is `{shown}`, but it must be a positive whole number.",
                "Give the number of digits the value is padded to, such as `width: 4`.",
            )
            for width, shown in (("0", "0"), ("-2", "-2"), ("1.5", "1.5"), ("true", "true"), ("'4'", "4"))
        ),
    ],
)
def test_a_width_that_cannot_pad_is_a_contract_error(charter, adr_kb, declared, message, hint):
    kb = adr_kb()
    contract = kb / "charter.yaml"
    contract.write_text(contract.read_text(encoding="utf-8") + f"      extra: {declared}\n", encoding="utf-8")

    result = _validate(charter, kb)

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["code"], diagnostic["line"]) == ("contract/invalid", 13)
    assert diagnostic["message"].endswith(message)
    assert diagnostic["hint"] == hint


@pytest.mark.parametrize(
    ("prose", "mentioned"),
    [
        ("Replaces ADR 0001.", True),
        ("Replaces adr #0001.", True),
        ("Replaces #0001.", True),
        ("Replaces ADR 1.", False),
        ("Replaces ADR 00010.", False),
    ],
)
def test_sweep_finds_a_note_by_its_padded_id(charter, adr_kb, prose, mentioned):
    kb = adr_kb({"0001 X.md": 1})
    write_files(kb, {"docs/adr/0002 Y.md": f"---\nkind: adr\nid: 2\ntitle: Y\n---\n# ADR 0002: Y\n\n{prose}\n"})

    result = charter("sweep", "0001 X", "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout
    found = [(entry["path"], entry["names"]) for entry in result.json()["mentioned_in"]]
    assert found == ([("docs/adr/0002 Y.md", ["0001"])] if mentioned else [])


def test_a_negative_id_pads_its_digits_after_the_sign(charter, adr_kb):
    kb = adr_kb({"-0007 X.md": -7, "-007 X.md": -8})

    result = _validate(charter, kb)

    assert _codes(result) == [("docs/adr/-007 X.md", "filenames/matches-filename")]


def test_describe_shows_the_width(charter, adr_kb):
    kb = adr_kb()

    markdown = charter("describe", "adr", cwd=kb).stdout
    described = charter("describe", "adr", "--format", "json", cwd=kb).json()

    assert "zero padded to 4 digits (`1` is `0001`)" in markdown
    widths = {field["name"]: field["width"] for field in described["kinds"][0]["fields"]}
    assert widths == {"kind": None, "id": 4, "title": None}


def test_the_rulebook_shows_the_width(charter, adr_kb):
    kb = adr_kb()
    contract = kb / "charter.yaml"
    contract.write_text(contract.read_text(encoding="utf-8") + "docs: {output: CHARTER.md}\n", encoding="utf-8")

    result = charter("docs", cwd=kb)

    assert result.exit_code == 0, result.stdout + result.stderr
    assert "zero padded to 4 digits (`1` is `0001`)" in (kb / "CHARTER.md").read_text(encoding="utf-8")


def test_an_id_wider_than_the_width_grows(charter, adr_kb):
    result = _validate(charter, adr_kb({"10000 X.md": 10000}))

    assert result.exit_code == 0, result.stdout
    assert _codes(result) == []
