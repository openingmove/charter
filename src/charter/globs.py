"""Globs over `/`-separated names: `*` and `?` stay within one level, `**` spans any number (including none)."""

import re

WILDCARDS = "*?"


def segments(glob: str) -> list[str]:
    return [segment for segment in glob.split("/") if segment]


def compile_glob(glob: str) -> re.Pattern[str]:
    parts = segments(glob)
    translated = []
    for position, segment in enumerate(parts):
        last = position == len(parts) - 1
        if segment == "**":
            translated.append(".*" if last else "(?:.*/)?")
            continue
        text = "".join("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char) for char in segment)
        translated.append(text if last else text + "/")
    # DOTALL: `.` in `**` must also cross a line feed, which is a legal file-name character.
    return re.compile("".join(translated), re.DOTALL)
