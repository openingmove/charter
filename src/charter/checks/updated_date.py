"""The optional `updated-date` check: a note whose content a change alters records the day in its `updated` field."""

import datetime
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from charter.checks import CheckRequest
from charter.checks.changes import skipped, text, touched_notes
from charter.contract import Contract, DeclaredShape
from charter.diagnostics import Diagnostic, Severity, code_list
from charter.fields import Invalid, declared_type
from charter.fieldtypes import FIELD_TYPES
from charter.history import MODIFIED, EditDelta, NoHistory
from charter.index import frontmatter_and_lines, frontmatter_of

ID = "updated-date"
STALE = f"{ID}/stale"
SKIPPED = f"{ID}/skipped"
DEFAULT_FIELD = "updated"


class UpdatedDateCheck:
    id = ID
    codes = frozenset({STALE, SKIPPED})
    params_schema = {
        "type": "object",
        "properties": {"field": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }

    def contract_problems(
        self, params: Mapping[str, Any], shapes: Sequence[DeclaredShape], invalid: Invalid
    ) -> Iterator[Diagnostic]:
        name = params.get("field", DEFAULT_FIELD)
        location = ["checks", ID, *(["with", "field"] if "field" in params else [])]
        holding = [shape for shape in shapes if name in shape.fields]
        if not holding:
            yield invalid(
                location,
                f"no kind declares the field `{name}`, whose date `{ID}` keeps fresh.",
                f"Declare `{name}: {{type: date}}` on the kinds whose notes record when they last changed, "
                "or name the field they use with `with: {field: NAME}`.",
            )
        elif mistyped := sorted({shape.kind for shape in holding if declared_type(shape.fields[name]) != "date"}):
            yield invalid(
                location,
                f"`{name}` is not a date on {code_list(mistyped)}, but `{ID}` compares dates.",
                f"Declare `{name}` with `type: date`.",
            )

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        history = request.history
        if isinstance(history, NoHistory):
            yield skipped(request.contract, SKIPPED, f"Updated dates (`{ID}`)", history)
        elif history is not None:
            yield from _stale(request.contract, history, request.today, request.commit)


def _stale(contract: Contract, edits: EditDelta, today: datetime.date, commit: str | None) -> Iterator[Diagnostic]:
    name = contract.check_config(ID).params.get("field", DEFAULT_FIELD)
    # A note the change adds has nothing to be fresher than; `charter new` dates it.
    paths = touched_notes(contract, edits, [MODIFIED])
    before, after = edits.before.read(paths), edits.after.read(paths)
    for path in paths:
        old, new = text(before.get(path)), text(after.get(path))
        # Equal text: only the permissions or the line endings changed.
        if old is None or new is None or old == new:
            continue
        frontmatter, lines = frontmatter_and_lines(new)
        shape = contract.shape_of(frontmatter)
        if shape is None or name not in shape.fields:
            continue
        given = frontmatter.get(name)
        value, previous = _date(given), _date(frontmatter_of(old).get(name))
        if value is None and given not in (None, ""):
            # A value that is not a date is the schema check's finding.
            continue
        if value == today or (value is not None and previous is not None and value > previous):
            continue
        yield _stale_diagnostic(path, lines.get(name), name, value, previous, today, commit)


def _stale_diagnostic(
    path: str,
    line: int | None,
    name: str,
    value: datetime.date | None,
    previous: datetime.date | None,
    today: datetime.date,
    commit: str | None,
) -> Diagnostic:
    changed = "This note changed" if commit is None else f"This note changed in commit {commit}"
    day = f"today ({today})" if commit is None else f"the day that commit was authored ({today})"
    if value is None:
        message = f"{changed}, but has no `{name}` date."
    elif previous is None:
        message = f"{changed}, but `{name}` is {value}, not {day}."
    else:
        message = f"{changed}, but `{name}` is {value}: neither {day} nor later than {previous}, its date before."
    if commit is None:
        hint = f"Set `{name}: {today}`."
    else:
        # Each commit is judged on its own, so only rewriting the commit clears it.
        hint = (
            f"Rewrite commit {commit} (`git rebase -i`, marking it `edit`) so that it sets `{name}: {today}`; "
            "rewriting keeps the day it was authored, and a later commit cannot clear it."
        )
    return Diagnostic(path, line, Severity.ERROR, STALE, message, hint)


def _date(value: Any) -> datetime.date | None:
    return value if FIELD_TYPES["date"].accepts(value) else None
