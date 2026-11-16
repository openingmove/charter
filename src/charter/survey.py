"""`charter survey`: a factual, read-only report of what a folder of Markdown files holds.

It runs before any contract exists, so it loads none and never searches for one. `survey(folder)` returns plain
data that serialises to the stable `charter-survey/1` JSON, and nothing in it depends on the machine (POSIX paths
relative to the folder, sorted keys and lists, no timestamps), so goldens match on every OS. The rules it applies
are documented in the README.
"""

import datetime
import json
import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from charter.body import parse_body
from charter.index import note_head
from charter.links import STYLES, body_links
from charter.tree import decode

FORMAT_ID = "charter-survey/1"
FORMATS = ("text", "json")
VALUE_CAP = 20
# Files named for each value, so a value that looks like a typo can be found.
EXAMPLE_FILES = 3
# Version-control and editor state are not content.
IGNORED_DIRECTORIES = frozenset({".git", ".obsidian"})
AGENT_FILE_NAMES = frozenset({"agents.md", "claude.md", "gemini.md"})
TITLE_PLACEHOLDER = "{{title}}"

_WORDS = re.compile(r"[A-Za-z](?:[A-Za-z _'-]*[A-Za-z])?")
_RULEBOOK_WORDS = re.compile(r"\b(?:rulebook|conventions?|style[ _-]?guide|rules|charter)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Note:
    path: str
    folder: str
    name: str
    has_frontmatter: bool
    frontmatter_error: str | None
    # Why the file could not be read; None when it was.
    problem: str | None
    # Frontmatter by field name, as parsed.
    values: dict[str, Any]
    # (level, text) in file order.
    headings: tuple[tuple[int, str], ...]
    links: dict[str, int]
    agent_file: bool
    rulebook: str | None


def survey(folder: Path) -> dict[str, Any]:
    """The survey of `folder`'s Markdown files. `folder` must be an existing directory."""
    notes = [_read(folder, path) for path in _markdown_files(folder)]
    return {
        "format": FORMAT_ID,
        "totals": {
            "files": len(notes),
            "folders": len({note.folder for note in notes}),
            "with_frontmatter": sum(note.has_frontmatter for note in notes),
        },
        "files": [_entry(note) for note in notes],
        "folders": _folders(notes),
        "fields": _fields(notes),
        "links": _link_styles(notes),
        "agent_files": [note.path for note in notes if note.agent_file],
        "rulebooks": [{"path": note.path, "reason": note.rulebook} for note in notes if note.rulebook is not None],
    }


def _markdown_files(folder: Path) -> list[str]:
    root = folder.resolve()
    found = []
    # os.walk does not follow symlinked directories, which keeps a link back up the tree from looping.
    for directory, subdirectories, filenames in os.walk(folder):
        subdirectories[:] = [name for name in subdirectories if name not in IGNORED_DIRECTORIES]
        for name in filenames:
            file = Path(directory, name)
            if not name.endswith(".md") or not file.is_file() or not file.resolve().is_relative_to(root):
                continue
            found.append(file.relative_to(folder).as_posix())
    return sorted(found)


def _read(folder: Path, path: str) -> _Note:
    directory, _, name = path.rpartition("/")
    agent_file = name.lower() in AGENT_FILE_NAMES
    try:
        text = decode((folder / path).read_bytes())
    except UnicodeDecodeError:
        return _unread(path, directory, name, agent_file, "not valid UTF-8")
    except OSError:
        return _unread(path, directory, name, agent_file, "could not be read")
    lines = text.split("\n")
    head = note_head(lines)
    body = parse_body(lines[head.body_start :], head.body_start + 1)
    headings = tuple((heading.level, heading.text) for heading in body.headings)
    links: Counter[str] = Counter()
    for link in body_links(body.prose, 1, STYLES):
        links[link.style] += 1
    for value in _strings(head.frontmatter.values()):
        for link in body_links([value], 1, STYLES):
            links[link.style] += 1
    return _Note(
        path,
        directory or ".",
        name,
        head.has_frontmatter,
        head.error,
        None,
        {str(field): value for field, value in head.frontmatter.items()},
        headings,
        dict(links),
        agent_file,
        None if agent_file else _rulebook_reason(name, headings),
    )


def _unread(path: str, directory: str, name: str, agent_file: bool, problem: str) -> _Note:
    rulebook = None if agent_file else _rulebook_reason(name, ())
    return _Note(path, directory or ".", name, False, None, problem, {}, (), {}, agent_file, rulebook)


def _entry(note: _Note) -> dict[str, Any]:
    return {
        "path": note.path,
        "folder": note.folder,
        "has_frontmatter": note.has_frontmatter,
        "frontmatter_error": note.frontmatter_error,
        "problem": note.problem,
        "fields": {field: _type_of(value) for field, value in sorted(note.values.items())},
    }


def _strings(values: Any) -> list[str]:
    found = []
    for value in values:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, list):
            found += _strings(value)
        elif isinstance(value, dict):
            found += _strings(value.values())
    return found


