"""The `residue` check: no note keeps template guidance or placeholders."""

from collections.abc import Iterator

from charter.checks import CheckRequest
from charter.diagnostics import Diagnostic, Severity
from charter.template import guide_text

LEFTOVER_GUIDE = "residue/guide"
LEFTOVER_PLACEHOLDER = "residue/placeholder"


class ResidueCheck:
    id = "residue"
    codes = frozenset({LEFTOVER_GUIDE, LEFTOVER_PLACEHOLDER})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        for note in request.target_notes():
            for comment in note.comments:
                if (guide := guide_text(comment)) is not None:
                    yield Diagnostic(
                        note.path,
                        comment.line,
                        Severity.ERROR,
                        LEFTOVER_GUIDE,
                        f"Guide comment left in the note: `{guide}`.",
                        "Follow the guidance, then delete the comment.",
                    )
            for placeholder in note.placeholders:
                yield Diagnostic(
                    note.path,
                    placeholder.line,
                    Severity.ERROR,
                    LEFTOVER_PLACEHOLDER,
                    f"Placeholder `{placeholder}` left in the note.",
                    "Replace it with the note's own text.",
                )
