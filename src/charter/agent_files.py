"""The agent files charter writes in a knowledge base: which, and how little of each.

One module decides, for `charter docs --link-agents` and `charter init --agents` alike. The knowledge base's
`AGENTS.md` gets one line importing the rulebook. Where a `CLAUDE.md` exists at or above the knowledge base,
Claude Code ignores `AGENTS.md`, so a `CLAUDE.md` beside it imports it too. A `CLAUDE.md` is never created
where none exists at or above, and nothing else in these files is ever touched.
"""

import posixpath
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from charter.checks.agents_include import decode_agent_text, points_at, unreadable_diagnostic
from charter.diagnostics import Refused
from charter.discovery import find_upward
from charter.files import append_lines, writing

CLAUDE_FILE = "CLAUDE.md"


class Outcome(Enum):
    CREATED = "created"
    APPENDED = "appended"
    ALREADY = "already"


@dataclass(frozen=True)
class AgentFile:
    path: str  # POSIX, relative to the knowledge-base folder
    target: str  # what the file now points at: the rulebook, or the agents file for a CLAUDE.md
    outcome: Outcome
    imports: bool  # whether the pointer is an `@` import rather than a Markdown link


def claude_path(agents_file: str) -> str:
    """Where the CLAUDE.md that imports `agents_file` lives: beside it, so it can import it by name."""
    return posixpath.join(posixpath.dirname(agents_file), CLAUDE_FILE)


def write_agent_files(folder: Path, rulebook: str, agents_file: str, failure_code: str) -> list[AgentFile]:
    """Makes the knowledge base's agent files point at the rulebook; returns every agent file it considered.

    `rulebook` and `agents_file` are POSIX paths relative to `folder`. A file that already points where it
    should is left byte-identical (outcome ALREADY). Raises Refused.
    """
    agents_line, agents_import = _rulebook_line(agents_file, rulebook)
    wanted = [(agents_file, rulebook, agents_line, agents_import)]
    if find_upward(folder / posixpath.dirname(agents_file), CLAUDE_FILE) is not None:
        wanted.append((claude_path(agents_file), agents_file, f"@{posixpath.basename(agents_file)}", True))
    # Check every path before the first write, so a refusal leaves nothing half-done.
    pending = [(path, target, line, imports, _outcome(folder, path, target)) for path, target, line, imports in wanted]
    changes = []
    for path, target, line, imports, outcome in pending:
        if outcome is not Outcome.ALREADY:
            file = folder / path
            with writing(path, failure_code):
                file.parent.mkdir(parents=True, exist_ok=True)
                append_lines(file, [line])
        changes.append(AgentFile(path, target, outcome, imports))
    return changes


def _outcome(folder: Path, path: str, target: str) -> Outcome:
    """What writing `path` would do; Raises Refused when something that is not a text file holds the path."""
    file = folder / path
    if not file.exists():
        return Outcome.CREATED
    try:
        if not file.is_file():
            raise OSError
        text = decode_agent_text(file.read_bytes())
    except OSError:
        raise Refused([
            unreadable_diagnostic(path, f"Agent files are text files; charter will not replace `{path}`.")
        ]) from None
    return Outcome.ALREADY if points_at(text, path, target) else Outcome.APPENDED


def _rulebook_line(agents_file: str, rulebook: str) -> tuple[str, bool]:
    """The one line that points the agents file at the rulebook, and whether it is an `@` import."""
    destination = _relative(rulebook, posixpath.dirname(agents_file))
    if re.search(r"\s", destination):
        # An `@` import ends at whitespace, so a path with a space is given as a link instead.
        return f"Read [{posixpath.basename(rulebook)}](<{destination}>) before creating or editing any note here.", False
    return f"read @{destination} before creating or editing any note here", True


def _relative(target: str, folder: str) -> str:
    # Both are normalised and relative to the same directory; os-independent, unlike os.path.relpath.
    start = [part for part in folder.split("/") if part]
    parts = target.split("/")
    common = 0
    while common < min(len(start), len(parts) - 1) and start[common] == parts[common]:
        common += 1
    return "/".join([".."] * (len(start) - common) + parts[common:])
