"""The libyaml loader and the pure-Python loader give the same data, node lines and errors.

`yamlsource.parse` tries libyaml's loader first and falls back to PyYAML's pure-Python one, so the two runs
below must agree on every input: the C path on a machine with libyaml, and the forced fallback everywhere.
"""

import os
import random
import re
from pathlib import Path

import pytest
import yaml

from charter import yamlsource

HERE = Path(__file__).parent
needs_libyaml = pytest.mark.skipif(
    not yaml.__with_libyaml__, reason="this PyYAML was built without libyaml, so there is no C path to compare"
)

HAND_WRITTEN = {
    "plain": "kind: note\ntitle: Hello\ntags: [a, b]\n",
    "tab": "a:\tb\n",
    "tab-indent": "a:\n\t- b\n",
    "trailing-tab": "a: b\t",
    "crlf": "a: b\r\nc: d\r\n",
    "bom-inside": "\ufeffa: 1\n",
    "bom-after-blank-line": "\n\n\ufeffa: b\n",
    "bom-after-content": "x: 1\n\ufeffa: b\n",
    "bom-doubled": "\ufeff\ufeffa: b\n",
    "bom-only-twice": "\ufeff\ufeff",
    "bom-start-of-plain-scalar-line": "\n\ufeffab",
    "bom-in-block-scalar": "a: |\n - @x\n  y\n\ufeff",
    "bom-in-block-scalar-body": "a: |\n  x\n\ufeffy\n",
    "bom-at-end": "a: b\n\ufeff",
    "unicode": "k: \u00e9\n\u00fc: \u65e5\u672c\n",
    "emoji": "a: \U0001f600\n",
    "flow": "a: [1, 2,\n  3]\nb: {x: 1, y: [2]}\n",
    "flow-colon": "tags: [voyage/south, weather:]\n",
    "flow-question": "a: [1, 2,\n  3?]\n",
    "literal": "a: |\n  x\n  y\nb: >-\n  z\n",
    "literal-comment": "a: |# not a comment\n  x\n",
    "keep": "a: |+\n  x\n\n\nb: 1\n",
    "anchor": "a: &x 1\nb: *x\n",
    "merge": "base: &b {x: 1}\nd:\n  <<: *b\n  y: 2\n",
    "merge-list": "x: &a {p: 1}\ny: &b {q: 2}\nz:\n  <<: [*a, *b]\n",
    "merge-scalar": "z:\n  <<: 5\n",
    "undefined-alias": "a: *nope\n",
    "duplicate-key": "a: 1\na: 2\n",
    "empty-values": "a:\nb: ~\nc: ''\nd:\n",
    "empty-item": "a:\n  -\n  - x\n",
    "empty-key": "? \n: x\n",
    "explicit-key": "? a\n: b\n",
    "bare-tag": "a: !\nb: !x y\n",
    "tag-str": "a: !!str 5\nb: !!int 7\n",
    "bad-tag-value": "a: !!int one\n",
    "unknown-tag": "a: !custom x\n",
    "python-tag": "a: !!python/object:os.system x\n",
    "dates": "a: 2026-01-05\nb: 2026-01-05 10:20:30\nc: 2002-12-14\n",
    "bad-date": "c: 2026-13-45\n",
    "numbers": "a: 1_000\nb: 0o17\nc: 017\nd: 0x1f\ne: 1:30\nf: 1e3\ng: .inf\nh: 1.5e+3\ni: 190:20:30.15\n",
    "bool-words": "a: on\nb: yes\nc: No\nd: off\ne: y\nf: n\n",
    "non-text-keys": "1: a\ntrue: b\nnull: c\n2026-01-01: d\n",
    "nel": "a: x\x85y\n",
    "line-separator": "a: x\u2028y\n",
    "paragraph-separator": "a: x\u2029y\n",
    "nbsp": "a: \u00a0b\n",
    "unterminated-quote": "a: 'open\n",
    "unterminated-flow": "a: [\n",
    "mapping-in-mapping": "a: b: c\n",
    "sequence-and-mapping": "- a\nb: c\n",
    "bad-indent": "a:\n   b: 1\n  c: 2\n",
    "control-char": "a: \x01\n",
    "reserved-indicator": "a: @x\nb: `y\n",
    "bad-escape": 'a: "bad \\q"\n',
    "bell": "a: x\x07y\n",
    "nul-on-line-3": "a: 1\nb: 2\nc: \x00\n",
    "del": "a: \x7f\n",
    "c1-control": "a: 1\nb: \x9f\n",
    "noncharacter": "a: " + chr(0xFFFE) + "\n",
    "control-after-crlf": "a: 1\r\nb: \x1b\r\n",
    "directive": "%YAML 1.1\n---\na: 1\n",
    "two-documents": "---\na: 1\n---\nb: 2\n",
    "comment-only": "# nothing here\n",
    "empty": "",
    "blank": "   \n",
    "long-line": "a: " + "x" * 5000 + "\n",
    "long-flow": "a: [" + ",".join(["1"] * 3000) + "]\n",
    "long-key": "k" * 1500 + ": 1\n",
    "multi-line-quoted": 'a: "multi\n  line"\nb: plain\n  continued\n\n  para\n',
}


