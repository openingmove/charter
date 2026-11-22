"""The parsed model of every note under the contract's root."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from charter import yamlsource
from charter.body import Body, Comment, Heading, Placeholder, parse_body
from charter.contract import Contract
from charter.diagnostics import Diagnostic, Severity
from charter.links import Link, RawLink, Resolver, body_links, field_link
from charter.tags import Tag, note_tags
from charter.tree import Tree, decode

UNREADABLE = "index/unreadable"
INVALID_FRONTMATTER = "index/invalid-frontmatter"
CODES = frozenset({UNREADABLE, INVALID_FRONTMATTER})

_FENCE = "---"
# The frontmatter field whose values a wikilink may name a note by.
ALIASES = "aliases"
# The frontmatter field holding a note's title, which `new` fills from its title argument.
TITLE = "title"


@dataclass(frozen=True)
class _Source:
    """What a note's body is parsed from, kept until something asks for a body part."""

    # Only the text takes part in equality: two notes differing in their bodies differ, and comparing them parses
    # nothing. The contract and resolver are shared by every note of an index.
    lines: list[str]
    # 0-based index of the first body line.
    start: int
    contract: Contract = field(compare=False, repr=False)
    resolver: Resolver = field(compare=False, repr=False)


# Test seam, not an option: called with the path of each note whose body is parsed.
_body_parsed: Callable[[str], None] | None = None


@dataclass(frozen=True)
class Note:
    path: str
    frontmatter: dict[str, Any]
    field_lines: dict[str, int]
    # False for a file with no `---` block at all, as opposed to an empty one.
    has_frontmatter: bool
    _source: _Source = field(repr=False)

    # (The plain properties below are cheap reads of the cached `_body`; the cached ones do work of their own.)
    # Everything below comes from the body and is parsed on first use: a run that judges one file has no need of
    # the other notes' bodies unless a check follows a link to them. Reading a part is what triggers the parse,
    # so no consumer can see an unparsed (empty) body.
    @cached_property
    def _body(self) -> Body:
        if _body_parsed is not None:
            _body_parsed(self.path)
        return parse_body(self._source.lines[self._source.start :], self._source.start + 1)

    @property
    def headings(self) -> tuple[Heading, ...]:
        return self._body.headings

    # Frontmatter link fields first, then body links, each in file order.
    @cached_property
    def links(self) -> tuple[Link, ...]:
        source = self._source
        raw = [
            *_field_links(self.frontmatter, self.field_lines, source.contract),
            *body_links(self._body.prose, source.start + 1, source.contract.links.styles),
        ]
        return tuple(source.resolver.resolve(link, self.path) for link in raw)

    # The `tags` field's tags, then inline `#tags` when the contract counts them, each in file order.
    @cached_property
    def tags(self) -> tuple[Tag, ...]:
        source = self._source
        return note_tags(
            self.frontmatter, self.field_lines, self._body.prose, source.start + 1, source.contract.tags.inline
        )

    # HTML comments outside code.
    @property
    def comments(self) -> tuple[Comment, ...]:
        return self._body.comments

    # `{{placeholders}}` outside code and HTML comments.
    @property
    def placeholders(self) -> tuple[Placeholder, ...]:
        return self._body.placeholders

    # Everything after the frontmatter, as written, for checks that need more than the parsed parts.
    @cached_property
    def body(self) -> str:
        return "\n".join(self._source.lines[self._source.start :])

    # The body line for line with code and HTML comments blanked, starting at line `body_line`.
    @cached_property
    def prose(self) -> tuple[str, ...]:
        return tuple(self._body.prose)

    @property
    def body_line(self) -> int:
        return self._source.start + 1


@dataclass(frozen=True)
class Index:
    notes: tuple[Note, ...]
    diagnostics: tuple[Diagnostic, ...]
    resolver: Resolver


class _FrontmatterError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(message)
        self.message = message
        self.line = line


def build_index(contract: Contract, pending: Mapping[str, str] | None = None) -> Index:
    """The index of the notes in the contract's tree, plus `pending` notes (text by diagnostic-form path) not yet
    written."""
    pending = pending or {}
    tree = contract.tree
    # Only notes are stat-ed here; the names of other files go to the resolver unchecked.
    paths = sorted({*tree.files(contract.root_path, ".md"), *pending})
    named = [path for path in paths if not contract.ignores(path)]
    markdown = [path for path in named if path.endswith(".md")]
    contents = tree.read(path for path in markdown if path not in pending)
    read: list[tuple[str, dict[str, Any], dict[str, int], bool, list[str], int]] = []
    diagnostics = []
    for path in markdown:
        reason = None
        if path in pending:
            text = pending[path]
        elif (content := contents.get(path)) is None:
            reason = "could not be read"
        else:
            try:
                text = decode(content)
            except UnicodeDecodeError:
                reason = "is not valid UTF-8 text"
        if reason is not None:
            diagnostics.append(
                Diagnostic(path, None, Severity.ERROR, UNREADABLE, f"The file {reason}.", None)
            )
            continue
        lines = text.split("\n")
        try:
            found = _frontmatter(lines)
        except _FrontmatterError as error:
            diagnostics.append(
                Diagnostic(
                    path,
                    error.line,
                    Severity.ERROR,
                    INVALID_FRONTMATTER,
                    error.message,
                    "Frontmatter is a YAML mapping between two `---` lines at the top of the file.",
                )
            )
            continue
        frontmatter, field_lines, body_start = found or ({}, {}, 0)
        read.append((path, frontmatter, field_lines, found is not None, lines, body_start))

    resolver = Resolver(
        contract.root_path,
        paths,
        named,
        {path: _aliases(frontmatter) for path, frontmatter, *_ in read},
        contract.links.resolve,
        # Names only: a file is checked, and its ignore policy read, when a link reaches it.
        [path for path in tree.listed(contract.root_path) if not path.endswith(".md")],
        tree.is_file,
        contract.ignores,
        tree.is_exact_file,
    )
    notes = tuple(
        Note(path, frontmatter, field_lines, has_frontmatter, _Source(lines, start, contract, resolver))
        for path, frontmatter, field_lines, has_frontmatter, lines, start in read
    )
    return Index(notes, tuple(diagnostics), resolver)