def _type_of(value: Any) -> str:
    # bool is checked before numbers: in Python it is an int.
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, datetime.date):
        return "date"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return "null"


def _rulebook_reason(name: str, headings: Sequence[tuple[int, str]]) -> str | None:
    if _RULEBOOK_WORDS.search(name.removesuffix(".md").replace("_", " ").replace("-", " ")):
        return "filename"
    if headings and _RULEBOOK_WORDS.search(headings[0][1]):
        return "heading"
    return None


def _filename_shape(name: str) -> str:
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    # Words are shaped and digits replaced in one pass, so an `N` never reads as a word.
    parts = []
    position = 0
    for found in _WORDS.finditer(stem):
        parts.append(re.sub(r"\d", "N", stem[position : found.start()]))
        parts.append(_word_shape(found.group(0)))
        position = found.end()
    parts.append(re.sub(r"\d", "N", stem[position:]))
    shaped = "".join(parts)
    return f"{shaped}.{extension}" if dot else shaped


def _word_shape(words: str) -> str:
    if re.fullmatch(r"[a-z]+", words):
        return "word"
    if re.fullmatch(r"[a-z]+(?:-[a-z]+)+", words):
        return "kebab-title"
    if re.fullmatch(r"[a-z]+(?:_[a-z]+)+", words):
        return "snake_title"
    return "Title"


def _folders(notes: list[_Note]) -> list[dict[str, Any]]:
    by_folder: dict[str, list[_Note]] = {}
    for note in notes:
        by_folder.setdefault(note.folder, []).append(note)
    folders = []
    for folder in sorted(by_folder, key=lambda name: ("" if name == "." else name)):
        members = by_folder[folder]
        shapes = Counter(_filename_shape(note.name) for note in members)
        carrying = Counter(field for note in members for field in note.values)
        outlines = Counter(_outline(note.headings) for note in members if note.headings)
        outline = None
        if outlines:
            best = min(outlines, key=lambda sequence: (-outlines[sequence], sequence))
            outline = {
                "headings": [f"{'#' * level} {text}" for level, text in best],
                "files": outlines[best],
            }
        folders.append({
            "folder": folder,
            "files": len(members),
            "filename_shapes": dict(sorted(shapes.items())),
            "fields": [{"name": name, "files": carrying[name]} for name in sorted(carrying)],
            "outline": outline,
        })
    return folders


def _outline(headings: Sequence[tuple[int, str]]) -> tuple[tuple[int, str], ...]:
    """A note's headings, with its title (a leading level-1 heading) as a placeholder: titles differ per note."""
    (level, text), *rest = headings
    return ((level, TITLE_PLACEHOLDER) if level == 1 else (level, text), *rest)


