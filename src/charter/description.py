"""The contract explained: a description assembled once from the contract, rendered as Markdown or JSON."""

import datetime
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any, NamedTuple

from charter.body import heading, parse_body
from charter.contract import AGENTS_INCLUDE, CONTRACT_FILENAME, Contract, Kind, Shape, StructureCutoff, Variant
from charter.diagnostics import code_list, code_span, yaml_text
from charter.fields import NEXT, TODAY, Field, describe_all, zero_padded
from charter.pathpolicy import POLICY_KEYS
from charter.plugin import Plugin
from charter.prose import LIST_ITEM
from charter.scaffold import named_shape, new_command
from charter.template import Template
from charter.validate import BUILTIN_CHECKS

JSON_FORMAT_ID = "charter-describe/1"
FORMATS = ("markdown", "json")


@dataclass(frozen=True)
class VariantChoice:
    """A value of a kind's field that makes a note one of the kind's variants."""

    value: Any
    variant: str


@dataclass(frozen=True)
class FieldDescription:
    name: str
    type: str
    of: str | None
    required: bool
    # Conditions in words: "`stage` is `cut`".
    required_when: str | None
    allowed_when: str | None
    values: tuple[str, ...] | None
    range: tuple[float, float] | None
    pattern: str | None
    to: tuple[str, ...] | None
    unique: bool
    matches_filename: bool
    # Digits an `int` value is zero padded to wherever it becomes text; None for plain decimal.
    width: int | None
    default: Any
    auto: str | None
    # Names the note's kind.
    discriminator: bool
    # The one value a note of this shape has: the kind's name, or the value selecting the variant.
    fixed: Any
    # On a kind with variants: the values that make a note a variant instead.
    selects: tuple[VariantChoice, ...]
    # What a value must be, in words: "an integer, from 1 to 100".
    expects: str
    description: str | None


@dataclass(frozen=True)
class OutlineEntry:
    level: int
    # As the template has it, placeholders included.
    text: str
    optional: bool
    repeat: bool
    # The template's `<!-- guide: … -->` text for the section.
    guide: str | None


@dataclass(frozen=True)
class VariantReference:
    name: str
    # The field values that make a note this variant.
    selection: dict[str, Any]


@dataclass(frozen=True)
class ShapeDescription:
    """A kind, or one of its variants, with everything a note of it needs."""

    name: str
    kind: str
    variant: str | None
    description: str | None
    # In diagnostic form: relative to the directory holding charter.yaml.
    path: str | None
    template: str | None
    # For a variant: the field values that make a note this variant.
    selection: dict[str, Any] | None
    # For a kind: its variants.
    variants: tuple[VariantReference, ...]
    # Severity of a field the shape does not declare; None when undeclared fields are allowed.
    unknown_fields: str | None
    count: int | None
    contiguous: str | None
    # Left out of the JSON when the kind declares none, so contracts without one describe as before.
    structure_cutoff: StructureCutoff | None
    fields: tuple[FieldDescription, ...]
    # None when the shape has no path, so `charter new` cannot place a note of it.
    new_command: str | None
    # The template's guidance before its first heading.
    lead: str | None
    outline: tuple[OutlineEntry, ...]


@dataclass(frozen=True)
class PolicyDescription:
    # Relative to the KB root.
    glob: str
    settings: dict[str, Any]


@dataclass(frozen=True)
class CheckDescription:
    id: str
    enabled: bool
    # The contract's override of the check's base severities; None keeps them.
    severity: str | None
    # Empty for a plugin, whose codes are whatever it reports under its id.
    codes: tuple[str, ...]
    # A plugin's directory, relative to the directory holding charter.yaml; None for a built-in check.
    source: str | None


@dataclass(frozen=True)
class PluginRules:
    id: str
    description: str | None
    # The plugin's `docs` file: Markdown with LF line endings, no byte order mark and no surrounding blank lines.
    docs: str | None


@dataclass(frozen=True)
class Description:
    # Whether this covers the whole contract, with path policies and checks, or only the kinds asked for.
    whole: bool
    root: str
    kinds: tuple[ShapeDescription, ...]
    paths: tuple[PolicyDescription, ...]
    checks: tuple[CheckDescription, ...]
    plugin_rules: tuple[PluginRules, ...]
    # Whether the contract guard is on (`agents.guard`); shown only in a whole description.
    guard: bool = False


