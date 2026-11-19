"""Every diagnostic code charter can emit is named in the user manual, `docs/guide/`.

This reads source files rather than driving the CLI: no argv run can show which codes exist but never fired, the
same reason the drift test on action/run.py reads source.
"""

import ast
import re
from pathlib import Path

from charter.validate import BUILTIN_CHECKS

ROOT = Path(__file__).resolve().parent.parent
# A code is `namespace/name`; the pattern is deliberately strict so ordinary strings do not match.
CODE = re.compile(r"[a-z][a-z0-9-]*/[a-z][a-z0-9-]+")
# Constants shaped like a code that are not one (media types and the like). The scan stays automatic so a new
# namespace is never missed; add a string here only when it is not a diagnostic code.
_NOT_CODES: frozenset[str] = frozenset()
SOURCES = [*(ROOT / "src" / "charter").rglob("*.py"), ROOT / "action" / "run.py"]


def _literal_codes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and CODE.fullmatch(node.value)
        and node.value not in _NOT_CODES
    }


def emitted_codes() -> set[str]:
    # Literals catch codes raised outside checks (`usage/...`, `new/...`); a check's `codes` also covers the ones
    # it builds from parts, such as `paths/read-only`.
    literals = set().union(*map(_literal_codes, SOURCES))
    return literals | {code for check in BUILTIN_CHECKS for code in check.codes}


def _mentioned(code: str, text: str) -> bool:
    return re.search(rf"(?<![\w/-]){re.escape(code)}(?![\w-])", text) is not None


def test_the_scan_finds_codes_of_every_kind():
    codes = emitted_codes()

    assert {"docs/stale", "usage/no-rulebook", "paths/read-only", "schema/required", "plugin/fetch-failed"} <= codes
    assert len(codes) > 90


def test_every_emitted_code_is_in_the_manual():
    manual = "\n".join(page.read_text(encoding="utf-8") for page in sorted((ROOT / "docs" / "guide").glob("*.md")))

    missing = sorted(code for code in emitted_codes() if not _mentioned(code, manual))

    assert not missing, (
        f"Not named in docs/guide/: {missing}. Add each to the manual (the diagnostic-codes page lists the codes "
        "no other page explains), or, if a string is not a diagnostic code, add it to _NOT_CODES in this test."
    )