def _fields(notes: list[_Note]) -> dict[str, Any]:
    carrying: Counter[str] = Counter()
    types: dict[str, Counter[str]] = {}
    values: dict[str, Counter[tuple[str, str]]] = {}
    examples: dict[tuple[str, tuple[str, str]], set[str]] = {}
    shown: dict[tuple[str, str], Any] = {}
    for note in notes:
        for name, value in note.values.items():
            carrying[name] += 1
            types.setdefault(name, Counter())[_type_of(value)] += 1
            counted = values.setdefault(name, Counter())
            for scalar in value if isinstance(value, list) else [value]:
                if not isinstance(scalar, dict | list):
                    identity = _scalar(scalar)
                    counted[identity] += 1
                    shown[identity] = _json_value(scalar)
                    examples.setdefault((name, identity), set()).add(note.path)
    fields = {}
    for name in sorted(carrying):
        ranked = sorted(values[name].items(), key=lambda item: (-item[1], item[0]))
        fields[name] = {
            "files": carrying[name],
            "types": dict(sorted(types[name].items())),
            "values": [
                {
                    "value": shown[identity],
                    "count": count,
                    "files": sorted(examples[name, identity])[:EXAMPLE_FILES],
                }
                for identity, count in ranked[:VALUE_CAP]
            ],
            "distinct": len(ranked),
            "truncated": len(ranked) > VALUE_CAP,
        }
    return fields


def _scalar(value: Any) -> tuple[str, str]:
    """A value's identity, so `1` and `"1"` stay apart: its type, and its text."""
    kind = _type_of(value)
    if kind == "null":
        return kind, ""
    if kind == "boolean":
        return kind, "true" if value else "false"
    if kind == "date":
        return kind, value.isoformat()
    return kind, repr(value) if kind == "number" else value


def _json_value(value: Any) -> Any:
    """A value as JSON holds it: dates as ISO text, and NaN and infinities (not JSON) as text."""
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _link_styles(notes: list[_Note]) -> dict[str, Any]:
    return {
        style: {
            "links": sum(note.links.get(style, 0) for note in notes),
            "files": sum(1 for note in notes if note.links.get(style)),
        }
        for style in sorted(STYLES)
    }


def to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def to_text(result: dict[str, Any]) -> str:
    totals = result["totals"]
    lines = [
        f"Surveyed {_count(totals['files'], 'Markdown file')} in {_count(totals['folders'], 'folder')}; "
        f"{totals['with_frontmatter']} with frontmatter.",
    ]
    if result["folders"]:
        lines += ["", "Folders:"]
    for folder in result["folders"]:
        shapes = ", ".join(f"{shape} x{count}" for shape, count in folder["filename_shapes"].items())
        lines.append(f"  {folder['folder']}: {_count(folder['files'], 'file')} ({shapes})")
        if folder["outline"]:
            outline = " / ".join(folder["outline"]["headings"])
            lines.append(f"    common outline ({_count(folder['outline']['files'], 'file')}): {outline}")
    if result["fields"]:
        lines += ["", "Fields:"]
    for name, field in result["fields"].items():
        types = ", ".join(f"{kind} x{count}" for kind, count in field["types"].items())
        lines.append(f"  {name}: in {_count(field['files'], 'file')}, {types}")
        shown = ", ".join(f"{_text_value(item['value'])} x{item['count']}" for item in field["values"])
        more = f", and {field['distinct'] - len(field['values'])} more" if field["truncated"] else ""
        if shown:
            lines.append(f"    values ({field['distinct']} distinct): {shown}{more}")
    problems = [file for file in result["files"] if file["frontmatter_error"] or file["problem"]]
    if problems:
        lines += ["", "Files that could not be read in full:"]
        lines += [f"  {file['path']}: {file['frontmatter_error'] or file['problem']}" for file in problems]
    lines += ["", "Links:"]
    lines += [
        f"  {style}: {_count(counts['links'], 'link')} in {_count(counts['files'], 'file')}"
        for style, counts in result["links"].items()
    ]
    lines += ["", "Agent files:"]
    lines += [f"  {path}" for path in result["agent_files"]] or ["  none"]
    lines += ["", "Rulebook-like documents:"]
    lines += [f"  {item['path']} (by {item['reason']})" for item in result["rulebooks"]] or ["  none"]
    return "\n".join(lines) + "\n"


def _text_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
