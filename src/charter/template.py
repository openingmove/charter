"""A kind's or variant's template: the body a new note starts from, and the outline its notes keep."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from charter.body import Comment, Heading, Placeholder, parse_body, placeholder_matches, placeholders

# Valid in every template besides the shape's fields: the day the note is created.
DATE = "date"
OPTIONAL = "optional"
REPEAT = "repeat"
_GUIDE = re.compile(r"\s*guide:(.*)", re.DOTALL)


def guide_text(comment: Comment) -> str | None:
    """The guidance of a `<!-- guide: … -->` comment, which a finished note must not keep; None for other comments."""
    guide = _GUIDE.match(comment.text)
    return " ".join(guide.group(1).split()) if guide is not None else None


@dataclass(frozen=True)
class Section:
    """A heading of the template, and how often a note may have it."""

    heading: Heading
    optional: bool
    # May appear any number of times, its placeholders standing for any text each time.
    repeat: bool
    # The `<!-- guide: … -->` text under the heading, before the next one; None without guidance.
    guide: str | None
    _pattern: re.Pattern[str] = field(compare=False, repr=False)

    @property
    def required(self) -> bool:
        return not (self.optional or self.repeat)

    @property
    def literal(self) -> bool:
        """Whether the heading holds no placeholder, so only one text matches it."""
        return not placeholder_matches(self.heading.text)

    def matches(self, heading: Heading) -> bool:
        return heading.level == self.heading.level and self._pattern.fullmatch(heading.text) is not None


@dataclass(frozen=True)
class Template:
    # In diagnostic form.
    path: str
    outline: tuple[Section, ...]
    # The guidance before the first heading; None without any.
    lead: str | None
    # Every placeholder outside code, including those inside comments, in line order.
    placeholders: tuple[Placeholder, ...]
    text: str = field(repr=False)


def _substitute(text: str, replace: Callable[[re.Match[str]], str], keep: Callable[[str], str] = str) -> str:
    """`text` with each placeholder outside code replaced; `keep` maps the text between them."""
    out, end = [], 0
    for match in placeholder_matches(text):
        out += [keep(text[end : match.start()]), replace(match)]
        end = match.end()
    return "".join([*out, keep(text[end:])])


def fill(text: str, values: Mapping[str, str]) -> str:
    """`text` with each placeholder outside code that `values` names replaced; the others stay for the author."""
    return _substitute(text, lambda match: values.get(match.group(1), match.group(0)))


def outline(template: Template | None, values: Mapping[str, str]) -> tuple[str, ...]:
    """The template's headings, filled from `values`, with their markers: `## Notes (optional)`."""
    return tuple(
        f"{fill(str(section.heading), values)}{' (optional)' if section.optional else ''}"
        f"{' (repeat)' if section.repeat else ''}"
        for section in (template.outline if template is not None else ())
    )


class TemplateError(Exception):
    def __init__(self, message: str, hint: str):
        super().__init__(message)
        self.message = message
        self.hint = hint


def parse_template(path: str, text: str) -> Template:
    lines = text.split("\n")
    if lines[0].rstrip() == "---":
        raise TemplateError(
            f"`{path}` has frontmatter; frontmatter belongs in charter.yaml.",
            "Declare fields, defaults and `auto` values in charter.yaml and keep only the note body in the template.",
        )
    body = parse_body(lines, 1)
    markers: dict[Heading, set[str]] = {}
    for comment in body.comments:
        marker = comment.text.strip()
        if marker not in (OPTIONAL, REPEAT):
            continue
        owner = _marked_heading(comment, body.headings, body.uncommented)
        if owner is None:
            raise TemplateError(
                f"`<!-- {marker} -->` (`{path}` line {comment.line}) follows no heading.",
                "Put the marker on the heading's line, or on the line after it.",
            )
        markers.setdefault(owner, set()).add(marker)
    in_comments = (placeholders(comment.text.split("\n"), comment.line) for comment in body.comments)
    guides = _guides(body.comments, body.headings)
    return Template(
        path=path,
        outline=tuple(
            Section(
                heading,
                OPTIONAL in markers.get(heading, ()),
                REPEAT in markers.get(heading, ()),
                guides.get(heading),
                _heading_pattern(heading.text),
            )
            for heading in body.headings
        ),
        lead=guides.get(None),
        placeholders=tuple(
            sorted([*body.placeholders, *(p for found in in_comments for p in found)], key=lambda p: p.line)
        ),
        text=text,
    )


def _guides(comments: tuple[Comment, ...], headings: tuple[Heading, ...]) -> dict[Heading | None, str]:
    """Each heading's guidance, joined; None keys the guidance before the first heading."""
    found: dict[Heading | None, list[str]] = {}
    for comment in comments:
        guide = guide_text(comment)
        if guide is None:
            continue
        owner = next((heading for heading in reversed(headings) if heading.line <= comment.line), None)
        found.setdefault(owner, []).append(guide)
    return {owner: " ".join(texts) for owner, texts in found.items()}


def _marked_heading(comment: Comment, headings: tuple[Heading, ...], uncommented: list[str]) -> Heading | None:
    """The heading a marker belongs to: on the same line, or above it with nothing but blank lines between."""
    for heading in reversed(headings):
        if heading.line == comment.line:
            return heading
        if heading.line < comment.line:
            # Template lines are numbered from 1, so line n is uncommented[n - 1].
            between = uncommented[heading.line : comment.line]
            return heading if all(not line.strip() for line in between) else None
    return None


def _heading_pattern(text: str) -> re.Pattern[str]:
    """Heading text with each placeholder outside code standing for any text."""
    return re.compile(_substitute(text, lambda match: ".+", re.escape))
