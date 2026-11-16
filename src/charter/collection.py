"""The notes of each kind taken together, and the values they hold."""

from collections.abc import Hashable, Iterable
from dataclasses import dataclass

from charter.contract import Contract, Shape
from charter.index import Note


@dataclass(frozen=True)
class Member:
    note: Note
    shape: Shape

    def value(self, field: str) -> Hashable | None:
        return self.shape.value_of(self.note.frontmatter, field)


def members_by_kind(contract: Contract, notes: Iterable[Note]) -> dict[str, tuple[Member, ...]]:
    """Every declared kind's notes in the index, variants included, in index order."""
    grouped: dict[str, list[Member]] = {kind: [] for kind in contract.kinds}
    for note in notes:
        if (shape := contract.shape_of(note.frontmatter)) is not None:
            grouped[shape.kind.name].append(Member(note, shape))
    return {kind: tuple(members) for kind, members in grouped.items()}


def holders(members: Iterable[Member], field: str) -> dict[Hashable, list[Member]]:
    """The members holding each valid value of `field`."""
    found: dict[Hashable, list[Member]] = {}
    for member in members:
        if (value := member.value(field)) is not None:
            found.setdefault(value, []).append(member)
    return found
