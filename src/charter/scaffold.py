"""`charter new`: a note drafted from its kind's contract, validated in memory, and written only if valid."""

import contextlib
import copy
import datetime
import errno
import itertools
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from charter import yamlsource
from charter.checks.paths import edit_violation_for
from charter.collection import holders, members_by_kind
from charter.contract import Contract, Kind, Shape, Variant
from charter.diagnostics import RUN_FAILURES, Diagnostic, Refused, Severity, code_list, suggestion, yaml_text
from charter.fields import NEXT, TODAY, Field, all_hold, same_value
from charter.history import ADDED
from charter.index import TITLE, build_index
from charter.pathpattern import Unrenderable, Unsafe
from charter.profiles import Profile
from charter.template import DATE, fill, outline
from charter.validate import validate

# Base severities without `residue`: a new note is meant to keep its template's guidance and open placeholders.
_PROFILE = Profile("new", {"residue": None}, downgrade_only=False)
# `new` reports missing fields itself, with what each may hold.
_REQUIRED = "schema/required"


@dataclass(frozen=True)
class Draft:
    path: str
    shape: str
    # Headings as the note has them, with their markers: `## Notes (optional)`.
    outline: tuple[str, ...]
    warnings: tuple[Diagnostic, ...]


def create(
    contract: Contract,
    named: str,
    title: str | None,
    settings: Sequence[str],
    *,
    today: datetime.date,
    write: bool,
) -> Draft:
    """Draft a note of `named` (`kind` or `kind/variant`) and, when `write`, write it. Raises Refused.

    Independent reasons to refuse are reported together, so one retry can address them all.
    """
    kind, variant = named_shape(contract, named)
    given = _given_values(contract, kind, variant, title, settings)
    shape, values, unfilled = _filled(contract, given, today)
    problems = [*unfilled.values(), *_missing_fields(contract, named, shape, values, unfilled)]

    # A padded field reads the same in the body as in the file name.
    texts = {name: _text(shape.fields.get(name), value) for name, value in values.items()}
    # One value set for body and outline, so the printed headings are the written ones.
    filled = {DATE: today.isoformat(), **texts}
    body = fill(shape.template.text, filled) if shape.template is not None else ""
    text = f"---\n{_frontmatter(contract, shape, values)}---\n{body}"

    placed = contract.rendered_path(shape, values)
    if placed is None:
        path = None
        problems.append(_no_path(contract, shape))
    else:
        # A note that cannot be placed is still checked where its pattern stands, so its other problems show too.
        path = placed if isinstance(placed, str) else contract.under_root(shape.path.text.replace("\\", "/"))
        problems.extend(_checked(contract, shape, placed, path, text, today))
        if not isinstance(placed, str) and not any(d.severity is Severity.ERROR for d in problems):
            problems.append(_unplaceable(contract, shape, placed))

    if path is None or any(d.severity is Severity.ERROR for d in problems):
        raise Refused(problems)
    if write:
        _write(contract, path, text)
    return Draft(path, shape.name, outline(shape.template, filled), tuple(problems))


def _text(field: Field | None, value: Any) -> str:
    return field.text(value) if field is not None else yaml_text(value)


def new_command(contract: Contract, shape: Shape) -> str:
    """The `charter new` command for a note of `shape`, giving exactly the values nothing else fills in."""
    fixed = {contract.discriminator}
    if shape.variant is not None:
        fixed.update(condition.field for condition in shape.variant.selection)
    title = _title_field(shape.fields)
    command = ["charter", "new", shape.name]
    if title is not None and _needs_value(shape.fields[title]):
        command.append('"TITLE"')
    command.extend(
        f"--set {field.name}={field.name.upper()}"
        for field in shape.fields.values()
        if field.name not in fixed and field.name != title and _needs_value(field)
    )
    return " ".join(command)


def _needs_value(field: Field) -> bool:
    return field.required and field.auto is None and field.default is None


