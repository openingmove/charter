"""Tags: what a note is tagged with, as the index records it, and the contract's allowlist."""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from charter.globs import compile_glob

_FIELD = "tags"
# A `#` at the start of a word; one inside a word is a link anchor or plain text, and `# ` opens a heading.
_INLINE = re.compile(r"(?<!\S)#([\w/-]+)")
# A tag never holds a space, so text holding several, in a list item or not, is split into them.
_SEPARATORS = re.compile(r"[,\s]+")
# A name of only digits, `-` and `/` (an issue number like `#123`, a rule like `#--`) is not a tag.
_NOT_A_TAG = re.compile(r"[\d/-]*")


@dataclass(frozen=True)
class Tag:
    name: str
    line: int | None


@dataclass(frozen=True)
class TagSettings:
    # Globs a tag must match; None when the contract sets no allowlist.
    allow: tuple[str, ...] | None
    # Whether `#tags` in the body count, besides the `tags` field.
    inline: bool

    @cached_property
    def _patterns(self) -> tuple[re.Pattern[str], ...]:
        # Tags nest with `/` like folders, so they match level by level as path globs do.
        return tuple(compile_glob(glob) for glob in self.allow or ())

    def allows(self, name: str) -> bool:
        # A `*` matches an empty level, so a malformed name like `a//b` would otherwise slip through.
        if "" in name.split("/"):
            return False
        return any(pattern.fullmatch(name) for pattern in self._patterns)


def note_tags(
    frontmatter: Mapping[str, Any], field_lines: Mapping[str, int], prose: Sequence[str], first_line: int, inline: bool
) -> tuple[Tag, ...]:
    """The `tags` field's tags, then inline ones when `inline`, from body lines as `Body.prose` leaves them."""
    found = [Tag(name, field_lines.get(_FIELD)) for name in _field_tags(frontmatter.get(_FIELD))]
    if inline:
        found += [
            Tag(name, number)
            for number, line in enumerate(prose, start=first_line)
            for match in _INLINE.finditer(line)
            if (name := _name(match.group(1)))
        ]
    return tuple(found)


def _field_tags(value: Any) -> Iterator[str]:
    # Values of other types are the schema check's finding when `tags` is declared.
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, str):
            yield from (name for text in _SEPARATORS.split(item) if (name := _name(text)))


def _name(text: str) -> str | None:
    name = text.removeprefix("#").rstrip("/")
    return None if _NOT_A_TAG.fullmatch(name) else name
