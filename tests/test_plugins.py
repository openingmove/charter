import json
import os
import shutil
import time

import pytest
from conftest import FIXTURES, commit_files, run_git, write_files
from plugin_support import (
    KINDS_TWO,
    LINKED,
    NOTE,
    OTHER,
    PROBE,
    plugin_kb,
    probe,
    rewrite_manifest,
)
from process_support import GONE_WITHIN_SECONDS, LEFTOVER_SECONDS, end, gone_within, windows_only


@pytest.fixture
def kb(make_kb):
    """A knowledge base under `notes/` whose contract ends with `checks`, and the named sample plugins in `tools/`."""
    return plugin_kb(make_kb)


def _diagnostics(result):
    return [(d["path"], d["line"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


BANNED = "  banned-words:\n    source: tools/banned-words\n    with: {words: [secret]}\n"


# --- running a plugin ---


def test_plugin_diagnostics_merge_into_the_output_with_contract_relative_paths(charter, kb):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb(BANNED, ["banned-words"]))

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("notes/a.md", 6, "error", "banned-words/found"),
        ("notes/b.md", 4, "error", "banned-words/found"),
    ]
    assert result.json()["diagnostics"][0]["message"] == "Heading `A secret step` contains `secret`."


def test_plugin_sees_only_the_files_selected_as_targets(charter, kb):
    result = charter("validate", "--file", "notes/b.md", "--format", "json", cwd=kb(BANNED, ["banned-words"]))

    assert _diagnostics(result) == [("notes/b.md", 4, "error", "banned-words/found")]


def test_plugin_runs_in_its_own_directory_and_receives_the_request(charter, kb):
    base = kb("  probe:\n    source: ./tools/probe\n", ["probe"])

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])
    request = json.loads((base / "tools" / "probe" / "request.json").read_text(encoding="utf-8"))
    notes = {note["path"]: note for note in request["index"]["notes"]}
    assert {key: request[key] for key in ("protocol", "plugin", "params", "mode", "root", "targets")} == {
        "protocol": "charter-plugin/1",
        "plugin": {"id": "probe", "version": "2.0.1"},
        "params": {},
        "mode": "vault",
        "root": "notes",
        "targets": ["a.md", "b.md"],
    }
    assert notes["a.md"] == {
        "path": "a.md",
        "kind": "entry",
        "variant": None,
        "frontmatter": {"kind": "entry"},
        "links": [{"raw": "[[b]]", "target": "b.md", "field": None, "line": 8}],
        "headings": [{"level": 1, "text": "Plans", "line": 4}, {"level": 2, "text": "A secret step", "line": 6}],
        "tags": [],
    }


def test_request_carries_the_day_the_run_is_judged_as_of(charter, kb, monkeypatch):
    base = kb("  probe:\n    source: ./tools/probe\n", ["probe"])
    monkeypatch.setenv("CHARTER_TODAY", "2024-03-05")

    charter("validate", "--format", "json", cwd=base)

    request = json.loads((base / "tools" / "probe" / "request.json").read_text(encoding="utf-8"))
    assert request["today"] == "2024-03-05"


def test_request_carries_variants_link_fields_tags_and_dates_as_json(charter, kb):
    kinds = (
        "kinds:\n  place:\n    variant_by: size\n    variants: {town: {}, city: {}}\n"
        "    fields:\n      near: {type: link, to: place}\n      founded: {type: date}\n"
    )
    notes = {
        "Ashby.md": "---\nkind: place\nsize: town\nnear: '[[Bram]]'\nfounded: 1801-02-03\ntags: [river]\n---\n",
        "Bram.md": "---\nkind: place\nsize: city\n---\n",
    }
    base = kb("  probe:\n    source: tools/probe\n", ["probe"], notes=notes, kinds=kinds)

    charter("validate", "--file", "notes/Ashby.md", "--format", "json", cwd=base)

    request = json.loads((base / "tools" / "probe" / "request.json").read_text(encoding="utf-8"))
    ashby = next(note for note in request["index"]["notes"] if note["path"] == "Ashby.md")
    assert request["targets"] == ["Ashby.md"]
    assert (ashby["kind"], ashby["variant"], ashby["tags"]) == ("place", "town", ["river"])
    assert ashby["frontmatter"]["founded"] == "1801-02-03"
    assert ashby["links"] == [{"raw": "[[Bram]]", "target": "Bram.md", "field": "near", "line": 4}]