def named_shape(contract: Contract, named: str) -> tuple[Kind, Variant | None]:
    kind_name, slash, variant_name = named.partition("/")
    kind = contract.kinds.get(kind_name)
    if kind is None:
        declared = f"Declared kinds: {code_list(sorted(contract.kinds))}."
        raise _usage(
            contract,
            "usage/unknown-kind",
            f"Kind `{kind_name}` is not declared in the contract.",
            suggestion(kind_name, contract.kinds, declared),
        )
    if not slash:
        return kind, None
    # Variant names are matched as text, as typed on the command line, whatever YAML read them as.
    names = {str(name): variant for name, variant in kind.variants.items()}
    if variant_name not in names:
        listed = f"Variants of `{kind_name}`: {code_list(names)}." if names else f"`{kind_name}` has no variants."
        raise _usage(
            contract,
            "usage/unknown-variant",
            f"Kind `{kind_name}` has no variant `{variant_name}`.",
            suggestion(variant_name, names, listed),
        )
    return kind, names[variant_name]


def _given_values(
    contract: Contract, kind: Kind, variant: Variant | None, title: str | None, settings: Sequence[str]
) -> dict[str, Any]:
    declared = _declared_fields(contract, kind, variant)
    fixed = {contract.discriminator: kind.name}
    if variant is not None:
        fixed.update((condition.field, condition.values[0]) for condition in variant.selection)

    given: dict[str, Any] = {}
    for setting in settings:
        name, equals, text = setting.partition("=")
        if not equals or not name:
            raise _usage(
                contract,
                "usage/invalid-set",
                f"`--set {setting}` is not of the form FIELD=VALUE.",
                "Write each value as `--set FIELD=VALUE`.",
            )
        field = declared.get(name)
        value = _parsed(field, text)
        if field is not None and field.type == "list":
            given.setdefault(name, []).append(value)
        elif name in given:
            raise _usage(
                contract,
                "usage/repeated-set",
                f"`{name}` is set more than once, but it holds a single value.",
                f"Give `--set {name}=VALUE` once.",
            )
        else:
            given[name] = value

    if title is not None:
        name = _title_field(declared)
        if name is None:
            raise _usage(
                contract,
                "usage/no-title-field",
                f"Kind `{kind.name}` has no `{TITLE}` field to take the title.",
                "Leave out the title and give the fields with `--set FIELD=VALUE`.",
            )
        if name in given:
            raise _conflict(contract, name, "the title argument")
        given[name] = title

    for name, value in given.items():
        if name in fixed and not same_value(value, fixed[name]):
            source = "the kind" if name == contract.discriminator else f"the variant `{variant.name}`"
            raise _conflict(contract, name, f"{source}, which fixes it to `{yaml_text(fixed[name])}`")
    return {**fixed, **given}


def _declared_fields(contract: Contract, kind: Kind, variant: Variant | None) -> dict[str, Field]:
    """The named variant's fields and the kind's, then those of any variant `--set` values may select."""
    declared = {**contract.kind_fields(kind), **(variant.fields if variant is not None else {})}
    for other in kind.variants.values():
        for name, field in other.fields.items():
            declared.setdefault(name, field)
    return declared


def _parsed(field: Field | None, text: str) -> Any:
    """A `--set` value as the field's type reads it; text when it is text, or when YAML cannot make it more."""
    if field is None:
        return text
    value_type = field.of if field.type == "list" else field.type
    if value_type in (None, "string", "link"):
        return text
    try:
        value, _ = yamlsource.parse(text)
    except yamlsource.YamlSyntaxError:
        return text
    return text if value is None else value


def _title_field(fields: Mapping[str, Field]) -> str | None:
    if TITLE in fields:
        return TITLE
    matched = [name for name, field in fields.items() if field.matches_filename]
    return matched[0] if len(matched) == 1 else None


def _filled(
    contract: Contract, given: Mapping[str, Any], today: datetime.date
) -> tuple[Shape, dict[str, Any], dict[str, Diagnostic]]:
    """The note's shape and values once defaults and `auto` values are filled in, and the fields that could not be.

    A filled value may select a variant, whose own declarations then decide the filling: each round starts again
    from the given values, so nothing filled for a shape the note did not end up with is kept.
    """
    taken = _taken_values(contract)
    shape = contract.shape_of(given)
    seen = {shape.name}
    while True:
        values, unfilled = dict(given), {}
        for field in shape.fields.values():
            if field.name in given:
                continue
            if field.auto == TODAY:
                values[field.name] = today
            elif field.auto == NEXT:
                free = _next_free(field, taken(shape.kind, field.name))
                if free is None:
                    unfilled[field.name] = _no_free_value(contract, shape.kind, field)
                else:
                    values[field.name] = free
            elif field.default is not None:
                values[field.name] = copy.deepcopy(field.default)
        settled = contract.shape_of(values)
        # Variant selection rules keep this from cycling; stopping at a repeat makes termination certain regardless.
        if settled.name == shape.name or settled.name in seen:
            return settled, values, unfilled
        seen.add(settled.name)
        shape = settled


