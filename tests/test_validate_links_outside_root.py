"""Links to files beside or below charter.yaml but outside `root` resolve when the file exists."""

import pytest
from conftest import commit_files, run_git, write_files
from links_support import KINDS, PAGE, kb as _kb, validate as _validate

NOTE = (
    PAGE
    + "[src](../src/app.py) [spec](../specs/design.md) [spec again](../specs/design)"
    + " [[../src/app.py]] [[../specs/design.md#Part]]\n"
)
OUTSIDE = {"src/app.py": "print()\n", "specs/design.md": "# Design\n"}


def _unresolved(result):
    return [d for d in result.json()["diagnostics"] if d["code"] == "links/unresolved"]


def _lines(result):
    return [d["line"] for d in _unresolved(result)]


def _outside(make_kb, *, note=NOTE, extra=None, top=""):
    """notes/Home.md with `note`, and files beside it under charter.yaml's directory but outside root."""
    kb = _kb(make_kb, {"Home.md": note}, top=top)
    make_kb({**OUTSIDE, **(extra or {})})
    return kb


def test_links_to_existing_files_outside_root_resolve(charter, make_kb):
    kb = _outside(make_kb)

    assert _unresolved(_validate(charter, kb)) == []


def test_only_existence_is_checked(charter, make_kb):
    kb = _outside(make_kb, note=PAGE + "[a](../specs/design.md#No-Such-Heading)\n")

    assert _unresolved(_validate(charter, kb)) == []


def test_missing_outside_and_above_contract_links_are_unresolved(charter, make_kb):
    kb = _outside(
        make_kb,
        note=PAGE + "[a](../src/gone.py)\n[b](../../etc/passwd)\n[c](../../x.md)\n[[../../x]]\n[d](../src)\n",
    )

    assert _lines(_validate(charter, kb)) == [4, 5, 6, 7, 8]


def test_a_file_above_the_contract_directory_is_not_reached(charter, tmp_path):
    (tmp_path / "secret.md").write_text("x")
    kb = tmp_path / "kb"
    write_files(kb, {"charter.yaml": f"charter: 1\nroot: notes\n{KINDS}", "notes/Home.md": PAGE + "[a](../../secret.md)\n"})

    assert _lines(_validate(charter, kb)) == [4]


def test_bare_names_never_match_files_outside_root(charter, make_kb):
    kb = _outside(
        make_kb,
        note=PAGE + "[[app.py]]\n[[design]]\n[[AGENTS.md]]\n[[Makefile]]\n[[src/app.py]]\n",
        extra={"AGENTS.md": "x", "Makefile": "x"},
    )

    assert _lines(_validate(charter, kb)) == [4, 5, 6, 7, 8]


def test_a_bare_name_is_matched_under_root_only(charter, make_kb):
    kb = _outside(make_kb, note=PAGE + "[[AGENTS.md]]\n", extra={"AGENTS.md": "outside"})
    write_files(kb, {"notes/AGENTS.md": "inside"})

    assert _unresolved(_validate(charter, kb)) == []


def test_explicit_path_wikilink_reaches_outside_root(charter, make_kb):
    kb = _outside(make_kb, note=PAGE + "[[../AGENTS.md]]\n", extra={"AGENTS.md": "x"})

    assert _unresolved(_validate(charter, kb)) == []


def test_agent_file_and_rulebook_outside_root_still_resolve(charter, make_kb):
    kb = _outside(
        make_kb,
        note=PAGE + "[a](../AGENTS.md) [b](../CHARTER.md)\n",
        extra={"AGENTS.md": "x", "CHARTER.md": "x"},
        top="agents: {file: AGENTS.md}\ndocs: {output: CHARTER.md}\n",
    )

    assert _unresolved(_validate(charter, kb)) == []


@pytest.mark.parametrize(
    ("target", "resolves"),
    [("..%2Fsrc%2Fapp.py", True), ("..%5Csrc%5Capp.py", False), ("<..\\src\\app.py>", False), ("..\\src\\app.py", False)],
)
def test_separator_forms_are_normalised_as_inside_root(charter, make_kb, target, resolves):
    # A percent-encoded `/` is a separator; a backslash is not, and never reaches the file system.
    kb = _outside(make_kb, note=PAGE + f"[a]({target})\n")

    assert (_lines(_validate(charter, kb)) == []) is resolves


def test_a_backslash_path_never_reaches_the_file_system_outside_root(charter, make_kb):
    kb = _outside(make_kb, note=PAGE + "[a](<sub\\..\\..\\src\\app.py>)\n")

    assert _lines(_validate(charter, kb)) == [4]


def test_root_at_the_contract_directory_is_unchanged(charter, make_kb):
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  page: {}\n",
        "a.md": PAGE + "[x](b.md) [y](../z.md)\n",
        "b.md": PAGE,
    })

    assert _lines(_validate(charter, kb)) == [4]


def test_file_mode_resolves_outside_root(charter, make_kb):
    kb = _outside(make_kb)

    assert _unresolved(_validate(charter, kb, "--file", "notes/Home.md")) == []


def _repo(make_kb, note):
    kb = _kb(make_kb, {"Home.md": note})
    run_git(kb, "init", "-q", "--initial-branch=main")
    return kb


def test_staged_resolves_outside_root_from_the_index_not_the_disk(charter, make_kb):
    kb = _repo(make_kb, NOTE)
    write_files(kb, {"src/app.py": "x"})
    run_git(kb, "add", "-A")
    write_files(kb, {"specs/design.md": "# D\n"})  # on disk, not staged

    first = _unresolved(_validate(charter, kb, "--staged"))
    run_git(kb, "add", "specs")
    second = _unresolved(_validate(charter, kb, "--staged"))

    assert {d["line"] for d in first} == {4} and all("design" in d["message"] for d in first)
    assert second == []


def test_range_judges_no_links_so_outside_root_files_are_never_read(charter, make_kb):
    # `--range` checks edit policies and history rules only; a link to a file that exists only on disk is not its business.
    kb = _repo(make_kb, PAGE)
    base = commit_files(kb, {})
    commit_files(kb, {"notes/Home.md": NOTE})

    result = _validate(charter, kb, f"--range={base}..HEAD")

    assert result.exit_code == 0 and _unresolved(result) == []


def test_outside_targets_match_case_exactly_on_every_file_system(charter, make_kb):
    kb = _outside(
        make_kb,
        note=PAGE + "[a](../SRC/app.py)\n[b](../src/APP.py)\n[c](../src/app.py)\n[[../Specs/design.md]]\n[[../specs/design.md]]\n",
    )

    assert _lines(_validate(charter, kb)) == [4, 5, 7]
