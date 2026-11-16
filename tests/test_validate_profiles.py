import time

import pytest

KINDS = "kinds:\n  entry:\n    fields:\n      n: {type: int}\n"
# One unknown field (downgraded by the default edit/commit profiles) and one type error (never downgraded).
UNKNOWN = "---\nkind: entry\nextra: 1\n---\n"
WRONG_TYPE = "---\nkind: entry\nn: many\n---\n"


def _severities(result):
    return [(d["path"], d["code"], d["severity"]) for d in result.json()["diagnostics"]]


@pytest.fixture
def kb(make_kb):
    def make(top="", notes=None):
        files = {"charter.yaml": f"charter: 1\nroot: notes\n{top}{KINDS}"}
        notes = notes if notes is not None else {"unknown.md": UNKNOWN, "wrong.md": WRONG_TYPE}
        files.update({f"notes/{path}": text for path, text in notes.items()})
        return make_kb(files)

    return make


# --- target modes ---


def test_file_validates_only_the_named_files(charter, kb):
    result = charter("validate", "--file", "notes/wrong.md", "--format", "json", cwd=kb())

    assert _severities(result) == [("notes/wrong.md", "schema/type", "error")]


def test_file_accepts_several_paths_and_absolute_ones(charter, kb):
    base = kb(notes={"a.md": WRONG_TYPE, "b.md": WRONG_TYPE, "c.md": WRONG_TYPE})

    result = charter("validate", "--file", "notes/a.md", str(base / "notes" / "c.md"), "--format", "json", cwd=base)

    assert [d["path"] for d in result.json()["diagnostics"]] == ["notes/a.md", "notes/c.md"]


def test_file_is_relative_to_the_working_directory(charter, kb):
    base = kb()

    result = charter("validate", "--config", "../charter.yaml", "--file", "wrong.md", "--format", "json", cwd=base / "notes")

    assert _severities(result) == [("notes/wrong.md", "schema/type", "error")]


def test_file_outside_the_knowledge_base_or_ignored_is_not_a_note(charter, kb):
    base = kb(top='paths:\n  "Scratch/**": {ignore: true}\n', notes={"Scratch/loose.md": "prose\n", "ok.md": UNKNOWN})
    (base / "README.md").write_text("prose\n", encoding="utf-8")

    result = charter("validate", "--file", "README.md", "notes/Scratch/loose.md", "--format", "json", cwd=base)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


def test_file_that_does_not_exist_is_a_usage_error(charter, kb):
    result = charter("validate", "--file", "notes/missing.md", "--format", "json", cwd=kb())

    assert result.exit_code == 2
    assert "profile" not in result.json()
    assert [(d["path"], d["severity"], d["code"]) for d in result.json()["diagnostics"]] == [
        ("notes/missing.md", "error", "usage/file-not-found")
    ]


def test_usage_errors_use_the_requested_format(charter, kb):
    result = charter("validate", "--file", "notes/missing.md", "--format", "agent", cwd=kb())

    assert result.exit_code == 2
    assert result.stdout.startswith("notes/missing.md: error usage/file-not-found: ")


def test_file_and_all_are_mutually_exclusive(charter, kb):
    assert charter("validate", "--all", "--file", "notes/wrong.md", cwd=kb()).exit_code == 2


def test_file_mode_is_fast_on_a_few_hundred_notes(charter, kb):
    base = kb(notes={f"Folder {i % 10}/note {i}.md": "---\nkind: entry\nn: 3\n---\n# Title\n\nBody.\n" for i in range(300)})

    start = time.perf_counter()
    result = charter("validate", "--file", "notes/Folder 3/note 3.md", cwd=base)
    elapsed = time.perf_counter() - start

    assert result.exit_code == 0
    # Typically a fraction of a second; the bound is loose so slow CI runners do not flake.
    assert elapsed < 5.0


# --- automatic profile selection ---


