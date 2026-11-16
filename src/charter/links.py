"""Link syntax and resolution: what a note links to, as the index records it.

Extraction finds links per the contract's `links.styles`; resolution maps each
to the files it may mean. Both are part of building the index, so every
consumer (the `links` check, `sweep`, plugins) sees the same resolved links.
"""

import bisect
import posixpath
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import PureWindowsPath
from urllib.parse import unquote

STYLES = ("wikilink", "markdown")
STRATEGIES = ("path", "basename", "alias")


@dataclass(frozen=True)
class LinkSettings:
    styles: tuple[str, ...]
    # Wikilink strategies in the order they are tried; the first that matches anything decides.
    resolve: tuple[str, ...]
    check_anchors: bool


@dataclass(frozen=True)
class RawLink:
    """A link as written, before resolution."""

    raw: str
    style: str
    # Frontmatter field the link came from; None for a body link.
    field: str | None
    line: int | None
    # What the link names, without label or anchor; empty for a link to a heading of its own note.
    name: str
    anchor: str | None
    # A URL: never resolved against the knowledge base.
    external: bool = False
    # Where `raw` starts in its line (`line`), for a body link: `raw` itself has code spans blanked to spaces, so
    # messages cut the written text from the note's own line at this column. A column in the line, not an offset
    # in the joined prose, because prose drops the length of code-block lines. None for a frontmatter link.
    column: int | None = None


@dataclass(frozen=True)
class Link(RawLink):
    # Every file the link may mean, in diagnostic form: one when resolved, several when ambiguous.
    candidates: tuple[str, ...] = ()
    strategy: str | None = None

    @property
    def target(self) -> str | None:
        return self.candidates[0] if len(self.candidates) == 1 else None


_WIKILINK = re.compile(r"(?<!\\)!?\[\[([^\[\]\n]+?)\]\]")
# A label may hold one level of brackets, so a linked image `[![alt](img.png)](note.md)` is one link.
_LABEL = r"(?:[^\[\]\\\n]|\\.|\[(?:[^\[\]\\\n]|\\.)*\])*"
_DESTINATION = r"<[^<>\n]*>|(?:[^\s()\\]|\\.|\((?:[^\s()\\]|\\.)*\))+"
_TITLE = r"\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)"
_MARKDOWN = re.compile(rf"(?<!\\)!?\[({_LABEL})\]\(\s*({_DESTINATION})(?:\s+(?:{_TITLE}))?\s*\)")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://|mailto:")
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")


def body_links(lines: Sequence[str], first_line: int, styles: Collection[str]) -> list[RawLink]:
    """Links in body lines numbered from `first_line`, as `Body.prose` leaves them."""
    text = "\n".join(lines)
    breaks = [offset for offset, char in enumerate(text) if char == "\n"]
    matches = []
    if "wikilink" in styles:
        matches += [(m.start(), m.group(0), m.group(1), _wikilink) for m in _WIKILINK.finditer(text)]
    if "markdown" in styles:
        matches += [(m.start(), m.group(0), m.group(2), _markdown) for m in _markdown_matches(text, 0, len(text))]
    links = []
    for start, raw, inner, parse in sorted(matches, key=lambda match: match[0]):
        index = bisect.bisect_left(breaks, start)
        link = parse(raw, inner, None, first_line + index)
        if not link.external:
            line_start = breaks[index - 1] + 1 if index else 0
            links.append(replace(link, column=start - line_start))
    return links


def _markdown_matches(text: str, start: int, end: int) -> Iterator[re.Match[str]]:
    for match in _MARKDOWN.finditer(text, start, end):
        yield match
        yield from _markdown_matches(text, match.start(1), match.end(1))


def field_link(value: str, field: str | None, line: int | None, styles: Collection[str]) -> RawLink:
    """The link a link field's value holds; a value in no allowed syntax is a bare name, resolved like a wikilink."""
    text = value.strip()
    if "wikilink" in styles and (whole := _WIKILINK.fullmatch(text)):
        return _wikilink(text, whole.group(1), field, line)
    if "markdown" in styles and (whole := _MARKDOWN.fullmatch(text)):
        return _markdown(text, whole.group(2), field, line)
    if _URL.match(text):
        return RawLink(text, "wikilink", field, line, text, None, external=True)
    return _wikilink(text, text, field, line)


def _wikilink(raw: str, inner: str, field: str | None, line: int | None) -> RawLink:
    # Inside a table cell the label separator is written `\|`.
    target = re.split(r"\\?\|", inner, maxsplit=1)[0]
    name, _, anchor = target.partition("#")
    return RawLink(raw, "wikilink", field, line, name.strip(), anchor.strip() or None)


