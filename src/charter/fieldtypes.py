"""The field types a contract may declare, and how a frontmatter value is judged against each."""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldType:
    accepts: Callable[[Any], bool]
    expected: str
    hint: str | None = None


FIELD_TYPES: dict[str, FieldType] = {
    "string": FieldType(lambda v: isinstance(v, str), "a string"),
    # bool is a subclass of int in Python, so numbers must exclude it explicitly.
    "int": FieldType(lambda v: isinstance(v, int) and not isinstance(v, bool), "an integer"),
    "number": FieldType(lambda v: isinstance(v, int | float) and not isinstance(v, bool), "a number"),
    "bool": FieldType(lambda v: isinstance(v, bool), "true or false"),
    "date": FieldType(
        lambda v: isinstance(v, datetime.date) and not isinstance(v, datetime.datetime),
        "a date (YYYY-MM-DD)",
        "Write the date unquoted as YYYY-MM-DD.",
    ),
    "link": FieldType(
        lambda v: isinstance(v, str),
        "a link",
        'Quote the link so YAML reads it as text, e.g. "[[Target]]".',
    ),
    "list": FieldType(lambda v: isinstance(v, list), "a list"),
}