def test_plain_validate_locally_uses_commit(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb())

    assert result.json()["profile"] == "commit"
    assert _severities(result) == [
        ("notes/unknown.md", "schema/unknown-field", "warning"),
        ("notes/wrong.md", "schema/type", "error"),
    ]


def test_file_uses_edit(charter, kb):
    result = charter("validate", "--file", "notes/unknown.md", "--format", "json", cwd=kb())

    assert result.json()["profile"] == "edit"
    assert result.exit_code == 0
    assert _severities(result) == [("notes/unknown.md", "schema/unknown-field", "warning")]


@pytest.mark.parametrize("argv", [[], ["--file", "notes/unknown.md"]])
def test_ci_true_uses_ci_whatever_the_target_mode(charter, kb, monkeypatch, argv):
    monkeypatch.setenv("CI", "true")

    result = charter("validate", *argv, "--format", "json", cwd=kb())

    assert result.json()["profile"] == "ci"
    assert ("notes/unknown.md", "schema/unknown-field", "error") in _severities(result)
    assert result.exit_code == 1


def test_ci_other_than_true_is_ignored(charter, kb, monkeypatch):
    monkeypatch.setenv("CI", "false")

    assert charter("validate", "--format", "json", cwd=kb()).json()["profile"] == "commit"


def test_charter_profile_forces_a_profile(charter, kb, monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("CHARTER_PROFILE", "edit")

    assert charter("validate", "--format", "json", cwd=kb()).json()["profile"] == "edit"


def test_profile_option_beats_the_environment(charter, kb, monkeypatch):
    monkeypatch.setenv("CHARTER_PROFILE", "edit")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb())

    assert result.json()["profile"] == "ci"
    assert result.exit_code == 1


@pytest.mark.parametrize("how", ["option", "env"])
def test_custom_profile_names_work_with_explicit_selection(charter, kb, monkeypatch, how):
    base = kb(top="profiles:\n  review: {schema/type: info}\n")
    argv = ["--profile", "review"] if how == "option" else []
    if how == "env":
        monkeypatch.setenv("CHARTER_PROFILE", "review")

    result = charter("validate", *argv, "--format", "json", cwd=base)

    assert result.json()["profile"] == "review"
    assert _severities(result) == [
        ("notes/unknown.md", "schema/unknown-field", "error"),
        ("notes/wrong.md", "schema/type", "info"),
    ]


@pytest.mark.parametrize("how", ["option", "env"])
def test_unknown_profile_is_a_usage_error(charter, kb, monkeypatch, how):
    argv = ["--profile", "reveiw"] if how == "option" else []
    if how == "env":
        monkeypatch.setenv("CHARTER_PROFILE", "reveiw")

    result = charter("validate", *argv, "--format", "json", cwd=kb())

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert (diagnostic["path"], diagnostic["code"]) == ("charter.yaml", "usage/unknown-profile")
    assert "`reveiw`" in diagnostic["message"]
    assert "`ci`" in diagnostic["hint"]


# --- built-in defaults ---


@pytest.mark.parametrize("profile, expected", [("edit", "warning"), ("commit", "warning"), ("ci", "error")])
def test_defaults_downgrade_missing_frontmatter_on_edit_and_commit_only(charter, kb, profile, expected):
    base = kb(notes={"loose.md": "prose\n"})

    result = charter("validate", "--profile", profile, "--format", "json", cwd=base)

    assert _severities(result) == [("notes/loose.md", "schema/missing-frontmatter", expected)]


def test_base_warnings_stay_warnings_in_ci(charter, kb):
    base = kb(top="", notes={"unknown.md": UNKNOWN})
    contract = base / "charter.yaml"
    text = contract.read_text(encoding="utf-8").replace("  entry:\n", "  entry:\n    unknown_fields: warn\n")
    contract.write_text(text, encoding="utf-8")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert (result.exit_code, _severities(result)) == (0, [("notes/unknown.md", "schema/unknown-field", "warning")])


