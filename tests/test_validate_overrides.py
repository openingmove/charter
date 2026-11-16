import os

import pytest
from conftest import COMMIT_MSG, commit_files, run_git, validate_commit_msg, write_files

CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
  "Research/**": {edit: create-only}
kinds:
  entry:
    fields:
      kind: {type: string, required: true}
      title: {type: string}
"""
NOTE = "---\nkind: entry\n---\n"
EDITED = NOTE + "Edited.\n"
FILES = {
    "charter.yaml": CONTRACT,
    "notes/Archive/old.md": NOTE,
    "notes/Archive/A — B.md": NOTE,
    "notes/Research/topic.md": NOTE,
    "notes/free.md": NOTE,
}
SUBJECT = "Fix a typo\n\nThe archive had a typo.\n\n"
# Allows the usual violation of these tests: changing the read-only `old.md`.
ALLOW_OLD = "Charter-Allow: paths/read-only notes/Archive/old.md — typo\n"


def _diagnostics(result):
    return [(d["path"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _committed(make_kb, files=FILES):
    kb = make_kb(files)
    run_git(kb, "init", "-q", "--initial-branch=main")
    commit_files(kb, {})
    return kb


def _stage(kb, files):
    write_files(kb, files)
    run_git(kb, "add", "-A")


def test_a_matching_trailer_downgrades_the_violation_to_a_warning_naming_the_trailer(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    trailer = "Charter-Allow: paths/read-only notes/Archive/old.md — fix a typo in the archive"

    result = validate_commit_msg(charter, kb, SUBJECT + trailer + "\n")

    assert result.exit_code == 0
    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]
    assert f"`{trailer}`" in result.json()["diagnostics"][0]["message"]


def test_the_overridden_violation_still_prints_in_text_output(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    write_files(kb, {COMMIT_MSG: SUBJECT + ALLOW_OLD})

    result = charter("validate", "--staged", "--commit-msg", COMMIT_MSG, cwd=kb)

    assert result.exit_code == 0
    assert "warning  paths/read-only" in result.stdout
    assert "Charter-Allow: paths/read-only notes/Archive/old.md — typo" in result.stdout


def test_a_double_hyphen_separates_the_reason_as_an_em_dash_does(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Research/topic.md": EDITED})

    result = validate_commit_msg(
        charter, kb, SUBJECT + "Charter-Allow: paths/create-only notes/Research/topic.md -- typo\n"
    )

    assert _diagnostics(result) == [("notes/Research/topic.md", "warning", "paths/create-only")]


def test_a_path_may_hold_spaces_and_dashes(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/A — B.md": EDITED})

    result = validate_commit_msg(
        charter, kb, SUBJECT + "Charter-Allow: paths/read-only notes/Archive/A — B.md — typo\n"
    )

    assert _diagnostics(result) == [("notes/Archive/A — B.md", "warning", "paths/read-only")]


def test_each_trailer_allows_only_its_own_code_and_path(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED, "notes/Research/topic.md": EDITED})
    message = SUBJECT + (
        "Charter-Allow: paths/read-only notes/Archive/old.md — typo\n"
        "Charter-Allow: paths/read-only notes/Research/topic.md — wrong code\n"
    )

    result = validate_commit_msg(charter, kb, message)

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "warning", "paths/read-only"),
        ("notes/Research/topic.md", "error", "paths/create-only"),
    ]


def test_a_trailer_that_matches_nothing_warns(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    trailer = "Charter-Allow: paths/read-only notes/Archive/olde.md — typo"

    result = validate_commit_msg(charter, kb, SUBJECT + trailer + "\n")

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
    ]
    unused = result.json()["diagnostics"][0]
    assert f"`{trailer}`" in unused["message"]
    assert unused["hint"] == "Did you mean `notes/Archive/old.md`?"


def test_an_unused_trailer_alone_does_not_block(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + ALLOW_OLD)

    assert result.exit_code == 0
    assert _diagnostics(result) == [("charter.yaml", "warning", "override/unused")]


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ("paths/read-only notes/Archive/old.md", "has no separator"),
        ("paths/read-only notes/Archive/old.md - typo", "has no separator"),
        ("paths/read-only notes/Archive/old.md —", "gives no reason"),
        ("paths/read-only notes/Archive/old.md --", "gives no reason"),
        ("paths/read-only — typo", "names no path before its separator"),
        ("paths/read-only", "names no path"),
    ],
)
def test_a_trailer_without_a_path_separator_or_reason_is_rejected(charter, make_kb, value, problem):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + f"Charter-Allow: {value}\n")

    assert result.exit_code == 1
    assert _diagnostics(result) == [
        ("charter.yaml", "error", "override/invalid"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
    ]
    invalid = result.json()["diagnostics"][0]
    assert problem in invalid["message"]
    assert "<diagnostic-code> <path> — <reason>" in invalid["hint"]


@pytest.mark.parametrize(
    "value",
    [
        "paths/read-only  notes/Archive/old.md  –  typo",
        "paths/read-only notes/Archive/old.md\t--\ttypo",
    ],
)
def test_whitespace_around_the_separator_and_an_en_dash_are_accepted(charter, make_kb, value):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + f"Charter-Allow: {value}\n")

    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


def test_the_trailer_path_must_be_the_whole_path(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(
        charter, kb, SUBJECT + "Charter-Allow: paths/read-only notes/Archive/old.md x — typo\n"
    )

    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "error", "paths/read-only"),
    ]


def test_a_trailer_for_a_path_holding_a_separator_does_not_allow_its_prefix(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "notes/Archive/A": "x\n"})
    _stage(kb, {"notes/Archive/A": "y\n", "notes/Archive/A — B.md": EDITED})

    result = validate_commit_msg(
        charter, kb, SUBJECT + "Charter-Allow: paths/read-only notes/Archive/A — B.md — typo\n"
    )

    assert _diagnostics(result) == [
        ("notes/Archive/A", "error", "paths/read-only"),
        ("notes/Archive/A — B.md", "warning", "paths/read-only"),
    ]


def test_paths_compare_in_one_unicode_normal_form(charter, make_kb):
    composed = "notes/Archive/Caf\u00e9.md"
    kb = _committed(make_kb, {**FILES, composed: NOTE})
    _stage(kb, {composed: EDITED})

    decomposed = "notes/Archive/Cafe\u0301.md"
    result = validate_commit_msg(charter, kb, SUBJECT + f"Charter-Allow: paths/read-only {decomposed} — typo\n")

    assert [(severity, code) for _, severity, code in _diagnostics(result)] == [("warning", "paths/read-only")]


def test_a_repeated_trailer_is_unused(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    message = SUBJECT + (
        "Charter-Allow: paths/read-only notes/Archive/old.md — typo\n"
        "Charter-Allow: paths/read-only notes/Archive/old.md — typo again\n"
    )

    result = validate_commit_msg(charter, kb, message)

    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "warning", "paths/read-only"),
    ]
    unused = result.json()["diagnostics"][0]
    assert "typo again" in unused["message"] and "repeats" in unused["message"]


def test_a_repository_with_other_trailer_separators_still_reads_the_trailer(charter, make_kb):
    kb = _committed(make_kb)
    run_git(kb, "config", "trailer.separators", "#")
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + ALLOW_OLD)

    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


def test_only_edit_policies_can_be_overridden(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + "Charter-Allow: schema/required notes/free.md — not needed\n")

    assert _diagnostics(result) == [("charter.yaml", "error", "override/invalid")]
    invalid = result.json()["diagnostics"][0]
    assert "`schema/required`" in invalid["message"]
    assert "`paths/create-only`, `paths/read-only`" in invalid["message"]


def test_a_mistyped_code_suggests_the_edit_policy_code(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + "Charter-Allow: paths/readonly notes/free.md — typo\n")

    assert result.json()["diagnostics"][0]["hint"] == "Did you mean `paths/read-only`?"


def test_the_trailer_key_is_case_insensitive_as_in_git(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + ALLOW_OLD.replace("Charter-Allow", "charter-allow"))

    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


@pytest.mark.parametrize(
    "message",
    [
        # Not in the trailer block: git reads trailers only from the message's last paragraph.
        "Fix\n\nCharter-Allow: paths/read-only notes/Archive/old.md — typo\n\nMore text.\n",
        # A comment line, which git strips from the message.
        "Fix\n\nSigned-off-by: A <a@example.com>\n# Charter-Allow: paths/read-only notes/Archive/old.md — typo\n",
        # Below the scissors line of `git commit --verbose`, where the diff is.
        (
            "Fix\n\n# ------------------------ >8 ------------------------\n"
            "# Do not modify or remove the line above.\n"
            "diff --git a/x b/x\n+Charter-Allow: paths/read-only notes/Archive/old.md — typo\n"
        ),
        # The subject line is never a trailer.
        "Charter-Allow: paths/read-only notes/Archive/old.md — typo\n",
    ],
)
def test_only_the_message_trailers_count(charter, make_kb, message):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, message)

    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_a_crlf_message_is_read_like_an_lf_one(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    message = SUBJECT + ALLOW_OLD

    result = validate_commit_msg(charter, kb, message.replace("\n", "\r\n").encode("utf-8"))

    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]


def test_a_continued_trailer_is_unfolded(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(
        charter, kb, SUBJECT + "Charter-Allow: paths/read-only notes/Archive/old.md — fix a typo\n  found in review\n"
    )

    assert _diagnostics(result) == [("notes/Archive/old.md", "warning", "paths/read-only")]
    assert "— fix a typo found in review`" in result.json()["diagnostics"][0]["message"]


def test_strict_leaves_overridden_violations_and_unused_trailers_as_warnings(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})
    message = SUBJECT + (
        "Charter-Allow: paths/read-only notes/Archive/old.md — typo\n"
        "Charter-Allow: paths/read-only notes/Archive/other.md — typo\n"
    )

    result = validate_commit_msg(charter, kb, message, "--strict")

    assert result.exit_code == 0
    assert _diagnostics(result) == [
        ("charter.yaml", "warning", "override/unused"),
        ("notes/Archive/old.md", "warning", "paths/read-only"),
    ]


def test_strict_still_fails_other_warnings(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": "---\nkind: entry\nextra: 1\n---\n"})

    result = charter("validate", "--staged", "--strict", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [
        ("charter.yaml", "info", "paths/edit-deferred"),
        ("notes/free.md", "error", "schema/unknown-field"),
    ]


def test_a_profile_may_set_the_severity_of_unused_trailers(charter, make_kb):
    kb = _committed(make_kb, {**FILES, "charter.yaml": CONTRACT + "profiles:\n  ci: {override/unused: error}\n"})
    _stage(kb, {"notes/free.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT + ALLOW_OLD)

    assert result.exit_code == 1
    assert _diagnostics(result) == [("charter.yaml", "error", "override/unused")]


# --- stages: edit policies at commit-msg, everything else at pre-commit ---


def test_the_commit_msg_stage_checks_only_edit_policies(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED, "notes/free.md": "---\nkind: entry\ntitle: [x]\n---\n"})

    result = validate_commit_msg(charter, kb, SUBJECT)

    assert _diagnostics(result) == [("notes/Archive/old.md", "error", "paths/read-only")]


def test_the_pre_commit_stage_leaves_edit_policies_to_the_commit_msg_stage(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED, "notes/free.md": "---\nkind: entry\ntitle: [x]\n---\n"})

    result = charter("validate", "--staged", "--profile", "ci", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [
        ("charter.yaml", "info", "paths/edit-deferred"),
        ("notes/free.md", "error", "schema/type"),
    ]
    assert "--commit-msg" in result.json()["diagnostics"][0]["hint"]


def test_the_pre_commit_stage_stays_quiet_when_the_commit_msg_hook_is_installed(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED, "notes/free.md": "---\nkind: entry\ntitle: [x]\n---\n"})

    result = charter("validate", "--staged", "--commit-msg-installed", "--profile", "ci", "--format", "json", cwd=kb)

    assert _diagnostics(result) == [("notes/free.md", "error", "schema/type")]


def test_commit_msg_installed_still_leaves_edit_policies_to_the_commit_msg_stage(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = charter("validate", "--staged", "--commit-msg-installed", "--format", "json", cwd=kb)

    assert result.exit_code == 0
    assert _diagnostics(result) == []


def test_commit_msg_installed_without_staged_is_a_usage_error(charter, make_kb):
    kb = _committed(make_kb)

    result = charter("validate", "--commit-msg-installed", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/commit-msg-installed-without-staged"]


def test_the_pre_commit_stage_says_nothing_of_edit_policies_a_contract_lacks(charter, make_kb):
    contract = CONTRACT.replace("{edit: read-only}", "{kinds: [entry]}").replace(
        "{edit: create-only}", "{kinds: [entry]}"
    )
    kb = _committed(make_kb, {**FILES, "charter.yaml": contract})
    _stage(kb, {"notes/Archive/old.md": EDITED})

    assert _diagnostics(charter("validate", "--staged", "--format", "json", cwd=kb)) == []


def test_before_the_first_commit_the_commit_msg_stage_says_edit_policies_were_skipped(charter, make_kb):
    kb = make_kb(FILES)
    run_git(kb, "init", "-q", "--initial-branch=main")
    run_git(kb, "add", "-A")

    result = validate_commit_msg(charter, kb, SUBJECT)

    assert _diagnostics(result) == [("charter.yaml", "info", "paths/edit-skipped")]


def test_commit_msg_selects_the_commit_profile(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/free.md": EDITED})
    write_files(kb, {COMMIT_MSG: SUBJECT})

    result = charter("validate", "--staged", "--commit-msg", COMMIT_MSG, "--format", "json", cwd=kb)

    assert result.json()["profile"] == "commit"


def test_commit_msg_needs_staged(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {COMMIT_MSG: SUBJECT})

    result = charter("validate", "--commit-msg", COMMIT_MSG, "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/commit-msg-without-staged"]


def test_a_missing_commit_message_file_is_a_usage_error(charter, make_kb):
    kb = _committed(make_kb)

    result = charter("validate", "--staged", "--commit-msg", "missing.txt", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/file-not-found"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions that bind the user")
def test_an_unreadable_commit_message_file_is_a_usage_error(charter, make_kb):
    kb = _committed(make_kb)
    write_files(kb, {COMMIT_MSG: SUBJECT})
    (kb / COMMIT_MSG).chmod(0)
    try:
        result = charter("validate", "--staged", "--commit-msg", COMMIT_MSG, "--format", "json", cwd=kb)
    finally:
        (kb / COMMIT_MSG).chmod(0o644)

    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/file-unreadable"]


def test_edit_policy_diagnostics_hint_at_the_trailer(charter, make_kb):
    kb = _committed(make_kb)
    _stage(kb, {"notes/Archive/old.md": EDITED})

    result = validate_commit_msg(charter, kb, SUBJECT)

    hint = result.json()["diagnostics"][0]["hint"]
    assert "`Charter-Allow: paths/read-only notes/Archive/old.md — <reason>`" in hint
