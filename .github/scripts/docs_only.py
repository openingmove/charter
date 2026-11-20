"""Decide whether a pull request changes only documentation.

Reads the changed paths from stdin, NUL-separated as `git diff --name-only -z`
writes them. Prints "true" when every path is under docs/ or images/, or is a
Markdown file at the repo root. Prints "false" otherwise, and also for an empty
list, so that an unknown change runs the full test matrix.
"""

import sys


def is_documentation(path: str) -> bool:
    if path.startswith(("docs/", "images/")):
        return True
    return "/" not in path and path.endswith(".md")


def main() -> None:
    paths = [p for p in sys.stdin.buffer.read().decode("utf-8").split("\0") if p]
    print("true" if paths and all(is_documentation(p) for p in paths) else "false")


if __name__ == "__main__":
    main()