@pytest.mark.parametrize("profile", ["edit", "commit"])
def test_defaults_only_downgrade(charter, kb, profile):
    base = kb(top="checks:\n  agents-include: {enabled: false}\n  schema: {severity: info}\n", notes={"unknown.md": UNKNOWN})

    result = charter("validate", "--profile", profile, "--format", "json", cwd=base)

    assert _severities(result) == [("notes/unknown.md", "schema/unknown-field", "info")]


# --- contract profiles ---


def test_a_contract_profile_replaces_the_built_in_default(charter, kb):
    base = kb(top="profiles:\n  commit: {schema/type: warning}\n")

    result = charter("validate", "--format", "json", cwd=base)

    assert _severities(result) == [
        ("notes/unknown.md", "schema/unknown-field", "error"),
        ("notes/wrong.md", "schema/type", "warning"),
    ]


def test_empty_commit_profile_enforces_base_severities(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(top="profiles:\n  commit: {}\n"))

    assert result.exit_code == 1
    assert ("notes/unknown.md", "schema/unknown-field", "error") in _severities(result)


def test_contract_profiles_leave_other_stages_on_their_defaults(charter, kb):
    result = charter("validate", "--file", "notes/unknown.md", "--format", "json", cwd=kb(top="profiles:\n  commit: {}\n"))

    assert _severities(result) == [("notes/unknown.md", "schema/unknown-field", "warning")]


@pytest.mark.parametrize("value", ["error", "warning", "info"])
def test_profile_values_set_the_severity(charter, kb, value):
    base = kb(top=f"profiles:\n  ci: {{schema/type: {value}}}\n", notes={"wrong.md": WRONG_TYPE})

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert _severities(result) == [("notes/wrong.md", "schema/type", value)]


def test_off_drops_the_diagnostic(charter, kb):
    base = kb(top="profiles:\n  ci: {schema/type: off}\n", notes={"wrong.md": WRONG_TYPE})

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