def build_description(contract: Contract, named: str | None = None) -> Description:
    """The whole contract, or only `named` (`kind`, with its variants, or `kind/variant`). Raises Refused."""
    if named is None:
        shapes = [shape for kind in contract.kinds.values() for shape in _kind_shapes(contract, kind)]
        return Description(
            whole=True,
            root=contract.root_path,
            kinds=tuple(_shape_description(contract, shape) for shape in shapes),
            paths=tuple(PolicyDescription(glob, settings) for glob, settings in contract.paths.declared.items()),
            checks=(
                *(
                    _check_description(contract, check.id, check.codes)
                    for check in BUILTIN_CHECKS
                    # A standalone knowledge base's description never mentions the agent layer.
                    if check.id != AGENTS_INCLUDE or contract.agent_layer_on
                ),
                *(_check_description(contract, plugin.id, (), plugin.source) for plugin in contract.plugins.values()),
            ),
            plugin_rules=_plugin_rules(contract.plugins.values(), None),
            guard=contract.agent_guard,
        )
    kind, variant = named_shape(contract, named)
    shapes = _kind_shapes(contract, kind) if variant is None else [_shape_of(contract, kind, variant)]
    return Description(
        whole=False,
        root=contract.root_path,
        kinds=tuple(_shape_description(contract, shape) for shape in shapes),
        paths=(),
        checks=(),
        plugin_rules=_plugin_rules(contract.plugins.values(), kind.name),
    )


def _plugin_rules(plugins: Iterable[Plugin], kind: str | None) -> tuple[PluginRules, ...]:
    """What the plugins say about their rules; with `kind`, only the plugins that run for it."""
    return tuple(
        PluginRules(plugin.id, plugin.description, plugin.docs)
        for plugin in plugins
        if (plugin.description or plugin.docs is not None) and (kind is None or plugin.runs_for_kind(kind))
    )


def _kind_shapes(contract: Contract, kind: Kind) -> list[Shape]:
    return [_shape_of(contract, kind, None), *(_shape_of(contract, kind, v) for v in kind.variants.values())]


def _shape_of(contract: Contract, kind: Kind, variant: Variant | None) -> Shape:
    return contract.shape_of({contract.discriminator: kind.name, **_selection(variant)})


def _selection(variant: Variant | None) -> dict[str, Any]:
    # A variant's conditions each fix one value.
    return {condition.field: condition.values[0] for condition in variant.selection} if variant is not None else {}


def _shape_description(contract: Contract, shape: Shape) -> ShapeDescription:
    kind, variant = shape.kind, shape.variant
    own_description = variant.description if variant is not None else None
    return ShapeDescription(
        name=shape.name,
        kind=kind.name,
        variant=variant.name if variant is not None else None,
        description=own_description or kind.description,
        path=contract.under_root(shape.path.text.replace("\\", "/")) if shape.path is not None else None,
        template=shape.template.path if shape.template is not None else None,
        selection=_selection(variant) if variant is not None else None,
        variants=tuple(
            VariantReference(f"{kind.name}/{other.name}", _selection(other))
            for other in (kind.variants.values() if variant is None else ())
        ),
        unknown_fields=str(kind.unknown_fields) if kind.unknown_fields is not None else None,
        count=kind.collection.count if kind.collection is not None else None,
        contiguous=kind.collection.contiguous if kind.collection is not None else None,
        structure_cutoff=kind.structure_cutoff if shape.template is not None else None,
        fields=_field_descriptions(contract, shape),
        new_command=new_command(contract, shape) if shape.path is not None else None,
        lead=shape.template.lead if shape.template is not None else None,
        outline=_outline(shape.template),
    )


def _field_descriptions(contract: Contract, shape: Shape) -> tuple[FieldDescription, ...]:
    fixed = {contract.discriminator: shape.kind.name, **_selection(shape.variant)}
    selects: dict[str, list[VariantChoice]] = {}
    if shape.variant is None:
        for variant in shape.kind.variants.values():
            for name, value in _selection(variant).items():
                selects.setdefault(name, []).append(VariantChoice(value, f"{shape.kind.name}/{variant.name}"))
    fields = dict(shape.fields)
    # A note always names its kind, whether or not the contract declares the field.
    fields.setdefault(contract.discriminator, Field(contract.discriminator, "string", required=True))
    ordered = [fields.pop(contract.discriminator), *fields.values()]
    return tuple(
        _field_description(
            field,
            shape.kind.allowed_values(field),
            discriminator=field.name == contract.discriminator,
            fixed=fixed.get(field.name),
            selects=tuple(selects.get(field.name, ())),
        )
        for field in ordered
    )


