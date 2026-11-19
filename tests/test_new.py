import datetime
import errno
import os
import pathlib
import re

import pytest


CONTRACT = """\
charter: 1
root: docs
vocabularies:
  stage: [idea, draft, locked]
  category: [place, chain]
paths:
  "Templates/**": {ignore: true}
kinds:
  thing:
    path: "Things/{id} {title}.md"
    template: Templates/Thing.md
    fields:
      kind: {type: string, required: true}
      id: {type: int, required: true, unique: true, range: [1, 5], auto: next}
      title: {type: string, required: true, matches_filename: true}
      stage: {enum: stage, required: true, default: idea}
      category: {enum: category, required: true}
      zone: {type: link, to: zone}
      tags: {type: list, of: string}
      created: {type: date, required: true, auto: today}
    variants:
      chain:
        set: {category: chain}
        template: Templates/Chain.md
        fields:
          steps: {type: int, required: true}
  zone:
    path: "Zones/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  log:
    variant_by: log_type
    path: "Logs/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
    variants:
      voyage: {path: "Voyages/{title}.md"}
      repair: {}
  scratch:
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""

THING_TEMPLATE = """\
# {{title}}
<!-- guide: why it is worth finding, first noted {{date}} -->

## Where

## Notes <!-- optional -->
"""

CHAIN_TEMPLATE = """\
# {{title}} in {{steps}} steps

## Steps