def test_plugin_at_the_contract_root_gets_root_dot(charter, make_kb):
    base = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
        "  probe: {source: tools/probe}\n",
        "a.md": "---\nkind: entry\n---\n",
    })
    shutil.copytree(FIXTURES / "plugins" / "probe", base / "tools" / "probe")

    result = charter("validate", "--format", "json", cwd=base)

    request = json.loads((base / "tools" / "probe" / "request.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert (request["root"], request["targets"]) == (".", ["a.md"])


def test_disabled_plugin_does_not_run(charter, kb):
    base = kb("  misbehave:\n    source: tools/misbehave\n    enabled: false\n    with: {behaviour: crash}\n", ["misbehave"])

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


# --- severities ---


def test_check_severity_overrides_a_plugin_diagnostic(charter, kb):
    result = charter(
        "validate", "--profile", "ci", "--format", "json", cwd=kb(BANNED + "    severity: warning\n", ["banned-words"])
    )

    assert result.exit_code == 0
    assert {severity for _, _, severity, _ in _diagnostics(result)} == {"warning"}


@pytest.mark.parametrize("key", ["banned-words", "banned-words/found"])
def test_profiles_name_a_plugin_or_its_codes(charter, kb, key):
    base = kb(BANNED, ["banned-words"], top=f"profiles:\n  review: {{{key}: info}}\n")

    result = charter("validate", "--profile", "review", "--format", "json", cwd=base)

    assert result.exit_code == 0
    assert {severity for _, _, severity, _ in _diagnostics(result)} == {"info"}


# --- failures: plugin/failed, exit 3 ---


MISBEHAVE = "  misbehave:\n    source: tools/misbehave\n    with: {{behaviour: {behaviour}}}\n"


@pytest.mark.parametrize(
    ("behaviour", "message"),
    [
        ("crash", "Plugin `misbehave` exited with status 4."),
        ("not-json", "Plugin `misbehave` did not write a JSON response"),
        ("wrong-protocol", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("malformed-diagnostic", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("foreign-code", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("escaping-path", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("backslash-path", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("drive-path", "Plugin `misbehave` did not follow `charter-plugin/1`"),
        ("flood", "Plugin `misbehave` wrote more than 16 MB to stdout or stderr."),
    ],
)
def test_plugin_failure_is_plugin_failed_at_its_check_and_exits_three(charter, kb, behaviour, message):
    base = kb(MISBEHAVE.format(behaviour=behaviour), ["misbehave"])

    result = charter("validate", "--format", "json", cwd=base)

    assert result.exit_code == 3
    assert _diagnostics(result) == [("charter.yaml", 7, "error", "plugin/failed")]
    assert result.json()["diagnostics"][0]["message"].startswith(message)


def test_plugin_failure_includes_its_stderr(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"]))

    assert "misbehave: could not read the traversal table" in result.json()["diagnostics"][0]["message"]


def test_plugin_failure_truncates_long_stderr_to_its_end(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(MISBEHAVE.format(behaviour="noisy-crash"), ["misbehave"]))

    message = result.json()["diagnostics"][0]["message"]
    assert result.exit_code == 3
    assert message.endswith("the real cause")
    assert len(message) < 2500


def test_plugin_that_outlives_its_timeout_fails(charter, kb):
    result = charter("validate", "--format", "json", cwd=kb(MISBEHAVE.format(behaviour="hang"), ["misbehave"]))

    assert result.exit_code == 3
    assert result.json()["diagnostics"][0]["message"].startswith("Plugin `misbehave` did not finish within 4000 ms.")


def test_plugin_whose_command_cannot_start_fails(charter, kb):
    base = kb("  probe:\n    source: tools/probe\n", ["probe"])
    rewrite_manifest(base / "tools" / "probe", run='["charter-test-no-such-program", "x"]')

    result = charter("validate", "--format", "json", cwd=base)

    assert result.exit_code == 3
    assert _diagnostics(result) == [("charter.yaml", 7, "error", "plugin/failed")]
    assert "`charter-test-no-such-program`" in result.json()["diagnostics"][0]["message"]


def test_plugin_failure_exits_three_even_beside_other_errors_and_in_every_format(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash") + BANNED, ["misbehave", "banned-words"])

    for output_format in ("json", "text", "agent"):
        result = charter("validate", "--format", output_format, cwd=base)
        assert result.exit_code == 3
        assert "plugin/failed" in result.stdout


def test_profiles_cannot_silence_plugin_failures(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"], top="profiles:\n  review: {misbehave: off}\n")

    result = charter("validate", "--profile", "review", "--format", "json", cwd=base)

    assert result.exit_code == 3


def test_check_severity_cannot_soften_a_plugin_failure(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash") + "    severity: info\n", ["misbehave"])

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (3, [("charter.yaml", 7, "error", "plugin/failed")])


@pytest.mark.skipif(os.name == "nt", reason="the stray process escapes through a POSIX session of its own")
def test_timeout_holds_when_a_process_the_plugin_started_keeps_its_output_open(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="orphan"), ["misbehave"])

    started = time.monotonic()
    result = charter("validate", "--format", "json", cwd=base)

    assert result.exit_code == 3
    assert result.json()["diagnostics"][0]["message"].startswith("Plugin `misbehave` did not finish within 4000 ms.")
    # The stray process sleeps for 30 seconds; charter stops waiting for it shortly after the timeout.
    assert time.monotonic() - started < 15


# The leave-child tests need the plugin to write `child.pid` before its timeout, and `uv` start-up counts
# against that timeout. A cold runner can take close to the fixture's 4000 ms just to start, so these tests
# give the plugin more time.
LEAVE_CHILD_TIMEOUT_MS = 10000

# The leftover child must outlive the last `gone_within` check by a clear margin; otherwise a test could pass
# because the child ended by itself, not because charter ended it.
assert LEAVE_CHILD_TIMEOUT_MS / 1000 + GONE_WITHIN_SECONDS <= LEFTOVER_SECONDS - 5


def _leave_child_kb(kb, behaviour):
    """A knowledge base whose `misbehave` plugin runs `behaviour` with LEAVE_CHILD_TIMEOUT_MS to finish."""
    base = kb(MISBEHAVE.format(behaviour=behaviour), ["misbehave"])
    rewrite_manifest(base / "tools" / "misbehave", timeout_ms=LEAVE_CHILD_TIMEOUT_MS)
    return base


def _left_child(base):
    """The pid of the process a `leave-child` plugin started, or None when it wrote none."""
    pid_file = base / "tools" / "misbehave" / "child.pid"
    return int(pid_file.read_text(encoding="utf-8")) if pid_file.exists() else None


@pytest.mark.parametrize(
    ("behaviour", "exit_code"), [("leave-child", 0), ("leave-child-and-hang", 3), ("leave-child-and-flood", 3)]
)
def test_a_process_the_plugin_left_running_ends_with_the_run(charter, kb, behaviour, exit_code):
    base = _leave_child_kb(kb, behaviour)
    pid = None
    try:
        result = charter("validate", "--format", "json", cwd=base)
        pid = _left_child(base)

        assert result.exit_code == exit_code
        assert pid is not None
        assert gone_within(pid)
    finally:
        end(pid)


@pytest.fixture(params=["_create", "_assign", "_resume"])
def job_refused(request, monkeypatch):
    """On Windows, makes one step of putting a command in a Job Object fail."""
    windows_only()
    from charter import winjob

    def refuse(*args):
        raise OSError("the job is refused")

    monkeypatch.setattr(winjob, request.param, refuse)


@pytest.mark.usefixtures("job_refused")
def test_a_plugin_runs_unchanged_when_charter_cannot_use_a_job(charter, kb):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb(BANNED, ["banned-words"]))

    assert (result.exit_code, result.stderr) == (1, "")
    assert _diagnostics(result) == [
        ("notes/a.md", 6, "error", "banned-words/found"),
        ("notes/b.md", 4, "error", "banned-words/found"),
    ]


@pytest.mark.usefixtures("job_refused")
def test_timeout_still_ends_the_plugin_and_what_it_started_when_charter_cannot_use_a_job(charter, kb):
    base = _leave_child_kb(kb, "leave-child-and-hang")
    pid = None
    try:
        result = charter("validate", "--format", "json", cwd=base)
        pid = _left_child(base)

        assert (result.exit_code, result.stderr) == (3, "")
        assert result.json()["diagnostics"][0]["message"].startswith(
            f"Plugin `misbehave` did not finish within {LEAVE_CHILD_TIMEOUT_MS} ms."
        )
        assert pid is not None
        assert gone_within(pid)
    finally:
        end(pid)


def test_response_may_start_with_a_byte_order_mark(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="bom"), ["misbehave"])

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, [("notes/a.md", 1, "error", "misbehave/found")])


OLD = "---\nkind: entry\ntitle: Old\n---\n"
NEW_KINDS = "kinds:\n  entry:\n    path: '{title}.md'\n    fields:\n      title: {type: string, required: true}\n"


def test_new_refuses_and_exits_three_when_a_plugin_fails(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"], notes={"Old.md": OLD}, kinds=NEW_KINDS)

    result = charter("new", "entry", "Fresh", cwd=base)

    assert result.exit_code == 3
    assert "plugin/failed" in result.stdout
    assert not (base / "notes" / "Fresh.md").exists()


def test_new_reports_plugin_diagnostics_on_the_new_note(charter, kb):
    base = kb(
        BANNED,
        ["banned-words"],
        notes={"Old.md": OLD, "Templates/entry.md": "# {{title}}\n"},
        top="paths:\n  'Templates/**': {ignore: true}\n",
        kinds=NEW_KINDS.replace("    fields:", "    template: Templates/entry.md\n    fields:"),
    )

    result = charter("new", "entry", "Secret plans", cwd=base)

    assert result.exit_code == 1
    assert "banned-words/found" in result.stdout
    assert not (base / "notes" / "Secret plans.md").exists()


# --- loading: contract errors, exit 2 ---


def _contract_error(charter, base):
    result = charter("validate", "--format", "json", cwd=base)
    assert result.exit_code == 2
    return result.json()["diagnostics"]


@pytest.mark.parametrize(
    "run",
    [
        '"uv run --script probe.py"',
        '["probe.sh"]',
        '["tools/probe.ps1", "--fast"]',
        '["PROBE.BAT"]',
        '["probe.cmd"]',
        '["bash", "check.sh"]',
        '["/bin/sh", "-c", "python3 probe.py"]',
        '["powershell.exe", "-File", "probe.ps1"]',
        "['C:\\Windows\\System32\\cmd.exe', '/c', 'probe.py']",
    ],
)
def test_shell_entry_points_are_rejected(charter, kb, run):
    base = kb("  probe:\n    source: tools/probe\n", ["probe"])
    rewrite_manifest(base / "tools" / "probe", run=run)

    diagnostics = _contract_error(charter, base)

    assert [(d["path"], d["line"], d["code"]) for d in diagnostics] == [("charter.yaml", 8, "contract/invalid")]
    assert "`tools/probe/charter-plugin.yaml`" in diagnostics[0]["message"]
    assert "shell" in diagnostics[0]["message"]


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"charter_plugin": "2"}, "charter_plugin"),
        ({"id": "other"}, "`other`"),
        ({"run": "[]"}, "run"),
        ({"version": None}, "version"),
        ({"timeout_ms": "0"}, "timeout_ms"),
        ({"colour": "blue"}, "colour"),
        ({"config_schema": "{type: nonsense}"}, "config_schema"),
        ({"docs": "3"}, "docs"),
        ({"docs": "MISSING.md"}, "`MISSING.md`"),
        ({"docs": "../banned-words/RULES.md"}, "outside the plugin's directory"),
        ({"docs": "/etc/hosts"}, "outside the plugin's directory"),
        ({"docs": "."}, "`.`"),
    ],
)
def test_invalid_manifest_is_a_contract_error(charter, kb, changes, fragment):
    base = kb("  probe:\n    source: tools/probe\n", ["probe"])
    rewrite_manifest(base / "tools" / "probe", **changes)

    diagnostics = _contract_error(charter, base)

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]
    assert fragment in diagnostics[0]["message"]


def test_source_without_a_manifest_is_a_contract_error(charter, kb):
    diagnostics = _contract_error(charter, kb("  probe:\n    source: tools/missing\n"))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]
    assert "`tools/missing/charter-plugin.yaml`" in diagnostics[0]["message"]


def test_builtin_check_takes_no_source(charter, kb):
    diagnostics = _contract_error(charter, kb("  schema:\n    source: tools/probe\n", ["probe"]))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]


def test_unknown_check_without_source_hints_at_source(charter, kb):
    diagnostics = _contract_error(charter, kb("  probe: {enabled: true}\n", ["probe"]))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(7, "contract/invalid")]
    assert "source" in diagnostics[0]["hint"]


