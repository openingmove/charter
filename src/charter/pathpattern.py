"""A kind's `path` pattern: a template over a note's fields that renders where the note belongs.

Patterns render from field texts (see `Shape.field_texts`): a field absent from the texts is missing,
and one mapped to None holds a value of the wrong type, which makes the path unrenderable.
"""

import re
import unicodedata
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Any

from charter.diagnostics import code_list, suggestion, yaml_text

SUFFIX_FILTER = "suffix"

FieldTexts = Mapping[str, str | None]


def _slug(text: str) -> str:
    # Accents fold to their base letter; other scripts keep their letters, so a slug is never empty by accident.
    unaccented = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", "-", unaccented.lower()).strip("-")


# `suffix` is not here: it needs the kind's table, and it alone renders a missing value.
_TEXT_FILTERS: dict[str, Callable[[str], str]] = {"lower": str.lower, "slug": _slug}
FILTERS = (SUFFIX_FILTER, *_TEXT_FILTERS)

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_HINT = "A placeholder is a field name in braces, optionally with filters: `{title}`, `{title|slug}`."

# Characters and names Windows refuses in a file or folder name; paths must work on every platform.
_WINDOWS_FORBIDDEN = frozenset('<>:"|?*')
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)


class PatternError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


@dataclass(frozen=True)
class Placeholder:
    field: str
    filters: tuple[str, ...]


@dataclass(frozen=True)
class Unrenderable:
    """A field the pattern needs that is missing, or holds a value of the wrong type."""

    field: str


@dataclass(frozen=True)
class Unsafe:
    """A field whose rendered text cannot be part of a path that works on every platform."""

    field: str
    reason: str


def text_of(value: Any) -> str:
    """A well-typed scalar field value as it appears in a path."""
    return unicodedata.normalize("NFC", yaml_text(value))


def segment_problem(name: str) -> str | None:
    """Why `name` cannot be a file or folder name on every platform, or None when it can."""
    return _character_problem(name) or _name_problem(name)


def _character_problem(text: str) -> str | None:
    for char in text:
        if char in "/\\":
            return f"contains `{char}`, which separates folders"
        if char in _WINDOWS_FORBIDDEN:
            return f"contains `{char}`, which Windows does not allow in file names"
        if ord(char) < 32:
            return "contains a control character"
    return None


def _name_problem(name: str) -> str | None:
    if name in ("", ".", ".."):
        return f"makes a file or folder named `{name}`" if name else "leaves a file or folder name empty"
    if name.endswith((".", " ")):
        return f"makes the name `{name}`, which ends in a dot or space that Windows drops"
    if windows_reserved(name):
        return f"makes the name `{name}`, which Windows reserves"
    return None


def windows_reserved(name: str) -> bool:
    """Whether Windows reserves the file or folder name `name` for a device, whatever its extension."""
    return name.split(".")[0].rstrip(" ").upper() in _WINDOWS_RESERVED