def _corpus_files() -> dict[str, str]:
    """Every frontmatter block and YAML file in the fixtures, examples and skills."""
    root = HERE.parent
    found: dict[str, str] = {}
    for folder in (HERE / "fixtures", root / "examples", root / "skills"):
        for path in sorted(folder.rglob("*")):
            if path.suffix not in (".md", ".yaml", ".yml") or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            if path.suffix == ".md":
                block = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
                text = block.group(1) if block else ""
            if text:
                found[str(path.relative_to(root))] = text
    return found


_PIECES = ["a", "b", "key", ": ", ":", "- ", "\n", "\n  ", " ", "[", "]", "{", "}", ",", "#", "&x ", "*x", "'", '"', "|", ">",
           "!", "?", "%", "@", "`", "\t", "\r\n", "1", "2026-01-01", "on", "yes", "~", "<<: ", "\u00e9", "\u0085", "\u2028", "\u2029", "\ufeff", ".", "=", "-",
           "\x07", "\x7f", "\x9f", "\ufffe"]


def _generated(count: int, seed: int = 1) -> dict[str, str]:
    """Random token soup plus real frontmatter with a few characters mutated, so both malformed and valid text
    reach the loaders."""
    rng = random.Random(seed)
    real = list(_corpus_files().values()) + list(HAND_WRITTEN.values())
    cases: dict[str, str] = {}
    for index in range(count):
        if index % 2:
            text = "".join(rng.choice(_PIECES) for _ in range(rng.randint(1, 14)))
        else:
            text = rng.choice(real)
            for _ in range(rng.randint(1, 2)):
                at = rng.randrange(len(text) + 1)
                text = text[:at] + rng.choice(_PIECES) + text[at + rng.randint(0, 3):]
        cases[f"generated-{index}"] = text
    return cases


def _outcome(text: str) -> tuple:
    """What a caller can observe of `parse`: the data, each node's kind, tag, text and line, or the failure."""
    try:
        data, root = yamlsource.parse(text)
    except yamlsource.YamlSyntaxError as error:
        return ("syntax", error.message, error.line)
    except yaml.YAMLError as error:
        return ("yaml", type(error).__name__, str(error))
    nodes: list[tuple] = []

    seen: set[int] = set()

    def walk(node: yaml.Node) -> None:
        if id(node) in seen:  # an alias to its own ancestor makes the tree a loop
            return
        seen.add(id(node))
        nodes.append((type(node).__name__, node.tag, node.start_mark.line, getattr(node, "value", None)
                      if isinstance(node, yaml.ScalarNode) else None))
        if isinstance(node, yaml.SequenceNode):
            for child in node.value:
                walk(child)
        elif isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                walk(key)
                walk(value)

    if root is not None:
        walk(root)
    return ("ok", repr(data), nodes)


