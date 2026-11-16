"""What checks that judge a change from its history share: the notes it touched, their text, and the infos for a
change they cannot judge."""

from collections.abc import Collection

from charter.contract import Contract
from charter.diagnostics import Diagnostic, Severity
from charter.history import EditDelta, NoHistory, Status
from charter.tree import decode


def touched_notes(contract: Contract, edits: EditDelta, statuses: Collection[Status]) -> list[str]:
    """The notes in scope that the change treated as one of `statuses`, sorted."""
    return [
        path
        for path in edits.touched()
        if path.endswith(".md") and contract.holds(path) and edits.status(path) in statuses
    ]


def text(content: bytes | None) -> str | None:
    """`content` as text; None when there is none or it is not UTF-8."""
    if content is None:
        return None
    try:
        return decode(content)
    except UnicodeDecodeError:
        return None


def skipped(contract: Contract, code: str, subject: str, history: NoHistory) -> Diagnostic:
    """The info for a run without history to judge; `subject` names what went unchecked, as a plural."""
    return Diagnostic(
        contract.file,
        None,
        Severity.INFO,
        code,
        f"{subject} were not checked: {history.reason}.",
        history.hint
        or f"{subject} compare files with the last git commit; run charter in a git repository to check them.",
    )


def deferred(contract: Contract, code: str, subject: str) -> Diagnostic:
    """The info for git's pre-commit stage, which leaves what a `Charter-Allow` trailer may overrule to the
    commit-msg stage; `subject` names it, as a plural."""
    return Diagnostic(
        contract.file,
        None,
        Severity.INFO,
        code,
        f"{subject} were not checked: they are checked with the commit message, at git's commit-msg stage, "
        "so that its `Charter-Allow` trailers count.",
        "Run `charter validate --staged --commit-msg FILE` from a commit-msg hook too.",
    )