def test_a_code_beats_its_check_id(charter, kb):
    base = kb(top="profiles:\n  ci: {schema/type: error, schema: off}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert _severities(result) == [("notes/wrong.md", "schema/type", "error")]


def test_a_check_id_covers_every_code_of_the_check(charter, kb):
    base = kb(top="profiles:\n  ci: {schema: info}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert {d["severity"] for d in result.json()["diagnostics"]} == {"info"}


def test_contract_profile_entries_may_raise_a_severity(charter, kb):
    base = kb(top="checks:\n  agents-include: {enabled: false}\n  schema: {severity: info}\nprofiles:\n  edit: {schema/unknown-field: warning}\n")

    result = charter("validate", "--profile", "edit", "--format", "json", cwd=base)

    assert ("notes/unknown.md", "schema/unknown-field", "warning") in _severities(result)


@pytest.mark.parametrize(
    "key, hint",
    [
        ("schema/unkown-field", "Did you mean `schema/unknown-field`?"),
        ("shema", "Did you mean `schema`?"),
        ("contract/invalid", None),
        ("frontmatter", None),
    ],
)
def test_profile_keys_must_name_a_known_check_or_code(charter, kb, key, hint):
    result = charter("validate", "--format", "json", cwd=kb(top=f"profiles:\n  ci: {{{key}: off}}\n"))

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    assert diagnostic["message"] == f"profiles.ci.{key}: unknown check or diagnostic code `{key}`."
    if hint:
        assert diagnostic["hint"] == hint


@pytest.mark.parametrize("key", ["index/unreadable", "paths", "paths/kind-not-allowed"])
def test_profile_keys_may_name_index_codes_and_other_checks(charter, kb, key):
    assert charter("validate", cwd=kb(top=f"profiles:\n  ci: {{{key}: off}}\n")).exit_code != 2


@pytest.mark.parametrize(
    "top, location",
    [
        ("profiles:\n  ci: {schema/type: fatal}\n", "profiles.ci.schema/type"),
        ("profiles:\n  ci:\n", "profiles.ci"),
        ("profiles: [ci]\n", "profiles"),
    ],
)
def test_invalid_profiles_are_contract_errors(charter, kb, top, location):
    result = charter("validate", "--format", "json", cwd=kb(top=top))

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    assert diagnostic["message"].startswith(f"{location}: ")


# --- checks.<id> ---


def test_disabled_check_reports_nothing(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(top="checks:\n  agents-include: {enabled: false}\n  schema: {enabled: false}\n"))

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


def test_check_severity_sets_the_base_severity_of_all_its_diagnostics(charter, kb):
    base = kb(top="checks:\n  agents-include: {enabled: false}\n  schema: {severity: warning}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert {d["severity"] for d in result.json()["diagnostics"]} == {"warning"}
    assert result.exit_code == 0


def test_profile_applies_on_top_of_check_severity(charter, kb):
    base = kb(top="checks:\n  agents-include: {enabled: false}\n  schema: {severity: warning}\nprofiles:\n  ci: {schema/type: error}\n")

    result = charter("validate", "--profile", "ci", "--format", "json", cwd=base)

    assert _severities(result) == [
        ("notes/unknown.md", "schema/unknown-field", "warning"),
        ("notes/wrong.md", "schema/type", "error"),
    ]


def test_check_config_applies_to_the_paths_check(charter, kb):
    base = kb(
        top='paths:\n  "Fixed/**": {kinds: [other]}\nchecks:\n  agents-include: {enabled: false}\n  paths: {severity: info}\n',
        notes={"Fixed/note.md": "---\nkind: entry\n---\n"},
    )
    contract = base / "charter.yaml"
    contract.write_text(contract.read_text(encoding="utf-8") + "  other: {}\n", encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=base)

    assert _severities(result) == [("notes/Fixed/note.md", "paths/kind-not-allowed", "info")]


def test_unknown_check_id_is_a_contract_error(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(top="checks:\n  agents-include: {enabled: false}\n  shema: {enabled: false}\n"))

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "contract/invalid"
    assert diagnostic["message"] == "checks.shema: unknown check `shema`."
    assert diagnostic["hint"] == "Did you mean `schema`?"


@pytest.mark.parametrize(
    "entry, location",
    [("{severity: off}", "checks.schema.severity"), ("{enabled: maybe}", "checks.schema.enabled"), ("{bogus: 1}", "checks.schema")],
)
def test_invalid_check_config_is_a_contract_error(charter, kb, entry, location):
    top = f"checks:\n  agents-include: {{enabled: false}}\n  schema: {entry}\n"
    result = charter("validate", "--format", "json", cwd=kb(top=top))

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["message"].startswith(f"{location}: ")


# --- --strict and output ---


def test_strict_turns_warnings_into_failures(charter, kb):
    result = charter("validate", "--strict", "--format", "json", cwd=kb(notes={"unknown.md": UNKNOWN}))

    assert result.exit_code == 1
    assert _severities(result) == [("notes/unknown.md", "schema/unknown-field", "error")]


def test_strict_leaves_info_alone(charter, kb):
    base = kb(top="profiles:\n  ci: {schema/type: info}\n", notes={"wrong.md": WRONG_TYPE})

    result = charter("validate", "--strict", "--profile", "ci", "--format", "json", cwd=base)

    assert (result.exit_code, _severities(result)) == (0, [("notes/wrong.md", "schema/type", "info")])


def test_text_output_names_the_profile(charter, kb):
    result = charter("validate", cwd=kb())

    assert result.stdout.endswith("1 error, 1 warning, 0 infos (profile: commit)\n")


def test_clean_text_output_names_the_profile(charter, kb):
    result = charter("validate", "--profile", "ci", cwd=kb(notes={"ok.md": "---\nkind: entry\n---\n"}))

    assert result.stdout == "No problems found (profile: ci).\n"


def test_agent_output_names_the_profile_after_its_diagnostics(charter, kb):
    result = charter("validate", "--file", "notes/unknown.md", "--format", "agent", cwd=kb())

    assert result.stdout.splitlines()[-1] == "(profile: edit)"