@pytest.mark.parametrize(
    ("checks", "line"),
    [
        ("  banned-words:\n    source: tools/banned-words\n    with: {words: secret}\n", 9),
        ("  banned-words:\n    source: tools/banned-words\n    with: {words: [secret], also: 1}\n", 9),
        ("  banned-words:\n    source: tools/banned-words\n", 7),
        ("  probe:\n    source: tools/probe\n    with: {words: [secret]}\n", 9),
        ("  schema:\n    with: {strict: true}\n", 8),
    ],
)
def test_parameters_are_validated_against_the_config_schema_at_load(charter, kb, checks, line):
    diagnostics = _contract_error(charter, kb(checks, ["banned-words", "probe"]))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(line, "contract/invalid")]


def test_parameter_error_names_the_parameter(charter, kb):
    base = kb("  banned-words:\n    source: tools/banned-words\n    with: {words: secret}\n", ["banned-words"])

    diagnostics = _contract_error(charter, base)

    assert diagnostics[0]["message"] == "checks.banned-words.with.words: expected a list, got `secret`."


@pytest.mark.parametrize("source", ["../elsewhere/probe", "/opt/plugins/probe", "C:/plugins/probe", "tools/../../probe"])
def test_source_outside_the_contract_directory_is_a_contract_error(charter, kb, source):
    diagnostics = _contract_error(charter, kb(f"  probe:\n    source: '{source}'\n", ["probe"]))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]
    assert "outside the directory holding charter.yaml" in diagnostics[0]["message"]


