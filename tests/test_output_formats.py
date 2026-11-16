import io
import sys

import pytest
from conftest import FIXTURES

CONTRACT = (
    "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n"
    "      title: {type: string, required: true}\n      n: {type: int}\n"
)


@pytest.fixture
def two_problem_kb(make_kb):
    return make_kb({
        "charter.yaml": CONTRACT,
        "notes/a.md": "---\nkind: entry\ntitle: A\nn: many\n---\n",
        "notes/b.md": "---\nkind: entyr\n---\n",
    })


def test_text_groups_diagnostics_by_file_with_a_summary(charter, two_problem_kb):
    result = charter("validate", cwd=two_problem_kb)

    assert result.exit_code == 1
    assert result.stdout == (
        "notes/a.md\n"
        "     4  error    schema/type  Field `n` must be an integer, got text `many`.\n"
        "\n"
        "notes/b.md\n"
        "     2  error    schema/unknown-kind  Kind `entyr` is not declared in the contract.\n"
        "        hint: Did you mean `entry`?\n"
        "\n"
        "2 errors, 0 warnings, 0 infos (profile: commit)\n"
    )


def test_text_reports_a_clean_run(charter):
    result = charter("validate", cwd=FIXTURES / "clean")

    assert result.stdout == "No problems found (profile: commit).\n"


def test_agent_prints_one_compact_line_per_diagnostic(charter, two_problem_kb):
    result = charter("validate", "--format", "agent", cwd=two_problem_kb)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "notes/a.md:4: error schema/type: Field `n` must be an integer, got text `many`.",
        "notes/b.md:2: error schema/unknown-kind: Kind `entyr` is not declared in the contract."
        " (hint: Did you mean `entry`?)",
        "(profile: commit)",
    ]


def test_agent_prints_nothing_on_a_clean_run(charter):
    result = charter("validate", "--format", "agent", cwd=FIXTURES / "clean")

    assert (result.exit_code, result.stdout) == (0, "")


def test_contract_diagnostics_use_the_requested_format(charter, tmp_path):
    result = charter("validate", "--format", "agent", cwd=tmp_path)

    assert result.exit_code == 2
    assert result.stdout.startswith("charter.yaml: error contract/not-found: ")


class _Terminal(io.StringIO):
    def isatty(self):
        return True


def test_text_is_coloured_on_a_terminal(charter, two_problem_kb, monkeypatch):
    terminal = _Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)

    charter("validate", cwd=two_problem_kb)

    assert "\033[31merror  \033[0m" in terminal.getvalue()


def test_no_color_disables_colour_on_a_terminal(charter, two_problem_kb, monkeypatch):
    terminal = _Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.setenv("NO_COLOR", "1")

    charter("validate", cwd=two_problem_kb)

    assert "\033[" not in terminal.getvalue()


def test_text_is_not_coloured_when_piped(charter, two_problem_kb):
    assert "\033[" not in charter("validate", cwd=two_problem_kb).stdout


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["frobnicate"],
        ["validate", "--format", "yaml"],
        ["validate", "--bogus"],
    ],
)
def test_usage_errors_exit_two(charter, tmp_path, argv):
    result = charter(*argv, cwd=tmp_path)

    assert result.exit_code == 2
    assert "usage: charter" in result.stderr


def test_version_is_printed(charter, tmp_path):
    result = charter("--version", cwd=tmp_path)

    assert result.exit_code == 0
    assert result.stdout.startswith("charter ")
