"""The contract guard: the `charter-hook` command behind the Claude Code plugin's hooks.

`skill-started` runs when the human types `/charter:establish`, `/charter:evolve` or `/charter:migrate`
(`GUARDED_SKILLS`), and records a marker for that session. `pre-tool-use` runs before a tool call that may write a
`charter.yaml`, and denies it when that contract opts in (`agents: {guard: true}`) and the session has no marker.
Agents cannot start those skills, so only a command the human typed produces a marker; a "yes" in the conversation
does not.

The plugin's `hooks/hooks.json` filters the calls, so these commands start only for a typed charter skill and for
a tool call that names a `charter.yaml`. Both exit 0 for every event they can answer, also an unreadable one, and
for a file system error: none of those blocks a call. Any other crash exits 1, which Claude Code reports as a hook
error and goes on.

It is a program of its own, not a `charter` subcommand, because Claude Code treats exit 2 as a block. An older
`charter` would answer an unknown subcommand with argparse's exit 2 and so refuse every charter skill and contract
write; a missing `charter-hook` is only a hook error. For the same reason this command never exits 2 itself, also
for an event it does not know.
"""

import datetime
import hashlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO

from charter import shellwrites
from charter.contract import CONTRACT_FILENAME

# The skills whose typed command lets the session write the contract, as Claude Code names a plugin skill.
GUARDED_SKILLS = ("charter:establish", "charter:evolve", "charter:migrate")
# Overrides the per-user folder the markers are kept in: for tests.
STATE_VARIABLE = "CHARTER_STATE_DIR"
# The file tools whose `file_path` is the one file they write.
FILE_TOOLS = ("Edit", "Write", "MultiEdit")
# The hook events `charter-hook` answers, as `hooks/hooks.json` names them.
EVENTS = ("skill-started", "pre-tool-use")


def typed_skills() -> str:
    """The guarded skills as the human types them, for prose: "`/charter:establish`, ... or `/charter:migrate`"."""
    commands = [f"`/{skill}`" for skill in GUARDED_SKILLS]
    return ", ".join(commands[:-1]) + " or " + commands[-1]


def _usage() -> str:
    return (
        "usage: charter-hook EVENT\n\n"
        "The contract guard's Claude Code hooks: read a hook event on stdin and answer it.\n\n"
        f"  skill-started  record that the human typed {typed_skills()} in this session\n"
        "  pre-tool-use   deny a write to a guarded charter.yaml in a session that started none of them\n"
    )


def main(argv: list[str] | None = None) -> int:
    """The `charter-hook` command. Never exits 2, which Claude Code would treat as a block."""
    args = sys.argv[1:] if argv is None else argv
    if args in (["-h"], ["--help"]):
        print(_usage(), end="")
        return 0
    if len(args) != 1 or args[0] not in EVENTS:
        known = ", ".join(EVENTS)
        print(f"charter-hook: no hook event {' '.join(args)!r}; this version answers {known}", file=sys.stderr)
        return 0
    try:
        event = read_event(sys.stdin)
        if event is None:
            return 0
        if args[0] == "skill-started":
            skill_started(event)
        elif decision := pre_tool_use(event):
            print(json.dumps(decision))
    except OSError as error:
        print(f"charter-hook {args[0]}: {error}", file=sys.stderr)
    except Exception as error:
        # Any other crash is a hook error: exit 1, never 2, which would block the call.
        print(f"charter-hook {args[0]}: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


def state_dir() -> Path:
    """The per-user folder charter keeps session markers in; never inside a repository."""
    if override := os.environ.get(STATE_VARIABLE):
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "charter"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "charter"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "charter"


def _marker(session_id: str) -> Path:
    # Hashed, so any session id is a safe file name on every platform.
    name = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return state_dir() / "sessions" / f"{name}.json"


def skill_started(event: dict[str, Any]) -> None:
    """Records that the human typed a guarded skill's command in the event's session."""
    session_id, command = event.get("session_id"), event.get("command_name")
    if not isinstance(session_id, str) or not session_id or command not in GUARDED_SKILLS:
        return
    marker = _marker(session_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    marker.write_text(json.dumps({"skill": command, "started": started}) + "\n", encoding="utf-8")


def pre_tool_use(event: dict[str, Any]) -> dict[str, Any] | None:
    """The deny decision for a tool call that writes a guarded contract without a marker; None to stay silent.

    Silence is no decision: the call goes on through Claude Code's own permission flow. The guard never answers
    "allow", which would skip the permission prompt the human would otherwise see.
    """
    session_id = event.get("session_id")
    tool_input = event.get("tool_input")
    cwd = event.get("cwd")
    if not isinstance(tool_input, dict) or not isinstance(cwd, str):
        return None
    guarded = [path for path in _written(event.get("tool_name"), tool_input, Path(cwd)) if _guard_on(path)]
    if not guarded:
        return None
    if isinstance(session_id, str) and session_id and _marker(session_id).is_file():
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _reason(guarded[0]),
        }
    }


def _reason(contract: Path) -> str:
    return (
        f"`{contract}` is a charter contract with its guard on: a contract changes only through Evolve, never by a "
        "direct edit, and a yes in this conversation does not change that. An agent cannot start Evolve. Stop and "
        "ask the human to type `/charter:evolve` if they want this change; once they have, this session may write "
        "the contract."
    )


def _written(tool: object, tool_input: dict[str, Any], cwd: Path) -> Iterator[Path]:
    """The `charter.yaml` files a tool call may write."""
    if tool in FILE_TOOLS:
        path = tool_input.get("file_path")
        if isinstance(path, str) and _is_contract_name(path):
            yield shellwrites.resolve(cwd, path)
    elif tool == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str):
            yield from shellwrites.written(command, cwd, _is_contract_name)


def _is_contract_name(path: str) -> bool:
    return path.replace("\\", "/").rsplit("/", 1)[-1] == CONTRACT_FILENAME


def _guard_on(path: Path) -> bool:
    """Whether the contract at `path` opts in with `agents: {guard: true}`.

    A file that is missing, unreadable or not a contract mapping has no opt-in the guard can see, so it is off.
    """
    import yaml

    try:
        data = yaml.safe_load(path.read_bytes())
    except (OSError, yaml.YAMLError, ValueError):
        return False
    agents = data.get("agents") if isinstance(data, dict) else None
    return isinstance(agents, dict) and agents.get("guard") is True


def read_event(stream: TextIO) -> dict[str, Any] | None:
    """The hook event on `stream` as JSON; None when it is not a JSON object."""
    raw = stream.buffer.read() if hasattr(stream, "buffer") else stream.read()
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None
