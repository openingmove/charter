"""`Charter-Allow` trailers: a commit's recorded decision to make an edit that an overridable check (an edit policy
or `protected-region`) forbids."""

import re
import unicodedata
from collections.abc import Collection, Iterable
from dataclasses import dataclass, replace

from charter.diagnostics import Diagnostic, Severity, code_list, suggestion
from charter.profiles import Finding

TRAILER = "Charter-Allow"
UNUSED = "override/unused"
INVALID = "override/invalid"
CODES = frozenset({UNUSED, INVALID})
_FORM = f"`{TRAILER}: <diagnostic-code> <path> — <reason>`"
# An em dash, an en dash or two hyphens, for keyboards without dashes. A single hyphen is too common in file
# names to separate anything.
_SEPARATOR = re.compile(r"(?:^|\s+)(?:—|–|--)(?:\s+|$)")


@dataclass(frozen=True)
class _Trailer:
    value: str
    code: str
    # Each way the text after the code splits into a path and a reason: a path may hold a separator too.
    paths: tuple[str, ...]

    def path_for(self, diagnostics: Iterable[Diagnostic]) -> str | None:
        """The path this trailer names among the paths `diagnostics` of its code have: the longest that fits,
        so a trailer for `a — b.md` never allows `a`."""
        named = {_normal(path): path for path in self.paths}
        fits = [d.path for d in diagnostics if d.code == self.code and _normal(d.path) in named]
        return max(fits, key=len, default=None)


def allow(
    trailers: Iterable[tuple[str, str]],
    findings: Iterable[Finding],
    anchor: str,
    overridable: Collection[str],
    commit: str | None = None,
) -> list[Finding]:
    """`findings` with those a `Charter-Allow` trailer in `trailers` (from `git.trailers`) allows marked allowed
    and naming it, plus a finding, on `anchor`, for each trailer that is malformed or allows nothing. Trailers may
    name only the `overridable` codes, whose findings a human may knowingly overrule. `commit` names the commit
    the trailers come from, when there is more than the one being made."""
    findings = list(findings)
    allowed: set[tuple[str, str]] = set()
    for value in (value for key, value in trailers if key.lower() == TRAILER.lower()):
        trailer = _parse(value, anchor, overridable, commit)
        if isinstance(trailer, Diagnostic):
            findings.append(Finding(trailer))
            continue
        path = trailer.path_for(f.diagnostic for f in findings)
        if path is None or (trailer.code, path) in allowed:
            findings.append(_unused(trailer, path, findings, anchor, commit))
            continue
        allowed.add((trailer.code, path))
        findings = [
            _allowed(f, value) if (f.diagnostic.code, f.diagnostic.path) == (trailer.code, path) else f
            for f in findings
        ]
    return findings


def _parse(value: str, anchor: str, overridable: Collection[str], commit: str | None) -> _Trailer | Diagnostic:
    code, rest = [*value.split(None, 1), "", ""][:2]
    splits = [(rest[: m.start()].strip(), rest[m.end() :].strip()) for m in _SEPARATOR.finditer(rest)]
    paths = tuple(path for path, reason in splits if path and reason)
    if not paths:
        if not rest:
            problem = "names no path"
        elif not splits:
            problem = "has no separator (`—`, `–` or `--`) between its path and its reason"
        elif not splits[0][0]:
            problem = "names no path before its separator"
        else:
            problem = "gives no reason after its separator"
        return _invalid(value, anchor, commit, problem, f"Write it as {_FORM}; the reason is required.")
    if code not in overridable:
        return _invalid(
            value,
            anchor,
            commit,
            f"names `{code}`, which no trailer can allow: trailers allow only {code_list(sorted(overridable))}",
            suggestion(code, overridable, f"Write it as {_FORM}, with the code the diagnostic gives."),
        )
    return _Trailer(value, code, paths)


def _normal(path: str) -> str:
    # The same name can reach charter composed or decomposed (macOS file names, a typed message).
    return unicodedata.normalize("NFC", path)


def _allowed(finding: Finding, value: str) -> Finding:
    diagnostic = finding.diagnostic
    message = f"{diagnostic.message} Allowed by the commit-message trailer `{TRAILER}: {value}`."
    return replace(
        finding, diagnostic=replace(diagnostic, message=message, hint=None), allowed=True, strict_exempt=True
    )


def _named(value: str, commit: str | None) -> str:
    return f"The trailer `{TRAILER}: {value}`" + ("" if commit is None else f" of commit {commit}")


def _invalid(value: str, anchor: str, commit: str | None, problem: str, hint: str) -> Diagnostic:
    message = f"{_named(value, commit)} {problem}, so it allows nothing."
    return Diagnostic(anchor, None, Severity.ERROR, INVALID, message, hint)


def _unused(
    trailer: _Trailer, duplicate: str | None, findings: list[Finding], anchor: str, commit: str | None
) -> Finding:
    if duplicate is not None:
        named = _named(trailer.value, commit)
        message = f"{named} repeats an earlier trailer for `{duplicate}`, so it allows nothing."
        hint = "Remove it: one trailer per file is enough."
    else:
        message = f"{_named(trailer.value, commit)} matches no `{trailer.code}` diagnostic, so it allows nothing."
        paths = [f.diagnostic.path for f in findings if f.diagnostic.code == trailer.code]
        hint = suggestion(trailer.paths[0], paths, "Check its code and path against the diagnostic, or remove it.")
    return Finding(Diagnostic(anchor, None, Severity.WARNING, UNUSED, message, hint), strict_exempt=True)