def _taken_values(contract: Contract) -> Callable[[Kind, str], set[Any]]:
    """The values each kind's notes hold for a field, reading the knowledge base only when first asked."""
    members = None

    def taken(kind: Kind, field: str) -> set[Any]:
        nonlocal members
        if members is None:
            members = members_by_kind(contract, build_index(contract).notes)
        return set(holders(members[kind.name], field))

    return taken


def _next_free(field: Field, taken: set[Any]) -> int | None:
    low, high = _id_bounds(field)
    candidates = itertools.count(low) if high is None else range(low, high + 1)
    return next((value for value in candidates if value not in taken), None)


def _id_bounds(field: Field) -> tuple[int, int | None]:
    if field.range is None:
        return 1, None
    return math.ceil(field.range[0]), math.floor(field.range[1])


def _no_free_value(contract: Contract, kind: Kind, field: Field) -> Diagnostic:
    low, high = _id_bounds(field)
    return _contract_error(
        contract,
        field.line,
        "new/no-free-value",
        f"Every `{field.name}` between {low} and {high} is taken by a `{kind.name}` note.",
        f"Free a value, or widen the `range` of `{field.name}`.",
    )


def _missing_fields(
    contract: Contract, named: str, shape: Shape, values: Mapping[str, Any], unfilled: Mapping[str, Diagnostic]
) -> list[Diagnostic]:
    title_field = _title_field(shape.fields)
    return [
        _contract_error(
            contract,
            field.line,
            "new/missing-field",
            f"`{shape.name}` needs `{field.name}`: "
            f"{field.describe(shape.kind.allowed_values(field))}.",
            f'Pass it as the title argument: charter new {named} "TITLE".'
            if field.name == title_field
            else f"Add `--set {field.name}=VALUE`.",
        )
        for field in shape.fields.values()
        if (field.required or (field.required_when and all_hold(field.required_when, values)))
        and values.get(field.name) in (None, "", [])
        and field.name not in unfilled
    ]


def _checked(
    contract: Contract, shape: Shape, placed: str | Unsafe | Unrenderable, path: str, text: str, today: datetime.date
) -> list[Diagnostic]:
    """What stops the note at `path`, or warns about it; the note is validated only where it would be indexed."""
    problems = []
    if isinstance(placed, str):
        try:
            if over_windows_name_limit(path, windows=_ON_WINDOWS):
                raise _NameTooLong
            if _present(contract.base_dir / path):
                problems.append(_exists(path))
        except _NameTooLong:
            problems.append(_name_too_long(path))
    # Creation is an addition, which an edit policy can judge without history.
    if isinstance(placed, str) and (violation := edit_violation_for(contract, path, ADDED)) is not None:
        problems.append(violation)
    if contract.ignores(path):
        return [
            *problems,
            _contract_error(
                contract,
                None,
                "new/ignored-path",
                f"`{path}` is ignored by a `paths:` policy, so the note could never be validated.",
                f"Change the `{shape.name}` path, or the `paths:` policy that ignores it.",
            ),
        ]
    # Agents create notes with `new` mid-session, so it is a per-edit run and must stay as fast as one.
    checked = validate(
        contract, frozenset({path}), _PROFILE, strict=False, today=today, pending={path: text}, per_edit=True
    )
    found = [
        d
        for d in checked
        # A run failure (a plugin that crashed) is anchored elsewhere, but leaves the note unchecked.
        if (d.path == path and d.code != _REQUIRED) or d.code in RUN_FAILURES
    ]
    return [*problems, *found]


def _unplaceable(contract: Contract, shape: Shape, placed: Unsafe | Unrenderable) -> Diagnostic:
    return _contract_error(
        contract,
        None,
        "new/unplaceable",
        f"The `{shape.name}` path `{shape.path.text}` cannot be rendered from `{placed.field}`.",
        f"Correct `--set {placed.field}`.",
    )


