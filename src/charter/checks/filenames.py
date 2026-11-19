"""The `filenames` check: a note lives where its kind's or variant's path renders, and `matches_filename` fields agree."""

import re
from collections.abc import Iterator
from typing import Any

from charter.checks import CheckRequest
from charter.contract import Contract, Mismatch, Misplacement, Shape
from charter.diagnostics import Diagnostic, Severity, code_list, yaml_text
from charter.fields import Field
from charter.index import Note

WRONG_PATH = "filenames/path"
MISMATCH = "filenames/matches-filename"
UNSAFE = "filenames/unsafe-value"

# A padded whole number as a file name spells it, sign included; ASCII digits only.
_WHOLE_NUMBER = re.compile(r"-?[0-9]+")


class FilenamesCheck:
    id = "filenames"
    codes = frozenset({WRONG_PATH, MISMATCH, UNSAFE})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        contract = request.contract
        for note in request.target_notes():
            shape = contract.shape_of(note.frontmatter)
            if shape is None:
                continue
            misplacement = contract.misplacement(note.path, shape, note.frontmatter)
            if misplacement is not None:
                yield from _diagnostics(note, contract, shape, misplacement)


def _diagnostics(note: Note, contract: Contract, shape: Shape, misplacement: Misplacement) -> Iterator[Diagnostic]:
    if (unsafe := misplacement.unsafe) is not None:
        value = yaml_text(note.frontmatter.get(unsafe.field))
        slugged = any(p.field == unsafe.field and "slug" in p.filters for p in shape.path.placeholders)
        hint = (
            f"`{unsafe.field}` already goes through `|slug` in the `{shape.name}` path pattern; "
            f"give it a value with at least one letter or digit."
            if slugged
            else f"Change `{unsafe.field}`, or render it through `|slug` in the `{shape.name}` path pattern."
        )
        yield Diagnostic(
            note.path,
            note.field_lines.get(unsafe.field),
            Severity.ERROR,
            UNSAFE,
            f"`{unsafe.field}` is `{value}`, which cannot be part of a path on every platform: it {unsafe.reason}.",
            hint,
        )
    for mismatch in misplacement.mismatches:
        message, hint = _mismatch_text(mismatch, shape.fields[mismatch.field], note.frontmatter.get(mismatch.field))
        yield Diagnostic(note.path, note.field_lines.get(mismatch.field), Severity.ERROR, MISMATCH, message, hint)
    if misplacement.expected is not None:
        yield Diagnostic(
            note.path,
            note.field_lines.get(contract.discriminator),
            Severity.ERROR,
            WRONG_PATH,
            f"The path does not match the `{shape.name}` path pattern `{shape.path.text}`; "
            f"expected `{misplacement.expected}`.",
            f"Rename the file to `{misplacement.expected}`, "
            f"or correct the fields the pattern uses ({code_list(shape.path.fields)}).",
        )


def _mismatch_text(mismatch: Mismatch, field: Field, value: Any) -> tuple[str, str]:
    """The message and hint for a `matches_filename` field whose value differs from its part of the path."""
    if field.width is None:
        return (
            f"`{mismatch.field}` is `{mismatch.text}`, but the filename has `{mismatch.in_path}`.",
            f"Rename the file to `{mismatch.expected}`, or set `{mismatch.field}` to `{mismatch.in_path}`.",
        )
    # The filename's number, read as YAML would not read it: `0010` is ten, not octal.
    named = int(mismatch.in_path) if _WHOLE_NUMBER.fullmatch(mismatch.in_path) else None
    return (
        f"`{mismatch.field}` is `{yaml_text(value)}`, written `{mismatch.text}` at `width: {field.width}`, "
        f"but the filename has `{mismatch.in_path}`.",
        f"Rename the file to `{mismatch.expected}`"
        + (f", or set `{mismatch.field}` to `{named}`." if named is not None and named != value else "."),
    )
