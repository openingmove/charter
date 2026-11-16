"""JSON Schema violations worded for people writing YAML."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from charter.diagnostics import code_list, suggestion, yaml_text

if TYPE_CHECKING:
    import jsonschema

_JSON_TYPES = {
    "string": "text",
    "integer": "an integer",
    "number": "a number",
    "boolean": "true or false",
    "array": "a list",
    "object": "a mapping",
    "null": "null",
}


def schema_message(problem: "jsonschema.ValidationError") -> tuple[str, str | None]:
    """(message, hint) in YAML terms, since jsonschema's own messages show Python reprs."""
    expected = problem.validator_value
    shown = f"`{yaml_text(problem.instance)}`"
    match problem.validator:
        case "type":
            names = [expected] if isinstance(expected, str) else expected
            return f"expected {' or '.join(_JSON_TYPES[name] for name in names)}, got {shown}.", None
        case "enum":
            return f"{shown} is not one of {code_list(expected)}.", None
        case "const":
            return f"must be `{yaml_text(expected)}`, got {shown}.", None
        case "additionalProperties":
            allowed = problem.schema.get("properties", {})
            unknown = [key for key in problem.instance if key not in allowed]
            listed = f"Allowed keys: {code_list(allowed)}."
            return f"unknown key {code_list(unknown)}.", suggestion(str(unknown[0]), allowed, listed) if allowed else None
        case "required":
            missing = [key for key in expected if key not in problem.instance]
            return f"missing required key {code_list(missing)}.", None
        case "minItems" | "minLength" | "minProperties" if expected == 1:
            return "must not be empty.", None
        case "minItems":
            return f"must have at least {expected} items.", None
        case "minimum":
            return f"must be at least {expected}, got {shown}.", None
        case "maxItems":
            return f"must have at most {expected} items.", None
        case "uniqueItems":
            return "must not repeat a value.", None
    return f"{problem.message}.", None


def dotted(path: Iterable[str | int]) -> str:
    """A location in a YAML or JSON document as written in messages: `checks.chains.with.words`."""
    return ".".join(str(step) for step in path)


def located_message(problem: "jsonschema.ValidationError") -> tuple[str, str | None]:
    """schema_message, prefixed with where in the document the problem is, unless it is the whole document."""
    message, hint = schema_message(problem)
    location = dotted(problem.absolute_path)
    return (f"{location}: {message}" if location else message), hint