@dataclass(frozen=True)
class PathPattern:
    text: str
    # Literal text and placeholders, in order.
    parts: tuple[str | Placeholder, ...]
    suffixes: Mapping[str, str]

    @classmethod
    def parse(cls, text: str, suffixes: Mapping[Any, str]) -> "PathPattern":
        parts: list[str | Placeholder] = []
        position = 0
        for match in _PLACEHOLDER.finditer(text):
            parts.append(_literal(text[position : match.start()]))
            parts.append(_placeholder(match.group(1)))
            position = match.end()
        parts.append(_literal(text[position:]))
        skeleton = "".join(part if isinstance(part, str) else "x" for part in parts)
        # Only the leading literal can hold a drive; a colon after a placeholder is just a character.
        if PureWindowsPath(parts[0]).drive or any(folder in ("", ".", "..") for folder in skeleton.split("/")):
            raise PatternError(
                f"`{text}` is not a path relative to `root`.",
                "Write it like `Folder/{title}.md`: no leading `/`, drive, empty folder, `.` or `..`.",
            )
        if not skeleton.endswith(".md"):
            raise PatternError(f"`{text}` does not end in `.md`.", "Notes are Markdown files, so the path ends in `.md`.")
        _check_literals(text, parts, skeleton)
        return cls(
            text,
            tuple(part for part in parts if part != ""),
            {text_of(key): unicodedata.normalize("NFC", value) for key, value in suffixes.items()},
        )

    @property
    def placeholders(self) -> tuple[Placeholder, ...]:
        return tuple(part for part in self.parts if isinstance(part, Placeholder))

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(placeholder.field for placeholder in self.placeholders))

    def render(self, texts: FieldTexts) -> str | Unsafe | Unrenderable:
        """The path relative to `root`, POSIX and NFC; Unsafe when a field's text would make it unportable."""
        pieces: list[tuple[str, str | None]] = []
        for part in self.parts:
            if isinstance(part, str):
                pieces.append((part, None))
                continue
            rendered = self._render(part, texts)
            if rendered is None:
                return Unrenderable(part.field)
            # Checked per value, before a separator in it could split the path into other names.
            problem = _character_problem(rendered) or (
                "renders as nothing" if not rendered and SUFFIX_FILTER not in part.filters else None
            )
            if problem:
                return Unsafe(part.field, problem)
            pieces.append((rendered, part.field))
        return _name_unsafe(pieces) or "".join(rendered for rendered, _ in pieces)

    def split(self, path: str, texts: FieldTexts, fields: Collection[str]) -> list[tuple[str, str]] | None:
        """What `path` holds where each unfiltered placeholder of `fields` stands, with every other part rendered.

        None when `path` does not fit the pattern even so, when the other parts cannot be rendered, or when
        `path` splits more than one way between those placeholders.
        """
        literal_parts, named = [], []
        for part in self.parts:
            if isinstance(part, Placeholder) and part.field in fields and not part.filters:
                literal_parts.append(None)
                named.append(part.field)
                continue
            rendered = part if isinstance(part, str) else self._render(part, texts)
            if rendered is None:
                return None
            literal_parts.append(re.escape(rendered))
        splits = {
            tuple(match.groups())
            for capture in ("([^/]+?)", "([^/]+)")
            if (match := re.fullmatch("".join(capture if p is None else p for p in literal_parts), path))
        }
        # The shortest and longest first captures agree only when the literals pin the split down.
        return list(zip(named, splits.pop(), strict=True)) if len(splits) == 1 else None

    def _render(self, placeholder: Placeholder, texts: FieldTexts) -> str | None:
        name = placeholder.field
        if name in texts and texts[name] is None:
            return None
        text = texts.get(name)
        for filter_name in placeholder.filters:
            if filter_name == SUFFIX_FILTER:
                text = self.suffixes.get(text, "") if text is not None else ""
            elif text is not None:
                text = unicodedata.normalize("NFC", _TEXT_FILTERS[filter_name](text))
        return text


def _name_unsafe(pieces: list[tuple[str, str | None]]) -> Unsafe | None:
    """The first field in a file or folder name that its text leaves unportable (`CON`, `Notes.`, `..`)."""
    segment, fields = "", []
    # The closing separator flushes the last name.
    for rendered, field in [*pieces, ("/", None)]:
        for position, chunk in enumerate(rendered.split("/")):
            if position > 0:
                problem = _name_problem(segment)
                if problem and fields:
                    return Unsafe(fields[0], problem)
                segment, fields = "", []
            segment += chunk
            if field is not None:
                fields.append(field)
    return None


def _check_literals(text: str, parts: list[str | Placeholder], skeleton: str) -> None:
    """Reject literal text that would make an unportable path, by the rules `filenames/unsafe-value` applies."""
    # `/` separates folders in a literal, so it is not a character problem there.
    problems = [(part, _character_problem(part.replace("/", ""))) for part in parts if isinstance(part, str)]
    # A placeholder stands in as `x`, which is portable, so only the literal text of a name can fail.
    problems += [(name, _name_problem(name)) for name in skeleton.split("/")]
    for shown, problem in problems:
        if problem:
            # The skeleton's `x` is not in the user's pattern, so say `{...}` for a placeholder.
            raise PatternError(
                f"`{text}` {problem.replace('`' + shown + '`', '`' + _as_written(shown, parts) + '`')}.",
                "Rename the folder or file in the literal text of the pattern.",
            )


def _as_written(name: str, parts: list[str | Placeholder]) -> str:
    # Re-render the skeleton name with `{...}` where the placeholder stood; first matching segment is enough.
    pattern = "".join(part if isinstance(part, str) else "\0" for part in parts)
    for segment in pattern.split("/"):
        if segment.replace("\0", "x") == name:
            return segment.replace("\0", "{...}")
    return name


def _literal(text: str) -> str:
    for brace in "{}":
        if brace in text:
            other = "}" if brace == "{" else "{"
            raise PatternError(f"`{brace}` has no matching `{other}`.", _HINT)
    # Either separator works in the contract; rendered paths always use `/`.
    return unicodedata.normalize("NFC", text.replace("\\", "/"))


def _placeholder(inner: str) -> Placeholder:
    field, *filters = (piece.strip() for piece in inner.split("|"))
    if not field:
        raise PatternError(f"`{{{inner}}}` names no field.", _HINT)
    for name in filters:
        if name not in FILTERS:
            raise PatternError(
                f"unknown filter `{name}` in `{{{inner}}}`.",
                suggestion(name, FILTERS, f"Filters: {code_list(FILTERS)}."),
            )
    return Placeholder(field, tuple(filters))
