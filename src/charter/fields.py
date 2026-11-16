"""Field declarations under a kind's `fields:`: their schema, their consistency rules and their meaning."""

import datetime
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from charter.diagnostics import Diagnostic, code_list, suggestion, yaml_text
from charter.fieldtypes import FIELD_TYPES

# What `charter new` fills an `auto` field with: the day it runs, or the next free value of a unique int.
TODAY = "today"
NEXT = "next"

# Condition values are checked in `spec_problems`, not here: a YAML date is a valid value but not a JSON type.
_CONDITIONS_SCHEMA = {"type": "object", "minProperties": 1}

FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"enum": list(FIELD_TYPES)},
        "of": {"enum": [name for name in FIELD_TYPES if name != "list"] + ["enum"]},
        "enum": {"type": "string", "minLength": 1},
        "values": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
        "required": {"type": "boolean"},
        "required_when": _CONDITIONS_SCHEMA,
        "allowed_when": _CONDITIONS_SCHEMA,
        "range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "pattern": {"type": "string", "minLength": 1},
        "to": {
            "type": ["string", "array"],
            "items": {"type": "string"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "matches_filename": {"type": "boolean"},
        "unique": {"type": "boolean"},
        # Checked against the field's type in `spec_problems`, like condition values.
        "default": {},
        "auto": {"enum": [TODAY, NEXT]},
        "description": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

VOCABULARIES_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
}

# Reports a contract problem at a location (a key path into charter.yaml).
Invalid = Callable[[Sequence[str | int], str, str | None], Diagnostic]


@dataclass(frozen=True)
class Condition:
    field: str
    values: tuple[Any, ...]
    # A condition on a list field holds when the list contains one of the values.
    on_list: bool = False

    def holds(self, frontmatter: dict[str, Any]) -> bool:
        actual = frontmatter.get(self.field)
        candidates = actual if self.on_list and isinstance(actual, list) else [actual]
        return any(same_value(candidate, value) for candidate in candidates for value in self.values)

    def describe(self) -> str:
        verb = "includes" if self.on_list else "is"
        return f"`{self.field}` {verb} " + " or ".join(f"`{yaml_text(value)}`" for value in self.values)


def all_hold(conditions: tuple[Condition, ...], frontmatter: dict[str, Any]) -> bool:
    return all(condition.holds(frontmatter) for condition in conditions)


def describe_all(conditions: tuple[Condition, ...]) -> str:
    return " and ".join(condition.describe() for condition in conditions)


def same_value(actual: Any, expected: Any) -> bool:
    # YAML reads `true` as a bool, and Python treats True == 1; a condition must not confuse them.
    return isinstance(actual, bool) == isinstance(expected, bool) and actual == expected


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    required: bool = False
    # Element type of a list; None leaves elements unconstrained.
    of: str | None = None
    # The allowed values, from a vocabulary (named here) or an inline `values:` list.
    values: tuple[str, ...] | None = None
    vocabulary: str | None = None
    range: tuple[float, float] | None = None
    pattern: re.Pattern[str] | None = None
    # Both apply only when every condition holds (AND).
    required_when: tuple[Condition, ...] = ()
    allowed_when: tuple[Condition, ...] = ()
    # Kinds a link value must point at; None allows any target.
    to: tuple[str, ...] | None = None
    matches_filename: bool = False
    # No other note of the kind may hold the same value.
    unique: bool = False
    # What `charter new` writes when no value is given; None for neither.
    default: Any = None
    auto: str | None = None
    # Where charter.yaml declares the field.
    line: int | None = None
    # One line, shown by `charter describe`.
    description: str | None = None

    @property
    def holds_links(self) -> bool:
        return self.type == "link" or (self.type == "list" and self.of == "link")

    def describe(self, choices: Sequence[Any] | None) -> str:
        """What a value must be, for someone about to give one: `an integer, from 1 to 100`.

        `choices` are the allowed values, which a `variant_by` field takes from the variants rather than itself.
        """
        if self.type != "list":
            parts = [FIELD_TYPES[self.type].expected]
        elif self.of is None:
            parts = ["a list"]
        else:
            parts = [f"a list, each item {FIELD_TYPES[self.of].expected}"]
        if choices is not None:
            parts.append(f"one of {code_list(str(choice) for choice in choices)}")
        if self.range is not None:
            parts.append(f"from {yaml_text(self.range[0])} to {yaml_text(self.range[1])}")
        if self.pattern is not None:
            parts.append(f"matching `{self.pattern.pattern}`")
        if self.to is not None:
            parts.append(f"linking to {' or '.join(f'`{kind}`' for kind in self.to)}")
        return ", ".join(parts)


def _types(spec: dict[str, Any]) -> tuple[str | None, str | None]:
    """(type, element type) with defaults applied; type is None when the spec gives no way to tell."""
    has_set = "enum" in spec or "values" in spec
    field_type = spec.get("type", "string" if has_set else None)
    of = "string" if spec.get("of") == "enum" else spec.get("of")
    if field_type == "list" and of is None:
        # Element rules imply the element type, so a list needs no `of` just to carry them.
        if has_set or "pattern" in spec:
            of = "string"
        elif "range" in spec:
            of = "number"
    return field_type, of


def declared_type(spec: dict[str, Any]) -> str | None:
    """The field's type with defaults applied; None when the spec gives no way to tell."""
    return _types(spec)[0]


def is_list(spec: dict[str, Any]) -> bool:
    return declared_type(spec) == "list"


def fixed_value_problem(
    spec: dict[str, Any], vocabularies: Mapping[str, Any], value: Any, what: str = "a fixed value"
) -> str | None:
    """Why `value` can never be a valid value of the single-value field `spec` declares; None when it can."""
    if not _is_condition_value(value):
        return f"{what} is text, a number, true or false, or a date (YYYY-MM-DD)."
    field_type = declared_type(spec)
    # A field without a type is reported where it is declared.
    if field_type is None:
        return None
    if not FIELD_TYPES[field_type].accepts(value):
        # Quoted, so the text "true" is not mistaken for the boolean it resembles.
        shown = f'the text `"{value}"`' if isinstance(value, str) else f"`{yaml_text(value)}`"
        return f"{shown} is not {FIELD_TYPES[field_type].expected}."
    allowed = vocabularies.get(spec["enum"]) if "enum" in spec else spec.get("values")
    if allowed is not None and value not in allowed:
        return f"`{yaml_text(value)}` is not one of {code_list(allowed)}."
    if "range" in spec and field_type in ("int", "number") and not spec["range"][0] <= value <= spec["range"][1]:
        low, high = spec["range"]
        return f"`{yaml_text(value)}` is outside the range {yaml_text(low)} to {yaml_text(high)}."
    if "pattern" in spec and field_type == "string" and (pattern := _compiled(spec["pattern"])):
        if not pattern.fullmatch(value):
            return f"`{value}` does not match the pattern `{spec['pattern']}`."
    return None


def _compiled(pattern: Any) -> re.Pattern[str] | None:
    # An invalid pattern is reported where it is declared; here it only means nothing to check.
    try:
        return re.compile(pattern)
    except (re.error, TypeError):
        return None


def _condition_value_problems(
    location: Sequence[str | int],
    target: Mapping[str, Any],
    values: Any,
    vocabularies: Mapping[str, Any],
    invalid: Invalid,
) -> Iterator[Diagnostic]:
    """Condition values that can never equal a value of the field they name, so the rule would never fire."""
    # On a list field a condition matches a list element, so each value is held to the element type.
    if is_list(target):
        of = _types(target)[1]
        if of is None:
            return
        target = {**target, "type": of}
    field = location[-1]
    listed = isinstance(values, list)
    for position, value in enumerate(values if listed else [values]):
        if problem := fixed_value_problem(target, vocabularies, value, "a condition value"):
            yield invalid(
                [*location, position] if listed else location,
                f"the condition on `{field}` can never hold: {problem}",
                f"A condition can only match a value `{field}` can hold.",
            )


def spec_problems(
    location: Sequence[str],
    spec: dict[str, Any],
    siblings: Mapping[str, Any],
    vocabularies: Mapping[str, Any],
    invalid: Invalid,
) -> Iterator[Diagnostic]:
    name = location[-1]
    field_type, of = _types(spec)
    if field_type is None:
        yield invalid(
            location,
            "the field has no `type`.",
            f"Set `type` to one of {code_list(FIELD_TYPES)}, or give an `enum` or `values` (which imply string).",
        )
        return

    has_set = "enum" in spec or "values" in spec
    if "enum" in spec and "values" in spec:
        yield invalid([*location, "values"], "`enum` and `values` cannot both be set.", "Use one source of allowed values.")
    if "enum" in spec and spec["enum"] not in vocabularies:
        declared = (
            f"Declared vocabularies: {code_list(vocabularies)}."
            if vocabularies
            else "Declare it under the top-level `vocabularies:`."
        )
        yield invalid(
            [*location, "enum"],
            f"vocabulary `{spec['enum']}` is not declared.",
            suggestion(spec["enum"], vocabularies, declared),
        )
    if "of" in spec and field_type != "list":
        yield invalid([*location, "of"], "`of` applies only to `type: list`.", None)
    if spec.get("of") == "enum" and not has_set:
        yield invalid([*location, "of"], "`of: enum` needs an `enum` or `values` on the field.", None)

    value_type = of if field_type == "list" else field_type
    if has_set and value_type != "string":
        yield invalid(
            [*location, "enum" if "enum" in spec else "values"],
            f"allowed values are strings, but the field holds `{value_type}`.",
            None,
        )
    if "range" in spec:
        low, high = spec["range"]
        if value_type not in ("int", "number"):
            yield invalid([*location, "range"], f"`range` applies to `int` and `number` values, not `{value_type}`.", None)
        elif low > high:
            yield invalid([*location, "range"], f"`range` minimum {low} is greater than its maximum {high}.", None)
    if "pattern" in spec:
        if value_type != "string":
            yield invalid([*location, "pattern"], f"`pattern` applies to `string` values, not `{value_type}`.", None)
        try:
            re.compile(spec["pattern"])
        except re.error as error:
            yield invalid([*location, "pattern"], f"`pattern` is not a valid regular expression ({error}).", None)

    if "to" in spec and value_type != "link":
        yield invalid(
            [*location, "to"],
            f"`to` applies to `link` values, not `{value_type}`.",
            "Use `type: link`, or `type: list` with `of: link`.",
        )

    if spec.get("matches_filename") is True and field_type == "list":
        yield invalid(
            [*location, "matches_filename"],
            "`matches_filename` applies to single values, not lists.",
            None,
        )

    if spec.get("unique") is True and field_type == "list":
        yield invalid([*location, "unique"], "`unique` applies to single values, not lists.", None)

    yield from _filling_problems(location, spec, field_type, of, vocabularies, invalid)

    if spec.get("required") is True:
        if "required_when" in spec:
            yield invalid(
                [*location, "required_when"],
                "`required_when` has no effect alongside `required: true`.",
                "Remove one: `required: true` always requires the field.",
            )
        if "allowed_when" in spec:
            yield invalid(
                [*location, "allowed_when"],
                "`required: true` contradicts `allowed_when`, which forbids the field when its conditions fail.",
                "To require the field exactly when it is allowed, use `required_when` with the same conditions.",
            )
    for key in ("required_when", "allowed_when"):
        for other, values in spec.get(key, {}).items():
            if other == name:
                yield invalid([*location, key], f"`{key}` cannot depend on the field itself.", None)
            elif other not in siblings:
                yield invalid(
                    [*location, key],
                    f"`{key}` refers to `{other}`, which is not a field of this kind.",
                    suggestion(str(other), siblings, f"Fields of this kind: {code_list(siblings)}."),
                )
            if not _is_condition(values):
                yield invalid(
                    [*location, key, other],
                    "a condition is a value or a non-empty list of values.",
                    "Values may be text, numbers, true or false, or dates (YYYY-MM-DD).",
                )
            elif other in siblings and other != name:
                yield from _condition_value_problems(
                    [*location, key, other], siblings[other], values, vocabularies, invalid
                )


def _filling_problems(
    location: Sequence[str],
    spec: dict[str, Any],
    field_type: str,
    of: str | None,
    vocabularies: Mapping[str, Any],
    invalid: Invalid,
) -> Iterator[Diagnostic]:
    """`default` and `auto`: what `charter new` fills the field with."""
    auto = spec.get("auto")
    if "default" in spec and auto is not None:
        yield invalid([*location, "default"], "`default` and `auto` cannot both be set.", "Keep one of them.")
    elif "default" in spec and (problem := _default_problem(spec, field_type, of, vocabularies, spec["default"])):
        yield invalid([*location, "default"], problem, None)
    if auto == TODAY and field_type != "date":
        yield invalid(
            [*location, "auto"], f"`auto: {TODAY}` fills in a date, but the field holds `{field_type}`.", None
        )
    elif auto == NEXT and (field_type != "int" or spec.get("unique") is not True):
        yield invalid(
            [*location, "auto"],
            f"`auto: {NEXT}` fills in the next free value of a unique integer field.",
            "Declare the field with `type: int` and `unique: true`.",
        )


def _default_problem(
    spec: dict[str, Any], field_type: str, of: str | None, vocabularies: Mapping[str, Any], value: Any
) -> str | None:
    if field_type != "list":
        return fixed_value_problem(spec, vocabularies, value, "a default")
    if not isinstance(value, list):
        return f"`{yaml_text(value)}` is not a list."
    if of is None:
        return None
    element = {**spec, "type": of}
    problems = (fixed_value_problem(element, vocabularies, item, "a default element") for item in value)
    return next((problem for problem in problems if problem), None)


def _is_condition(values: Any) -> bool:
    if isinstance(values, list):
        return bool(values) and all(_is_condition_value(value) for value in values)
    return _is_condition_value(values)


def _is_condition_value(value: Any) -> bool:
    if isinstance(value, datetime.date):
        return not isinstance(value, datetime.datetime)
    return isinstance(value, str | int | float | bool)


def parse_field(
    name: str,
    spec: dict[str, Any],
    siblings: Mapping[str, dict[str, Any]],
    vocabularies: Mapping[str, list[str]],
    line: int | None = None,
) -> Field:
    field_type, of = _types(spec)
    vocabulary = spec.get("enum")
    values = vocabularies[vocabulary] if vocabulary else spec.get("values")

    def conditions(key: str) -> tuple[Condition, ...]:
        return tuple(
            Condition(
                other,
                tuple(expected) if isinstance(expected, list) else (expected,),
                on_list=is_list(siblings[other]),
            )
            for other, expected in spec.get(key, {}).items()
        )

    return Field(
        name=name,
        type=field_type,
        required=spec.get("required", False),
        of=of,
        values=tuple(values) if values is not None else None,
        vocabulary=vocabulary,
        range=tuple(spec["range"]) if "range" in spec else None,
        pattern=re.compile(spec["pattern"]) if "pattern" in spec else None,
        required_when=conditions("required_when"),
        allowed_when=conditions("allowed_when"),
        to=link_targets(spec),
        matches_filename=spec.get("matches_filename", False),
        unique=spec.get("unique", False),
        default=spec.get("default"),
        auto=spec.get("auto"),
        line=line,
        description=spec.get("description"),
    )


def link_targets(spec: dict[str, Any]) -> tuple[str, ...] | None:
    to = spec.get("to")
    if to is None:
        return None
    return (to,) if isinstance(to, str) else tuple(to)