@pytest.mark.parametrize("check_id", ["plugin", "contract", "usage", "index", "files"])
def test_core_namespaces_are_not_plugin_ids(charter, kb, check_id):
    diagnostics = _contract_error(charter, kb(f"  {check_id}:\n    source: tools/probe\n", ["probe"]))

    assert [(d["line"], d["code"]) for d in diagnostics] == [(7, "contract/invalid")]
    assert "reserved" in diagnostics[0]["message"]


def test_profiles_cannot_name_plugin_failed(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"], top="profiles:\n  review: {plugin/failed: off}\n")

    diagnostics = _contract_error(charter, base)

    assert [(d["line"], d["code"]) for d in diagnostics] == [(4, "contract/invalid")]


def test_disabled_plugin_is_not_read(charter, kb):
    base = kb("  probe:\n    source: tools/not-installed\n    enabled: false\n    with: {anything: 1}\n")

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, result.json()["diagnostics"]) == (0, [])


@pytest.mark.parametrize("requirement", [">=0.0.1", ">0.0.1,<9999", "!=0.0.0, >= 0.1", "<9999.0.0"])
def test_met_charter_requirement_loads(charter, kb, requirement):
    base = kb("  probe:\n    source: tools/probe\n", ["probe"])
    rewrite_manifest(base / "tools" / "probe", requires=f"{{charter: '{requirement}'}}")

    result = charter("validate", "--format", "json", cwd=base)

    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("requirement", "fragment"),
    [
        ("<0.0.1", "requires charter `<0.0.1`, but this is charter"),
        (">=0.0.1,==9999", "requires charter `>=0.0.1,==9999`"),
        ("~=1.0", "not a version requirement"),
        (">=1.x", "not a version requirement"),
    ],
)
def test_unmet_or_malformed_charter_requirement_is_a_contract_error(charter, kb, requirement, fragment):
    base = kb("  probe:\n    source: tools/probe\n", ["probe"])
    rewrite_manifest(base / "tools" / "probe", requires=f"{{charter: '{requirement}'}}")

    diagnostics = _contract_error(charter, base)

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]
    assert fragment in diagnostics[0]["message"]


# --- scope, needs, triggers and hook ---


EVERY_NOTE = ["Places/Town.md", "a.md", "b.md", "c.md", "d.md"]


def _received(base):
    request = base / "tools" / "probe" / "request.json"
    return json.loads(request.read_text(encoding="utf-8")) if request.exists() else None


def _indexed(request):
    return [note["path"] for note in request["index"]["notes"]]


def test_file_scope_plugin_receives_the_targets_and_the_notes_they_link_to(charter, kb):
    base = probe(kb, scope="file")

    result = charter("validate", "--file", "notes/a.md", "--format", "json", cwd=base)

    request = _received(base)
    assert result.exit_code == 0
    assert (request["mode"], request["targets"], _indexed(request)) == ("file", ["a.md"], ["a.md", "b.md"])


def test_file_scope_plugin_receives_the_whole_index_on_a_whole_run(charter, kb):
    base = probe(kb, scope="file")

    charter("validate", "--format", "json", cwd=base)

    request = _received(base)
    assert (request["mode"], _indexed(request)) == ("vault", EVERY_NOTE)