def _pure(monkeypatch: pytest.MonkeyPatch, text: str) -> tuple:
    monkeypatch.setenv(yamlsource.LOADER_ENV, "python")
    return _outcome(text)


def _selected(monkeypatch: pytest.MonkeyPatch, text: str) -> tuple:
    monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)
    return _outcome(text)


def test_forced_fallback_runs_the_pure_python_loader(monkeypatch):
    monkeypatch.setenv(yamlsource.LOADER_ENV, "python")
    assert yamlsource.loader_class("a: 1\n") is None


@needs_libyaml
def test_libyaml_loader_is_chosen_for_plain_text(monkeypatch):
    monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)
    assert issubclass(yamlsource.loader_class("kind: note\ntags: [a, b]\n"), yaml.CSafeLoader)


@needs_libyaml
@pytest.mark.parametrize(
    "text",
    ["a:\tb\n", "a: !\n", "a: Why?\n", "a: |#\n  x\n", "a: x\x85y\n", "a: x\u2028y\n", "a: x\u2029y\n", "\n\ufeffa: b\n"],
)
def test_text_the_loaders_read_differently_uses_the_pure_python_loader(monkeypatch, text):
    monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)
    assert yamlsource.loader_class(text) is None


@pytest.mark.parametrize("name", HAND_WRITTEN)
def test_hand_written_cases_agree(monkeypatch, name):
    if not yaml.__with_libyaml__:
        pytest.skip("this PyYAML was built without libyaml, so there is no C path to compare")
    text = HAND_WRITTEN[name]
    assert _selected(monkeypatch, text) == _pure(monkeypatch, text)


@needs_libyaml
def test_fixture_and_example_frontmatter_agree(monkeypatch):
    corpus = _corpus_files()
    assert len(corpus) > 50
    for name, text in corpus.items():
        assert _selected(monkeypatch, text) == _pure(monkeypatch, text), name


@needs_libyaml
def test_generated_text_agrees(monkeypatch):
    for name, text in _generated(int(os.environ.get("CHARTER_YAML_FUZZ", "4000"))).items():
        assert _selected(monkeypatch, text) == _pure(monkeypatch, text), (name, text)


@pytest.mark.parametrize(
    "text, message, line",
    [
        ("a: [\n", "expected the node content, but found '<stream end>'", 2),
        ("a: 'open\n", "found unexpected end of stream", 2),
        ("a: 1\nb: *nope\n", "found undefined alias 'nope'", 2),
        ("a: 1\nb: !!int one\n", "invalid value `one` (invalid literal for int() with base 10: 'one')", 2),
    ],
)
def test_errors_keep_the_pure_python_message_and_line(monkeypatch, text, message, line):
    monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)
    with pytest.raises(yamlsource.YamlSyntaxError) as raised:
        yamlsource.parse(text)
    assert (raised.value.message, raised.value.line) == (message, line)


def test_diagnostics_are_the_same_through_the_cli(monkeypatch, charter, make_kb):
    """A malformed contract reports one line and message whichever loader ran."""
    kb = make_kb({"charter.yaml": "charter: 1\nroot: docs\nkinds: [\n", "docs/.keep": ""})
    runs = []
    for forced in ("python", None):
        if forced:
            monkeypatch.setenv(yamlsource.LOADER_ENV, forced)
        else:
            monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)
        runs.append(charter("validate", "--format", "json", cwd=kb))
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].exit_code == runs[1].exit_code != 0


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\ufeff"])
def test_pure_only_pattern_matches_the_invisible_characters(char):
    assert yamlsource._PURE_ONLY.search(f"a: x{char}y\n")


def test_yamlsource_spells_invisible_characters_as_escapes():
    # Invisible literals in the source are easy to lose in an editor and unreadable in review.
    source = Path(yamlsource.__file__).read_text(encoding="utf-8")
    assert not {"\u2028", "\u2029", "\ufeff"} & set(source)
