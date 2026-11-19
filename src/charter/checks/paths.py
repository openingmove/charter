"""The `paths` check: a note's kind is one its path policy allows, and edits keep to edit policies."""

from collections.abc import Iterator

from charter.checks import CheckRequest
from charter.checks.changes import deferred, skipped
from charter.contract import Contract
from charter.diagnostics import Diagnostic, Severity, code_list
from charter.history import ADDED, MODIFIED, EditDelta, NoHistory
from charter.pathpolicy import CREATE_ONLY, READ_ONLY, Setting

EDIT_SKIPPED = "paths/edit-skipped"
EDIT_DEFERRED = "paths/edit-deferred"
EDIT_POLICY_CODES = frozenset({f"paths/{READ_ONLY}", f"paths/{CREATE_ONLY}"})


class PathsCheck:
    id = "paths"
    codes = frozenset({"paths/kind-not-allowed", *EDIT_POLICY_CODES, EDIT_SKIPPED, EDIT_DEFERRED})
    overridable = EDIT_POLICY_CODES

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        yield from _kinds_not_allowed(request)

    def judges_edits(self, contract: Contract, targets: frozenset[str] | None = None) -> bool:
        if targets is None:
            return contract.paths.declares("edit")
        # The same lookup `edit_violations` makes for each touched file, so git is not asked about files it skips.
        return any(_edit_policy(contract, path) is not None for path in targets)

    def edit_diagnostics(self, request: CheckRequest) -> Iterator[Diagnostic]:
        contract, history = request.contract, request.history
        if isinstance(history, NoHistory):
            if contract.paths.declares("edit"):
                yield skipped(contract, EDIT_SKIPPED, "Edit policies", history)
        elif history is not None:
            yield from edit_violations(contract, history, request.commit)

    def deferred(self, contract: Contract) -> Diagnostic:
        return deferred(contract, EDIT_DEFERRED, "Edit policies")


def edit_violations(contract: Contract, edits: EditDelta, commit: str | None = None) -> Iterator[Diagnostic]:
    """How a change breaks the edit policies. `commit` names the commit that made the change, if any."""
    for path in edits.touched():
        if (violation := edit_violation_for(contract, path, edits.status(path), commit)) is not None:
            yield violation


def edit_violation_for(contract: Contract, path: str, status: str, commit: str | None = None) -> Diagnostic | None:
    """How a file `status` (added, modified or deleted) at `path` breaks the edit policy that covers it, if it
    does: adding, changing or deleting a file under `read-only`, or changing or deleting one under `create-only`.
    `charter new` asks it about a note it would add."""
    policy = _edit_policy(contract, path)
    if policy is None or (policy.value == CREATE_ONLY and status == ADDED):
        return None
    return _edit_diagnostic(path, policy, status, commit)


def _edit_policy(contract: Contract, path: str) -> Setting | None:
    """The edit policy that covers `path`, if the contract holds the path and a policy sets `edit` there."""
    return contract.path_policy(path).get("edit") if contract.holds(path) else None


def _edit_diagnostic(path: str, policy: Setting, status: str, commit: str | None) -> Diagnostic:
    code = f"paths/{policy.value}"
    trailer = f"`Charter-Allow: {code} {path} — <reason>`"
    verb = "changed" if status == MODIFIED else status
    if commit is not None:
        message = f"but commit {commit} {verb} it."
        # Each commit is judged on its own, so only rewriting the commit clears it.
        hint = (
            f"Rewrite commit {commit} (`git rebase -i`) so that it "
            f"{'does not add the file' if status == ADDED else 'leaves the file as it was'}; a later commit "
            f"cannot undo it. If a human decided on this edit, reword its message to add the trailer {trailer}."
        )
    else:
        message = f"but it was {verb}."
        if status == ADDED:
            hint = "Remove the file; nothing may be added under a read-only path."
        elif policy.value == CREATE_ONLY:
            hint = "Restore the file as it was; put new material in a new file instead."
        else:
            hint = "Restore the file as it was."
        hint += f" If a human decided on this edit, they can allow it with the commit-message trailer {trailer}."
    message = f"This file is {policy.value} under path policy `{policy.glob}`, {message}"
    return Diagnostic(path, None, Severity.ERROR, code, message, hint)


def _kinds_not_allowed(request: CheckRequest) -> Iterator[Diagnostic]:
    contract = request.contract
    for note in request.target_notes():
        # A missing or undeclared kind is the schema check's finding; reporting it twice is noise.
        if (declared := contract.kind_of(note.frontmatter)) is None:
            continue
        kind = declared.name
        allowed = contract.path_policy(note.path).get("kinds")
        if allowed is None or kind in allowed.value:
            continue
        yield Diagnostic(
            note.path,
            note.field_lines.get(contract.discriminator),
            Severity.ERROR,
            "paths/kind-not-allowed",
            f"Kind `{kind}` is not allowed by path policy `{allowed.glob}`, "
            f"which allows {code_list(allowed.value)}.",
            f"Move the note to a path that allows `{kind}`, "
            f"or add `{kind}` to the `kinds` of `{allowed.glob}` in charter.yaml.",
        )