## Ending {{stage}}
<!-- repeat -->
"""


@pytest.fixture
def kb(make_kb):
    def make(notes=None, contract=CONTRACT):
        return make_kb({
            "charter.yaml": contract,
            "docs/Templates/Thing.md": THING_TEMPLATE,
            "docs/Templates/Chain.md": CHAIN_TEMPLATE,
            **{f"docs/{path}": text for path, text in (notes or {}).items()},
        })

    return make


def _new(charter, kb, *argv):
    return charter("new", *argv, "--format", "agent", cwd=kb)


def _found(result):
    """(path, code) of each diagnostic line in agent output."""
    return [
        (match.group(1), match.group(2))
        for match in re.finditer(r"^(.+?)(?::\d+)?: (?:error|warning|info) (\S+):", result.stdout, re.MULTILINE)
    ]


def _thing(id, title="Old", category="place"):
    return f"---\nkind: thing\nid: {id}\ntitle: {title}\nstage: idea\ncategory: {category}\ncreated: 2026-01-01\n---\n"


def _dated(run):
    """The result of `run`, and the days it may have taken as today: a run can cross midnight."""
    before = datetime.date.today().isoformat()
    result = run()
    return result, {before, datetime.date.today().isoformat()}


def _read(kb, path):
    return (kb / path).read_text(encoding="utf-8")


# --- writing a note ---


def test_writes_frontmatter_in_contract_order_with_defaults_autos_and_the_template_body(charter, kb):
    kb = kb()

    result, days = _dated(lambda: _new(charter, kb, "thing", "Lighthouse", "--set", "category=place"))

    assert result.exit_code == 0, result.stdout
    assert _read(kb, "docs/Things/1 Lighthouse.md") in {
        "---\n"
        "kind: thing\n"
        "id: 1\n"
        "title: Lighthouse\n"
        "stage: idea\n"
        "category: place\n"
        f"created: {day}\n"
        "---\n"
        "# Lighthouse\n"
        f"<!-- guide: why it is worth finding, first noted {day} -->\n"
        "\n"
        "## Where\n"
        "\n"
        "## Notes <!-- optional -->\n"
        for day in days
    }


def test_prints_the_created_path_and_the_section_outline(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "Lighthouse", "--set", "category=place")

    assert result.stdout == (
        "created docs/Things/1 Lighthouse.md (thing)\n"
        "section # Lighthouse\n"
        "section ## Where\n"
        "section ## Notes (optional)\n"
    )


@pytest.mark.parametrize("output_format", ["text", "agent"])
def test_the_printed_outline_is_filled_with_the_values_of_the_written_body_date_included(
    charter, kb, monkeypatch, output_format
):
    monkeypatch.setenv("CHARTER_TODAY", "2026-10-14")
    kb = kb()
    (kb / "docs/Templates/Thing.md").write_text(
        "# {{title}}\n\n## Notes from {{date}}\n<!-- repeat -->\n\n## Kept `{{date}}`\n", encoding="utf-8"
    )

    result = charter("new", "thing", "Lighthouse", "--set", "category=place", "--format", output_format, cwd=kb)

    assert result.exit_code == 0, result.stdout
    written = _read(kb, "docs/Things/1 Lighthouse.md")
    assert "## Notes from 2026-10-14\n" in written
    assert "## Notes from 2026-10-14 (repeat)" in result.stdout
    assert "{{date}} (repeat)" not in result.stdout
    # Placeholders in code stay literal in the outline, as in the body.
    assert "## Kept `{{date}}`" in written
    assert "## Kept `{{date}}`" in result.stdout


def test_text_output_names_the_path_and_outline(charter, kb):
    kb = kb()

    result = charter("new", "thing/chain", "Bridge", "--set", "steps=3", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert result.stdout == (
        "Created `docs/Things/1 Bridge.md` (thing/chain).\n"
        "\n"
        "Sections to fill in:\n"
        "  # Bridge in 3 steps\n"
        "  ## Steps\n"
        "  ## Ending idea (repeat)\n"
    )


def test_the_written_note_passes_validation_apart_from_template_residue(charter, kb):
    kb = kb()
    _new(charter, kb, "thing", "Lighthouse", "--set", "category=place")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)

    assert {d["code"] for d in result.json()["diagnostics"]} == {"residue/guide"}


def test_set_values_override_defaults_and_autos_and_take_the_field_type(charter, kb):
    kb = kb({"Zones/North.md": "---\nkind: zone\ntitle: North\n---\n"})

    result = _new(charter, kb, "thing", "Lighthouse", "--set", "category=place", "--set", "stage=draft",
                  "--set", "id=4", "--set", "created=2026-02-03", "--set", "zone=[[North]]")

    assert result.exit_code == 0, result.stdout
    assert _read(kb, "docs/Things/4 Lighthouse.md").startswith(
        "---\nkind: thing\nid: 4\ntitle: Lighthouse\nstage: draft\ncategory: place\n"
        "zone: '[[North]]'\ncreated: 2026-02-03\n---\n"
    )


def test_a_list_field_takes_one_element_per_set(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "Lighthouse", "--set", "category=place",
                  "--set", "tags=coast", "--set", "tags=night")

    assert result.exit_code == 0, result.stdout
    assert "tags:\n- coast\n- night\n" in _read(kb, "docs/Things/1 Lighthouse.md")


def test_text_values_stay_text(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "1999", "--set", "category=place")

    assert result.exit_code == 0, result.stdout
    assert "title: '1999'\n" in _read(kb, "docs/Things/1 1999.md")


def test_a_kind_without_a_template_gets_frontmatter_only(charter, kb):
    kb = kb()

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 0, result.stdout
    assert result.stdout == "created docs/Zones/North.md (zone)\n"
    assert _read(kb, "docs/Zones/North.md") == "---\nkind: zone\ntitle: North\n---\n"


# --- auto ids ---


def test_auto_next_takes_the_smallest_free_value(charter, kb):
    kb = kb({"Things/1 A.md": _thing(1, "A"), "Things/3 C.md": _thing(3, "C")})

    result = _new(charter, kb, "thing", "B", "--set", "category=place")

    assert result.exit_code == 0, result.stdout
    assert (kb / "docs/Things/2 B.md").is_file()


def test_auto_next_counts_notes_of_every_variant(charter, kb):
    kb = kb({"Things/1 A.md": _thing(1, "A", "chain").replace("created", "steps: 2\ncreated")})

    result = _new(charter, kb, "thing", "B", "--set", "category=place")

    assert (kb / "docs/Things/2 B.md").is_file(), result.stdout


def test_refuses_when_no_value_is_free(charter, kb):
    kb = kb({f"Things/{n} T{n}.md": _thing(n, f"T{n}") for n in range(1, 6)})

    result = _new(charter, kb, "thing", "Six", "--set", "category=place")

    assert result.exit_code == 1
    assert result.stdout.startswith("charter.yaml:14: error new/no-free-value: ")
    assert _found(result) == [("charter.yaml", "new/no-free-value")]
    assert "between 1 and 5" in result.stdout


def test_no_free_value_does_not_hide_missing_fields(charter, kb):
    kb = kb({f"Things/{n} T{n}.md": _thing(n, f"T{n}") for n in range(1, 6)})

    result = _new(charter, kb, "thing", "--set", "stage=drafty")

    assert _found(result) == [
        ("charter.yaml", "new/no-free-value"),
        ("charter.yaml", "new/missing-field"),
        ("charter.yaml", "new/missing-field"),
        ("docs/Things/{id} {title}.md", "schema/enum"),
    ]


# --- refusals ---


def test_missing_required_fields_are_listed_with_type_and_allowed_values(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing")

    assert result.exit_code == 1
    assert result.stdout == (
        "charter.yaml:15: error new/missing-field: `thing` needs `title`: a string."
        ' (hint: Pass it as the title argument: charter new thing "TITLE".)\n'
        "charter.yaml:17: error new/missing-field: `thing` needs `category`: a string, one of `place`, `chain`."
        " (hint: Add `--set category=VALUE`.)\n"
    )
    assert not (kb / "docs/Things").exists()


def test_a_variant_by_kind_lists_its_variants_as_the_allowed_values(charter, kb):
    kb = kb()

    result = _new(charter, kb, "log", "Trip")

    assert result.exit_code == 1
    assert "`log` needs `log_type`: a string, one of `voyage`, `repair`." in result.stdout


def test_an_invalid_note_is_refused_with_the_validator_diagnostics(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "Lighthouse", "--set", "category=place", "--set", "stage=drafty",
                  "--set", "colour=red")

    assert result.exit_code == 1
    assert _found(result) == [
        ("docs/Things/1 Lighthouse.md", "schema/enum"),
        ("docs/Things/1 Lighthouse.md", "schema/unknown-field"),
    ]
    assert not (kb / "docs/Things").exists()


def test_a_note_that_breaks_a_cross_note_rule_is_refused(charter, kb):
    kb = kb({"Things/1 A.md": _thing(1, "A")})

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "id=1")

    assert _found(result) == [("docs/Things/1 B.md", "ids/duplicate")]
    assert not (kb / "docs/Things/1 B.md").exists()


def test_a_broken_link_is_refused(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "zone=[[Nowhere]]")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["links/unresolved"]


def test_never_overwrites_an_existing_file(charter, kb):
    kb = kb({"Zones/North.md": "keep me\n"})

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert _found(result) == [("docs/Zones/North.md", "new/exists")]
    assert _read(kb, "docs/Zones/North.md") == "keep me\n"


def test_an_unportable_path_value_is_refused(charter, kb):
    kb = kb()

    result = _new(charter, kb, "zone", "North/South")

    assert result.exit_code == 1
    assert _found(result) == [("docs/Zones/{title}.md", "filenames/unsafe-value")]


def test_a_mistyped_path_value_is_refused_with_every_other_problem(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "id=four", "--set", "stage=drafty")

    assert result.exit_code == 1
    assert _found(result) == [
        ("docs/Things/{id} {title}.md", "schema/type"),
        ("docs/Things/{id} {title}.md", "schema/enum"),
    ]


def test_an_unplaceable_note_is_refused_even_when_no_check_explains_why(charter, kb):
    kb = kb(contract=CONTRACT + "checks:\n  agents-include: {enabled: false}\n  schema: {enabled: false}\n")

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "id=four")

    assert result.exit_code == 1
    assert _found(result) == [("charter.yaml", "new/unplaceable")]
    assert not (kb / "docs/Things").exists()


def test_a_note_whose_path_is_ignored_is_refused_unwritten(charter, kb):
    ignored = '"Templates/**": {ignore: true}\n  "Zones/**": {ignore: true}'
    kb = kb(contract=CONTRACT.replace('"Templates/**": {ignore: true}', ignored))

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert _found(result) == [("charter.yaml", "new/ignored-path")]
    assert not (kb / "docs/Zones").exists()


FOLDER_TITLE_CONTRACT = CONTRACT.replace('path: "Zones/{title}.md"', 'path: "Zones/{title}/Note.md"')


def test_an_over_long_title_is_refused_and_nothing_is_written(charter, kb):
    kb = kb()

    result = _new(charter, kb, "zone", "N" * 300)

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]
    assert "too long" in result.stdout
    assert "Traceback" not in result.stderr
    assert not (kb / "docs/Zones").exists()


def test_a_dry_run_cannot_see_an_over_long_title_when_the_target_folder_is_missing(charter, kb):
    # Known limit, pinned so a change is deliberate: the probe gets "not found" for the missing folder before any length check.
    # Windows has one fixed limit, which charter checks before the probe, so a dry run there sees it.
    kb = kb()

    dry = _new(charter, kb, "zone", "N" * 300, "--dry-run")
    real = _new(charter, kb, "zone", "N" * 300)

    if os.name == "nt":
        assert [code for _, code in _found(dry)] == ["new/name-too-long"]
    else:
        assert dry.exit_code == 0
        assert dry.stdout.startswith("would create docs/Zones/")
    assert real.exit_code == 1
    assert [code for _, code in _found(real)] == ["new/name-too-long"]
    assert not (kb / "docs/Zones").exists()


def test_an_over_long_title_in_a_folder_name_is_refused_unwritten(charter, kb):
    kb = kb(contract=FOLDER_TITLE_CONTRACT)

    result = _new(charter, kb, "zone", "N" * 300)

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]
    assert not (kb / "docs/Zones").exists()


def test_a_dry_run_refuses_an_over_long_title_when_the_target_folder_exists(charter, kb):
    # The covered case: a file system names a length problem only inside a folder that exists, and the probe is all a dry run has.
    kb = kb({"Zones/Old.md": "x\n"})

    result = _new(charter, kb, "zone", "N" * 300, "--dry-run")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]
    assert sorted(path.name for path in (kb / "docs/Zones").iterdir()) == ["Old.md"]


@pytest.mark.parametrize(
    ("path", "too_long"),
    [
        ("docs/" + "N" * 252 + ".md", False),  # 255 units: the limit itself
        ("docs/" + "N" * 253 + ".md", True),
        ("N" * 256 + "/a.md", True),  # a folder name counts too
        ("docs/" + "\U0001F600" * 128 + ".md", True),  # a character outside the BMP is two UTF-16 units
        ("docs/" + "\u00e9" * 252 + ".md", False),  # one unit each, though two UTF-8 bytes
    ],
)
def test_the_windows_name_limit_counts_utf16_units_in_each_name(path, too_long):
    from charter.scaffold import over_windows_name_limit

    assert over_windows_name_limit(path, windows=True) is too_long
    assert over_windows_name_limit(path, windows=False) is False


def _failing(monkeypatch, method, error):
    """Make `Path.<method>` raise `error` for the note North.md, and behave normally otherwise."""

    real = getattr(pathlib.Path, method)

    def failing(self, *args, **kwargs):
        if self.name == "North.md":
            raise error
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, method, failing)


def test_a_name_too_long_raised_by_the_existence_probe_is_a_refusal(charter, kb, monkeypatch):
    kb = kb()
    _failing(monkeypatch, "stat", OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG)))

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]
    assert not (kb / "docs/Zones").exists()


def test_a_name_too_long_raised_on_write_is_a_refusal_that_leaves_nothing(charter, kb, monkeypatch):
    kb = kb()
    _failing(monkeypatch, "open", OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG)))

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]
    assert not (kb / "docs/Zones").exists()


def test_a_name_too_long_raised_when_the_folder_is_made_is_a_refusal(charter, kb, monkeypatch):
    kb = kb()
    real = pathlib.Path.mkdir

    def mkdir(self, *args, **kwargs):
        if self.name == "Zones":
            raise OSError(errno.ENAMETOOLONG, os.strerror(errno.ENAMETOOLONG))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "mkdir", mkdir)

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/name-too-long"]


def test_a_permission_error_is_not_called_a_long_name(charter, kb, monkeypatch):
    kb = kb()
    _failing(monkeypatch, "open", PermissionError(errno.EACCES, os.strerror(errno.EACCES)))

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert [code for _, code in _found(result)] == ["new/write-failed"]
    assert not (kb / "docs/Zones").exists()


def test_a_folder_that_cannot_be_made_is_a_failed_write(charter, kb):
    kb = kb({"Zones": "a file where the folder should be\n"})

    result = _new(charter, kb, "zone", "North")

    assert result.exit_code == 1
    assert _found(result) == [("docs/Zones/North.md", "new/write-failed")]


def test_a_kind_without_a_path_is_refused(charter, kb):
    kb = kb()

    result = _new(charter, kb, "scratch", "Idea")

    assert result.exit_code == 1
    assert _found(result) == [("charter.yaml", "new/no-path")]


# --- dry run ---


def test_dry_run_writes_nothing_and_reports_what_it_would_create(charter, kb):
    kb = kb()

    result = _new(charter, kb, "zone", "North", "--dry-run")

    assert result.exit_code == 0
    assert result.stdout == "would create docs/Zones/North.md (zone)\n"
    assert not (kb / "docs/Zones").exists()


def test_dry_run_still_refuses_an_invalid_note(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "B", "--dry-run")

    assert result.exit_code == 1
    assert {code for _, code in _found(result)} == {"new/missing-field"}


# --- variants ---


def test_kind_slash_variant_fixes_the_set_values_and_uses_the_variant_template(charter, kb):
    kb = kb()

    result, days = _dated(lambda: _new(charter, kb, "thing/chain", "Bridge", "--set", "steps=3"))

    assert result.exit_code == 0, result.stdout
    assert _read(kb, "docs/Things/1 Bridge.md") in {
        "---\nkind: thing\nid: 1\ntitle: Bridge\nstage: idea\ncategory: chain\n"
        f"created: {day}\nsteps: 3\n---\n"
        "# Bridge in 3 steps\n\n## Steps\n\n## Ending idea\n<!-- repeat -->\n"
        for day in days
    }
    assert "(thing/chain)" in result.stdout


def test_a_default_that_selects_a_variant_fills_in_the_variant_defaults(charter, kb):
    # The kind's default selects `chain`, which redeclares `stage` with a default of its own.
    steps = "steps: {type: int, required: true}"
    contract = CONTRACT.replace("{enum: category, required: true}", "{enum: category, default: chain}")
    contract = contract.replace(steps, steps + "\n          stage: {enum: stage, default: draft}")
    kb = kb(contract=contract)

    result = _new(charter, kb, "thing", "Bridge", "--set", "steps=3")

    assert result.exit_code == 0, result.stdout
    assert "(thing/chain)" in result.stdout
    assert "stage: draft\n" in _read(kb, "docs/Things/1 Bridge.md")


def test_set_values_select_a_variant(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing", "Bridge", "--set", "category=chain", "--set", "steps=3")

    assert result.exit_code == 0, result.stdout
    assert "(thing/chain)" in result.stdout


def test_a_selected_variant_lists_its_own_missing_fields(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing/chain", "Bridge")

    assert _found(result) == [("charter.yaml", "new/missing-field")]
    assert "`thing/chain` needs `steps`: an integer." in result.stdout


def test_variant_by_variants_are_named_by_the_field(charter, kb):
    kb = kb()

    result = _new(charter, kb, "log/voyage", "Trip")

    assert result.exit_code == 0, result.stdout
    assert _read(kb, "docs/Voyages/Trip.md") == "---\nkind: log\ntitle: Trip\nlog_type: voyage\n---\n"


def test_a_set_value_contradicting_the_variant_is_a_usage_error(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thing/chain", "Bridge", "--set", "category=place", "--set", "steps=3")

    assert result.exit_code == 2
    assert _found(result) == [("charter.yaml", "usage/conflicting-set")]


def test_a_variant_named_by_a_non_string_key_is_a_contract_error(charter, kb):
    kb = kb(contract=CONTRACT.replace("voyage: {path", "2024: {path").replace("Voyages/", "Old/"))

    result = _new(charter, kb, "log/2024", "Trip")

    # YAML reads the name as a number, which no note's text value can select: refused when the contract loads.
    assert result.exit_code == 2
    assert _found(result) == [("charter.yaml", "contract/invalid")]
    assert not (kb / "docs/Old").exists()


# --- usage errors ---


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["thng", "X"], "usage/unknown-kind"),
        (["thing/chian", "X"], "usage/unknown-variant"),
        (["zone/big", "X"], "usage/unknown-variant"),
        (["zone", "X", "--set", "title"], "usage/invalid-set"),
        (["zone", "X", "--set", "title=Y"], "usage/conflicting-set"),
        (["zone", "X", "--set", "kind=thing"], "usage/conflicting-set"),
        (["zone", "--set", "title=A", "--set", "title=B"], "usage/repeated-set"),
    ],
)
def test_usage_errors_exit_two(charter, kb, argv, code):
    kb = kb()

    result = _new(charter, kb, *argv)

    assert result.exit_code == 2, result.stdout
    assert [found for _, found in _found(result)] == [code]


def test_unknown_kind_suggests_the_closest(charter, kb):
    kb = kb()

    result = _new(charter, kb, "thng", "X")

    assert "Did you mean `thing`?" in result.stdout


def test_a_title_without_a_title_field_is_a_usage_error(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  day:\n    path: '{day}.md'\n    fields:\n"
        "      kind: {type: string}\n      day: {type: date, required: true, auto: today}\n",
    })

    refused = _new(charter, kb, "day", "Monday")
    created, days = _dated(lambda: _new(charter, kb, "day"))

    assert refused.exit_code == 2
    assert _found(refused) == [("charter.yaml", "usage/no-title-field")]
    assert created.exit_code == 0, created.stdout
    assert any((kb / f"{day}.md").is_file() for day in days)


def test_an_invalid_contract_exits_two(charter, make_kb):
    kb = make_kb({"charter.yaml": "charter: 1\n"})

    result = _new(charter, kb, "thing", "X")

    assert result.exit_code == 2
    assert _found(result) == [("charter.yaml", "contract/invalid")]


# --- contract: default and auto ---


@pytest.mark.parametrize(
    "field_spec",
    [
        "{type: int, default: many}",
        "{values: [a, b], default: c}",
        "{type: list, of: int, default: [1, x]}",
        "{type: list, default: solo}",
        "{type: string, default: {a: 1}}",
        "{type: int, unique: true, auto: next, default: 1}",
        "{type: string, auto: today}",
        "{type: int, auto: next}",
        "{type: string, unique: true, auto: next}",
        "{type: date, auto: yesterday}",
    ],
)
def test_invalid_default_or_auto_is_a_contract_error(charter, make_kb, field_spec):
    kb = make_kb({"charter.yaml": f"charter: 1\nkinds:\n  entry:\n    fields:\n      value: {field_spec}\n"})

    result = charter("validate", "--format", "agent", cwd=kb)

    assert result.exit_code == 2, result.stdout
    assert _found(result) == [("charter.yaml", "contract/invalid")]


@pytest.mark.parametrize(
    "field_spec",
    [
        "{type: int, default: 3}",
        "{values: [a, b], default: b}",
        "{type: list, of: int, default: [1, 2]}",
        "{type: date, default: 2026-01-01}",
        "{type: date, auto: today}",
        "{type: int, unique: true, auto: next}",
    ],
)
def test_valid_default_or_auto_loads(charter, make_kb, field_spec):
    kb = make_kb({"charter.yaml": f"charter: 1\nkinds:\n  entry:\n    fields:\n      value: {field_spec}\n"})

    result = charter("validate", "--format", "agent", cwd=kb)

    assert result.exit_code == 0, result.stdout


def test_a_field_required_by_a_condition_is_missing_once_the_condition_holds(charter, kb):
    reason = "      reason: {type: string, required_when: {stage: locked}}\n"
    kb = kb(contract=CONTRACT.replace("      tags:", reason + "      tags:"))

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "stage=locked")

    assert _found(result) == [("charter.yaml", "new/missing-field")]
    assert "`thing` needs `reason`: a string." in result.stdout


def test_warnings_do_not_stop_the_note_and_are_reported(charter, kb):
    kb = kb(contract=CONTRACT + "checks:\n  agents-include: {enabled: false}\n  links: {severity: warning}\n")

    result = _new(charter, kb, "thing", "B", "--set", "category=place", "--set", "zone=[[Nowhere]]")

    assert result.exit_code == 0, result.stdout
    assert result.stdout.startswith("created docs/Things/1 B.md (thing)\n")
    assert _found(result) == [("docs/Things/1 B.md", "links/unresolved")]
    assert (kb / "docs/Things/1 B.md").is_file()


# --- placeholders in code stay literal ---

LITERAL_CONTRACT = """\
charter: 1
root: docs
paths:
  "Templates/**": {ignore: true}
