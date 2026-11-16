"""The `schema` check: every note has a declared kind and its fields match their declarations, with none undeclared."""

import datetime
from collections.abc import Iterator
from typing import Any

from charter.checks import CheckRequest
from charter.contract import Contract, Shape
from charter.diagnostics import Diagnostic, Severity, code_list, suggestion
from charter.fields import Field, all_hold, describe_all
from charter.fieldtypes import FIELD_TYPES
from charter.index import Note


class SchemaCheck:
    id = "schema"
    codes = frozenset({
        "schema/missing-frontmatter",
        "schema/missing-kind",
        "schema/unknown-kind",
        "schema/unknown-variant",
        "schema/unknown-field",
        "schema/not-allowed",
        "schema/required",
        "schema/type",
        "schema/item-type",
        "schema/enum",
        "schema/range",
        "schema/pattern",
    })

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        for note in request.target_notes():
            yield from _check_note(note, request.contract)


def _check_note(note: Note, contract: Contract) -> Iterator[Diagnostic]:
    discriminator = contract.discriminator
    declared = code_list(sorted(contract.kinds))
    kind_name = note.frontmatter.get(discriminator)

    if _is_empty(kind_name):
        # Exempt files need no kind; one that does declare a kind is checked like any note.
        if contract.allows_untyped(note.path):
            return
        if not note.has_frontmatter:
            yield _error(
                note,
                1,
                "schema/missing-frontmatter",
                "File has no frontmatter, so its kind is unknown.",
                f"Start the file with frontmatter declaring `{discriminator}: <kind>` (declared kinds: {declared}), "
                "or allow untyped files at this path with an `untyped: allow` path policy.",
            )
            return
        yield _error(
            note,
            1,
            "schema/missing-kind",
            f"Note has no `{discriminator}` field, so its kind is unknown.",
            f"Add `{discriminator}: <kind>` to the frontmatter. Declared kinds: {declared}.",
        )
        return

    shape = contract.shape_of(note.frontmatter)
    if shape is None:
        yield _error(
            note,
            note.field_lines.get(discriminator, 1),
            "schema/unknown-kind",
            f"Kind `{kind_name}` is not declared in the contract.",
            suggestion(str(kind_name), contract.kinds, f"Declared kinds: {declared}."),
        )
        return

    for field in shape.fields.values():
        choices = shape.kind.allowed_values(field)
        yield from _check_field(note, field, choices)
    if shape.unknown_variant is not None:
        yield _unknown_variant(note, shape)
    if shape.kind.unknown_fields is not None:
        yield from _unknown_fields(note, contract, shape, shape.kind.unknown_fields)


def _unknown_variant(note: Note, shape: Shape) -> Diagnostic:
    kind = shape.kind
    return _error(
        note,
        note.field_lines.get(kind.variant_by),
        "schema/unknown-variant",
        f"`{kind.variant_by}` is `{shape.unknown_variant}`, which names no variant of kind `{kind.name}`.",
        suggestion(shape.unknown_variant, kind.variants, f"Variants of `{kind.name}`: {code_list(kind.variants)}."),
    )


def _unknown_fields(note: Note, contract: Contract, shape: Shape, severity: Severity) -> Iterator[Diagnostic]:
    known = [contract.discriminator, *shape.fields, *contract.common_fields]
    kind, variant = shape.kind.name, shape.variant
    declare_under = f"kinds.{kind}.fields" if variant is None else f"kinds.{kind}.variants.{variant.name}.fields"
    for key in note.frontmatter:
        if key in known:
            continue
        name = str(key)
        yield Diagnostic(
            note.path,
            note.field_lines.get(name),
            severity,
            "schema/unknown-field",
            f"Field `{name}` is not declared for {'kind' if variant is None else 'variant'} `{shape.name}`.",
            suggestion(
                name,
                known,
                f"Remove it, or declare it under `{declare_under}` or `common_fields` in charter.yaml.",
            ),
        )


def _check_field(note: Note, field: Field, choices: tuple[str, ...] | None) -> Iterator[Diagnostic]:
    """`choices` are the values a single-value field may take, when the contract limits them."""
    value = note.frontmatter.get(field.name)
    line = note.field_lines.get(field.name)
    if field.allowed_when and not all_hold(field.allowed_when, note.frontmatter):
        if not _is_empty(value):
            yield _error(
                note,
                line,
                "schema/not-allowed",
                f"Field `{field.name}` is only allowed when {describe_all(field.allowed_when)}.",
                f"Remove `{field.name}`, or change the fields it depends on.",
            )
        return

    if _is_empty(value):
        required_when = bool(field.required_when) and all_hold(field.required_when, note.frontmatter)
        if field.required or required_when:
            state = "missing" if line is None else "empty"
            message = (
                f"Field `{field.name}` is {state}, but is required when {describe_all(field.required_when)}."
                if required_when
                else f"Required field `{field.name}` is {state}."
            )
            yield _error(
                note,
                line or 1,
                "schema/required",
                message,
                f"Set `{field.name}` to {field.describe(choices)}.",
            )
        return

    field_type = FIELD_TYPES[field.type]
    if not field_type.accepts(value):
        yield _error(
            note,
            line,
            "schema/type",
            f"Field `{field.name}` must be {field_type.expected}, got {_describe(value)}.",
            field_type.hint,
        )
        return

    if field.type != "list":
        yield from _check_value(note, line, field, value, f"Field `{field.name}`")
        return
    item_type = FIELD_TYPES.get(field.of)
    for position, item in enumerate(value, start=1):
        label = f"Item {position} of `{field.name}`"
        if item_type is not None and not item_type.accepts(item):
            yield _error(
                note,
                line,
                "schema/item-type",
                f"{label} must be {item_type.expected}, got {_describe(item)}.",
                item_type.hint,
            )
            continue
        yield from _check_value(note, line, field, item, label)


def _check_value(note: Note, line: int | None, field: Field, value: Any, label: str) -> Iterator[Diagnostic]:
    if field.values is not None and value not in field.values:
        source = f"vocabulary `{field.vocabulary}`" if field.vocabulary else "the allowed values"
        yield _error(
            note,
            line,
            "schema/enum",
            f"{label} is `{value}`, which is not in {source}.",
            suggestion(value, field.values, f"Allowed values: {code_list(field.values)}."),
        )
    if field.range is not None and not field.range[0] <= value <= field.range[1]:
        low, high = field.range
        yield _error(
            note,
            line,
            "schema/range",
            f"{label} is {value}, outside the range {low} to {high}.",
            f"Use a value from {low} to {high} inclusive.",
        )
    if field.pattern is not None and not field.pattern.fullmatch(value):
        yield _error(
            note,
            line,
            "schema/pattern",
            f"{label} is `{value}`, which does not match the pattern `{field.pattern.pattern}`.",
            "The whole value must match the pattern.",
        )


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _describe(value: Any) -> str:
    if value is None:
        return "an empty (null) value"
    if isinstance(value, bool):
        return f"boolean `{str(value).lower()}`"
    if isinstance(value, int | float):
        return f"number `{value}`"
    if isinstance(value, str):
        return f"text `{value}`"
    if isinstance(value, datetime.datetime):
        return "a date-time"
    if isinstance(value, datetime.date):
        return f"date `{value.isoformat()}`"
    if isinstance(value, list):
        return "a list"
    return "a mapping"


def _error(note: Note, line: int | None, code: str, message: str, hint: str | None) -> Diagnostic:
    return Diagnostic(note.path, line, Severity.ERROR, code, message, hint)