@pytest.mark.parametrize("scope", ["vault", None])
def test_vault_scope_plugin_receives_the_whole_index_for_a_single_file(charter, kb, scope):
    base = probe(kb, scope=scope)

    charter("validate", "--file", "notes/a.md", "--format", "json", cwd=base)

    request = _received(base)
    assert (request["mode"], request["targets"], _indexed(request)) == ("vault", ["a.md"], EVERY_NOTE)


def test_body_is_sent_only_when_the_plugin_needs_it(charter, kb):
    base = probe(kb, needs="[body]")

    charter("validate", "--file", "notes/a.md", "--format", "json", cwd=base)

    notes = {note["path"]: note for note in _received(base)["index"]["notes"]}
    assert notes["a.md"]["body"] == "# Plans\n\n## A secret step\n\nSee [[b]].\n"
    assert notes["b.md"]["body"] == "# Secret notes\n"


def test_body_of_a_note_without_frontmatter_is_its_whole_text(charter, kb):
    base = probe(kb, notes={"a.md": "Just text.\r\nMore.\r\n"}, needs="[body]")

    charter("validate", "--format", "json", cwd=base)

    assert _received(base)["index"]["notes"][0]["body"] == "Just text.\nMore.\n"


@pytest.mark.parametrize(
    ("triggers", "target", "runs"),
    [
        ("{kinds: [place]}", "notes/a.md", False),
        ("{kinds: [place]}", "notes/Places/Town.md", True),
        ("{globs: ['Places/**']}", "notes/a.md", False),
        ("{globs: ['Places/**']}", "notes/Places/Town.md", True),
        ("{globs: ['*.md']}", "notes/Places/Town.md", False),
        ("{kinds: [place], globs: ['a.md']}", "notes/a.md", True),
        ("{kinds: [], globs: ['a.md']}", "notes/a.md", True),
    ],
)
def test_triggers_limit_when_a_plugin_runs(charter, kb, triggers, target, runs):
    base = probe(kb, triggers=triggers)

    result = charter("validate", "--file", target, "--format", "json", cwd=base)

    assert result.exit_code == 0
    assert (_received(base) is not None) == runs


def test_kind_triggers_fire_on_a_whole_run(charter, kb):
    base = probe(kb, triggers="{kinds: [place]}")

    charter("validate", "--format", "json", cwd=base)

    assert _received(base) is not None


def test_glob_triggers_need_a_matching_note_even_on_a_whole_run(charter, kb):
    base = probe(kb, triggers="{globs: ['Meta/Traversal.md']}")

    charter("validate", "--format", "json", cwd=base)

    assert _received(base) is None


@pytest.mark.parametrize(
    ("hook", "argv", "runs"),
    [
        ("false", ["--file", "notes/a.md"], False),
        ("false", ["--all"], True),
        ("false", [], True),
        ("true", ["--file", "notes/a.md"], True),
    ],
)
def test_plugin_without_hook_is_skipped_per_edit_only(charter, kb, hook, argv, runs):
    base = probe(kb, hook=hook)

    charter("validate", *argv, "--format", "json", cwd=base)

    assert (_received(base) is not None) == runs


def test_new_leaves_out_a_plugin_without_hook(charter, kb):
    base = kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"], notes={"Old.md": OLD}, kinds=NEW_KINDS)
    rewrite_manifest(base / "tools" / "misbehave", hook="false")

    result = charter("new", "entry", "Fresh", cwd=base)

    assert result.exit_code == 0
    assert (base / "notes" / "Fresh.md").exists()
    assert charter("validate", "--all", cwd=base).exit_code == 3


def test_file_scope_plugin_gets_no_notes_when_only_the_contract_is_targeted(charter, kb):
    base = probe(kb, scope="file")

    charter("validate", "--file", "charter.yaml", "--format", "json", cwd=base)

    request = _received(base)
    assert (request["mode"], request["targets"], _indexed(request)) == ("file", [], [])


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"scope": "note"}, "scope"),
        ({"needs": "[headings]"}, "needs"),
        ({"needs": "body"}, "needs"),
        ({"triggers": "{paths: [a.md]}"}, "paths"),
        ({"triggers": "{kinds: place}"}, "kinds"),
        ({"triggers": "{}"}, "never run"),
        ({"triggers": "{kinds: [], globs: []}"}, "never run"),
        ({"hook": "sometimes"}, "hook"),
    ],
)
def test_invalid_scope_needs_triggers_or_hook_is_a_contract_error(charter, kb, changes, fragment):
    base = kb(PROBE, ["probe"])
    rewrite_manifest(base / "tools" / "probe", **changes)

    diagnostics = _contract_error(charter, base)

    assert [(d["line"], d["code"]) for d in diagnostics] == [(8, "contract/invalid")]
    assert fragment in diagnostics[0]["message"]


def test_a_trigger_kind_the_contract_does_not_declare_is_a_contract_error_with_a_hint(charter, kb):
    base = kb(PROBE, ["probe"], kinds=KINDS_TWO)
    rewrite_manifest(base / "tools" / "probe", triggers="{kinds: [placs]}")

    diagnostics = _contract_error(charter, base)

    assert [(d["line"], d["code"]) for d in diagnostics] == [(9, "contract/invalid")]
    assert "tools/probe/charter-plugin.yaml" in diagnostics[0]["message"]
    assert "`placs`" in diagnostics[0]["message"]
    assert diagnostics[0]["hint"] == "Did you mean `place`?"