kinds:
  entry:
    path: "{title}.md"
    template: Templates/Entry.md
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
"""

LITERAL_TEMPLATE = """\
# {{title}}

## `{{title}}` Z

Write `{{title}}` for the name.

```
{{title}}
```
"""


def test_placeholders_in_code_stay_literal_and_the_dry_run_outline_matches(charter, make_kb):
    kb = make_kb({"charter.yaml": LITERAL_CONTRACT, "docs/Templates/Entry.md": LITERAL_TEMPLATE})

    dry = charter("new", "entry", "Hello", "--dry-run", "--format", "agent", cwd=kb)
    result = _new(charter, kb, "entry", "Hello")

    assert result.exit_code == 0, result.stdout
    assert _read(kb, "docs/Hello.md") == (
        "---\nkind: entry\ntitle: Hello\n---\n"
        "# Hello\n\n## `{{title}}` Z\n\nWrite `{{title}}` for the name.\n\n```\n{{title}}\n```\n"
    )
    assert "section ## `{{title}}` Z\n" in result.stdout
    assert [line for line in dry.stdout.splitlines() if line.startswith("section")] == [
        line for line in result.stdout.splitlines() if line.startswith("section")
    ]
    validated = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)
    assert validated.json()["diagnostics"] == []


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_a_blank_line_inside_a_fence_does_not_shift_the_placeholders_after_it(charter, make_kb, newline):
    template = "# {{title}}\n\n```\n  \n\ncode\n```\n\nBy {{title}} x\n".replace("\n", newline)
    kb = make_kb({"charter.yaml": LITERAL_CONTRACT, "docs/Templates/Entry.md": template})

    result = _new(charter, kb, "entry", "Hello")

    assert result.exit_code == 0, result.stdout
    body = _read(kb, "docs/Hello.md").split("---\n", 2)[2]
    # `charter new` reads the template with universal newlines, so the note is written with LF either way.
    assert body == "# Hello\n\n```\n  \n\ncode\n```\n\nBy Hello x\n"


@pytest.mark.parametrize(
    "text",
    [
        "```\n  \ncode\n```\n{{title}} x\n",
        "```\r\n\r\ncode\r\n```\r\n{{title}} x\r\n",
        "~~~\n\t\n   \n~~~\ntext\n",
        "para\n\n    indented\n  \n    more\n\nafter `a  b` end\n",
        "```\nunclosed\n  \n\n",
        "",
    ],
)
def test_blanking_code_keeps_the_length_of_the_text(text):
    from charter.prose import blank_code

    blanked = blank_code(text)

    assert len(blanked) == len(text)
    assert blanked.count("\n") == text.count("\n")
