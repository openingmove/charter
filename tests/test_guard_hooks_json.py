"""The plugin's `hooks/hooks.json`: the contract guard's hooks start a process only for a typed charter skill and
for a tool call that names a `charter.yaml`, and run `charter-hook` without a shell."""

import json
import re
import tomllib
from pathlib import Path

import pytest

from charter import guard

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
HOOKS = json.loads((ROOT / "hooks" / "hooks.json").read_text("utf-8"))["hooks"]
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))


def handlers(event):
    return [(group.get("matcher"), handler) for group in HOOKS[event] for handler in group["hooks"]]


def test_the_plugin_has_only_the_guard_hooks():
    assert sorted(HOOKS) == ["PreToolUse", "UserPromptExpansion"]


@pytest.mark.parametrize("event", ["PreToolUse", "UserPromptExpansion"])
def test_every_hook_runs_the_charter_hook_command_as_an_argument_list(event):
    for _, handler in handlers(event):
        # Exec form: no shell, so the same on Windows, macOS and Linux. A command of its own, not a `charter`
        # subcommand: a command line tool too old to have it lacks the whole program, which Claude Code reports as a
        # hook error and goes on, where an unknown subcommand exits 2 and blocks every charter skill and contract
        # write.
        assert handler["type"] == "command"
        assert handler["command"] == "charter-hook"
        assert len(handler["args"]) == 1


def test_the_charter_hook_command_is_a_console_script_of_the_guard():
    assert PYPROJECT["project"]["scripts"]["charter-hook"] == "charter.guard:main"


def test_every_hook_event_is_one_the_command_answers(capsys):
    for event in HOOKS:
        for _, handler in handlers(event):
            assert handler["args"][0] in guard.EVENTS
            assert guard.main(["--help"]) == 0
    capsys.readouterr()


def test_the_skill_matcher_is_built_from_the_guarded_skills():
    [(matcher, _)] = handlers("UserPromptExpansion")

    assert matcher == "^(" + "|".join(guard.GUARDED_SKILLS) + ")$"


def test_the_skill_hook_starts_only_for_the_charter_skills_that_may_write_the_contract():
    [(matcher, handler)] = handlers("UserPromptExpansion")
    skills = [f"{PLUGIN['name']}:{Path(path).name}" for path in PLUGIN["skills"]]

    assert handler["args"] == ["skill-started"]
    assert "if" not in handler  # `if` is for tool events only; on this event it would stop the hook ever running
    assert sorted(name for name in skills if re.search(matcher, name)) == sorted(guard.GUARDED_SKILLS)
    for other in ("charter:survey", "evolve", "other:evolve", "charter:evolve-x", "xcharter:evolve", ""):
        assert not re.search(matcher, other)


def test_every_tool_hook_is_filtered_to_calls_that_name_charter_yaml():
    tool_hooks = handlers("PreToolUse")

    assert {matcher for matcher, _ in tool_hooks} == {*guard.FILE_TOOLS, "Bash"}
    for matcher, handler in tool_hooks:
        assert handler["args"] == ["pre-tool-use"]
        # One tool per group, and an `if` rule on every handler: no process starts for any other call.
        assert re.fullmatch(r"[A-Za-z]+", matcher)
        rule = re.fullmatch(r"(\w+)\((.*)\)", handler["if"])
        assert rule, handler["if"]
        assert "charter.yaml" in rule.group(2)
        if matcher == "Bash":
            assert handler["if"] == "Bash(*charter.yaml*)"
        else:
            assert rule.group(2) == "**/charter.yaml"


@pytest.mark.parametrize("tool", ["Edit", "Write"])
def test_each_file_tool_names_itself_in_its_rule(tool):
    # A live check found Claude Code matches a Write call against a `Write(...)` rule, not an `Edit(...)` rule.
    assert [handler["if"] for matcher, handler in handlers("PreToolUse") if matcher == tool] == [
        f"{tool}(**/charter.yaml)"
    ]
