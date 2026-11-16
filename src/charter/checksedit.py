"""Edits to charter.yaml (`checks:` entries, and top-level sections added at the end), written in the file's own
style and leaving everything else as written: comments, quoting, indentation and line endings. Each edit is verified by parsing the result, and refused with
NotEditable when the result would say anything else than intended."""

import codecs
import json
import re
from collections.abc import Callable
from typing import Any

import yaml

from charter import yamlsource


class NotEditable(Exception):
    pass


def add_check(raw: bytes, check_id: str, source: str) -> bytes:
    """`raw` with `checks.<check_id>: {source: <source>}` added."""

    def edit(text: str, root: yaml.MappingNode) -> str:
        key = _yaml_key(check_id)
        found = _item(root, "checks")
        if found is None:
            return _append_block(text, text, "", ["checks:", f"  {key}:", f"    source: {source}"])
        return _insert(text, found[1], f"{key}: {{source: {source}}}", [f"{key}:", f"  source: {source}"])

    def expected(data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "checks": {**data.get("checks", {}), check_id: {"source": source}}}

    return _edited(raw, edit, expected)


def add_sections(raw: bytes, sections: dict[str, str]) -> bytes:
    """`raw` with each top-level section of `sections` (name to flow-style value, such as `{file: AGENTS.md}`) appended
    after everything else. A name `raw` already has must not be given."""

    def edit(text: str, root: yaml.MappingNode) -> str:
        if root.flow_style or any(_item(root, name) for name in sections):
            raise NotEditable
        return _append_block(text, text, "", ["", *(f"{name}: {value}" for name, value in sections.items())])

    def expected(data: dict[str, Any]) -> dict[str, Any]:
        return {**data, **{name: yamlsource.parse(value)[0] for name, value in sections.items()}}

    return _edited(raw, edit, expected)


def set_enabled(raw: bytes, check_id: str, enabled: bool) -> bytes:
    """`raw` with `checks.<check_id>.enabled` set, in place when it is written already."""
    word = "true" if enabled else "false"

    def edit(text: str, root: yaml.MappingNode) -> str:
        entry = _entry(root, check_id)
        found = _item(entry, "enabled")
        if found is None:
            return _insert(text, entry, f"enabled: {word}", [f"enabled: {word}"])
        value = found[1]
        return text[: value.start_mark.index] + word + text[value.end_mark.index :]

    def expected(data: dict[str, Any]) -> dict[str, Any]:
        checks = data["checks"]
        return {**data, "checks": {**checks, check_id: {**checks[check_id], "enabled": enabled}}}

    return _edited(raw, edit, expected)


def remove_check(raw: bytes, check_id: str) -> bytes:
    """`raw` without `checks.<check_id>`, and without `checks:` when that was its only entry."""

    def edit(text: str, root: yaml.MappingNode) -> str:
        checks = _item(root, "checks")[1]
        return _remove(text, root, "checks") if len(checks.value) == 1 else _remove(text, checks, check_id)

    def expected(data: dict[str, Any]) -> dict[str, Any]:
        checks = {name: config for name, config in data["checks"].items() if name != check_id}
        return {**data, "checks": checks} if checks else {k: v for k, v in data.items() if k != "checks"}

    return _edited(raw, edit, expected)


def _edited(
    raw: bytes,
    edit: Callable[[str, yaml.MappingNode], str],
    expected: Callable[[dict[str, Any]], dict[str, Any]],
) -> bytes:
    bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
    text = raw[len(bom) :].decode("utf-8")
    data, root = yamlsource.parse(text)
    edited = edit(text, root)
    try:
        if yamlsource.parse(edited)[0] != expected(data):
            raise NotEditable
    except yamlsource.YamlSyntaxError:
        raise NotEditable from None
    return bom + edited.encode("utf-8")


def _item(mapping: yaml.Node, name: str) -> tuple[yaml.Node, yaml.Node] | None:
    return next(((key, value) for key, value in mapping.value if key.value == name), None)


def _entry(root: yaml.MappingNode, check_id: str) -> yaml.MappingNode:
    return _item(_item(root, "checks")[1], check_id)[1]


def _insert(text: str, mapping: yaml.MappingNode, flow_item: str, block_lines: list[str]) -> str:
    """`text` with an item added at the end of `mapping`: `flow_item` if it is written `{...}`, else `block_lines`
    indented like its other keys."""
    if mapping.flow_style:
        close = mapping.end_mark.index - 1
        before = text[:close].rstrip()
        return before + (", " if mapping.value else "") + flow_item + text[len(before) :]
    indent = " " * mapping.value[0][0].start_mark.column
    head = _trimmed(text[: mapping.end_mark.index])
    return _append_block(text, head, indent, block_lines)


def _append_block(text: str, head: str, indent: str, lines: list[str]) -> str:
    # New lines end like the line they follow, or the file's first line.
    newline = (re.findall(r"\r?\n", head) or re.findall(r"\r?\n", text)[:1] or ["\n"])[-1]
    ending = newline if head and not head.endswith("\n") else ""
    return head + ending + "".join(f"{indent}{line}{newline}" for line in lines) + text[len(head) :]


def _remove(text: str, mapping: yaml.MappingNode, name: str) -> str:
    position = next(index for index, (key, _) in enumerate(mapping.value) if key.value == name)
    key, value = mapping.value[position]
    if mapping.flow_style:
        start, end = key.start_mark.index, value.end_mark.index
        if following := re.match(r"\s*,\s*", text[end:]):
            end += following.end()
        elif preceding := re.search(r",\s*$", text[:start]):
            start = preceding.start()
        return text[:start] + text[end:]
    start = text.rfind("\n", 0, key.start_mark.index) + 1
    if text[start : key.start_mark.index].strip():
        raise NotEditable
    later = mapping.value[position + 1][0] if position + 1 < len(mapping.value) else None
    boundary = text.rfind("\n", 0, later.start_mark.index) + 1 if later is not None else mapping.end_mark.index
    # Blank lines and comments after the item belong to whatever follows.
    end = len(_trimmed(text[:boundary]))
    return text[:start] + text[end:]


def _trimmed(text: str) -> str:
    lines = re.findall(r"[^\n]*\n|[^\n]+", text)
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    return "".join(lines)


def _yaml_key(check_id: str) -> str:
    """`check_id` as a YAML mapping key: plain where YAML reads it back as that text (`yes` would read as true)."""
    try:
        plain = yamlsource.parse(f"{check_id}: x")[0]
    except yamlsource.YamlSyntaxError:
        plain = None
    return check_id if plain == {check_id: "x"} else json.dumps(check_id)