def _field_description(
    field: Field, choices: tuple[str, ...] | None, *, discriminator: bool, fixed: Any, selects: tuple[VariantChoice, ...]
) -> FieldDescription:
    return FieldDescription(
        name=field.name,
        type=field.type,
        of=field.of,
        required=field.required,
        required_when=describe_all(field.required_when) or None,
        allowed_when=describe_all(field.allowed_when) or None,
        values=choices,
        range=field.range,
        pattern=field.pattern.pattern if field.pattern is not None else None,
        to=field.to,
        unique=field.unique,
        matches_filename=field.matches_filename,
        width=field.width,
        default=field.default,
        auto=field.auto,
        discriminator=discriminator,
        fixed=fixed,
        selects=selects,
        expects=field.describe(choices),
        description=field.description,
    )


def _outline(template: Template | None) -> tuple[OutlineEntry, ...]:
    return tuple(
        OutlineEntry(section.heading.level, section.heading.text, section.optional, section.repeat, section.guide)
        for section in (template.outline if template is not None else ())
    )


def _check_description(
    contract: Contract, check_id: str, codes: Iterable[str], source: str | None = None
) -> CheckDescription:
    config = contract.check_config(check_id)
    return CheckDescription(
        check_id,
        config.enabled,
        str(config.severity) if config.severity is not None else None,
        tuple(sorted(codes)),
        source,
    )


# JSON


def to_json(description: Description) -> str:
    document: dict[str, Any] = {
        "format": JSON_FORMAT_ID,
        "root": description.root,
        "kinds": [_shape_json(shape) for shape in description.kinds],
    }
    if description.whole:
        document["paths"] = [asdict(policy) for policy in description.paths]
        document["checks"] = [asdict(check) for check in description.checks]
        document["guard"] = description.guard
    document["plugin_rules"] = [asdict(rules) for rules in description.plugin_rules]
    return json.dumps(document, indent=2, ensure_ascii=False, default=_iso_date) + "\n"


def _shape_json(shape: ShapeDescription) -> dict[str, Any]:
    document = asdict(shape)
    if shape.structure_cutoff is None:
        del document["structure_cutoff"]
    return document


def _iso_date(value: Any) -> str:
    # Dates (a `default`, or a value selecting a variant) are the only values JSON has no type for.
    if isinstance(value, datetime.date):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} has no JSON form")


# Markdown


def to_markdown(description: Description) -> str:
    """The whole contract under `# Kinds`, `# Path policies`, `# Checks` and, when it is on, `# Contract guard`;
    selected kinds as top-level sections.

    Either way, plugin rule docs follow under `# Plugin rules`.
    """
    if not description.whole:
        lines = [line for shape in description.kinds for line in _shape_lines(shape, "#")]
        lines.extend(_plugin_rule_lines(description.plugin_rules))
        return "\n".join(lines)
    lines = ["# Kinds", ""]
    if description.kinds:
        lines.extend(line for shape in description.kinds for line in _shape_lines(shape, "##"))
    else:
        lines.extend(["No kinds are declared.", ""])
    lines.extend(_policy_lines(description))
    lines.extend(_check_lines(description.checks))
    lines.extend(_guard_lines(description.guard))
    lines.extend(_plugin_rule_lines(description.plugin_rules))
    return "\n".join(lines)


def _guard_lines(guard: bool) -> Iterator[str]:
    if not guard:
        return
    # Imported here: only a contract with the guard on needs the hook module and its shell reader.
    from charter.guard import typed_skills

    yield "# Contract guard"
    yield ""
    yield (
        f"The contract guard is on. In Claude Code with the charter plugin, a write to `{CONTRACT_FILENAME}` is "
        f"refused unless the human typed {typed_skills()} in that session. An agent cannot start those skills, "
        "and a yes in the conversation does not lift the guard: when the contract needs to change, stop and ask the "
        "human to run `/charter:evolve`."
    )
    yield ""


_UNDECLARED = {"error": "an error", "warning": "a warning", None: "allowed"}


