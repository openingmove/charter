"""`charter sweep`: the notes that depend on a note, for whoever is about to change a fact in it.

Dependents are notes whose links may mean it, or whose prose names it by title, filename, alias or id; the note's
own links are what it depends on. Notes under a `sweep: false` path policy appear in none of these lists.
"""

import json
import posixpath
import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from charter.body import heading
from charter.contract import Contract
from charter.diagnostics import Diagnostic, Refused, Severity, code_list, suggestion
from charter.index import ALIASES, TITLE, Index, Note, build_index
from charter.links import Link, field_link
from charter.prose import LIST_ITEM

JSON_FORMAT_ID = "charter-sweep/1"
_ID = "id"
_NOT_A_NOTE_HINT = "Name a note by its path, filename, alias or wikilink."


@dataclass(frozen=True)
class Reference:
    """A link from another note that resolves to the swept note, or is ambiguous between it and others."""

    path: str
    line: int | None
    field: str | None
    raw: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class Mention:
    path: str
    line: int
    names: tuple[str, ...]


@dataclass(frozen=True)
class Sweep:
    note: str
    linked_from: tuple[Reference, ...]
    mentioned_in: tuple[Mention, ...]
    links_to: tuple[Link, ...]
    # Notes charter could not parse, so whatever they say about the note is unknown.
    unsearched: tuple[str, ...]


@dataclass(frozen=True)
class _Names:
    # Matches casefolded NFC text; capturing group i stands for spelled[i - 1].
    pattern: re.Pattern[str]
    spelled: tuple[str, ...]


def find(contract: Contract, named: str) -> Sweep:
    """The sweep of the note `named` by a path from the working directory or as a wikilink names it; raises
    Refused (usage) when that is no single note."""
    index = build_index(contract)
    path = _named_path(contract, index, named)
    note = next((note for note in index.notes if note.path == path), None)
    if note is None:
        raise _not_a_note(contract, named)
    others = [other for other in index.notes if other.path != path and contract.sweeps(other.path)]
    names = _names(contract, note)
    return Sweep(
        path,
        tuple(
            Reference(other.path, link.line, link.field, link.raw, link.candidates)
            for other in others
            for link in other.links
            if path in link.candidates
        ),
        tuple(mention for other in others for mention in _mentions(other, path, names)) if names else (),
        tuple(
            link
            for link in note.links
            if not link.external and link.target != path and (link.target is None or contract.sweeps(link.target))
        ),
        tuple(sorted({d.path for d in index.diagnostics if contract.sweeps(d.path)})),
    )


def _named_path(contract: Contract, index: Index, named: str) -> str:
    file = Path(named)
    if file.is_file():
        path = contract.path_of(file)
        if path is None:
            raise _not_a_note(contract, named)
        return path
    link = field_link(named, None, None, ("wikilink",))
    candidates = () if link.external or not link.name else index.resolver.resolve(link, contract.root_path).candidates
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise _refused(
            contract,
            "usage/ambiguous-note",
            f"`{named}` may name any of {code_list(candidates)}.",
            "Name the note by its path from the knowledge-base root.",
        )
    raise _refused(
        contract,
        "usage/unknown-note",
        f"`{named}` names no note: it is neither a file nor a note's path, filename or alias.",
        suggestion(link.name, index.resolver.names(), _NOT_A_NOTE_HINT),
    )


def _not_a_note(contract: Contract, named: str) -> Refused:
    return _refused(
        contract,
        "usage/not-a-note",
        f"`{named}` is not a note: charter sweeps Markdown notes under the knowledge-base root that no "
        "`ignore: true` path policy covers and that it can read.",
        _NOT_A_NOTE_HINT,
    )


def _refused(contract: Contract, code: str, message: str, hint: str) -> Refused:
    return Refused([Diagnostic(contract.file, None, Severity.ERROR, code, message, hint)], usage=True)


def _names(contract: Contract, note: Note) -> _Names | None:
    frontmatter = note.frontmatter
    words = [frontmatter.get(TITLE), posixpath.basename(note.path).removesuffix(".md"), *_list(frontmatter, ALIASES)]
    alternatives: dict[str, str] = {}
    for word in words:
        if not isinstance(word, str) or not word.strip():
            continue
        name = _nfc(word)
        alternatives.setdefault(r"\s+".join(map(re.escape, name.casefold().split())), name)
    note_id = frontmatter.get(_ID)
    if isinstance(note_id, (int, str)) and not isinstance(note_id, bool) and str(note_id).strip():
        text = _nfc(str(note_id).strip())
        escaped = re.escape(text.casefold())
        kind = frontmatter.get(contract.discriminator)
        # A number alone is too common in prose to mean the note; written after its kind or `#` it does.
        if isinstance(kind, str) and kind.strip():
            alternatives.setdefault(rf"{re.escape(_nfc(kind).casefold())}\s+#?{escaped}", text)
        alternatives.setdefault(rf"#{escaped}", text)
        if any(char.isalpha() for char in text):
            alternatives.setdefault(escaped, text)
    if not alternatives:
        return None
    # Longest first, so a title that contains the filename is found as the title.
    ordered = sorted(alternatives, key=len, reverse=True)
    groups = "|".join(f"({alternative})" for alternative in ordered)
    return _Names(re.compile(rf"(?<!\w)(?:{groups})(?!\w)"), tuple(alternatives[a] for a in ordered))


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _list(frontmatter: dict[str, Any], field: str) -> list[Any]:
    value = frontmatter.get(field)
    return value if isinstance(value, list) else [value]