def _field_links(frontmatter: dict[str, Any], field_lines: dict[str, int], contract: Contract) -> Iterator[RawLink]:
    shape = contract.shape_of(frontmatter)
    fields = shape.fields if shape is not None else {}
    for name, value in frontmatter.items():
        field = fields.get(name)
        if field is None or not field.holds_links:
            continue
        # Values of the wrong type are the schema check's finding.
        for item in value if isinstance(value, list) else [value]:
            # A blank value is no link, as a blank value is no value for `required`.
            if isinstance(item, str) and item.strip():
                yield field_link(item, name, field_lines.get(name), contract.links.styles)


def _aliases(frontmatter: Mapping[str, Any]) -> list[str]:
    value = frontmatter.get(ALIASES)
    values = value if isinstance(value, list) else [value]
    return [alias for alias in values if isinstance(alias, str) and alias]


def frontmatter_of(text: str) -> dict[str, Any]:
    """The frontmatter of a note's `text`; empty when it has none, or none that parses."""
    return frontmatter_and_lines(text)[0]


def kinds_before(contract: Contract, before: Tree, leaving_out: frozenset[str] = frozenset()) -> frozenset[str]:
    """The kinds of the notes in `before`, other than those at `leaving_out`: the notes the knowledge base would
    index."""
    notes = [
        path
        for path in before.files(contract.root_path)
        if path.endswith(".md") and not contract.ignores(path) and path not in leaving_out
    ]
    kinds = set()
    for content in before.read(notes).values():
        try:
            kind = contract.kind_of(frontmatter_of(decode(content)))
        except UnicodeDecodeError:
            continue
        if kind is not None:
            kinds.add(kind.name)
    return frozenset(kinds)


def frontmatter_and_lines(text: str) -> tuple[dict[str, Any], dict[str, int]]:
    """`frontmatter_of(text)`, and the 1-based line of each of its keys."""
    try:
        found = _frontmatter(text.split("\n"))
    except _FrontmatterError:
        return {}, {}
    return found[:2] if found else ({}, {})


def body_start(lines: list[str]) -> int:
    """The 0-based index of the first body line: after the frontmatter block's closing `---`, whether or not its
    YAML parses; 0 without a complete block."""
    if not lines or lines[0].rstrip() != _FENCE:
        return 0
    close = _closing_fence(lines)
    return 0 if close is None else close + 1


def _closing_fence(lines: list[str]) -> int | None:
    return next((i for i in range(1, len(lines)) if lines[i].rstrip() == _FENCE), None)


def _frontmatter(lines: list[str]) -> tuple[dict[str, Any], dict[str, int], int] | None:
    """Return (frontmatter, 1-based line of each key, 0-based index of the first body line), or None without one."""
    if not lines or lines[0].rstrip() != _FENCE:
        return None
    close = _closing_fence(lines)
    if close is None:
        raise _FrontmatterError("Frontmatter has no closing `---` line.", 1)

    try:
        data, node = yamlsource.parse("\n".join(lines[1:close]))
    except yamlsource.YamlSyntaxError as error:
        line = error.line + 1 if error.line else 1
        raise _FrontmatterError(f"Invalid YAML in frontmatter: {error.message}.", line) from None
    if data is None:
        return {}, {}, close + 1
    if not isinstance(data, dict):
        raise _FrontmatterError("Frontmatter must be a YAML mapping of fields.", 2)
    # The YAML text starts on file line 2, after the opening fence.
    lines_by_key = {key: line + 1 for key, line in yamlsource.key_lines(node).items()}
    return data, lines_by_key, close + 1


@dataclass(frozen=True)
class NoteHead:
    """A note's frontmatter read on its own: a block that does not parse is reported in `error`, not raised."""

    frontmatter: dict[str, Any]
    has_frontmatter: bool
    # Why the block does not parse; None when it parses or there is none.
    error: str | None
    # The 0-based index of the first body line.
    body_start: int


def note_head(lines: list[str]) -> NoteHead:
    try:
        found = _frontmatter(lines)
    except _FrontmatterError as error:
        # A block that does not parse still hides its YAML from the body.
        return NoteHead({}, True, error.message, body_start(lines))
    if found is None:
        return NoteHead({}, False, None, 0)
    return NoteHead(found[0], True, None, found[2])