def _shape_lines(shape: ShapeDescription, heading: str) -> Iterator[str]:
    yield f"{heading} `{shape.name}`"
    yield ""
    if shape.description:
        yield shape.description
        yield ""
    if shape.selection is not None:
        yield f"- Variant of `{shape.kind}`: a `{shape.kind}` note is this variant when {_conditions(shape.selection)}."
    yield f"- Path: `{shape.path}`." if shape.path is not None else "- Path: none declared."
    if shape.template is not None:
        yield f"- Template: `{shape.template}`."
    if shape.structure_cutoff is not None:
        cutoff = shape.structure_cutoff
        yield (
            f"- Structure cutoff: a note whose `{cutoff.field}` is before {cutoff.date.isoformat()} is a legacy note "
            "and is not checked against the template's headings; every other note, one without a valid date "
            "included, is."
        )
    yield f"- Undeclared fields: {_UNDECLARED[shape.unknown_fields]}."
    collection = [
        *([f"exactly {shape.count} notes"] if shape.count is not None else []),
        *([f"`{shape.contiguous}` values run without gaps"] if shape.contiguous is not None else []),
    ]
    if collection:
        yield f"- All `{shape.kind}` notes together: {', '.join(collection)}."
    if shape.variants:
        yield "- Variants, each with its own section: a note with these values is the variant, not the plain kind."
        yield from (f"  - `{variant.name}`: {_conditions(variant.selection)}." for variant in shape.variants)
    yield ""
    if shape.new_command is not None:
        yield "Create one with:"
        yield ""
        yield "```"
        yield shape.new_command
        yield "```"
        if shape.variants:
            yield ""
            yield "A value that selects a variant creates that variant instead: use the variant's own command."
    else:
        yield "`charter new` cannot create one: it has no path."
    yield ""
    yield f"{heading}# Fields"
    yield ""
    yield "| Field | Required | Value | Description |"
    yield "|---|---|---|---|"
    for field in shape.fields:
        cells = (f"`{field.name}`", _required(field), _value(field, shape), field.description or "")
        yield "| " + " | ".join(_cell(cell) for cell in cells) + " |"
    yield ""
    if shape.lead is not None or shape.outline:
        yield f"{heading}# Body outline"
        yield ""
        if shape.lead is not None:
            yield shape.lead
            yield ""
        yield from (_outline_line(entry) for entry in shape.outline)
        yield ""


def _conditions(selection: dict[str, Any]) -> str:
    return " and ".join(f"`{name}` is `{yaml_text(value)}`" for name, value in selection.items())


def _required(field: FieldDescription) -> str:
    if field.required:
        return "yes"
    if field.required_when is not None:
        return f"when {field.required_when}"
    return "no"


def _value(field: FieldDescription, shape: ShapeDescription) -> str:
    if field.discriminator:
        return f"names the kind: always `{shape.kind}`"
    if field.fixed is not None:
        return f"always `{yaml_text(field.fixed)}`, which makes the note this variant"
    notes = [field.expects]
    notes.extend(f"`{yaml_text(choice.value)}` makes it `{choice.variant}`" for choice in field.selects)
    if field.allowed_when is not None:
        notes.append(f"allowed only when {field.allowed_when}")
    if field.unique:
        notes.append(f"unique among `{shape.kind}` notes")
    if field.width is not None:
        notes.append(f"written zero padded to {field.width} digits (`1` is `{zero_padded(1, field.width)}`)")
    if field.matches_filename:
        notes.append("matches its part of the file name")
    if field.default is not None:
        notes.append(f"default `{yaml_text(field.default)}`")
    if field.auto == TODAY:
        notes.append("`charter new` fills in today's date")
    elif field.auto == NEXT:
        notes.append("`charter new` fills in the next free value")
    return "; ".join(notes)


def _outline_line(entry: OutlineEntry) -> str:
    markers = "".join(f" ({marker})" for marker, on in (("optional", entry.optional), ("repeat", entry.repeat)) if on)
    guide = f": {entry.guide}" if entry.guide is not None else ""
    return f"- {code_span('#' * entry.level + ' ' + entry.text)}{markers}{guide}"


def _cell(text: str) -> str:
    # A bare `|` would end the cell, even inside a code span.
    return text.replace("|", "\\|")


def _policy_lines(description: Description) -> Iterator[str]:
    yield "# Path policies"
    yield ""
    if not description.paths:
        yield "No path policies are declared."
        yield ""
        return
    root = "the directory holding charter.yaml" if description.root == "." else f"`{description.root}`"
    yield (
        f"Globs are relative to the knowledge-base root, {root}; the paths above are relative to the directory "
        "holding charter.yaml. Each key takes its value from the most specific matching glob."
    )
    yield ""
    yield "| Glob | Policy |"
    yield "|---|---|"
    for policy in description.paths:
        meaning = "; ".join(POLICY_KEYS[key].meaning(value) for key, value in policy.settings.items())
        yield f"| {_cell(f'`{policy.glob}`')} | {_cell(meaning)} |"
    yield ""