def _markdown(raw: str, destination: str, field: str | None, line: int | None) -> RawLink:
    if destination.startswith("<"):
        destination = destination[1:-1]
    destination = _ESCAPE.sub(r"\1", destination)
    if _SCHEME.match(destination):
        return RawLink(raw, "markdown", field, line, destination, None, external=True)
    path, _, anchor = destination.partition("#")
    return RawLink(raw, "markdown", field, line, unquote(path), unquote(anchor) or None)


def wikilink_name(text: str) -> str | None:
    """The note a link field's value names when it is exactly one wikilink; None when it is anything else."""
    whole = _WIKILINK.fullmatch(text.strip())
    return _wikilink(text, whole.group(1), None, None).name if whole else None


class Resolver:
    """Resolves links against the files under the KB root, and by explicit path against others beside or below the
    contract's directory.

    An explicit path (a Markdown link, or a wikilink written as a path) may name any file under root, Markdown
    or not, ignored or not, or a file outside root that `outside_is_file` finds, matching case exactly. The
    name-based strategies (`basename`, `alias`) consider only files under root that are not
    ignored, so an ignored copy of a file never makes a link ambiguous.

    `files` and `named` are known to exist. `listed` are other files seen in a directory listing
    but not checked: a candidate among them is checked (and, for a name, tested against `ignored`)
    only when a link reaches it, so a large tree of attachments costs a listing, not a stat each.
    Everything is fixed at construction, so a result never depends on which links came first.
    """

    def __init__(
        self,
        root: str,
        files: Collection[str],
        named: Iterable[str],
        aliases: Mapping[str, Collection[str]],
        order: Iterable[str],
        listed: Collection[str] = (),
        is_file: Callable[[str], bool] = lambda path: True,
        ignored: Callable[[str], bool] = lambda path: False,
        outside_is_file: Callable[[str], bool] | None = None,
    ):
        self._root = root
        self._files = frozenset(files)
        self._order = tuple(order)
        self._is_file = is_file
        self._ignored = ignored
        # Matches case exactly, as names under root do, whatever the file system.
        self._outside_is_file = outside_is_file or is_file
        self._known = frozenset(named)
        self._listed = frozenset(listed) - self._files
        self._by_name: dict[str, list[str]] = {}
        for path in sorted({*self._known, *self._listed}):
            # A note is named without `.md`; any other file by its full filename.
            self._by_name.setdefault(posixpath.basename(path).removesuffix(".md"), []).append(path)
        self._by_alias: dict[str, list[str]] = {}
        for path in sorted(aliases):
            for alias in aliases[path]:
                self._by_alias.setdefault(alias, []).append(path)

    def _named(self, name: str) -> tuple[str, ...]:
        return tuple(
            path
            for path in self._by_name.get(name, ())
            if path in self._known or (not self._ignored(path) and self._is_file(path))
        )

    @cached_property
    def _all_names(self) -> list[str]:
        return sorted({*(name for name in self._by_name if self._named(name)), *self._by_alias})

    def names(self) -> list[str]:
        """Every name a wikilink may use, for "did you mean" hints. Checking the listed files is deferred to
        the first call, which only an unresolved wikilink makes."""
        return self._all_names

    def resolve(self, link: RawLink, source: str) -> Link:
        if link.external:
            return Link(**vars(link))
        if not link.name:
            return Link(**vars(link), candidates=(source,))
        if link.style == "markdown":
            relative = posixpath.join(posixpath.dirname(source), link.name)
            return Link(**vars(link), candidates=self._path(relative), strategy="path")
        for strategy in self._order:
            if candidates := self._strategy(strategy, link.name):
                return Link(**vars(link), candidates=candidates, strategy=strategy)
        return Link(**vars(link))

    def _strategy(self, strategy: str, name: str) -> tuple[str, ...]:
        if strategy == "path":
            return self._path(posixpath.join(self._root, name))
        if strategy == "basename":
            if "/" in name:
                return ()
            return self._named(name.removesuffix(".md"))
        return tuple(self._by_alias.get(name, ()))

    def _path(self, joined: str) -> tuple[str, ...]:
        path = posixpath.normpath(joined)
        outside = self._outside_root(path)
        for candidate in (path, f"{path}.md"):
            if candidate in self._files or (candidate in self._listed and self._is_file(candidate)):
                return (candidate,)
            # Beside or below the contract but not under root: only this target is checked, never a listing.
            if outside and self._outside_is_file(candidate):
                return (candidate,)
        return ()

    def _outside_root(self, path: str) -> bool:
        """Whether `path` (normalised, diagnostic form) is a place beside or below the contract's directory that
        is not under root. A path that leaves the contract's directory, or is not plainly POSIX relative, is
        never outside root: it must not reach the file system."""
        if path == ".." or path.startswith(("../", "/")) or "\\" in path or PureWindowsPath(path).drive:
            return False
        return self._root != "." and path != self._root and not path.startswith(f"{self._root}/")
