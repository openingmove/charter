"""Rendering diagnostics as text, json or agent output."""

import json
import os
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from itertools import groupby
from typing import TextIO

from charter.diagnostics import Diagnostic, Severity

JSON_FORMAT_ID = "charter-diagnostics/1"

_COLOURS = {
    Severity.ERROR: "\033[31m",
    Severity.WARNING: "\033[33m",
    Severity.INFO: "\033[36m",
}
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


# The lone surrogates `surrogateescape` leaves for the bytes of a path that is not valid UTF-8. `chr()` builds
# them, and the backslash in `printable`, so no lone surrogate or backslash literal sits in the source for an
# editor or tool to rewrite.
_UNDECODED_BYTE = re.compile("[" + chr(0xDC80) + "-" + chr(0xDCFF) + "]")


def printable(text: str) -> str:
    """`text` with each byte that was not valid UTF-8 spelled as a backslash, `x` and two hex digits.

    Valid text is returned as it is. A literal backslash is not doubled, so the escape is for reading, not
    for round-tripping.
    """
    return _UNDECODED_BYTE.sub(lambda found: f"{chr(92)}x{ord(found.group()) - 0xDC00:02x}", text)


def _printable(d: Diagnostic) -> Diagnostic:
    return replace(d, path=printable(d.path), message=printable(d.message), hint=d.hint and printable(d.hint))


def render(diagnostics: list[Diagnostic], output_format: str, stream: TextIO, profile: str | None = None) -> None:
    """`profile` names the active severity profile; None when none applied (an invalid contract)."""
    # Ordering here, not in each producer, is what keeps output deterministic across platforms.
    # Sorting after the escape is deliberate: a path that is not valid UTF-8 sorts by its escaped form, as shown.
    _RENDERERS[output_format](sorted(map(_printable, diagnostics), key=Diagnostic.sort_key), stream, profile)


def _summary(diagnostics: list[Diagnostic]) -> dict[str, int]:
    counts = Counter(d.severity for d in diagnostics)
    return {
        "errors": counts[Severity.ERROR],
        "warnings": counts[Severity.WARNING],
        "infos": counts[Severity.INFO],
    }


def _render_json(diagnostics: list[Diagnostic], stream: TextIO, profile: str | None) -> None:
    document = {
        "format": JSON_FORMAT_ID,
        **({} if profile is None else {"profile": profile}),
        "diagnostics": [d.to_dict() for d in diagnostics],
        "summary": _summary(diagnostics),
    }
    stream.write(json.dumps(document, indent=2) + "\n")


def _render_agent(diagnostics: list[Diagnostic], stream: TextIO, profile: str | None) -> None:
    for d in diagnostics:
        location = d.path if d.line is None else f"{d.path}:{d.line}"
        hint = f" (hint: {d.hint})" if d.hint else ""
        stream.write(f"{location}: {d.severity} {d.code}: {d.message}{hint}\n")
    # A clean run stays silent, so a hook can treat any output as something to fix.
    if diagnostics and profile is not None:
        stream.write(_profile_note(profile) + "\n")


def _render_text(diagnostics: list[Diagnostic], stream: TextIO, profile: str | None) -> None:
    colour = stream.isatty() and "NO_COLOR" not in os.environ

    def paint(text: str, style: str) -> str:
        return f"{style}{text}{_RESET}" if colour else text

    suffix = "" if profile is None else " " + _profile_note(profile)
    if not diagnostics:
        stream.write(f"No problems found{suffix}.\n")
        return

    for path, group in groupby(diagnostics, key=lambda d: d.path):
        stream.write(paint(path, _BOLD) + "\n")
        for d in group:
            line = "" if d.line is None else str(d.line)
            severity = paint(f"{d.severity:<7}", _COLOURS[d.severity])
            stream.write(f"  {line:>4}  {severity}  {d.code}  {d.message}\n")
            if d.hint:
                stream.write(" " * 8 + paint(f"hint: {d.hint}", _DIM) + "\n")
        stream.write("\n")

    summary = _summary(diagnostics)
    stream.write(
        f"{_plural(summary['errors'], 'error')}, "
        f"{_plural(summary['warnings'], 'warning')}, "
        f"{_plural(summary['infos'], 'info')}{suffix}\n"
    )


def _profile_note(profile: str) -> str:
    return f"(profile: {profile})"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


_RENDERERS: dict[str, Callable[[list[Diagnostic], TextIO, str | None], None]] = {
    "text": _render_text,
    "json": _render_json,
    "agent": _render_agent,
}
FORMATS = tuple(_RENDERERS)


def render_draft(
    path: str, shape: str, outline: tuple[str, ...], output_format: str, stream: TextIO, *, written: bool
) -> None:
    """What `charter new` created (or, when not `written`, would create), and the sections left to fill in."""
    if output_format == "agent":
        stream.write(f"{'created' if written else 'would create'} {path} ({shape})\n")
        stream.writelines(f"section {heading}\n" for heading in outline)
        return
    stream.write(f"{'Created' if written else 'Would create'} `{path}` ({shape}).\n")
    if outline:
        stream.write("\nSections to fill in:\n")
        stream.writelines(f"  {heading}\n" for heading in outline)