def _check_lines(checks: tuple[CheckDescription, ...]) -> Iterator[str]:
    yield "# Checks"
    yield ""
    yield "| Check | Enabled | Severity | Codes |"
    yield "|---|---|---|---|"
    for check in checks:
        enabled = "yes" if check.enabled else "no"
        codes = code_list(check.codes) if check.source is None else f"`{check.id}/…`"
        yield f"| `{check.id}` | {enabled} | {check.severity or 'base'} | {codes} |"
    yield ""


def _plugin_rule_lines(rules: tuple[PluginRules, ...]) -> Iterator[str]:
    if not rules:
        return
    yield "# Plugin rules"
    yield ""
    for plugin in rules:
        yield f"## `{plugin.id}`"
        yield ""
        if plugin.description:
            yield plugin.description
            yield ""
        if plugin.docs is not None:
            yield from _nested(_atx(_without_front_matter(plugin.docs.split("\n"))), 2)
            yield ""


_FRONT_MATTER_LINE = re.compile(r"^(\s*$|#|[ \t]|-[ \t]|[\w.-]+[ \t]*:([ \t]|$))")


def _without_front_matter(lines: list[str]) -> list[str]:
    """The lines without a leading `---` block, which Markdown would fold into a heading and a stray rule.

    The block is dropped only when it is closed by a second `---` line and every line between looks like front
    matter (blank, comment, `key: value`, list item or continuation). A real thematic break followed by prose and
    a later `---` divider would otherwise lose its content, so any other document is left as written.
    """
    if not lines or lines[0].rstrip() != "---":
        return lines
    for number in range(1, len(lines)):
        if lines[number].rstrip() == "---":
            rest = lines[number + 1 :]
            while rest and not rest[0].strip():
                rest = rest[1:]
            return rest
        if not _FRONT_MATTER_LINE.match(lines[number]):
            break
    return lines


class _Heading(NamedTuple):
    level: int
    indent: int


def _nested(lines: list[str], level: int) -> list[str]:
    """Markdown whose headings are moved down so the shallowest sits just below a heading of `level`.

    Markdown has no heading below level 6, so deeper ones stay at 6.
    """
    view = parse_body(lines, 0).uncommented
    headings: dict[int, _Heading] = {}
    for number, line in enumerate(lines):
        # Up to three spaces of indent still make a heading; four make a code block, which `view` has blanked.
        indent = len(line) - len(line.lstrip(" "))
        parsed = heading(view[number][indent:], number) if indent <= 3 else None
        # A heading that follows a comment on its line is left as written rather than rewritten around the comment.
        if parsed and line[indent:].startswith("#" * parsed.level):
            headings[number] = _Heading(parsed.level, indent)
    if not headings:
        return lines
    shift = level + 1 - min(found.level for found in headings.values())
    # The indent stays, so a heading inside a list item remains part of it.
    return [
        " " * headings[number].indent
        + "#" * min(headings[number].level + shift, 6)
        + line[headings[number].indent + headings[number].level :]
        if number in headings
        else line
        for number, line in enumerate(lines)
    ]


_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")


def _atx(lines: list[str]) -> list[str]:
    """The lines with each setext heading, a paragraph underlined with `===` or `---`, written as one ATX line."""
    # Code and comments are blank here, so they end paragraphs and underline nothing.
    view = parse_body(lines, 0).uncommented
    result: list[str] = []
    start = 0
    for number, line in enumerate(lines):
        underline = _SETEXT_UNDERLINE.match(view[number])
        paragraph = view[start:number]
        # Below a list item or quote, `---` is a thematic break; an ATX heading is never underlined.
        plain = not any(LIST_ITEM.match(text) or text.lstrip()[:1] in "#>" for text in paragraph)
        if underline and paragraph and plain:
            level = 1 if underline.group(1)[0] == "=" else 2
            del result[-len(paragraph) :]
            result.append(f"{'#' * level} {' '.join(' '.join(paragraph).split())}")
            start = number + 1
            continue
        result.append(line)
        if not view[number].strip():
            start = number + 1
    return result
