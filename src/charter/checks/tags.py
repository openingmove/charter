"""The `tags` check: every tag matches a glob in `tags.allow`, when the contract sets one."""

from collections.abc import Iterator

from charter.checks import CheckRequest
from charter.diagnostics import Diagnostic, Severity, code_list

NOT_ALLOWED = "tags/not-allowed"


class TagsCheck:
    id = "tags"
    codes = frozenset({NOT_ALLOWED})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        settings = request.contract.tags
        if settings.allow is None:
            return
        permitted = (
            f"`tags.allow` permits {code_list(settings.allow)}"
            if settings.allow
            else "`tags.allow` is empty, so no tags are allowed"
        )
        for note in request.target_notes():
            for tag in note.tags:
                if settings.allows(tag.name):
                    continue
                yield Diagnostic(
                    note.path,
                    tag.line,
                    Severity.ERROR,
                    NOT_ALLOWED,
                    f"Tag `{tag.name}` is not allowed; {permitted}.",
                    f"Use an allowed tag, or add a glob matching `{tag.name}` to `tags.allow` in charter.yaml.",
                )
