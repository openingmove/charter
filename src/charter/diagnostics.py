import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def capped_at(self, ceiling: "Severity") -> "Severity":
        return min(self, ceiling, key=_SEVERITY_RANK.index)


_SEVERITY_RANK = (Severity.INFO, Severity.WARNING, Severity.ERROR)

# Every contract spelling of a severity: `warning`/`off` in checks and profiles, `warn`/`allow` in
# `unknown_fields`. None means the diagnostic is not reported.
SEVERITY_NAMES: dict[str, Severity | None] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "warn": Severity.WARNING,
    "info": Severity.INFO,
    "off": None,
    "allow": None,
}


PLUGIN_FAILED = "plugin/failed"
PLUGIN_MODIFIED = "plugin/modified"
FILES_LEFTOVER = "files/leftover"
# The namespaces of the codes charter reports itself; no check may take one as its id.
CORE_NAMESPACES = frozenset({"contract", "docs", "files", "index", "init", "new", "plugin", "snapshot", "usage"})
# Codes meaning the run itself could not be completed, with the exit code each forces.
# No severity setting changes them, so they can never be silenced.
RUN_FAILURES = {PLUGIN_FAILED: 3, PLUGIN_MODIFIED: 3}
EXIT_CLEAN = 0
EXIT_ERRORS = 1


@dataclass(frozen=True)
class Diagnostic:
    """One finding. `path` is POSIX and relative to the directory holding charter.yaml."""

    path: str
    line: int | None
    severity: Severity
    code: str
    message: str
    hint: str | None = None

    def sort_key(self):
        return (self.path, self.line or 0, self.code, self.message)

    def to_dict(self):
        return {
            "path": self.path,
            "line": self.line,
            "severity": str(self.severity),
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


def exit_code(diagnostics: Iterable[Diagnostic]) -> int:
    """A run failure's exit code, else 1 when any diagnostic is an error, else 0."""
    diagnostics = list(diagnostics)
    forced = [RUN_FAILURES[d.code] for d in diagnostics if d.code in RUN_FAILURES]
    if forced:
        return max(forced)
    return EXIT_ERRORS if any(d.severity is Severity.ERROR for d in diagnostics) else EXIT_CLEAN


def code_list(names: Iterable[str]) -> str:
    """Names as a comma-separated list of code spans, the form messages and hints use."""
    return ", ".join(f"`{name}`" for name in names)


def code_span(text: str) -> str:
    """`text` as one Markdown code span, however many backticks it holds itself."""
    if "`" not in text:
        return f"`{text}`"
    longest = max(len(run) for run in re.findall(r"`+", text))
    fence = "`" * (longest + 1)
    return f"{fence} {text} {fence}"


def yaml_text(value: Any) -> str:
    """A YAML value as a contract author would write it (`true`, `null`, `2026-03-01`, `[a, b]`)."""
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(yaml_text(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}: {yaml_text(item)}" for key, item in value.items()) + "}"
    return str(value)


def suggestion(name: str, candidates: Iterable[str], otherwise: str) -> str:
    """A "did you mean" hint for the candidate closest to `name`, or `otherwise` when none is close."""
    candidates = list(candidates)
    close = difflib.get_close_matches(name, candidates, n=1) or _within_edit_distance(name, candidates)
    return f"Did you mean `{close[0]}`?" if close else otherwise


def _within_edit_distance(name: str, candidates: list[str]) -> list[str]:
    # difflib's similarity ratio misses short names (`ix` for `id`); a small edit distance does not.
    # Short names allow only one edit, so two-letter names are not "close" to every other two-letter name.
    limit = 1 if len(name) <= 4 else 2
    distances = [(_edit_distance(name, candidate), candidate) for candidate in candidates]
    best = min(distances, key=lambda pair: pair[0], default=None)
    return [best[1]] if best is not None and best[0] <= limit else []


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


class Refused(Exception):
    """A command did nothing, for the reasons in `diagnostics`. `usage` when the command itself was wrong."""

    def __init__(self, diagnostics: list[Diagnostic], *, usage: bool = False):
        super().__init__("; ".join(d.message for d in diagnostics))
        self.diagnostics = diagnostics
        self.usage = usage