def test_a_trigger_kind_the_contract_declares_loads(charter, kb):
    base = kb(PROBE, ["probe"], kinds=KINDS_TWO)
    rewrite_manifest(base / "tools" / "probe", triggers="{kinds: [place, entry]}")

    assert charter("validate", "--format", "json", cwd=base).exit_code == 0


# --- charter plugin run ---


def test_dump_input_writes_the_exact_request_without_running_the_plugin(charter, kb):
    base = probe(kb, scope="file", needs="[body]")

    dumped = charter("plugin", "run", "probe", "--dump-input", "--file", "notes/a.md", cwd=base)

    assert (dumped.exit_code, dumped.stderr) == (0, "")
    assert _received(base) is None
    charter("validate", "--file", "notes/a.md", "--format", "json", cwd=base)
    assert json.loads(dumped.stdout) == _received(base)


def test_dump_input_defaults_to_a_whole_run(charter, kb):
    dumped = charter("plugin", "run", "probe", "--dump-input", cwd=probe(kb))

    assert json.loads(dumped.stdout)["targets"] == EVERY_NOTE


def test_dump_input_ignores_triggers_and_hook(charter, kb):
    base = probe(kb, triggers="{kinds: [place]}", hook="false")

    dumped = charter("plugin", "run", "probe", "--dump-input", "--file", "notes/a.md", cwd=base)

    assert json.loads(dumped.stdout)["targets"] == ["a.md"]


def test_plugin_run_reports_only_that_plugins_diagnostics(charter, kb):
    base = kb(BANNED, ["banned-words"], notes={"a.md": NOTE, "b.md": OTHER, "c.md": "no frontmatter\n"})

    result = charter("plugin", "run", "banned-words", "--profile", "ci", "--format", "json", cwd=base)

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("notes/a.md", 6, "error", "banned-words/found"),
        ("notes/b.md", 4, "error", "banned-words/found"),
    ]


def test_plugin_run_runs_a_plugin_its_triggers_and_hook_would_skip(charter, kb):
    base = probe(kb, triggers="{kinds: [place]}", hook="false")

    result = charter("plugin", "run", "probe", "--file", "notes/a.md", "--format", "json", cwd=base)

    assert result.exit_code == 0
    assert _received(base)["targets"] == ["a.md"]


