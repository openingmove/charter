"""Path policies (`paths:` in charter.yaml): glob → settings, resolved per key.

Each key takes its value from the most specific matching glob that sets it, so a
narrower glob overrides only the keys it names. Globs are relative to the KB root
and match folder by folder (see `globs`). `\\` is read as a folder separator so a
contract behaves the same whichever platform it was written on.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from charter.diagnostics import code_list
from charter.globs import WILDCARDS, compile_glob, segments


@dataclass(frozen=True)
class PolicyKey:
    schema: dict[str, Any]
    # What a value of the key means, in words.
    meaning: Callable[[Any], str]


READ_ONLY, CREATE_ONLY = "read-only", "create-only"
EDIT_MEANINGS = {
    READ_ONLY: "no files may be added, changed or deleted",
    CREATE_ONLY: "new files may be added; existing files may not change or be deleted",
}

# Every key a `paths:` entry may set: the contract schema and `charter describe` both read this.
POLICY_KEYS: dict[str, PolicyKey] = {
    "ignore": PolicyKey(
        {"type": "boolean"}, lambda value: "ignored: not notes, never validated" if value else "not ignored"
    ),
    "kinds": PolicyKey(
        {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
        lambda kinds: f"only kinds {code_list(kinds)}",
    ),
    "untyped": PolicyKey({"const": "allow"}, lambda _: "files need no kind"),
    "links": PolicyKey({"const": "skip"}, lambda _: "links are not checked"),
    "edit": PolicyKey({"enum": list(EDIT_MEANINGS)}, lambda policy: f"{policy}: {EDIT_MEANINGS[policy]}"),
    "sweep": PolicyKey(
        {"type": "boolean"},
        lambda value: f"{'included in' if value else 'left out of'} `charter sweep` results",
    ),
}


@dataclass(frozen=True)
class Setting:
    value: Any
    glob: str


class PathPolicies:
    def __init__(self, rules: Mapping[str, Mapping[str, Any]]):
        # As declared, in declaration order: what the contract says, for describing it.
        self.declared = {glob: dict(settings) for glob, settings in rules.items()}
        # Stable sort: among equally specific globs the first declared wins.
        ranked = sorted(rules.items(), key=lambda rule: -_specificity(rule[0]))
        self._rules = [(compile_glob(_folders(glob)), glob, settings) for glob, settings in ranked]

    def declares(self, key: str) -> bool:
        return any(key in settings for settings in self.declared.values())

    def resolve(self, path: str) -> dict[str, Setting]:
        """The effective settings for `path`, a POSIX path relative to the KB root."""
        resolved: dict[str, Setting] = {}
        for pattern, glob, settings in self._rules:
            if pattern.fullmatch(path):
                for key, value in settings.items():
                    resolved.setdefault(key, Setting(value, glob))
        return resolved


def _folders(glob: str) -> str:
    return glob.replace("\\", "/")


def _specificity(glob: str) -> int:
    return sum(1 for segment in segments(_folders(glob)) for char in segment if char not in WILDCARDS)
