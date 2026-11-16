"""What a run's change did to the knowledge base's files: the earlier version that edits are judged against."""

from dataclasses import dataclass
from typing import Literal

from charter.tree import Tree

Status = Literal["added", "modified", "deleted"]
ADDED: Status = "added"
MODIFIED: Status = "modified"
DELETED: Status = "deleted"


@dataclass(frozen=True)
class EditDelta:
    # Only the files the change modified, retyped (a permission change included) or deleted, as they were.
    before: Tree
    # The knowledge base as the change leaves it.
    after: Tree
    # Files the change created.
    added: frozenset[str]

    def touched(self) -> list[str]:
        """Every file the change added, modified, retyped or deleted, sorted."""
        return sorted({*self.before.files("."), *self.added})

    def status(self, path: str) -> Status:
        """How the change treated `path`, one of the `touched` files."""
        if path in self.added:
            return ADDED
        return MODIFIED if self.after.is_file(path) else DELETED


@dataclass(frozen=True)
class NoHistory:
    """No earlier version of the knowledge base can be read, for `reason`."""

    reason: str
    # What to do about it, when the usual advice (run charter in a git repository) does not fit.
    hint: str | None = None


# None: the run compares nothing with an earlier version (`charter new`, which only adds a note).
History = EditDelta | NoHistory | None
