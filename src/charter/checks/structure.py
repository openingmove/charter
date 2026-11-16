"""The `structure` check: a note keeps its template's headings, in order, as often as each may appear."""

from collections.abc import Iterator

from charter.body import Heading
from charter.checks import CheckRequest
from charter.diagnostics import Diagnostic, Severity, code_span
from charter.index import Note
from charter.template import Section, Template

MISSING = "structure/missing-heading"
ORDER = "structure/heading-order"
REPEATED = "structure/repeated-heading"


class StructureCheck:
    id = "structure"
    codes = frozenset({MISSING, ORDER, REPEATED})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        for note in request.target_notes():
            shape = request.contract.shape_of(note.frontmatter)
            # Legacy notes are exempt from the template's headings only; every other check still judges them.
            if shape is not None and shape.template is not None and not shape.is_legacy(note.frontmatter):
                yield from _findings(note, shape.template)


def _show(heading: Heading) -> str:
    return code_span(str(heading))


def _findings(note: Note, template: Template) -> Iterator[Diagnostic]:
    outline = template.outline
    # Each section's first heading, wherever it is.
    seen: dict[int, Heading] = {}
    # The headings each section matched in place.
    placed: dict[int, list[Heading]] = {}
    # The next section a heading may match in place; headings the template does not name are extra, and allowed.
    cursor = 0
    for heading in note.headings:
        last = cursor - 1
        if last >= 0 and outline[last].repeat and outline[last].matches(heading):
            placed[last].append(heading)
            continue
        here = _in_place(outline, cursor, heading)
        if here is not None:
            placed[here] = [heading]
            seen.setdefault(here, heading)
            cursor = here + 1
            continue
        # Out of place, only a heading the template spells out is the template's; one a placeholder matches is extra.
        earlier = next((i for i in range(cursor) if outline[i].literal and outline[i].matches(heading)), None)
        if earlier is None:
            continue
        if earlier in seen and not outline[earlier].repeat:
            yield Diagnostic(
                note.path,
                heading.line,
                Severity.ERROR,
                REPEATED,
                f"{_show(heading)} appears more than once; the template `{template.path}` allows it once.",
                f"Merge the {_show(heading)} sections into the one at line {seen[earlier].line}.",
            )
            continue
        seen.setdefault(earlier, heading)
        follows = placed[last][0]
        yield Diagnostic(
            note.path,
            heading.line,
            Severity.ERROR,
            ORDER,
            f"{_show(heading)} is out of order: the template puts it before {_show(follows)}.",
            f"Move the {_show(heading)} section above {_show(follows)} (line {follows.line}).",
        )

    for position, section in enumerate(outline):
        if section.required and position not in seen:
            yield Diagnostic(
                note.path,
                None,
                Severity.ERROR,
                MISSING,
                f"Heading {_show(section.heading)} from the template `{template.path}` is missing.",
                _placement(section.heading, position, placed),
            )


def _in_place(outline: tuple[Section, ...], cursor: int, heading: Heading) -> int | None:
    """The section from `cursor` on that `heading` takes.

    A literal heading may skip sections, which are then missing or out of order. A placeholder heading matches
    almost anything, so it only takes a heading when no required section would be skipped to reach it.
    """
    for position in range(cursor, len(outline)):
        section = outline[position]
        if section.matches(heading) and (
            section.literal or not any(skipped.required for skipped in outline[cursor:position])
        ):
            return position
    return None


def _placement(missing: Heading, position: int, placed: dict[int, list[Heading]]) -> str:
    previous = next((placed[i][-1] for i in sorted(placed, reverse=True) if i < position), None)
    if previous is not None:
        return f"Add {_show(missing)} after the {_show(previous)} section."
    following = next((placed[i][0] for i in sorted(placed) if i > position), None)
    if following is not None:
        return f"Add {_show(missing)} before {_show(following)}."
    return f"Add {_show(missing)} to the note."