def _no_path(contract: Contract, shape: Shape) -> Diagnostic:
    return _contract_error(
        contract,
        None,
        "new/no-path",
        f"`{shape.name}` has no `path`, so a new note has no place to go.",
        f"Declare a `path` pattern on `{shape.name}`.",
    )


def _frontmatter(contract: Contract, shape: Shape, values: Mapping[str, Any]) -> str:
    own = shape.variant.fields if shape.variant is not None else {}
    order = dict.fromkeys([contract.discriminator, *shape.kind.fields, *own, *shape.fields, *values])
    ordered = {name: values[name] for name in order if name in values}
    return yamlsource.dump(ordered, width=math.inf)


def _write(contract: Contract, path: str, text: str) -> None:
    file = contract.base_dir / path
    # Deepest first, so they can be removed in this order if the note cannot be written.
    created = [folder for folder in file.parents if not folder.exists()]
    opened = False
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation: a file that appeared since the path was checked is still never overwritten.
        with file.open("x", encoding="utf-8", newline="") as stream:
            opened = True
            stream.write(text)
    except OSError as error:
        if opened:
            file.unlink(missing_ok=True)
        for folder in created:
            with contextlib.suppress(OSError):
                folder.rmdir()
        if isinstance(error, FileExistsError) and not opened and file.exists():
            raise Refused([_exists(path)]) from None
        if _too_long(error):
            raise Refused([_name_too_long(path)]) from None
        raise Refused([
            Diagnostic(
                path,
                None,
                Severity.ERROR,
                "new/write-failed",
                f"`{path}` could not be written: {error.strerror or error}.",
                "Check that the folder can be written to and that the path is not too long for the file system.",
            )
        ]) from None


class _NameTooLong(Exception):
    """The file system rejected a name or a whole path for its length."""


# Windows reports ERROR_FILENAME_EXCED_RANGE under another errno; the limits themselves belong to the file system.
_WINDOWS_PATH_TOO_LONG = 206


_ON_WINDOWS = os.name == "nt"
# Every Windows file system caps one name at 255 UTF-16 code units. Windows reports a longer name under errors
# that also mean other things, and a missing folder hides it, so the limit is checked before the file system.
_WINDOWS_NAME_LIMIT = 255


def over_windows_name_limit(path: str, *, windows: bool) -> bool:
    """Whether a name in `path` (diagnostic form) is longer than Windows allows; always False elsewhere."""
    units = (len(part.encode("utf-16-le")) // 2 for part in PurePosixPath(path).parts)
    return windows and any(count > _WINDOWS_NAME_LIMIT for count in units)


def _too_long(error: OSError) -> bool:
    return error.errno == errno.ENAMETOOLONG or getattr(error, "winerror", None) == _WINDOWS_PATH_TOO_LONG


def _present(file: Path) -> bool:
    """Whether `file` exists; `Path.exists` hides a name that is too long, so a dry run would promise a write."""
    try:
        file.stat()
    except OSError as error:
        if _too_long(error):
            raise _NameTooLong from None
        # Anything else (a missing folder, no permission) is for the write to report.
        return False
    return True


def _name_too_long(path: str) -> Diagnostic:
    return Diagnostic(
        path,
        None,
        Severity.ERROR,
        "new/name-too-long",
        f"`{path}` cannot be created: the title makes the file name too long for the file system.",
        "Give the note a shorter title.",
    )


def _exists(path: str) -> Diagnostic:
    return Diagnostic(
        path,
        None,
        Severity.ERROR,
        "new/exists",
        f"`{path}` already exists; charter new never overwrites a file.",
        "Give the note a different title or values, or edit the existing note.",
    )


def _contract_error(contract: Contract, line: int | None, code: str, message: str, hint: str) -> Diagnostic:
    return Diagnostic(contract.file, line, Severity.ERROR, code, message, hint)


def _usage(contract: Contract, code: str, message: str, hint: str) -> Refused:
    return Refused([_contract_error(contract, None, code, message, hint)], usage=True)


def _conflict(contract: Contract, name: str, source: str) -> Refused:
    return _usage(
        contract,
        "usage/conflicting-set",
        f"`--set {name}` conflicts with {source}.",
        f"Leave out `--set {name}`.",
    )
