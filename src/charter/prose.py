"""A note body with the parts where Markdown syntax is literal blanked, keeping every line so line numbers stay put."""

import re

_CODE_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
# HTML comments (unclosed ones run to the end), and code spans, which may cross line breaks but not a blank line.
_CODE_SPAN = r"(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)"
_LITERAL = re.compile(rf"<!--.*?(?:-->|\Z)|{_CODE_SPAN}", re.DOTALL)
_CODE_SPANS = re.compile(_CODE_SPAN, re.DOTALL)


def blank_code_blocks(lines: list[str]) -> list[str]:
    """The lines with fenced and indented code blocks blanked, so line numbers stay put."""
    blanked = []
    fence = None
    in_code = False
    # An indented line continues a list item rather than starting code.
    in_list = False
    previous_blank = True
    for line in lines:
        marker = _CODE_FENCE.match(line)
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            blanked.append("")
            continue
        if not line.strip():
            previous_blank = True
            blanked.append(line)
            continue
        indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
        if indent >= 4 and (in_code or (previous_blank and not in_list)):
            in_code = True
            blanked.append("")
        elif marker:
            fence, in_code = marker.group(1), False
            blanked.append("")
        else:
            if indent < 4:
                in_list = bool(LIST_ITEM.match(line)) or (in_list and not previous_blank)
            in_code = False
            blanked.append(line)
        previous_blank = False
    return blanked



def split_literals(code_free: list[str]) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    """Two views of lines from `blank_code_blocks`, and their HTML comments.

    Prose has code spans and comments blanked: where links and tags are found. Uncommented has comments
    cut but their line breaks kept, as a reader sees the text. Each comment comes with the index of its first line.
    """
    text = "\n".join(code_free)
    prose, uncommented, comments = [], [], []
    end = 0
    for match in _LITERAL.finditer(text):
        before, literal = text[end : match.start()], match.group(0)
        prose += [before, _spaces(literal)]
        if literal.startswith("<!--"):
            comments.append((text.count("\n", 0, match.start()), literal[4:].removesuffix("-->")))
            uncommented += [before, "\n" * literal.count("\n")]
        else:
            uncommented += [before, literal]
        end = match.end()
    return "".join([*prose, text[end:]]).split("\n"), "".join([*uncommented, text[end:]]).split("\n"), comments


def _spaces(text: str) -> str:
    """`text` as spaces, keeping line breaks, so offsets and line numbers stay put."""
    return re.sub(r"[^\n]", " ", text)


def blank_code_spans(text: str) -> str:
    """`text` with each code span (not HTML comments) replaced by spaces, so its offsets stay put."""
    return _CODE_SPANS.sub(lambda match: _spaces(match.group(0)), text)


def blank_code(text: str) -> str:
    """`text` with fenced and indented code blocks and code spans replaced by spaces, offsets kept."""
    lines = text.split("\n")
    # `blank_code_blocks` empties a blanked line, whatever its length, so a whitespace-only one needs spaces too.
    kept = [blanked or _spaces(line) for line, blanked in zip(lines, blank_code_blocks(lines))]
    return blank_code_spans("\n".join(kept))
