"""YAML parsing that keeps the node tree, so diagnostics can point at source lines."""

import os
import re
from collections.abc import Sequence
from typing import Any, NamedTuple

import yaml


class YamlSyntaxError(Exception):
    def __init__(self, message: str, line: int | None):
        super().__init__(message)
        self.message = message
        self.line = line


class _Constructs:
    def construct_object(self, node, deep=False):
        # PyYAML's constructors raise ValueError, TypeError, AttributeError and others
        # for values like `2026-13-45` or `!!int one`; pin each to the node that failed.
        try:
            return super().construct_object(node, deep)
        except (yaml.YAMLError, YamlSyntaxError):
            raise
        except Exception as error:
            shown = f" `{node.value}`" if isinstance(node, yaml.ScalarNode) else ""
            raise YamlSyntaxError(f"invalid value{shown} ({error})", node.start_mark.line + 1) from None


class _Loader(_Constructs, yaml.SafeLoader):
    pass


def _make_libyaml_loader() -> type | None:
    if not yaml.__with_libyaml__:
        return None

    class CLoader(_Constructs, yaml.CSafeLoader):
        def construct_object(self, node, deep=False):
            # An empty plain value (`key:`, `- `, a bare `---`) is a node with no text of its own; libyaml
            # places it at the start of the next token, PyYAML at the end of the previous one, so its line
            # differs. Giving up here sends the document to the pure-Python loader.
            if isinstance(node, yaml.ScalarNode) and not node.value and not node.style:
                raise ValueError("empty plain scalar")
            return super().construct_object(node, deep)

    return CLoader


_CLoader = _make_libyaml_loader()

# Set to `python` to force the pure-Python loader (tests, or a suspected libyaml difference).
LOADER_ENV = "CHARTER_YAML_LOADER"

# Text holding any of these always takes the pure-Python path. Each was found by running both loaders over real
# and mutated frontmatter (tests/test_yaml_loaders.py repeats that run). The guard reads the whole text,
# comments and prose included, which only costs speed.
_PURE_ONLY = re.compile(r"[\t\x85\u2028\u2029\ufeff!?]|[|>][-+0-9]*#")
# \t      libyaml accepts a tab where PyYAML rejects it (after a plain value, after a block scalar header).
# \x85    NEL is a line break to libyaml and ordinary text to PyYAML, so the two count lines differently.
# \u2028  LS is likewise a line break to libyaml only.
# \u2029  PS is likewise a line break to libyaml only.
# \ufeff  libyaml skips a BOM at the start of any line, PyYAML only at the start of the text, so
#         "\n\ufeffa: b" has the key `a` in one and the key "\ufeffa" in the other.
# !       a bare `!` tag reads as the string '' in libyaml and as null in PyYAML.
# ?       libyaml accepts a `?` inside a flow collection, and places the empty key or value after a `?` on
#         another line.
# |# >#   libyaml accepts a `#` straight after a block scalar header, PyYAML does not.


def loader_class(text: str) -> type | None:
    """libyaml's loader when it is built in, not switched off and `text` holds nothing the two loaders read
    differently; None when only the pure-Python loader should run."""
    if _CLoader is None or os.environ.get(LOADER_ENV) == "python" or _PURE_ONLY.search(text):
        return None
    return _CLoader


class _Dumper(yaml.SafeDumper):
    # Two fields holding the same object (an `auto: today` date, a shared list) would otherwise be written as an
    # anchor and an alias, and editing one value would silently change the other.
    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump(data: Any, width: float = 80) -> str:
    """YAML for `data`: insertion order, block style, unescaped Unicode, never an anchor or alias. `width` is
    PyYAML's line width; a note's frontmatter passes infinity so values are never folded."""
    return yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=width
    )


def parse(text: str) -> tuple[Any, yaml.Node | None]:
    """Return (data, root node). Raises YamlSyntaxError with a 1-based line."""
    fast = loader_class(text)
    if fast is not None:
        try:
            return _parse(fast, text)
        except Exception:
            # Any failure on the fast path, whatever its type, falls back to the reference loader, which
            # re-raises the real error: libyaml words errors differently and rejects a few things PyYAML
            # accepts, so messages and lines never depend on which loader ran.
            pass
    return _parse(_Loader, text)


# What the scanner counts as one line break, so a character's line agrees with the lines of its neighbours.
_LINE_BREAK = re.compile(r"\r\n|[\r\n\x85\u2028\u2029]")


def _parse(loader_type: type, text: str) -> tuple[Any, yaml.Node | None]:
    try:
        loader = loader_type(text)
    except yaml.reader.ReaderError as error:
        # An unprintable character is rejected while the loader reads the text, before any mark exists.
        line = len(_LINE_BREAK.findall(text, 0, error.position)) + 1
        raise YamlSyntaxError(f"unacceptable character #x{error.character:04x}: {error.reason}", line) from None
    try:
        node = loader.get_single_node()
        data = loader.construct_document(node) if node is not None else None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        problem = getattr(error, "problem", None) or str(error)
        raise YamlSyntaxError(problem, mark.line + 1 if mark else None) from None
    finally:
        loader.dispose()
    return data, node


def line_of(node: yaml.Node | None, location: Sequence[str | int]) -> int | None:
    """1-based line of the deepest node along `location` (mapping keys and list indices)."""
    line = node.start_mark.line + 1 if node is not None else None
    for step in location:
        if isinstance(node, yaml.MappingNode):
            pair = _pair(node, step)
            if pair is None:
                break
            # A key's line reads better than its value's: block values start on the next line.
            line = pair[0].start_mark.line + 1
            node = pair[1]
        elif isinstance(node, yaml.SequenceNode) and isinstance(step, int) and step < len(node.value):
            node = node.value[step]
            line = node.start_mark.line + 1
        else:
            break
    return line


_STRING_TAG = "tag:yaml.org,2002:str"
_READ_AS = {
    "int": "an integer",
    "float": "a number",
    "bool": "true or false",
    "null": "null",
    "timestamp": "a date",
}


def _pair(node: yaml.MappingNode, step: object) -> tuple[yaml.Node, yaml.Node] | None:
    return next(((k, v) for k, v in node.value if k.value == step), None)


class NonTextKey(NamedTuple):
    # As written in the source; `null` for an empty key.
    text: str
    read_as: str
    line: int


def non_text_keys(node: yaml.Node | None, location: Sequence[str]) -> list[NonTextKey]:
    """Each key of the mapping at `location` that YAML does not read as text (`1`, `yes`, `on`, `2026-01-01`).
    Empty when `location` is not a mapping."""
    for step in location:
        pair = _pair(node, step) if isinstance(node, yaml.MappingNode) else None
        if pair is None:
            return []
        node = pair[1]
    if not isinstance(node, yaml.MappingNode):
        return []
    return [
        NonTextKey(key.value or "null", _READ_AS.get(key.tag.rpartition(":")[2], "not text"), key.start_mark.line + 1)
        for key, _ in node.value
        if isinstance(key, yaml.ScalarNode) and key.tag != _STRING_TAG
    ]


def key_lines(node: yaml.Node | None) -> dict[str, int]:
    """1-based line of each top-level key of a mapping node."""
    if not isinstance(node, yaml.MappingNode):
        return {}
    return {
        key.value: key.start_mark.line + 1
        for key, _ in node.value
        if isinstance(key, yaml.ScalarNode)
    }
