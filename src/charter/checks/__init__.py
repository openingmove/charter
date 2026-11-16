"""The interface every check implements, built-in or external.

A check receives the index and the targets selected for this run and returns
diagnostics at their base severity. The core applies profiles and formats the
output, so a check never decides exit codes or presentation.
"""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from charter.contract import Contract
from charter.diagnostics import Diagnostic
from charter.history import History
from charter.index import Note
from charter.links import Resolver


@dataclass(frozen=True)
class CheckRequest:
    contract: Contract
    notes: tuple[Note, ...]
    targets: frozenset[str]
    resolver: Resolver
    # Kinds this run touches: findings about a kind's notes taken together are reported for these.
    kinds: frozenset[str]
    # The run covers the whole knowledge base, not just selected files.
    whole: bool
    # The run checks one edit as it happens (`validate --file`, `new`), so it must stay fast:
    # plugins with `hook: false` stay out of it.
    per_edit: bool
    # What the run's change did to the files that existed before it.
    history: History
    # The day the change is judged as of: the local date, or for a commit already made, the day it was authored.
    today: datetime.date
    # The commit that made the change, by git's abbreviated id; None for a change not yet committed. A run that
    # judges a commit carries no index (`notes` is empty): only checks that judge `history` alone run there.
    commit: str | None = None

    def target_notes(self) -> Iterable[Note]:
        return (note for note in self.notes if note.path in self.targets)


class Check(Protocol):
    # Names the check in `checks:` and `profiles:`.
    id: str
    # Every diagnostic code the check can report; profiles may name any of them.
    codes: frozenset[str]

    def run(self, request: CheckRequest) -> Iterable[Diagnostic]: ...


class OverridableCheck(Protocol):
    """A check whose findings a `Charter-Allow` trailer may allow. Its edit judgements are left out of `run`: they
    wait for the commit message, at git's commit-msg stage."""

    id: str
    # The codes a trailer may allow.
    overridable: frozenset[str]

    def judges_edits(self, contract: Contract, targets: frozenset[str] | None = None) -> bool:
        """Whether the contract gives this enabled check edits to judge: in just `targets` (diagnostic-form
        paths) when given, else anywhere."""
        ...

    def edit_diagnostics(self, request: CheckRequest) -> Iterable[Diagnostic]:
        """How the request's history keeps to the check, or why that cannot be judged."""
        ...

    def deferred(self, contract: Contract) -> Diagnostic:
        """The info for git's pre-commit stage, which leaves the edits to the commit-msg stage."""
        ...