def test_plugin_run_reports_a_plugin_failure(charter, kb):
    result = charter("plugin", "run", "misbehave", cwd=kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"]))

    assert result.exit_code == 3
    assert "plugin/failed" in result.stdout


@pytest.mark.parametrize("plugin_id", ["schema", "nothing", "probe"])
def test_plugin_run_of_an_unknown_or_disabled_plugin_is_a_usage_error(charter, kb, plugin_id):
    base = kb("  probe:\n    source: tools/probe\n    enabled: false\n", ["probe"])

    result = charter("plugin", "run", plugin_id, "--format", "json", cwd=base)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/unknown-plugin"]
    assert _received(base) is None


def test_dump_input_of_an_unknown_plugin_is_a_usage_error(charter, kb):
    result = charter("plugin", "run", "nope", "--dump-input", cwd=probe(kb))

    assert result.exit_code == 2
    assert "usage/unknown-plugin" in result.stdout


def _committed_probe(kb, **manifest):
    base = probe(kb, **manifest)
    run_git(base, "init", "-q", "--initial-branch=main")
    commit_files(base, {})
    return base


def test_a_plugin_that_needs_before_receives_each_touched_files_earlier_content(charter, kb):
    base = _committed_probe(kb, needs="[before]")
    write_files(base, {"notes/c.md": "---\nkind: entry\n---\n# Changed\n", "notes/e.md": "---\nkind: entry\n---\n"})
    (base / "notes/d.md").unlink()
    run_git(base, "add", "-A")

    # A staged run starts the plugin from a temporary copy, so the request is read from --dump-input.
    dumped = charter("plugin", "run", "probe", "--dump-input", "--staged", cwd=base)

    assert json.loads(dumped.stdout)["before"] == {
        "available": True,
        "reason": None,
        "files": [
            {"path": "c.md", "status": "modified", "content": "---\nkind: entry\n---\n# Unrelated\n"},
            {"path": "d.md", "status": "deleted", "content": "---\nkind: entry\n---\nBack to [[a]].\n"},
            {"path": "e.md", "status": "added", "content": None},
        ],
    }


def test_before_compares_the_working_copy_with_the_last_commit_on_a_whole_run(charter, kb):
    base = _committed_probe(kb, needs="[before]")
    write_files(base, {"notes/c.md": "---\nkind: entry\n---\n# Changed\n", "notes/new.md": "---\nkind: entry\n---\n"})

    dumped = charter("plugin", "run", "probe", "--dump-input", cwd=base)

    files = json.loads(dumped.stdout)["before"]["files"]
    assert [(f["path"], f["status"]) for f in files] == [("c.md", "modified"), ("new.md", "added")]


def test_before_says_why_it_is_unavailable_outside_a_git_repository(charter, kb):
    base = probe(kb, needs="[before]")

    charter("validate", "--format", "json", cwd=base)

    before = _received(base)["before"]
    assert (before["available"], before["files"]) == (False, [])
    assert "git repository" in before["reason"]


def test_before_is_sent_only_when_the_plugin_needs_it(charter, kb):
    base = _committed_probe(kb)

    dumped = charter("plugin", "run", "probe", "--dump-input", cwd=base)

    assert "before" not in json.loads(dumped.stdout)


def test_dump_input_takes_the_staged_files_as_targets(charter, kb):
    base = _committed_probe(kb)
    write_files(base, {"notes/c.md": "---\nkind: entry\n---\n# Changed\n", "notes/d.md": "---\nkind: entry\n---\n"})
    run_git(base, "add", "notes/c.md")

    dumped = charter("plugin", "run", "probe", "--dump-input", "--staged", cwd=base)

    assert json.loads(dumped.stdout)["targets"] == ["c.md"]


@pytest.mark.parametrize("deleted, runs", [("notes/Places/Town.md", True), ("notes/c.md", False)])
def test_a_staged_deletion_runs_plugins_triggered_by_its_kind(charter, kb, deleted, runs):
    # A plugin that always fails shows whether it ran.
    base = kb(MISBEHAVE.format(behaviour="crash"), ["misbehave"], notes=LINKED, kinds=KINDS_TWO)
    rewrite_manifest(base / "tools" / "misbehave", triggers="{kinds: [place]}")
    run_git(base, "init", "-q", "--initial-branch=main")
    commit_files(base, {})
    run_git(base, "rm", "-q", deleted)

    result = charter("validate", "--staged", "--format", "json", cwd=base)

    assert [d["code"] for d in result.json()["diagnostics"]] == (["plugin/failed"] if runs else [])


@pytest.mark.parametrize("options", [["--profile", "ci"], ["--strict"], ["--strict", "--profile", "ci"]])
def test_dump_input_refuses_severity_options(charter, kb, options):
    base = probe(kb)

    result = charter("plugin", "run", "probe", "--dump-input", *options, "--format", "json", cwd=base)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/conflicting-options"]


@pytest.mark.parametrize("given", [["--format", "text"], ["--format", "agent"], ["--format", "json"], ["--format=json"]])
def test_dump_input_refuses_format_even_when_it_is_the_default(charter, kb, given):
    base = probe(kb)

    result = charter("plugin", "run", "probe", "--dump-input", *given, cwd=base)

    assert result.exit_code == 2
    assert _received(base) is None
    if "json" in given[-1]:
        assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/conflicting-options"]
    else:
        assert "usage/conflicting-options" in result.stdout


# --- rule docs ---

RULES_SECTION = """\
# Plugin rules

## `banned-words`

Headings must not contain banned words.

### Banned words

No heading may contain a word listed in `checks.banned-words.with.words`.

#### Rewording

Say what the section is about instead:

```yaml
# not a heading: code stays as written
words: [secret]
```
"""


def test_describe_ends_with_plugin_rule_docs_under_the_plugin_id(charter, kb):
    result = charter("describe", cwd=kb(BANNED, ["banned-words"]))

    assert result.exit_code == 0
    assert result.stdout.endswith("\n" + RULES_SECTION)


def test_check_table_lists_enabled_plugins_after_the_builtins(charter, kb):
    base = kb(BANNED + "  probe:\n    source: tools/probe\n    enabled: false\n", ["banned-words", "probe"])

    lines = charter("describe", cwd=base).stdout.splitlines()

    rows = [line for line in lines if line.startswith("| `")]
    assert rows[-1] == "| `banned-words` | yes | base | `banned-words/…` |"
    assert not any("probe" in line for line in lines)


def test_describe_json_carries_plugin_rules_and_plugin_checks(charter, kb):
    result = charter("describe", "--format", "json", cwd=kb(BANNED, ["banned-words"]))

    document = result.json()
    assert document["plugin_rules"] == [
        {
            "id": "banned-words",
            "description": "Headings must not contain banned words.",
            "docs": (FIXTURES / "plugins" / "banned-words" / "RULES.md").read_text(encoding="utf-8").rstrip("\n"),
        }
    ]
    checks = {check["id"]: check for check in document["checks"]}
    assert checks["banned-words"] == {
        "id": "banned-words",
        "enabled": True,
        "severity": None,
        "codes": [],
        "source": "tools/banned-words",
    }
    assert checks["schema"]["source"] is None


@pytest.mark.parametrize(
    ("triggers", "shown"),
    [(None, True), ("{kinds: [entry]}", True), ("{kinds: [other]}", False), ('{globs: ["*.md"]}', False)],
)
def test_describing_a_kind_shows_the_rules_of_plugins_that_run_for_it(charter, kb, triggers, shown):
    base = kb(BANNED, ["banned-words"], kinds="kinds:\n  entry: {}\n  other: {}\n")
    if triggers is not None:
        rewrite_manifest(base / "tools" / "banned-words", triggers=triggers)

    result = charter("describe", "entry", cwd=base)

    assert result.exit_code == 0
    assert result.stdout.endswith("\n" + RULES_SECTION) is shown
    assert ("Plugin rules" in result.stdout) is shown


def test_plugin_without_docs_or_description_adds_no_rules_section(charter, kb):
    base = kb(BANNED, ["banned-words"])
    rewrite_manifest(base / "tools" / "banned-words", docs=None, description=None)

    result = charter("describe", cwd=base)

    assert "Plugin rules" not in result.stdout
    assert "| `banned-words` | yes | base | `banned-words/…` |" in result.stdout
    assert charter("describe", "--format", "json", cwd=base).json()["plugin_rules"] == []


@pytest.mark.parametrize("docs", [None, "EMPTY.md"])
def test_plugin_with_only_a_description_shows_it_under_plugin_rules(charter, kb, docs):
    base = kb(BANNED, ["banned-words"])
    (base / "tools" / "banned-words" / "EMPTY.md").write_text("\n \n", encoding="utf-8")
    rewrite_manifest(base / "tools" / "banned-words", docs=docs)

    result = charter("describe", cwd=base)

    assert result.stdout.endswith(
        "\n# Plugin rules\n\n## `banned-words`\n\nHeadings must not contain banned words.\n"
    )
    assert charter("describe", "--format", "json", cwd=base).json()["plugin_rules"] == [
        {"id": "banned-words", "description": "Headings must not contain banned words.", "docs": None}
    ]


def _rules_shown(charter, kb, docs):
    base = kb(BANNED, ["banned-words"])
    (base / "tools" / "banned-words" / "RULES.md").write_text(docs, encoding="utf-8")
    rewrite_manifest(base / "tools" / "banned-words", description=None)
    return charter("describe", cwd=base).stdout.partition("## `banned-words`\n\n")[2]


def test_setext_headings_in_rule_docs_are_nested_below_the_plugin(charter, kb):
    docs = "Title\n=====\n\nSome text\nover two lines.\n\nPart\none\n---\n\n- item\n---\n\nEnd.\n"

    assert _rules_shown(charter, kb, docs) == (
        "### Title\n\nSome text\nover two lines.\n\n#### Part one\n\n- item\n---\n\nEnd.\n"
    )


def test_only_headings_outside_code_and_comments_are_nested(charter, kb):
    docs = "<!--\n# hidden\n-->\n\n## Real\n\n```\n# code\n```\n\n#not-a-heading\n"

    assert _rules_shown(charter, kb, docs) == (
        "<!--\n# hidden\n-->\n\n### Real\n\n```\n# code\n```\n\n#not-a-heading\n"
    )


@pytest.mark.parametrize("indent", [1, 2, 3])
def test_indented_headings_in_rule_docs_are_nested_like_the_others(charter, kb, indent):
    pad = " " * indent
    docs = f"# One\n\n{pad}# Same level\n\n{pad}## Below\n"

    assert _rules_shown(charter, kb, docs) == f"### One\n\n{pad}### Same level\n\n{pad}#### Below\n"


def test_four_space_indent_and_fenced_lines_in_rule_docs_are_not_headings(charter, kb):
    docs = "# One\n\n    # code block\n\n  ```\n  # fenced\n  ```\n"

    assert _rules_shown(charter, kb, docs) == "### One\n\n    # code block\n\n  ```\n  # fenced\n  ```\n"


def test_leading_front_matter_block_in_rule_docs_is_dropped(charter, kb):
    docs = "---\nname: banned\n---\n\n# Banned\n\nText.\n"

    assert _rules_shown(charter, kb, docs) == "### Banned\n\nText.\n"


def test_front_matter_with_a_list_and_comment_is_dropped_with_the_blank_lines_after_it(charter, kb):
    docs = "---\n# note\nname: banned\ntags:\n  - a\n- b\n---\n\n\n# Banned\n"

    assert _rules_shown(charter, kb, docs) == "### Banned\n"


def test_front_matter_with_windows_line_endings_is_dropped(charter, kb):
    docs = "---\r\nname: banned\r\n---\r\n\r\n# Banned\r\n"

    assert _rules_shown(charter, kb, docs) == "### Banned\n"


@pytest.mark.parametrize(
    "docs",
    [
        "---\n\nIntro prose that matters.\n\n## Part\n\nmore text.\n\n---\n\nTail\n",
        "---\n\nIntro: not front matter.\n\nSee below.\n\n---\n\nTail\n",
    ],
)
def test_leading_dashes_around_prose_in_rule_docs_keep_all_content(charter, kb, docs):
    shown = _rules_shown(charter, kb, docs)

    assert "Intro" in shown
    assert "more text." in shown or "See below." in shown
    assert shown.endswith("Tail\n")


def test_an_empty_leading_dashes_block_is_dropped(charter, kb):
    assert _rules_shown(charter, kb, "---\n---\n# Banned\n") == "### Banned\n"


def test_list_item_heading_keeps_its_place_in_the_item(charter, kb):
    assert _rules_shown(charter, kb, "# One\n\n- item\n  # heading\n") == "### One\n\n- item\n  ### heading\n"


def test_unclosed_leading_dashes_in_rule_docs_are_left_as_written(charter, kb):
    assert _rules_shown(charter, kb, "---\n\n# Banned\n") == "---\n\n### Banned\n"


def test_nested_headings_stop_at_level_six(charter, kb):
    assert _rules_shown(charter, kb, "# One\n\n###### Six\n") == "### One\n\n###### Six\n"


def test_rulebook_holds_plugin_rules_and_goes_stale_when_they_change(charter, kb):
    base = kb(BANNED, ["banned-words"], top="docs: {}\n")
    assert charter("docs", cwd=base).exit_code == 0
    assert (base / "CHARTER.md").read_text(encoding="utf-8").endswith("\n" + RULES_SECTION)
    assert charter("docs", "--check", cwd=base).exit_code == 0

    rules = base / "tools" / "banned-words" / "RULES.md"
    rules.write_text(rules.read_text(encoding="utf-8").replace("instead", "plainly"), encoding="utf-8")
    result = charter("docs", "--check", cwd=base)

    assert result.exit_code == 1
    assert "docs/stale" in result.stdout


def test_rule_docs_render_the_same_whatever_their_line_endings_and_byte_order_mark(charter, kb):
    base = kb(BANNED, ["banned-words"], top="docs: {}\n")
    charter("docs", cwd=base)
    rules = base / "tools" / "banned-words" / "RULES.md"
    rules.write_bytes(b"\xef\xbb\xbf" + rules.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") + b"\r\n\r\n")

    assert charter("docs", "--check", cwd=base).exit_code == 0
