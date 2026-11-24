"""The `ids` check: `unique` values are unique across a kind, and a kind's `collection` is complete."""

import math
from collections.abc import Iterable, Iterator

from charter.checks import CheckRequest
from charter.collection import Member, holders, members_by_kind
from charter.contract import Contract, Kind
from charter.diagnostics import Diagnostic, Severity, code_list, yaml_text
from charter.fields import Field
from charter.index import Note

DUPLICATE = "ids/duplicate"
COUNT = "ids/count"
GAP = "ids/gap"
# The codes about a kind's notes taken together, reported on the contract at the kind's `collection`.
COLLECTION_CODES = frozenset({COUNT, GAP})
# A run this long is counted, not listed end to end, so a typo like `50000000` stays readable.
_LONG_RUN = 1000


class IdsCheck:
    id = "ids"
    codes = frozenset({DUPLICATE, COUNT, GAP})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        contract = request.contract
        # Judged against every note of each kind, whichever notes this run targets.
        grouped = members_by_kind(contract, request.notes)
        for kind in contract.kinds.values():
            declared = contract.kind_fields(kind)
            for field in _unique_fields(kind, declared):
                yield from _duplicates(kind, field, grouped[kind.name], request.targets)
            if kind.collection is not None and kind.name in request.kinds:
                yield from _incomplete(kind, declared, grouped[kind.name], contract.file)


def collection_findings(contract: Contract, kind: Kind, notes: Iterable[Note]) -> list[Diagnostic]:
    """The `ids/count` and `ids/gap` findings for `kind`'s `collection`, judged against `notes`."""
    if kind.collection is None:
        return []
    members = members_by_kind(contract, notes)[kind.name]
    return list(_incomplete(kind, contract.kind_fields(kind), members, contract.file))


def _unique_fields(kind: Kind, declared: dict[str, Field]) -> list[str]:
    declarations = [
        *declared.values(),
        *(field for variant in kind.variants.values() for field in variant.fields.values()),
    ]
    return list(dict.fromkeys(field.name for field in declarations if field.unique))


def _duplicates(
    kind: Kind, field: str, collection: tuple[Member, ...], targets: frozenset[str]
) -> Iterator[Diagnostic]:
    for value, holding in holders(collection, field).items():
        if len(holding) < 2:
            continue
        for member in holding:
            if member.note.path not in targets or not member.shape.fields[field].unique:
                continue
            others = code_list(other.note.path for other in holding if other is not member)
            yield Diagnostic(
                member.note.path,
                member.note.field_lines.get(field),
                Severity.ERROR,
                DUPLICATE,
                f"`{field}` is `{yaml_text(value)}`, as in {others}; "
                f"`{field}` must be unique across `{kind.name}` notes.",
                f"Give each `{kind.name}` note its own `{field}`.",
            )


def _incomplete(
    kind: Kind, declared: dict[str, Field], collection: tuple[Member, ...], contract_file: str
) -> Iterator[Diagnostic]:
    rules = kind.collection
    if rules.count is not None and len(collection) != rules.count:
        yield Diagnostic(
            contract_file,
            rules.count_line,
            Severity.ERROR,
            COUNT,
            f"Kind `{kind.name}` has {len(collection)} notes, but its `collection` declares `count: {rules.count}`.",
            f"Add or remove `{kind.name}` notes, or change the `count`.",
        )
    if rules.contiguous is None:
        return
    field = rules.contiguous
    values = sorted(holders(collection, field))
    if not values:
        return
    bounds = declared[field].range
    start = math.ceil(bounds[0]) if bounds is not None else values[0]
    # Values past the range maximum are `schema/range` findings, not the end of the sequence.
    end = min(values[-1], math.floor(bounds[1])) if bounds is not None else values[-1]
    missing = _missing_spans(values, start, end)
    if missing:
        yield Diagnostic(
            contract_file,
            rules.contiguous_line,
            Severity.ERROR,
            GAP,
            f"`{kind.name}` notes skip `{field}` {_spans(missing)}; "
            f"the collection's `{field}` values must have no gaps.",
            f"Add `{kind.name}` notes with those values, or renumber so `{field}` runs without gaps.",
        )


def _missing_spans(present: list[int], start: int, end: int) -> list[tuple[int, int]]:
    """The inclusive runs of integers in `start..end` that `present` (sorted) lacks, without counting through them."""
    spans: list[tuple[int, int]] = []
    next_wanted = start
    for value in present:
        if value > end:
            break
        if value > next_wanted:
            spans.append((next_wanted, value - 1))
        next_wanted = max(next_wanted, value + 1)
    if next_wanted <= end:
        spans.append((next_wanted, end))
    return spans


def _spans(spans: list[tuple[int, int]]) -> str:
    """Runs shortened: `1–2, 5, 7–9`; a long run states its size: `4–49999999 (49999996 values)`."""
    parts = []
    for low, high in spans:
        if low == high:
            parts.append(str(low))
        elif high - low + 1 > _LONG_RUN:
            parts.append(f"{low}–{high} ({high - low + 1} values)")
        else:
            parts.append(f"{low}–{high}")
    return ", ".join(parts)
