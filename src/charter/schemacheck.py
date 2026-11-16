"""Check data against a JSON Schema without importing `jsonschema` when the data plainly conforms.

Importing `jsonschema` costs far more than checking a contract against its schema, and nearly every run
loads a valid contract. `conforms` answers only the question "is this surely valid?" for the few keywords
charter's own schemas use. Anything else, and any invalid or doubtful data, goes to `jsonschema`, so the
findings and their wording are exactly its own.
"""

import re
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import jsonschema


class _Unsure(Exception):
    """The schema or data uses something this module does not judge; ask `jsonschema`."""


# Dates and the like are left to jsonschema, which has its own rules for them.
_PLAIN = (dict, list, str, int, float, bool, type(None))
_SCALAR_TYPES = (str, int, bool)


def errors(schema: Mapping[str, Any], instance: Any) -> "list[jsonschema.ValidationError]":
    """What `jsonschema.Draft202012Validator(schema).iter_errors(instance)` yields, without the import when none do."""
    if conforms(schema, instance):
        return []
    import jsonschema  # only invalid or unusual data needs the full validator and its messages

    return list(jsonschema.Draft202012Validator(schema).iter_errors(instance))


def conforms(schema: Mapping[str, Any], instance: Any) -> bool:
    """True only when `instance` certainly satisfies `schema`; False means invalid or not sure."""
    try:
        return _holds(schema, instance)
    except (_Unsure, re.error, TypeError, AttributeError, KeyError, ValueError, RecursionError):
        # A schema may hold a pattern, number or rule this module cannot use; `jsonschema` decides and reports it.
        return False


def _holds(schema: Any, instance: Any) -> bool:
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, dict):
        raise _Unsure
    if not schema:
        return True
    if not isinstance(instance, _PLAIN):
        raise _Unsure
    for keyword, value in schema.items():
        rule = _RULES.get(keyword)
        if rule is None:
            raise _Unsure
        if not rule(value, instance, schema):
            return False
    return True


def _is_type(name: str, instance: Any) -> bool:
    match name:
        case "string":
            return isinstance(instance, str)
        case "object":
            return isinstance(instance, dict)
        case "array":
            return isinstance(instance, list)
        case "boolean":
            return isinstance(instance, bool)
        case "null":
            return instance is None
        case "number":
            return isinstance(instance, int | float) and not isinstance(instance, bool)
        case "integer":
            return (isinstance(instance, int) and not isinstance(instance, bool)) or (
                isinstance(instance, float) and instance.is_integer()
            )
    raise _Unsure


def _type(value: Any, instance: Any, schema: dict) -> bool:
    names = [value] if isinstance(value, str) else value
    # Every name is looked at, so an unknown one forces the fallback even when an earlier name matches.
    return any([_is_type(name, instance) for name in names])


def _same(a: Any, b: Any) -> bool:
    """Equal as JSON values (`true` is not `1`); only plain scalars are compared."""
    for item in (a, b):
        if item is not None and type(item) not in _SCALAR_TYPES:
            raise _Unsure
    return type(a) is type(b) and a == b


def _enum(value: list, instance: Any, schema: dict) -> bool:
    return any(_same(member, instance) for member in value)


def _const(value: Any, instance: Any, schema: dict) -> bool:
    return _same(value, instance)


def _properties(value: dict, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, dict) or all(_holds(sub, instance[key]) for key, sub in value.items() if key in instance)


def _additional_properties(value: Any, instance: Any, schema: dict) -> bool:
    if "patternProperties" in schema:
        raise _Unsure
    if not isinstance(instance, dict):
        return True
    declared = schema.get("properties", {})
    return all(_holds(value, item) for key, item in instance.items() if key not in declared)


def _required(value: list, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, dict) or all(key in instance for key in value)


def _conditional(value: Any, instance: Any, schema: dict, *, when: bool) -> bool:
    """`then` (when the `if` schema holds) or `else` (when it does not); neither applies without an `if`."""
    return "if" not in schema or _holds(schema["if"], instance) != when or _holds(value, instance)


def _then(value: Any, instance: Any, schema: dict) -> bool:
    return _conditional(value, instance, schema, when=True)


def _else(value: Any, instance: Any, schema: dict) -> bool:
    return _conditional(value, instance, schema, when=False)


def _items(value: Any, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, list) or all(_holds(value, item) for item in instance)


def _min_items(value: int, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, list) or len(instance) >= value


def _max_items(value: int, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, list) or len(instance) <= value


def _unique_items(value: bool, instance: Any, schema: dict) -> bool:
    if not value or not isinstance(instance, list):
        return True
    for kind in (str, int):
        if all(type(item) is kind for item in instance):
            return len(set(instance)) == len(instance)
    raise _Unsure


def _min_length(value: int, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, str) or len(instance) >= value


def _minimum(value: int, instance: Any, schema: dict) -> bool:
    if isinstance(instance, bool) or not isinstance(instance, int | float):
        return True
    return instance >= value


def _min_properties(value: int, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, dict) or len(instance) >= value


def _pattern(value: str, instance: Any, schema: dict) -> bool:
    return not isinstance(instance, str) or re.search(value, instance) is not None


def _property_names(value: Any, instance: Any, schema: dict) -> bool:
    if not isinstance(instance, dict):
        return True
    if not all(isinstance(key, str) for key in instance):
        raise _Unsure
    return all(_holds(value, key) for key in instance)


def _annotation(value: Any, instance: Any, schema: dict) -> bool:
    return True


_RULES: dict[str, Callable[[Any, Any, dict], bool]] = {
    "$schema": _annotation,
    "title": _annotation,
    "description": _annotation,
    "if": _annotation,
    "type": _type,
    "enum": _enum,
    "const": _const,
    "properties": _properties,
    "additionalProperties": _additional_properties,
    "required": _required,
    "then": _then,
    "else": _else,
    "items": _items,
    "minItems": _min_items,
    "maxItems": _max_items,
    "uniqueItems": _unique_items,
    "minLength": _min_length,
    "minimum": _minimum,
    "minProperties": _min_properties,
    "pattern": _pattern,
    "propertyNames": _property_names,
}
