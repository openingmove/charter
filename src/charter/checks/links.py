"""The `links` check: links resolve to exactly one file, anchors name real headings, link fields reach their kinds."""

import posixpath
import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from charter.checks import CheckRequest
from charter.contract import Contract
from charter.diagnostics import Diagnostic, Severity, code_list, code_span, suggestion
from charter.index import Note
from charter.links import Link, Resolver, wikilink_name


class LinksCheck:
    id = "links"
    codes = frozenset({"links/unresolved", "links/ambiguous", "links/missing-anchor", "links/wrong-kind"})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        contract = request.contract
        notes = {note.path: note for note in request.notes}
        for note in request.target_notes():
            if contract.skips_links(note.path):
                continue
            for link in note.links:
                if link.external:
                    yield from _wrong_kind(note, link, None, contract)
                elif not link.candidates:
                    yield _unresolved(note, link, contract, request.resolver)
                elif link.target is None:
                    yield _ambiguous(note, link, contract)
                else:
                    target = notes.get(link.target)
                    if contract.links.check_anchors and link.anchor and target is not None:
                        yield from _missing_anchor(note, link, target)
                    yield from _wrong_kind(note, link, target, contract)


def _written(note: Note, link: Link) -> str:
    """The link as the note writes it: `raw` has code spans blanked, so a body link is cut from the body again."""
    if link.column is None or link.line is None:
        return link.raw
    lines = note.body.split("\n")
    first = link.line - note.body_line
    # A link may run over several lines; each piece of `raw` is cut from the same line of the note.
    pieces = link.raw.split("\n")
    if first < 0 or first + len(pieces) > len(lines):
        return link.raw
    written = [
        lines[first + number][link.column if number == 0 else 0 :][: len(piece)]
        for number, piece in enumerate(pieces)
    ]
    return "\n".join(written)


def _unresolved(note: Note, link: Link, contract: Contract, resolver: Resolver) -> Diagnostic:
    named = wikilink_name(link.raw) if link.field is not None and "wikilink" not in contract.links.styles else None
    if named:
        return _error(
            note,
            link,
            "links/unresolved",
            f"Link {code_span(_written(note, link))} uses wikilink syntax, which `links.styles` does not enable.",
            f"Write a Markdown link such as `[{named.removesuffix('.md')}]({named.removesuffix('.md')}.md)`,"
            " or add `wikilink` to `links.styles` in charter.yaml.",
        )
    if link.style == "markdown":
        return _error(
            note,
            link,
            "links/unresolved",
            f"Link {code_span(_written(note, link))} does not resolve to a file.",
            "Markdown link paths are relative to the linking note's folder; `.md` may be omitted.",
        )
    *others, last = contract.links.resolve
    strategies = f"{', '.join(others)} or {last}" if others else last
    return _error(
        note,
        link,
        "links/unresolved",
        f"Link {code_span(_written(note, link))} matches no note by {strategies}.",
        suggestion(link.name, resolver.names(), "Check the spelling, or create the note."),
    )


def _ambiguous(note: Note, link: Link, contract: Contract) -> Diagnostic:
    first = PurePosixPath(link.candidates[0]).relative_to(contract.root_path).as_posix()
    one = "note" if first.endswith(".md") else "file"
    return _error(
        note,
        link,
        "links/ambiguous",
        f"Link {code_span(_written(note, link))} is ambiguous: {code_list(link.candidates)} all match by {link.strategy}.",
        _ambiguous_hint(note, link, contract, first, one),
    )


def _ambiguous_hint(note: Note, link: Link, contract: Contract, first: str, one: str) -> str:
    """How to name one file, in a form the contract's styles and strategies accept."""
    if "path" in contract.links.resolve:
        return f"Link by path to name one {one}, e.g. `[[{first.removesuffix('.md')}]]`."
    if "markdown" in contract.links.styles:
        relative = posixpath.relpath(link.candidates[0], posixpath.dirname(note.path))
        label = posixpath.basename(first).removesuffix(".md")
        return f"Link with a Markdown link to name one {one}, e.g. `[{label}]({relative})`."
    return "Make the name unique, or add `path` to `links.resolve` in charter.yaml to link by path."


def _missing_anchor(note: Note, link: Link, target: Note) -> Iterator[Diagnostic]:
    # `^id` names a block, not a heading.
    if link.anchor.startswith("^"):
        return
    if link.style == "markdown":
        wanted = link.anchor
        known = [_slug(heading.text) for heading in target.headings]
        if wanted in known or wanted in (heading.text for heading in target.headings):
            return
    else:
        # `[[Note#Section#Subsection]]` names the last heading.
        wanted = link.anchor.split("#")[-1].strip()
        known = [heading.text for heading in target.headings]
        if wanted in known:
            return
    listed = f"Headings in `{target.path}`: {code_list(known)}." if known else f"`{target.path}` has no headings."
    yield _error(
        note,
        link,
        "links/missing-anchor",
        f"Link {code_span(_written(note, link))} points at heading `{wanted}`, which `{target.path}` does not have.",
        suggestion(wanted, known, listed),
    )


def _wrong_kind(note: Note, link: Link, target: Note | None, contract: Contract) -> Iterator[Diagnostic]:
    if link.field is None:
        return
    # Only a declared field of the note's kind or variant yields a field link, so the note has a shape.
    shape = contract.shape_of(note.frontmatter)
    field = shape.fields.get(link.field) if shape is not None else None
    allowed = field.to if field is not None else None
    if allowed is None:
        return
    # The raw value, not `kind_of`: the message names even an undeclared kind the target claims.
    kind = target.frontmatter.get(contract.discriminator) if target is not None else None
    if kind in allowed:
        return
    wanted = f"kind {code_list(allowed)}" if len(allowed) == 1 else f"one of the kinds {code_list(allowed)}"
    if link.external:
        found = f"holds the URL `{link.name}`"
    elif target is None and _is_unreadable_note(link.target, contract):
        found = (
            f"links to `{link.target}`, which has no valid kind"
            " (it could not be read as a note; see its own findings)"
        )
    elif target is None:
        found = f"links to `{link.target}`, which is not a note"
    elif kind is None:
        found = f"links to `{link.target}`, which has no kind"
    else:
        found = f"links to `{link.target}`, which is kind `{kind}`"
    yield _error(
        note,
        link,
        "links/wrong-kind",
        f"Field `{link.field}` {found}; it must link to a note of {wanted}.",
        f"Link to a note of {wanted}, or change `to` for this field in charter.yaml.",
    )


def _is_unreadable_note(path: str, contract: Contract) -> bool:
    """A Markdown file the knowledge base holds that the index could not parse, so it is no indexed note."""
    return path.endswith(".md") and contract.holds(path)


def _slug(heading: str) -> str:
    """The anchor most Markdown renderers give a heading: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def _error(note: Note, link: Link, code: str, message: str, hint: str) -> Diagnostic:
    return Diagnostic(note.path, link.line, Severity.ERROR, code, message, hint)