def _mentions(note: Note, swept: str, names: _Names) -> Iterator[Mention]:
    # Links that may mean the swept note are listed as links already; other links' text may still name it.
    linking: dict[int, list[str]] = {}
    for link in note.links:
        if link.field is None and link.line is not None and swept in link.candidates:
            linking.setdefault(link.line, []).append(link.raw)
    lines = []
    for number, line in enumerate(note.prose, start=note.body_line):
        for raw in linking.get(number, ()):
            line = line.replace(raw, " " * len(raw))
        lines.append(_nfc(line))
    for first, text in _paragraphs(lines, note.body_line):
        # Casefolding never adds or removes a line break, so counting them still finds the line.
        folded = text.casefold()
        found: dict[int, list[str]] = {}
        for match in names.pattern.finditer(folded):
            line = first + folded.count("\n", 0, match.start())
            found.setdefault(line, []).append(names.spelled[match.lastindex - 1])
        for line, spelled in found.items():
            yield Mention(note.path, line, tuple(dict.fromkeys(spelled)))


def _paragraphs(lines: list[str], first_line: int) -> Iterator[tuple[int, str]]:
    """Runs of lines a name may wrap across, each with its first line number: blank lines, headings and list
    items break runs."""
    run: list[str] = []
    start, closed = first_line, False
    for number, line in enumerate(lines, start=first_line):
        blank = not line.strip()
        is_heading = heading(line, number) is not None
        if run and (closed or blank or is_heading or LIST_ITEM.match(line)):
            yield start, "\n".join(run)
            run = []
        if not blank:
            if not run:
                start = number
            run.append(line)
        closed = is_heading
    if run:
        yield start, "\n".join(run)


def to_json(swept: Sweep) -> str:
    document = {
        "format": JSON_FORMAT_ID,
        "note": swept.note,
        "linked_from": [
            {**vars(reference), "candidates": list(reference.candidates)} for reference in swept.linked_from
        ],
        "mentioned_in": [{**vars(mention), "names": list(mention.names)} for mention in swept.mentioned_in],
        "links_to": [
            {"line": link.line, "field": link.field, "raw": link.raw, "target": link.target,
             "candidates": list(link.candidates)}
            for link in swept.links_to
        ],
        "unsearched": list(swept.unsearched),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def to_text(swept: Sweep) -> str:
    sections = [
        ("Linked from", [f"{_at(r.path, r.line)}  {_reference_text(r)}" for r in swept.linked_from]),
        ("Mentioned in", [f"{_at(m.path, m.line)}  {', '.join(m.names)}" for m in swept.mentioned_in]),
        (
            "Links to",
            [
                f"{'' if link.line is None else link.line}  {_link_text(link.field, link.raw)} -> {_resolution(link)}"
                for link in swept.links_to
            ],
        ),
    ]
    if swept.unsearched:
        sections.append(("Not searched, as charter could not read them", list(swept.unsearched)))
    lines = [f"Sweep of `{swept.note}`"]
    for title, entries in sections:
        lines.append("")
        if entries:
            lines.append(f"{title} ({len(entries)}):")
            lines += [f"  {entry}" for entry in entries]
        else:
            lines.append(f"{title}: none")
    return "\n".join(lines) + "\n"


def to_agent(swept: Sweep) -> str:
    lines = [
        *(f"linked-from {_at(r.path, r.line)} {_reference_text(r)}" for r in swept.linked_from),
        *(f"mentioned-in {_at(m.path, m.line)} {', '.join(m.names)}" for m in swept.mentioned_in),
        *(
            f"links-to {_resolution(link)} (line {link.line}, {_link_text(link.field, link.raw)})"
            for link in swept.links_to
        ),
        *(f"unsearched {path}" for path in swept.unsearched),
    ]
    return "".join(f"{line}\n" for line in lines)


def _at(path: str, line: int | None) -> str:
    return path if line is None else f"{path}:{line}"


def _reference_text(reference: Reference) -> str:
    text = _link_text(reference.field, reference.raw)
    if len(reference.candidates) > 1:
        text += f" (ambiguous: {', '.join(reference.candidates)})"
    return text


def _link_text(field: str | None, raw: str) -> str:
    return raw if field is None else f"{field}: {raw}"


def _resolution(link: Link) -> str:
    if link.target is not None:
        return link.target
    if link.candidates:
        return "ambiguous: " + ", ".join(link.candidates)
    return "unresolved"


RENDERERS: dict[str, Callable[[Sweep], str]] = {"text": to_text, "json": to_json, "agent": to_agent}
FORMATS = tuple(RENDERERS)
