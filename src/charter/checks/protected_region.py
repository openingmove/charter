"""The optional `protected-region` check: notes of the configured kinds only grow, by text appended below a marker
heading; everything above it, and everything already below it, stays as committed."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from charter.body import Heading, heading, parse_body
from charter.checks import CheckRequest
from charter.checks.changes import deferred, skipped, text, touched_notes
from charter.contract import Contract, DeclaredShape, Kind
from charter.diagnostics import Diagnostic, Severity, code_list, suggestion
from charter.fields import Invalid
from charter.history import ADDED, DELETED, MODIFIED, EditDelta, NoHistory
from charter.index import body_start, frontmatter_of

ID = "protected-region"
CHANGED = f"{ID}/changed"
SKIPPED = f"{ID}/skipped"
DEFERRED = f"{ID}/deferred"
_PARAMS = ("kinds", "marker")
_DELETES = "deletes it, and no note it adds continues its text"
_SUBJECT = f"Protected regions (`{ID}`)"


class ProtectedRegionCheck:
    id = ID
    codes = frozenset({CHANGED, SKIPPED, DEFERRED})
    overridable = frozenset({CHANGED})
    params_schema = {
        "type": "object",
        "properties": {
            "kinds": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
            "marker": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }

    def contract_problems(
        self, params: Mapping[str, Any], shapes: Sequence[DeclaredShape], invalid: Invalid
    ) -> Iterator[Diagnostic]:
        # Required only once enabled, so a disabled entry needs no parameters.
        if missing := [name for name in _PARAMS if name not in params]:
            yield invalid(
                ["checks", ID],
                f"`{ID}` needs {code_list(missing)} to know which notes to protect.",
                f'Write it as `{ID}: {{enabled: true, with: {{kinds: [KIND], marker: "## Amendments"}}}}`.',
            )
            return
        declared = sorted({shape.kind for shape in shapes})
        for position, kind in enumerate(params["kinds"]):
            if kind not in declared:
                yield invalid(
                    ["checks", ID, "with", "kinds", position],
                    f"unknown kind `{kind}`.",
                    suggestion(kind, declared, f"Declared kinds: {code_list(declared)}."),
                )
        if heading(params["marker"], 0) is None:
            yield invalid(
                ["checks", ID, "with", "marker"],
                f"`{params['marker']}` is not a Markdown ATX heading (`#` to `######`), but `{ID}` protects the text above a heading.",
                'Write the marker as a heading line, such as `"## Amendments (append-only)"`.',
            )

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        return iter(())

    def judges_edits(self, contract: Contract, targets: frozenset[str] | None = None) -> bool:
        # Whatever the targets, a note it protects may be moved to or from them, so it always needs the history.
        return True

    def edit_diagnostics(self, request: CheckRequest) -> Iterator[Diagnostic]:
        history = request.history
        if isinstance(history, NoHistory):
            yield skipped(request.contract, SKIPPED, _SUBJECT, history)
        elif history is not None:
            yield from _violations(request.contract, history, request.commit)

    def deferred(self, contract: Contract) -> Diagnostic:
        return deferred(contract, DEFERRED, _SUBJECT)


@dataclass(frozen=True)
class _Breach:
    # None when the text in question is gone.
    line: int | None
    # Completes "but the change …".
    what: str
    # Without the marker before the change, all of the note's text is protected.
    marked: bool = True


def _violations(contract: Contract, edits: EditDelta, commit: str | None) -> Iterator[Diagnostic]:
    params = contract.check_config(ID).params
    kinds, marker = set(params["kinds"]), heading(params["marker"], 0)
    assert marker is not None  # contract_problems refuses a marker that is not a heading
    paths = touched_notes(contract, edits, [MODIFIED, DELETED])
    added = touched_notes(contract, edits, [ADDED])
    before, after = edits.before.read(paths), edits.after.read([*paths, *added])
    # A note's path follows its fields, so a permitted frontmatter change can move a protected note.
    moved_to: set[str] = set()
    for path in paths:
        content = before.get(path)
        if content is None or content == after.get(path):
            continue
        # The kind the note had is what protected it; changing the kind does not lift the protection.
        kind = contract.kind_of(frontmatter_of(_lenient(content)))
        if kind is None or kind.name not in kinds:
            continue
        old, new = text(content), text(after.get(path))
        if edits.status(path) == DELETED:
            # Deletion and move come first. Committed text that is not UTF-8 is compared byte for byte, enough to
            # tell whether an added note continues it.
            old_bytes_only = old is None
            if old is None:
                old = _lossless(content)
            move = next(
                (
                    candidate
                    for candidate in added
                    if candidate not in moved_to
                    and _continues(contract, kind, marker, old, after.get(candidate), lossless=old_bytes_only)
                ),
                None,
            )
            if move is not None:
                moved_to.add(move)
                continue
            breach = _Breach(None, _DELETES)
        elif old is None:
            breach = _Breach(None, "changes it, and its committed text is not UTF-8, so what changed is unknown")
        elif new is None:
            breach = _Breach(None, "leaves text that is not UTF-8")
        elif (breach := _breach(old, new, marker)) is None:
            continue
        yield _diagnostic(path, kind.name, marker, breach, commit)


def _continues(
    contract: Contract, kind: Kind, marker: Heading, old: str, content: bytes | None, *, lossless: bool
) -> bool:
    """Whether the added note `content` is of `kind` and continues `old`. Text that is not UTF-8 counts as a
    candidate only `lossless`ly, when the deleted note's own text is not UTF-8 either. Its kind is read from a
    lenient decoding, as for the deleted note, because the YAML reader rejects the lone surrogates of the
    lossless one; a byte that is not UTF-8 inside the frontmatter then cannot make the check raise."""
    if content is None:
        return False
    moved = text(content)
    kind_source = moved
    if moved is None:
        if not lossless:
            return False
        moved, kind_source = _lossless(content), _lenient(content)
    return contract.kind_of(frontmatter_of(kind_source)) == kind and _breach(old, moved, marker) is None


def _breach(old: str, new: str, marker: Heading) -> _Breach | None:
    """How `new` is something other than `old` with lines appended under `marker`, if it is. Only bodies count: the
    frontmatter is not protected. Trailing whitespace, trailing blank lines and line endings are not text."""
    old_lines, new_lines = old.split("\n"), new.split("\n")
    old_start, new_start = body_start(old_lines), body_start(new_lines)
    kept = _significant(old_lines[old_start:])
    given = _significant(new_lines[new_start:])
    old_marker, new_marker = _marker_at(old_lines[old_start:], marker), _marker_at(new_lines[new_start:], marker)
    differs = next((i for i, line in enumerate(kept) if i >= len(given) or given[i] != line), None)
    if differs is None:
        if old_marker is not None:
            return None
        appended = next((i for i in range(len(kept), len(given)) if given[i]), None)
        if appended is None or appended == new_marker:
            return None
        return _Breach(
            new_start + appended + 1, f"adds text without it; text may only be added under `{marker}`", marked=False
        )
    line = new_start + differs + 1 if differs < len(given) else None
    if old_marker is None:
        return _Breach(line, "changes its text", marked=False)
    if differs < old_marker or (differs == old_marker and new_marker is not None and new_marker > differs):
        return _Breach(line, "changes its text above the marker")
    if differs == old_marker:
        return _Breach(line, "changes or removes the marker heading")
    return _Breach(line, "changes its text below the marker, where text may only be added at the end")


def _significant(lines: list[str]) -> list[str]:
    stripped = [line.rstrip() for line in lines]
    while stripped and not stripped[-1]:
        stripped.pop()
    return stripped


def _marker_at(lines: list[str], marker: Heading) -> int | None:
    found = (h.line for h in parse_body(lines, 0).headings if (h.level, h.text) == (marker.level, marker.text))
    return next(found, None)


def _diagnostic(path: str, kind: str, marker: Heading, breach: _Breach, commit: str | None) -> Diagnostic:
    trailer = f"`Charter-Allow: {CHANGED} {path} — <reason>`"
    if breach.marked:
        protected = f"may change only by adding text at the end, below `{marker}`"
    else:
        protected = f"has no `{marker}` heading, so all of its text is protected"
    actor = "the change" if commit is None else f"commit {commit}"
    message = f"This `{kind}` note {protected} (`checks.{ID}`), but {actor} {breach.what}."
    if commit is not None:
        # Each commit is judged on its own, so only rewriting the commit clears it.
        hint = (
            f"Rewrite commit {commit} (`git rebase -i`) so that it only adds text at the end of the note, below "
            f"`{marker}`; a later commit cannot undo it. If a human decided on this edit, reword its message to add "
            f"the trailer {trailer}."
        )
    else:
        restore = "Restore the note" if breach.line is None else "Restore the note's text"
        hint = (
            f"{restore} as it was, and add amendments at the end, below `{marker}`. If a human decided on this "
            f"edit, they can allow it with the commit-message trailer {trailer}."
        )
    return Diagnostic(path, breach.line, Severity.ERROR, CHANGED, message, hint)


def _read(content: bytes, errors: str) -> str:
    # The same universal newlines as `tree.decode`, for bytes that may not be UTF-8.
    return content.decode("utf-8-sig", errors=errors).replace("\r\n", "\n").replace("\r", "\n")


def _lenient(content: bytes) -> str:
    # Enough to read the kind from a note whose bytes are not all UTF-8; the YAML reader accepts it.
    return _read(content, "replace")


def _lossless(content: bytes) -> str:
    # Bytes that are not UTF-8 survive as lone surrogates, so two notes compare equal exactly where their bytes do.
    return _read(content, "surrogateescape")
