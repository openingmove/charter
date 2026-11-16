"""What charter reads from a Markdown body outside code: headings, HTML comments and `{{placeholders}}`."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from charter.prose import blank_code, blank_code_blocks, split_literals

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
PLACEHOLDER_SYNTAX = re.compile(r"\{\{[ \t]*([^{}\n]*?)[ \t]*\}\}")


@dataclass(frozen=True)
class Heading:
    level: int
    # As rendered: without HTML comments, and with runs of whitespace as one space.
    text: str
    line: int

    def __str__(self) -> str:
        return f"{'#' * self.level} {self.text}"


@dataclass(frozen=True)
class Comment:
    # Between `<!--` and `-->`, as written.
    text: str
    line: int


@dataclass(frozen=True)
class Placeholder:
    name: str
    line: int

    def __str__(self) -> str:
        return f"{{{{{self.name}}}}}"


@dataclass(frozen=True)
class Body:
    # Code and HTML comments blanked, line for line: where links and tags are found.
    prose: list[str]
    # Each line with its HTML comments cut out and code blanked.
    uncommented: list[str]
    headings: tuple[Heading, ...]
    comments: tuple[Comment, ...]
    # Outside code and HTML comments.
    placeholders: tuple[Placeholder, ...]


def parse_body(lines: list[str], first_line: int) -> Body:
    """The body whose lines are numbered from `first_line`."""
    code_free = blank_code_blocks(lines)
    text, uncommented, comments = split_literals(code_free)
    return Body(
        prose=text,
        uncommented=uncommented,
        headings=tuple(
            found for number, line in enumerate(uncommented, start=first_line) if (found := heading(line, number))
        ),
        comments=tuple(Comment(inner, first_line + index) for index, inner in comments),
        placeholders=placeholders(text, first_line),
    )


def heading(line: str, number: int) -> Heading | None:
    if (match := _HEADING.match(line)) is None:
        return None
    return Heading(len(match.group(1)), " ".join(match.group(2).split()), number)


def placeholders(lines: Sequence[str], first_line: int) -> tuple[Placeholder, ...]:
    return tuple(
        Placeholder(match.group(1), number)
        for number, line in enumerate(lines, start=first_line)
        for match in PLACEHOLDER_SYNTAX.finditer(line)
    )


def placeholder_matches(text: str) -> list[re.Match[str]]:
    """The placeholders in `text` outside code, which is literal; offsets are those of `text`."""
    return list(PLACEHOLDER_SYNTAX.finditer(blank_code(text)))
