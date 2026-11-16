"""Loading and validating charter.yaml."""

import dataclasses
import datetime
import os
import posixpath
import unicodedata
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Protocol

import yaml

from charter import yamlsource
from charter.diagnostics import SEVERITY_NAMES, Diagnostic, Severity, code_list, suggestion
from charter.fields import (
    FIELD_SCHEMA,
    VOCABULARIES_SCHEMA,
    Condition,
    Field,
    Invalid,
    all_hold,
    declared_type,
    fixed_value_problem,
    is_list,
    link_targets,
    parse_field,
    same_value,
    spec_problems,
)
from charter.fieldtypes import FIELD_TYPES
from charter.files import contract_relative
from charter.links import STRATEGIES, STYLES, LinkSettings
from charter.lock import LOCK_FILENAME, Locked, LockError, parse_lock
from charter.pathpattern import (
    SUFFIX_FILTER,
    PathPattern,
    PatternError,
    Unrenderable,
    Unsafe,
    segment_problem,
    text_of,
)
from charter.pathpolicy import POLICY_KEYS, PathPolicies, Setting
from charter.plugin import Plugin, load_plugins
from charter.schemacheck import errors as schema_errors
from charter.schematext import dotted, schema_message
from charter.tags import TagSettings
from charter.template import DATE, Template, TemplateError, parse_template
from charter.tree import Tree, WorkingTree, decode

CONTRACT_FILENAME = "charter.yaml"
# The kind key holding the table the `suffix` filter maps values through.
_SUFFIX_TABLE = "suffix"
# How a `variant_by` field the kind does not declare is declared for it.
_IMPLICIT_SELECTOR = {"type": "string", "required": True}

_VARIANT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "set": {"type": "object", "minProperties": 1},
        "path": {"type": "string", "minLength": 1},
        "template": {"type": "string", "minLength": 1},
        "fields": {"type": "object", "additionalProperties": FIELD_SCHEMA},
    },
    "additionalProperties": False,
}

_COLLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "minimum": 0},
        "contiguous": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
    "minProperties": 1,
}

# The date is checked in `_cutoff_problems`: a YAML date is not a JSON type.
_CUTOFF_SCHEMA = {
    "type": "object",
    "properties": {"field": {"type": "string", "minLength": 1}, "date": {}},
    "required": ["field", "date"],
    "additionalProperties": False,
}

_KIND_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "fields": {"type": "object", "additionalProperties": FIELD_SCHEMA},
        "unknown_fields": {"enum": ["error", "warn", "allow"]},
        "path": {"type": "string", "minLength": 1},
        "template": {"type": "string", "minLength": 1},
        _SUFFIX_TABLE: {"type": "object", "additionalProperties": {"type": "string"}},
        "variant_by": {"type": "string", "minLength": 1},
        "variants": {"type": "object", "minProperties": 1, "additionalProperties": _VARIANT_SCHEMA},
        "collection": _COLLECTION_SCHEMA,
        "structure_cutoff": _CUTOFF_SCHEMA,
    },
    "additionalProperties": False,
}

_NAMES_SCHEMA = {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "uniqueItems": True}

# A list of names, or a mapping that may also declare each field; branching on the
# shape keeps errors pointed at the offending entry rather than at the whole key.
_COMMON_FIELDS_SCHEMA = {
    "if": {"type": "array"},
    "then": _NAMES_SCHEMA,
    "else": {
        # Only non-lists reach here; naming both types makes the error read "expected a list or a mapping".
        "type": ["array", "object"],
        "additionalProperties": {"if": {"type": "null"}, "else": FIELD_SCHEMA},
    },
}

_PATH_POLICY_SCHEMA = {
    "type": "object",
    "properties": {key: policy_key.schema for key, policy_key in POLICY_KEYS.items()},
    "additionalProperties": False,
}

_LINKS_SCHEMA = {
    "type": "object",
    "properties": {
        "styles": {"type": "array", "items": {"enum": list(STYLES)}, "minItems": 1, "uniqueItems": True},
        "resolve": {"type": "array", "items": {"enum": list(STRATEGIES)}, "minItems": 1, "uniqueItems": True},
        "check_anchors": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "allow": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
        "inline": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean"},
        "severity": {"enum": [str(s) for s in Severity]},
        "source": {"type": "string", "minLength": 1},
        "with": {"type": "object"},
    },
    "additionalProperties": False,
}
_CHECKS_SCHEMA = {"type": "object", "additionalProperties": _CHECK_SCHEMA}

# YAML 1.1 reads an unquoted `off` as false, so false means `off` too.
_PROFILE_SCHEMA = {
    "type": "object",
    "propertyNames": {"minLength": 1},
    "additionalProperties": {"if": {"const": False}, "else": {"enum": [*(str(s) for s in Severity), "off"]}},
}

CONTRACT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "charter": {"const": 1},
        "root": {"type": "string", "minLength": 1},
        "discriminator": {"type": "string", "minLength": 1},
        "links": _LINKS_SCHEMA,
        "tags": _TAGS_SCHEMA,
        "paths": {
            "type": "object",
            "propertyNames": {"pattern": r"[^/\\]"},
            "additionalProperties": _PATH_POLICY_SCHEMA,
        },
        "vocabularies": VOCABULARIES_SCHEMA,
        "common_fields": _COMMON_FIELDS_SCHEMA,
        "agent_files": _NAMES_SCHEMA,
        "agents": {
            "type": "object",
            "properties": {"file": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "docs": {
            "type": "object",
            "properties": {"output": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "kinds": {"type": "object", "additionalProperties": _KIND_SCHEMA},
        "checks": _CHECKS_SCHEMA,
        "profiles": {"type": "object", "additionalProperties": _PROFILE_SCHEMA},
    },
    "required": ["charter", "kinds"],
    "additionalProperties": False,
}


DEFAULT_AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
DEFAULT_DOCS_OUTPUT = "CHARTER.md"
DEFAULT_AGENTS_FILE = "AGENTS.md"
AGENTS_INCLUDE = "agents-include"


def declared_paths(data: object) -> tuple[str, str]:
    """The rulebook and agents file a contract's data names, their defaults where it does not. Tolerates data that
    has not been validated (a section that is not a mapping, a path that is not text), which count as not named."""

    def declared(section: str, key: str, default: str) -> str:
        value = data.get(section) if isinstance(data, dict) else None
        value = value.get(key) if isinstance(value, dict) else None
        return value if isinstance(value, str) else default

    return declared("docs", "output", DEFAULT_DOCS_OUTPUT), declared("agents", "file", DEFAULT_AGENTS_FILE)


@dataclass(frozen=True)
class Variant:
    name: str
    # Declared over the kind's fields, replacing any of the same name.
    fields: dict[str, Field]
    # None keeps the kind's path.
    path: PathPattern | None
    # None keeps the kind's template.
    template: Template | None
    # A note is this variant when all of these hold: its `set` values, or its name as the `variant_by` value.
    selection: tuple[Condition, ...]
    description: str | None = None


@dataclass(frozen=True)
class KindCollection:
    """What the notes of a kind must add up to, taken together."""

    count: int | None
    # An int field whose values must run without gaps.
    contiguous: str | None
    # Where each is declared in the contract file: findings about the whole collection point there.
    count_line: int | None
    contiguous_line: int | None


@dataclass(frozen=True)
class StructureCutoff:
    """Notes whose `field` holds a date before `date` are legacy notes: the template's headings are not judged."""

    field: str
    date: datetime.date


@dataclass(frozen=True)
class Kind:
    name: str
    fields: dict[str, Field]
    # Severity of `schema/unknown-field` for this kind; None when unknown fields are allowed.
    unknown_fields: Severity | None
    # Where a note of this kind belongs, rendered from its fields; None places no constraint.
    path: PathPattern | None
    # The field whose value names a note's variant; None selects variants by their `set` values.
    variant_by: str | None
    variants: dict[str, Variant]
    template: Template | None
    collection: KindCollection | None
    description: str | None = None
    structure_cutoff: StructureCutoff | None = None

    def allowed_values(self, field: Field) -> tuple[str, ...] | None:
        """A `variant_by` field takes the names of the variants; any other field its own allowed values."""
        return tuple(self.variants) if field.name == self.variant_by else field.values

    def variant_for(self, frontmatter: Mapping[str, Any]) -> Variant | None:
        # The contract guarantees that at most one variant's selection can hold.
        return next((v for v in self.variants.values() if all_hold(v.selection, frontmatter)), None)

    def unknown_variant(self, frontmatter: Mapping[str, Any]) -> str | None:
        """The `variant_by` value when it names no variant; a missing or mistyped one is the schema check's finding."""
        value = frontmatter.get(self.variant_by) if self.variant_by is not None else None
        return value if isinstance(value, str) and value and value not in self.variants else None


@dataclass(frozen=True)
class Shape:
    """What a note's kind, and its variant if it has one, require of it."""

    kind: Kind
    variant: Variant | None
    # The declared common fields, then the kind's, then the variant's; a later declaration wins.
    fields: dict[str, Field]
    path: PathPattern | None
    # A `variant_by` value that names no variant of the kind.
    unknown_variant: str | None
    template: Template | None

    def is_legacy(self, frontmatter: Mapping[str, Any]) -> bool:
        """Whether the note is dated before its kind's structure cutoff. A missing or mistyped date is not legacy."""
        cutoff = self.kind.structure_cutoff
        value = self.value_of(frontmatter, cutoff.field) if cutoff is not None else None
        return value is not None and value < cutoff.date

    @property
    def name(self) -> str:
        return self.kind.name if self.variant is None else f"{self.kind.name}/{self.variant.name}"

    def value_of(self, frontmatter: Mapping[str, Any], name: str) -> Any:
        """The note's value of the single-value field `name`; None when absent, empty or not of the declared type."""
        field = self.fields.get(name)
        value = frontmatter.get(name)
        if field is None or field.type == "list" or not _present(value):
            return None
        return value if FIELD_TYPES[field.type].accepts(value) else None

    def field_texts(self, frontmatter: Mapping[str, Any]) -> dict[str, str | None]:
        """Each declared single-value field present in `frontmatter` as path text; None when mistyped."""
        texts: dict[str, str | None] = {}
        for name, field in self.fields.items():
            if field.type != "list" and _present(frontmatter.get(name)):
                value = self.value_of(frontmatter, name)
                texts[name] = text_of(value) if value is not None else None
        return texts


def _present(value: Any) -> bool:
    return value is not None and value != ""


@dataclass(frozen=True)
class Mismatch:
    """A `matches_filename` field whose text differs from its part of the note's path."""

    field: str
    text: str
    in_path: str
    # Where the note belongs, in diagnostic form.
    expected: str


@dataclass(frozen=True)
class Misplacement:
    """Why a note is not where its fields say it belongs: at most one of these is set."""

    unsafe: Unsafe | None = None
    mismatches: tuple[Mismatch, ...] = ()
    # The rendered path, when neither of the above explains the difference more precisely.
    expected: str | None = None


@dataclass(frozen=True)
class CheckConfig:
    enabled: bool = True
    severity: Severity | None = None
    # A plugin's directory, as written.
    source: str | None = None
    # `with`, read-only. An optional check's is valid against its `params_schema`; a plugin's against its manifest.
    params: Mapping[str, Any] = dataclasses.field(default_factory=lambda: MappingProxyType({}))


class OptionalCheck(Protocol):
    """A shipped check that stays off until `checks:` enables it, and that may take parameters (`with`)."""

    # JSON Schema for `checks.<id>.with`.
    params_schema: dict[str, Any]

    def contract_problems(
        self, params: Mapping[str, Any], shapes: Sequence["DeclaredShape"], invalid: Invalid
    ) -> Iterable[Diagnostic]:
        """What keeps the check from working with this contract, once enabled with valid `params`."""
        ...


# Profile keys are diagnostic codes or check ids; None turns the diagnostic off.
ProfileSeverities = dict[str, Severity | None]


@dataclass(frozen=True)
class PluginSettings:
    """What `charter plugin` manages. A Contract is one; `load_plugin_settings` reads one from a contract that may
    be invalid anywhere but in `checks:`, so that a plugin which made it invalid can still be disabled, updated
    or removed."""

    # The contract file itself, in diagnostic form.
    file: str
    base_dir: Path
    checks: dict[str, CheckConfig]
    # charter.lock's plugins by id.
    locked: dict[str, Locked]

    @property
    def plugin_ids(self) -> list[str]:
        """Every check with a `source`, and every plugin in the lock."""
        return sorted({*(i for i, config in self.checks.items() if config.source is not None), *self.locked})

    def check_config(self, check_id: str) -> CheckConfig:
        return self.checks.get(check_id, CheckConfig())


@dataclass(frozen=True)
class Contract(PluginSettings):
    root: Path
    discriminator: str
    kinds: dict[str, Kind]
    paths: PathPolicies
    # Valid on every kind; None where the contract names the field without declaring it.
    common_fields: dict[str, Field | None]
    # Filenames (`agent_files:`) that need no kind at any depth; any number of them may exist.
    agent_file_names: frozenset[str]
    # In diagnostic form, so it compares directly with a note's path. Defaulted even when no rulebook is generated.
    docs_output: str
    # Whether the contract declares a `docs:` section.
    docs_declared: bool
    # The one agent-instruction file (`agents.file`) that must link to docs_output, in diagnostic form; None
    # when the contract declares no `agents:` section, which leaves the agent layer off.
    agents_file: str | None
    # Enabled external plugins by check id.
    plugins: dict[str, Plugin]
    profiles: dict[str, ProfileSeverities]
    links: LinkSettings
    tags: TagSettings
    # Where the contract, its templates and the knowledge base are read from.
    tree: Tree
    # Optional checks: off unless `checks:` enables them.
    off_by_default: frozenset[str]

    def check_config(self, check_id: str) -> CheckConfig:
        return self.checks.get(check_id, CheckConfig(enabled=check_id not in self.off_by_default))

    @property
    def agent_layer_on(self) -> bool:
        """Whether the contract declares `agents:`: the agent files, the rulebook link and `agents-include`."""
        return self.agents_file is not None

    @property
    def rulebook_generated(self) -> bool:
        """Whether `charter docs` has a rulebook to write: the contract declares `docs:` or the agent layer."""
        return self.docs_declared or self.agent_layer_on

    @property
    def root_path(self) -> str:
        """The KB root in diagnostic form (`.` when it is the contract's own directory)."""
        return self.relative(self.root)

    def relative(self, path: Path) -> str:
        """The form every diagnostic uses for a path: POSIX, relative to base_dir."""
        return path.relative_to(self.base_dir).as_posix()

    def path_of(self, file: Path) -> str | None:
        """`file` (relative to the working directory, or absolute) in diagnostic form; None outside base_dir."""
        # Lexical first so a symlinked root keeps its path; resolved second for a symlinked working directory.
        typed = Path(os.path.abspath(file))
        if typed.is_relative_to(self.base_dir):
            return self.relative(typed)
        # Reached through a link to the contract folder (a symlinked parent, or `link -> .` inside it): the
        # outermost ancestor that is the contract folder gives the path form discovery shows without `--config`.
        try:
            for ancestor in reversed(typed.parents):
                if ancestor.is_dir() and ancestor.samefile(self.base_dir):
                    return typed.relative_to(ancestor).as_posix()
        except OSError:
            pass
        resolved = file.resolve()
        return self.relative(resolved) if resolved.is_relative_to(self.base_dir) else None

    def path_policy(self, path: str) -> dict[str, Setting]:
        """Effective `paths:` settings for `path`, given in diagnostic form (relative to base_dir)."""
        below = self._below_root(path)
        if below is None:
            raise ValueError(f"{path!r} is not under root {self.root_path!r}")
        return self.paths.resolve(below)

    def _below_root(self, path: str) -> str | None:
        """`path` relative to root, or None when it is not under root; a path in another normal form still counts."""
        posix = PurePosixPath(path)
        if posix.is_relative_to(self.root_path):
            return posix.relative_to(self.root_path).as_posix()
        # `root` stays as written for file access; only this comparison takes the NFC form, as `misplacement` does.
        nfc, root = PurePosixPath(unicodedata.normalize("NFC", path)), PurePosixPath(self.root_nfc)
        return nfc.relative_to(root).as_posix() if nfc.is_relative_to(root) else None

    @property
    def root_nfc(self) -> str:
        """`root_path` in NFC, for comparing with NFC note paths; `root` itself stays as written for file access."""
        return unicodedata.normalize("NFC", self.root_path)

    def ignores(self, path: str) -> bool:
        ignore = self.path_policy(path).get("ignore")
        return ignore is not None and ignore.value

    def holds(self, path: str) -> bool:
        """Whether `path` (diagnostic form) is part of the knowledge base: under root and not ignored."""
        return self._below_root(path) is not None and not self.ignores(path)

    def skips_links(self, path: str) -> bool:
        return "links" in self.path_policy(path)

    def sweeps(self, path: str) -> bool:
        sweep = self.path_policy(path).get("sweep")
        return sweep is None or sweep.value

    def kind_of(self, frontmatter: Mapping[str, Any]) -> Kind | None:
        kind_name = frontmatter.get(self.discriminator)
        return self.kinds.get(kind_name) if isinstance(kind_name, str) else None

    def shape_of(self, frontmatter: Mapping[str, Any]) -> Shape | None:
        """The kind and variant a note's frontmatter selects, with what they declare; None without a declared kind."""
        kind = self.kind_of(frontmatter)
        if kind is None:
            return None
        variant = kind.variant_for(frontmatter)
        own = variant.fields if variant is not None else {}
        path = variant.path if variant is not None and variant.path is not None else kind.path
        template = variant.template if variant is not None and variant.template is not None else kind.template
        return Shape(
            kind, variant, {**self.kind_fields(kind), **own}, path, kind.unknown_variant(frontmatter), template
        )

    def template_of(self, frontmatter: Mapping[str, Any]) -> Template | None:
        """The template a note's body keeps to; None without a declared kind or a template for its shape."""
        shape = self.shape_of(frontmatter)
        return shape.template if shape is not None else None

    def kind_fields(self, kind: Kind) -> dict[str, Field]:
        """The fields every note of `kind` has: the declared common fields, then the kind's own."""
        declared_common = {name: field for name, field in self.common_fields.items() if field is not None}
        return {**declared_common, **kind.fields}

    def rendered_path(self, shape: Shape, frontmatter: Mapping[str, Any]) -> str | Unsafe | Unrenderable | None:
        """Where a note of `shape` with this frontmatter belongs, in diagnostic form.

        Unsafe when a field's text cannot be part of a portable path; Unrenderable when a field the pattern
        needs is missing or mistyped (the schema check's finding); None when the shape has no path pattern.
        """
        if shape.path is None:
            return None
        rendered = shape.path.render(shape.field_texts(frontmatter))
        return self.under_root(rendered) if isinstance(rendered, str) else rendered

    def under_root(self, path: str) -> str:
        """`path`, relative to root, in diagnostic form."""
        return path if self.root_path == "." else f"{self.root_path}/{path}"

    def misplacement(self, path: str, shape: Shape, frontmatter: Mapping[str, Any]) -> Misplacement | None:
        """How a note at `path` (diagnostic form) disagrees with where its fields say it belongs; None if it doesn't."""
        texts = shape.field_texts(frontmatter)
        matched = [name for name, field in shape.fields.items() if field.matches_filename]
        # macOS file systems may hand back decomposed names; a path matches regardless of normal form.
        actual = PurePosixPath(unicodedata.normalize("NFC", path))

        if shape.path is None:
            mismatches = []
            for name in matched:
                text = texts.get(name)
                if text is None or text == actual.stem:
                    continue
                if problem := segment_problem(f"{text}.md"):
                    return Misplacement(unsafe=Unsafe(name, problem))
                mismatches.append(Mismatch(name, text, actual.stem, (actual.parent / f"{text}.md").as_posix()))
            return Misplacement(mismatches=tuple(mismatches)) if mismatches else None

        expected = self.rendered_path(shape, frontmatter)
        if isinstance(expected, Unsafe):
            return Misplacement(unsafe=expected)
        if isinstance(expected, Unrenderable) or unicodedata.normalize("NFC", expected) == actual.as_posix():
            return None
        found = shape.path.split(actual.relative_to(self.root_nfc).as_posix(), texts, matched) or []
        mismatches = tuple(Mismatch(name, texts[name], text, expected) for name, text in found if texts[name] != text)
        return Misplacement(mismatches=mismatches) if mismatches else Misplacement(expected=expected)

    def allows_untyped(self, path: str) -> bool:
        return (
            "untyped" in self.path_policy(path)
            or (self.rulebook_generated and path == self.docs_output)
            or (self.agent_layer_on and path == self.agents_file)
            or PurePosixPath(path).name in self.agent_file_names
        )


class ContractError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]):
        super().__init__("invalid contract")
        self.diagnostics = diagnostics


def _read_contract(config_path: Path, tree: Tree | None) -> tuple[Path, Tree, dict[str, Any], yaml.Node, Invalid]:
    """The resolved path, the tree it was read from (the working copy unless `tree` is given), the data and node
    tree of a contract that is a YAML mapping, and how to report a problem in it. Raises ContractError."""
    resolved = config_path.resolve()
    tree = tree or WorkingTree(resolved.parent)
    content = tree.read([resolved.name]).get(resolved.name)
    if content is None:
        raise ContractError([
            Diagnostic(
                path=config_path.name or CONTRACT_FILENAME,
                line=None,
                severity=Severity.ERROR,
                code="contract/not-found",
                message=f"No contract found at `{config_path.as_posix()}`.",
                hint="Check the `--config` path, or leave it out to use the nearest charter.yaml above the working directory.",
            )
        ])

    config_path = resolved

    def error(code: str, line: int | None, message: str, hint: str | None = None) -> Diagnostic:
        return Diagnostic(config_path.name, line, Severity.ERROR, code, message, hint)

    try:
        data, node = yamlsource.parse(decode(content))
    except UnicodeDecodeError:
        raise ContractError([error("contract/yaml", None, "The contract is not valid UTF-8 text.")]) from None
    except yamlsource.YamlSyntaxError as syntax:
        raise ContractError([error("contract/yaml", syntax.line, f"Invalid YAML: {syntax.message}.")]) from None

    if not isinstance(data, dict):
        raise ContractError([
            error(
                "contract/invalid",
                1,
                "The contract must be a YAML mapping.",
                "Start with `charter: 1` and a `kinds:` mapping.",
            )
        ])

    def invalid(location: Sequence[str | int], message: str, hint: str | None = None) -> Diagnostic:
        return error("contract/invalid", yamlsource.line_of(node, location), f"{_location(location)}: {message}", hint)

    return config_path, tree, data, node, invalid


def _off_by_default(data: Mapping[str, Any], optional_checks: Collection[str]) -> frozenset[str]:
    """The built-in checks that run only when `checks:` enables them; one rule for the strict and lenient loaders."""
    # `agents-include` belongs to the agent layer, so it is off until the contract declares `agents:`.
    return frozenset(optional_checks) | (frozenset() if "agents" in data else frozenset({AGENTS_INCLUDE}))


def load_plugin_settings(config_path: Path, *, optional_checks: Collection[str]) -> PluginSettings:
    """Raises ContractError when the contract cannot be read, `checks:` is invalid, or the lock is."""
    config_path, tree, data, _, invalid = _read_contract(config_path, None)
    checks = data.get("checks", {})
    problems = [
        invalid(["checks", *problem.absolute_path], *schema_message(problem))
        for problem in schema_errors(_CHECKS_SCHEMA, checks)
    ]
    if problems:
        raise ContractError(problems)
    base_dir = config_path.parent
    return PluginSettings(
        config_path.name, base_dir, _check_configs(checks, _off_by_default(data, optional_checks)), _read_locked(tree)
    )


def _check_configs(
    checks: Mapping[str, Mapping[str, Any]], off_by_default: Collection[str]
) -> dict[str, CheckConfig]:
    return {
        check_id: CheckConfig(
            enabled=config.get("enabled", check_id not in off_by_default),
            severity=Severity(config["severity"]) if "severity" in config else None,
            source=config.get("source"),
            params=MappingProxyType(dict(config.get("with") or {})),
        )
        for check_id, config in checks.items()
    }


def _read_locked(tree: Tree) -> dict[str, Locked]:
    try:
        return parse_lock(tree.read([LOCK_FILENAME]).get(LOCK_FILENAME))
    except LockError as error:
        raise ContractError(error.diagnostics) from None


def _has_link_part(base_dir: Path, relative: Path) -> bool:
    """Whether `relative`, or any folder on the way to it, is a symbolic link under `base_dir`."""
    parts = [*reversed(relative.parents), relative]
    return any((base_dir / part).is_symlink() for part in parts if part.parts)


def _missing_root(invalid: Invalid, written: str, root: Path, base_dir: Path, tree: Tree) -> Diagnostic:
    """Why `root` is no directory of `tree`. A git tree holds no empty directory and no entry for a link, so a
    directory that exists on disk is named for what it is. Only this failing path looks at the disk, and a failure
    is never reused by ContentMemo, so the disk is not part of any reused answer. It is the current checkout, not
    the commit being judged, so for an older commit in a range the message describes the checkout."""
    if not isinstance(tree, WorkingTree) and root.is_dir():
        if _has_link_part(base_dir, root.relative_to(base_dir)):
            return invalid(
                ["root"],
                f"`{written}` is a link, which the {tree.holder} cannot follow, so it holds no directory there.",
                "Point `root` at the folder the link leads to, or make it a real folder.",
            )
        return invalid(
            ["root"],
            f"no files under `{written}` in the {tree.holder}.",
            "A git tree holds no empty folders: add a file below it, then stage or commit it.",
        )
    return invalid(
        ["root"], f"directory `{written}` does not exist.", "`root` is the knowledge-base directory, relative to charter.yaml."
    )


def load_contract(
    config_path: Path,
    *,
    check_codes: Mapping[str, Collection[str]],
    core_codes: Collection[str],
    optional_checks: Mapping[str, OptionalCheck],
    tree: Tree | None = None,
) -> Contract:
    """Load and validate a contract. Raises ContractError carrying `contract/*` diagnostics.

    `check_codes` maps each check that exists to the codes it reports; `core_codes` are the codes
    reported outside any check. Together they are what `checks:` and `profiles:` may name. `optional_checks`
    are the built-in checks that stay off until `checks:` enables them, by id.
    The contract, its templates, the lock, the plugins and the knowledge base it governs are read from `tree`,
    by default the working copy.
    """
    config_path, tree, data, node, invalid = _read_contract(config_path, tree)
    problems = [
        invalid(list(problem.absolute_path), *schema_message(problem))
        for problem in schema_errors(CONTRACT_SCHEMA, data)
    ]
    if problems:
        raise ContractError(problems)

    base_dir = config_path.parent
    # Normalised lexically, not resolved, so a symlinked root still counts as inside base_dir. (A git tree has no
    # directory entry for a link, so a tree reports a root that is a link as one, not as missing.)
    root = Path(os.path.normpath(base_dir / data.get("root", ".")))
    if not root.is_relative_to(base_dir):
        raise ContractError([
            invalid(
                ["root"],
                f"`{data['root']}` is outside the directory holding charter.yaml.",
                "Diagnostic paths are relative to charter.yaml, so the knowledge base must sit beside or below it.",
            )
        ])
    # Asked of the tree the contract was read from, so a commit's root is judged by that commit, not the checkout.
    if not tree.is_directory(root.relative_to(base_dir).as_posix()):
        raise ContractError([_missing_root(invalid, data["root"], root, base_dir, tree)])

    # Before anything indexes or sorts by name: a non-text name would crash those, and no note could match it.
    if name_problems := list(_name_problems(data, node, invalid)):
        raise ContractError(name_problems)

    # Entries are matched against bare file names, so one with a separator would silently never match.
    if agent_file_problems := list(_agent_file_problems(data, invalid)):
        raise ContractError(agent_file_problems)

    declared_common = _declared_common_fields(data)
    docs_output, agents_file = declared_paths(data)
    agent_layer = "agents" in data
    off_by_default = _off_by_default(data, optional_checks)
    shapes = _declared_shapes(data, declared_common)
    path_patterns, pattern_problems = _parse_paths(shapes, invalid)
    templates, template_problems = _load_templates(shapes, tree, root.relative_to(base_dir).as_posix(), invalid)
    locked = _read_locked(tree)
    plugins, plugin_problems = load_plugins(
        data.get("checks", {}),
        check_codes,
        tree,
        node,
        invalid,
        locked,
        builtins_with_params=optional_checks,
        kinds=data["kinds"],
    )
    check_configs = _check_configs(data.get("checks", {}), off_by_default)
    semantic_problems = [
        *_field_problems(data, declared_common, shapes, invalid),
        *_description_problems(declared_common, shapes, invalid),
        *_variant_problems(data, shapes, invalid),
        *_collection_problems(shapes, invalid),
        *_cutoff_problems(shapes, invalid),
        *pattern_problems,
        *_path_problems(shapes, path_patterns, invalid),
        *_suffix_table_problems(shapes, path_patterns, invalid),
        *template_problems,
        *_placeholder_problems(shapes, templates, invalid),
        *_path_policy_problems(data, invalid),
        *plugin_problems,
        *_check_problems(data, check_codes, core_codes, invalid),
        *_optional_check_problems(optional_checks, check_configs, shapes, invalid),
    ]
    rulebook, agents = contract_relative(docs_output), contract_relative(agents_file)
    declared = ((["docs", "output"], docs_output, rulebook), (["agents", "file"], agents_file, agents))
    for location, path, relative in declared:
        if relative is None:
            semantic_problems.append(
                invalid(
                    location,
                    f"`{path}` is outside the directory holding charter.yaml.",
                    f"`{'.'.join(location)}` is a path relative to charter.yaml, beside or below it.",
                )
            )
    # `docs --link-agents` appends a line to agents.file, which would make a generated rulebook at the same path
    # stale. Compared in diagnostic form, so `./CHARTER.md`, `a//b.md` and backslash spellings are the same path.
    if agent_layer and rulebook is not None and rulebook == agents:
        agents_file_named = "file" in (data["agents"] or {})
        semantic_problems.append(
            invalid(
                ["agents", "file"] if agents_file_named else ["docs", "output"],
                f"`agents.file` and `docs.output` name the same file, `{rulebook}`.",
                "The rulebook is generated and the agents file is hand-written; give them different paths.",
            )
        )
    if semantic_problems:
        raise ContractError(semantic_problems)

    vocabularies = data.get("vocabularies", {})
    links = data.get("links", {})
    tags = data.get("tags", {})
    return Contract(
        file=config_path.name,
        base_dir=base_dir,
        root=root,
        discriminator=data.get("discriminator", "kind"),
        kinds=_kinds(shapes, path_patterns, templates, vocabularies, node),
        paths=PathPolicies(data.get("paths", {})),
        common_fields={
            name: parse_field(
                name,
                declared_common[name],
                declared_common,
                vocabularies,
                yamlsource.line_of(node, ("common_fields", name)),
            )
            if name in declared_common
            else None
            for name in data.get("common_fields", ())
        },
        agent_file_names=frozenset(data.get("agent_files", DEFAULT_AGENT_FILES)),
        docs_output=contract_relative(docs_output),
        docs_declared="docs" in data,
        agents_file=contract_relative(agents_file) if agent_layer else None,
        checks=check_configs,
        plugins=plugins,
        locked=locked,
        profiles={
            name: {key: SEVERITY_NAMES["off" if value is False else value] for key, value in severities.items()}
            for name, severities in data.get("profiles", {}).items()
        },
        links=LinkSettings(
            styles=tuple(links.get("styles", STYLES)),
            resolve=tuple(links.get("resolve", STRATEGIES)),
            check_anchors=links.get("check_anchors", False),
        ),
        tags=TagSettings(
            allow=tuple(tags["allow"]) if "allow" in tags else None,
            inline=tags.get("inline", False),
        ),
        tree=tree,
        off_by_default=off_by_default,
    )


@dataclass(frozen=True, eq=False)
class DeclaredShape:
    """A kind, or one of its variants, as charter.yaml declares it."""

    kind: str
    # None for the kind itself.
    variant: str | None
    location: tuple[str, ...]
    # The kind's or the variant's own mapping.
    spec: dict
    # Declared at this level: the kind's fields (with an implicit `variant_by` field), or the variant's.
    own_fields: dict[str, dict]
    # What the own fields' conditions may name: the kind's fields, then the variant's.
    siblings: dict[str, dict]
    # Every field a note of this shape has: the declared common fields, then the siblings.
    fields: dict[str, dict]
    # The field values that make a note this variant; empty for a kind.
    selection: dict[str, Any]
    # For a variant, its kind's shape.
    parent: "DeclaredShape | None"

    @property
    def kind_spec(self) -> dict:
        return self.spec if self.parent is None else self.parent.spec

    @property
    def inherits_path(self) -> bool:
        return self.parent is not None and "path" not in self.spec


def _name_problems(data: dict, node: yaml.Node | None, invalid: Invalid) -> Iterator[Diagnostic]:
    """Kind, variant and field names YAML reads as something other than text (`1`, `yes`, `on`, a date)."""
    locations: list[list[str]] = [["kinds"], ["common_fields"]]
    for kind_name, kind in data["kinds"].items():
        if not isinstance(kind_name, str):
            continue
        locations += [["kinds", kind_name, "fields"], ["kinds", kind_name, "variants"]]
        for variant_name in kind.get("variants", {}):
            if isinstance(variant_name, str):
                variant = ["kinds", kind_name, "variants", variant_name]
                # `set` names fields too.
                locations += [[*variant, "fields"], [*variant, "set"]]
    for location in locations:
        for key in yamlsource.non_text_keys(node, location):
            problem = invalid(
                [*location, key.text],
                f"the name `{key.text}` is not text; YAML reads it as {key.read_as}.",
                f'Quote it: `"{key.text}"`.',
            )
            # The location shows the key as written, which line_of cannot look up for an empty key.
            yield dataclasses.replace(problem, line=key.line)


def _agent_file_problems(data: dict, invalid: Invalid) -> Iterator[Diagnostic]:
    """`agent_files` entries are matched against bare file names, so one with a separator could never match."""
    for index, entry in enumerate(data.get("agent_files", [])):
        if "/" in entry or "\\" in entry:
            yield invalid(
                ["agent_files", index],
                f"`{entry}` contains a path separator.",
                "`agent_files` lists bare file names, matched at any depth. "
                "For one specific path, use a `paths:` policy with `untyped: allow`.",
            )


def _declared_shapes(data: dict, declared_common: dict[str, dict]) -> list[DeclaredShape]:
    shapes = []
    for kind_name, kind_spec in data["kinds"].items():
        location = ("kinds", kind_name)
        kind_fields = _kind_fields(kind_spec, declared_common)
        kind = DeclaredShape(
            kind_name, None, location, kind_spec, kind_fields, kind_fields, {**declared_common, **kind_fields}, {}, None
        )
        shapes.append(kind)
        selector = kind_spec.get("variant_by")
        for variant_name, variant in kind_spec.get("variants", {}).items():
            own = variant.get("fields", {})
            siblings = {**kind_fields, **own}
            shapes.append(
                DeclaredShape(
                    kind_name,
                    variant_name,
                    (*location, "variants", variant_name),
                    variant,
                    own,
                    siblings,
                    {**declared_common, **siblings},
                    {selector: variant_name} if selector is not None else variant.get("set", {}),
                    kind,
                )
            )
    return shapes


def _kind_fields(kind_spec: dict, declared_common: Mapping[str, dict]) -> dict[str, dict]:
    """The kind's field declarations, including its `variant_by` field when declared nowhere else."""
    fields = kind_spec.get("fields", {})
    selector = kind_spec.get("variant_by")
    if selector is None or selector in fields or selector in declared_common:
        return fields
    return {**fields, selector: _IMPLICIT_SELECTOR}


def _kinds(
    shapes: list[DeclaredShape],
    patterns: Mapping[DeclaredShape, PathPattern],
    templates: Mapping[DeclaredShape, Template],
    vocabularies: Mapping[str, list[str]],
    node: yaml.Node | None,
) -> dict[str, Kind]:
    def parsed(shape: DeclaredShape) -> dict[str, Field]:
        return {
            name: parse_field(
                name, spec, shape.siblings, vocabularies, yamlsource.line_of(node, _declared_at(shape, name))
            )
            for name, spec in shape.own_fields.items()
        }

    kinds = {}
    for kind in (shape for shape in shapes if shape.parent is None):
        variants = {
            shape.variant: Variant(
                name=shape.variant,
                fields=parsed(shape),
                path=patterns.get(shape),
                template=templates.get(shape),
                selection=tuple(Condition(field, (value,)) for field, value in shape.selection.items()),
                description=shape.spec.get("description"),
            )
            for shape in shapes
            if shape.parent is kind
        }
        kinds[kind.kind] = Kind(
            name=kind.kind,
            fields=parsed(kind),
            unknown_fields=SEVERITY_NAMES[kind.spec.get("unknown_fields", "error")],
            path=patterns.get(kind),
            variant_by=kind.spec.get("variant_by"),
            variants=variants,
            template=templates.get(kind),
            collection=_collection(kind, node),
            description=kind.spec.get("description"),
            structure_cutoff=_structure_cutoff(kind),
        )
    return kinds


def _declared_at(shape: DeclaredShape, name: str) -> tuple[str, ...]:
    """Where `shape` declares the field `name`; an implicit `variant_by` field is declared by `variant_by` itself."""
    if name in shape.spec.get("fields", {}):
        return (*shape.location, "fields", name)
    return (*shape.location, "variant_by")


def _structure_cutoff(kind: DeclaredShape) -> StructureCutoff | None:
    spec = kind.spec.get("structure_cutoff")
    return StructureCutoff(spec["field"], spec["date"]) if spec is not None else None


def _collection(kind: DeclaredShape, node: yaml.Node | None) -> KindCollection | None:
    spec = kind.spec.get("collection")
    if spec is None:
        return None
    location = (*kind.location, "collection")
    return KindCollection(
        count=spec.get("count"),
        contiguous=spec.get("contiguous"),
        count_line=yamlsource.line_of(node, (*location, "count")),
        contiguous_line=yamlsource.line_of(node, (*location, "contiguous")),
    )


def _declared_common_fields(data: dict) -> dict[str, dict]:
    """The `common_fields` entries that carry a field declaration (only the mapping form can)."""
    common = data.get("common_fields", {})
    if not isinstance(common, dict):
        return {}
    return {name: spec for name, spec in common.items() if spec is not None}


def _with_variant_names(shape: DeclaredShape) -> dict[str, dict]:
    """The shape's siblings, with an implicit `variant_by` field allowing exactly the variant names.

    Only for checking conditions: giving the field `values` in the shape itself would trip `_selector_problems`.
    """
    selector = shape.kind_spec.get("variant_by")
    if selector is None or shape.siblings.get(selector) is not _IMPLICIT_SELECTOR:
        return shape.siblings
    return {**shape.siblings, selector: {**_IMPLICIT_SELECTOR, "values": list(shape.kind_spec.get("variants", {}))}}


def _field_problems(
    data: dict, declared_common: dict[str, dict], shapes: list[DeclaredShape], invalid: Invalid
) -> Iterator[Diagnostic]:
    vocabularies = data.get("vocabularies", {})
    declared = [(("common_fields", name), spec, declared_common) for name, spec in declared_common.items()]
    for shape in shapes:
        location = (*shape.location, "fields")
        siblings = _with_variant_names(shape)
        declared += [((*location, name), spec, siblings) for name, spec in shape.own_fields.items()]
    for location, spec, siblings in declared:
        yield from spec_problems(location, spec, siblings, vocabularies, invalid)
        yield from _link_target_problems(location, spec, data["kinds"], invalid)


def _description_problems(
    declared_common: dict[str, dict], shapes: list[DeclaredShape], invalid: Invalid
) -> Iterator[Diagnostic]:
    """Descriptions spanning lines, which a one-line summary (and a Markdown table cell) cannot hold."""
    described = [(("common_fields", name), spec) for name, spec in declared_common.items()]
    for shape in shapes:
        described.append((shape.location, shape.spec))
        described += [((*shape.location, "fields", name), spec) for name, spec in shape.spec.get("fields", {}).items()]
    for location, spec in described:
        if any(line_break in spec.get("description", "") for line_break in "\r\n"):
            yield invalid(
                [*location, "description"],
                "a description is one line.",
                "Write it on a single line; a folded `>` block keeps a final line break unless written `>-`.",
            )


def _link_target_problems(location: Sequence, spec: dict, kinds: dict, invalid: Invalid) -> Iterator[Diagnostic]:
    to = spec.get("to")
    for position, kind in enumerate(link_targets(spec) or ()):
        if kind not in kinds:
            yield invalid(
                [*location, "to"] if isinstance(to, str) else [*location, "to", position],
                f"kind `{kind}` is not declared.",
                suggestion(kind, kinds, f"Declared kinds: {code_list(sorted(kinds))}."),
            )


def _parse_paths(
    shapes: list[DeclaredShape], invalid: Invalid
) -> tuple[dict[DeclaredShape, PathPattern], list[Diagnostic]]:
    """Each kind's and variant's own `path`, parsed, and the ones that do not parse."""
    patterns, problems = {}, []
    for shape in shapes:
        if "path" not in shape.spec:
            continue
        try:
            patterns[shape] = PathPattern.parse(shape.spec["path"], shape.kind_spec.get(_SUFFIX_TABLE, {}))
        except PatternError as error:
            problems.append(invalid([*shape.location, "path"], error.message, error.hint))
    return patterns, problems


def _load_templates(
    shapes: list[DeclaredShape], tree: Tree, root: str, invalid: Invalid
) -> tuple[dict[DeclaredShape, Template], list[Diagnostic]]:
    """Each kind's and variant's own template, parsed once per file, and the ones that do not load."""
    templates, problems = {}, []
    parsed: dict[str, Template | Diagnostic] = {}
    for shape in shapes:
        if "template" not in shape.spec:
            continue
        declared = shape.spec["template"]
        location = [*shape.location, "template"]
        path = _template_path(root, declared)
        if path is None:
            problems.append(
                invalid(
                    location,
                    f"`{declared}` is outside the directory holding charter.yaml.",
                    "`template` is a path relative to `root`, inside the directory holding charter.yaml.",
                )
            )
            continue
        if path not in parsed:
            parsed[path] = _template(tree, path, location, invalid)
        result = parsed[path]
        if isinstance(result, Template):
            templates[shape] = result
        else:
            problems.append(result)
    return templates, problems


def _template_path(root: str, declared: str) -> str | None:
    """The template `declared` relative to `root`, in diagnostic form; None outside the contract's directory."""
    posix = declared.replace("\\", "/")
    if PureWindowsPath(declared).drive or posixpath.isabs(posix):
        return None
    return contract_relative(posixpath.join(root, posix))


def _template(tree: Tree, path: str, location: list, invalid: Invalid) -> Template | Diagnostic:
    content = tree.read([path]).get(path)
    if content is None:
        return invalid(location, f"`{path}` does not exist.", "`template` is a path relative to `root`.")
    try:
        return parse_template(path, decode(content))
    except UnicodeDecodeError:
        return invalid(location, f"`{path}` is not valid UTF-8 text.")
    except TemplateError as error:
        return invalid(location, error.message, error.hint)


def _placeholder_problems(
    shapes: list[DeclaredShape], templates: Mapping[DeclaredShape, Template], invalid: Invalid
) -> Iterator[Diagnostic]:
    """Placeholders in each shape's own template that name none of its fields.

    A variant that keeps its kind's template has every field the kind has, so only own templates need checking.
    """
    for shape in shapes:
        template = templates.get(shape)
        if template is None:
            continue
        name = shape.kind if shape.variant is None else f"{shape.kind}/{shape.variant}"
        known = [*shape.fields, DATE]
        for placeholder in template.placeholders:
            if placeholder.name in known:
                continue
            yield invalid(
                [*shape.location, "template"],
                f"`{placeholder}` (`{template.path}` line {placeholder.line}) is not a field of `{name}`.",
                suggestion(
                    placeholder.name,
                    known,
                    f"A placeholder names a field of `{name}` ({code_list(shape.fields)}) or `{{{{{DATE}}}}}`.",
                ),
            )


@dataclass(frozen=True)
class _PathIssue:
    message: str
    hint: str | None
    # The field at fault; None when the path itself is.
    field: str | None = None


def _path_problems(
    shapes: list[DeclaredShape], patterns: Mapping[DeclaredShape, PathPattern], invalid: Invalid
) -> Iterator[Diagnostic]:
    """Each shape's path, its own or its kind's, against the fields a note of that shape has."""
    for shape in shapes:
        pattern = patterns.get(shape.parent if shape.inherits_path else shape)
        if pattern is None:
            continue
        has_table = _SUFFIX_TABLE in shape.kind_spec
        issues = [
            *_placeholder_issues(pattern, shape.fields, shape.selection, has_table),
            *_matches_filename_issues(pattern, shape.fields),
        ]
        for issue in issues:
            if not shape.inherits_path:
                yield invalid([*shape.location, "path"], issue.message, issue.hint)
            # The kind's path is checked against the kind; only the variant's own declarations can break it here.
            elif issue.field in shape.own_fields:
                yield invalid(
                    [*shape.location, "fields", issue.field],
                    issue.message,
                    f"The variant keeps the kind's path `{pattern.text}`: give the variant its own `path`, "
                    f"or declare `{issue.field}` as the kind does.",
                )


def _placeholder_issues(
    pattern: PathPattern, fields: dict[str, dict], guaranteed: Collection[str], has_table: bool
) -> Iterator[_PathIssue]:
    for placeholder in pattern.placeholders:
        name = placeholder.field
        spec = fields.get(name)
        if spec is None:
            yield _PathIssue(
                f"`{{{name}}}` is not a field of this kind.",
                suggestion(
                    name,
                    fields,
                    f"Fields of this kind: {code_list(fields)}." if fields else "Declare it under the kind's `fields:`.",
                ),
            )
        elif is_list(spec):
            yield _PathIssue(f"`{name}` is a list, which cannot be part of a path.", None, name)
        # A field that selects the variant is always present on a note of it.
        elif (
            spec.get("required") is not True
            and name not in guaranteed
            and placeholder.filters[:1] != (SUFFIX_FILTER,)
        ):
            yield _PathIssue(
                f"`{name}` is not required, so a note may lack it and its path could not be rendered.",
                f"Make `{name}` `required: true`, or render it through the `suffix` filter, "
                "which renders a missing value as nothing.",
                name,
            )
    if _uses_suffix(pattern) and not has_table:
        yield _PathIssue(
            "the `suffix` filter needs a `suffix` table on the kind.",
            'Map values to suffixes, e.g. `suffix: {deferred: " (Deferred)"}`.',
        )


def _matches_filename_issues(pattern: PathPattern, fields: dict[str, dict]) -> Iterator[_PathIssue]:
    unfiltered = {placeholder.field for placeholder in pattern.placeholders if not placeholder.filters}
    for name, spec in fields.items():
        if spec.get("matches_filename") is True and name not in unfiltered:
            yield _PathIssue(
                f"`{name}` has `matches_filename`, but the path `{pattern.text}` has no `{{{name}}}` placeholder.",
                f"Add `{{{name}}}`, without filters, to the path.",
                name,
            )


def _uses_suffix(pattern: PathPattern) -> bool:
    return any(SUFFIX_FILTER in placeholder.filters for placeholder in pattern.placeholders)


def _suffix_table_problems(
    shapes: list[DeclaredShape], patterns: Mapping[DeclaredShape, PathPattern], invalid: Invalid
) -> Iterator[Diagnostic]:
    for kind in shapes:
        if kind.parent is not None or _SUFFIX_TABLE not in kind.spec:
            continue
        location = [*kind.location, _SUFFIX_TABLE]
        with_paths = [shape for shape in shapes if (shape is kind or shape.parent is kind) and "path" in shape.spec]
        if not with_paths:
            yield invalid(location, "the `suffix` table has no effect without a `path`.", None)
        # Only once every path parsed: an unparsable one may be the one using the table.
        elif all(shape in patterns for shape in with_paths) and not any(
            _uses_suffix(patterns[shape]) for shape in with_paths
        ):
            yield invalid(location, "the `suffix` table has no effect: no placeholder uses `|suffix`.", None)


def _variant_problems(data: dict, shapes: list[DeclaredShape], invalid: Invalid) -> Iterator[Diagnostic]:
    vocabularies = data.get("vocabularies", {})
    for shape in shapes:
        if shape.parent is None:
            yield from _selector_problems(
                shape, [s for s in shapes if s.parent is shape], data.get("discriminator", "kind"), invalid
            )
        else:
            yield from _selection_problems(shape, vocabularies, invalid)


def _collection_problems(shapes: list[DeclaredShape], invalid: Invalid) -> Iterator[Diagnostic]:
    for kind in shapes:
        field = kind.spec.get("collection", {}).get("contiguous") if kind.parent is None else None
        if field is None:
            continue
        location = [*kind.location, "collection", "contiguous"]
        if field not in kind.fields:
            yield invalid(
                location,
                f"`{field}` is not a field of this kind.",
                suggestion(field, kind.fields, f"Fields of this kind: {code_list(kind.fields)}."),
            )
        elif (field_type := declared_type(kind.fields[field])) != "int":
            yield invalid(location, f"`{field}` holds `{field_type}`, but a contiguous sequence needs `int`.", None)
    yield from _retyped_field_problems(shapes, invalid)


def _cutoff_problems(shapes: list[DeclaredShape], invalid: Invalid) -> Iterator[Diagnostic]:
    """A cutoff needs a real date, a template, and a date field that every note of the kind must have.

    The field is looked up in the kind's merged view (`common_fields` plus the kind's `fields`), as for `ids`; a
    field only a variant declares is not on every note. A variant that redeclares it must keep it a required date.
    """
    for kind in shapes:
        spec = kind.spec.get("structure_cutoff") if kind.parent is None else None
        if spec is None:
            continue
        location = [*kind.location, "structure_cutoff"]
        yield from _cutoff_setting_problems(kind, spec, location, invalid)
        name = spec["field"]
        if name not in kind.fields:
            others = [v.variant for v in shapes if v.parent is kind and name in v.own_fields]
            yield invalid(
                [*location, "field"],
                f"`{name}` is not a field of this kind.",
                f"Only variant `{others[0]}` declares it; declare it on the kind or in `common_fields`."
                if others
                else suggestion(name, kind.fields, f"Fields of this kind: {code_list(kind.fields)}."),
            )
            continue
        yield from _cutoff_field_problems(name, kind.fields[name], "", [*location, "field"], invalid)
        for variant in (v for v in shapes if v.parent is kind and name in v.own_fields):
            yield from _cutoff_field_problems(
                name,
                variant.own_fields[name],
                f" in variant `{variant.variant}`",
                [*variant.location, "fields", name],
                invalid,
            )


def _cutoff_setting_problems(
    kind: DeclaredShape, spec: dict, location: list[str], invalid: Invalid
) -> Iterator[Diagnostic]:
    date = spec["date"]
    if not isinstance(date, datetime.date) or isinstance(date, datetime.datetime):
        yield invalid(
            [*location, "date"],
            "the cutoff date must be a date.",
            "Write it unquoted as YYYY-MM-DD, e.g. `date: 2026-01-01`.",
        )
    if "template" not in kind.spec:
        yield invalid(
            location,
            "the kind has no template, so there is no structure to exempt notes from.",
            "Give the kind a `template`, or remove `structure_cutoff`.",
        )


def _cutoff_field_problems(
    name: str, spec: dict, where: str, location: list[str], invalid: Invalid
) -> Iterator[Diagnostic]:
    """`where` is empty for the kind's own declaration, else " in variant `x`"."""
    hint = f"Declare `{name}` as `{{type: date, required: true}}`, or name another field."
    if (field_type := declared_type(spec)) != "date":
        message = f"`{name}` holds `{field_type}`{where}, but the structure cutoff reads a `date`."
        yield invalid(location, message, hint)
    if spec.get("required") is not True:
        message = f"`{name}` is not required{where}, so a note could escape the cutoff by leaving it out."
        yield invalid(location, message, hint)


def _retyped_field_problems(shapes: list[DeclaredShape], invalid: Invalid) -> Iterator[Diagnostic]:
    """A variant may not change the type of a field the collection compares across notes.

    Mixed types would make `contiguous` sort strings against ints, and `unique` treat `True` as `1`.
    Variants do not nest, so a kind's direct variants are all there is.
    """
    for kind in shapes:
        if kind.parent is not None:
            continue
        variants = [shape for shape in shapes if shape.parent is kind]
        contiguous = kind.spec.get("collection", {}).get("contiguous")
        for variant in variants:
            for name, spec in variant.own_fields.items():
                if name == contiguous:
                    yield from _retyped_contiguous(variant, name, spec, invalid)
        for name in dict.fromkeys(name for variant in variants for name in variant.own_fields):
            if name != contiguous:
                yield from _retyped_unique(kind, variants, name, invalid)


def _retyped_contiguous(variant: DeclaredShape, name: str, spec: dict, invalid: Invalid) -> Iterator[Diagnostic]:
    if (field_type := declared_type(spec)) != "int":
        message = f"`{name}` holds `{field_type}` here, but a contiguous sequence needs `int`."
        yield invalid([*variant.location, "fields", name], message, "Declare the field as `int` in every variant.")


def _retyped_unique(
    kind: DeclaredShape, variants: list[DeclaredShape], name: str, invalid: Invalid
) -> Iterator[Diagnostic]:
    # The kind's view includes `common_fields`; a variant declaring the field is compared with the first source.
    declarations = [(shape, shape.own_fields[name]) for shape in variants if name in shape.own_fields]
    if name in kind.fields:
        source, reference_spec = "the kind", kind.fields[name]
    else:
        first, reference_spec = declarations[0]
        source = f"variant `{first.variant}`"
        declarations = declarations[1:]
    if not (reference_spec.get("unique") is True or any(spec.get("unique") is True for _, spec in declarations)):
        return
    reference = declared_type(reference_spec)
    for variant, spec in declarations:
        if (field_type := declared_type(spec)) != reference:
            message = (
                f"`{name}` holds `{field_type}` here but `{reference}` in {source}; "
                "a `unique` field keeps one type."
            )
            hint = "Declare the field with the same type in every variant."
            yield invalid([*variant.location, "fields", name], message, hint)


def _selector_problems(
    kind: DeclaredShape, variants: list[DeclaredShape], discriminator: str, invalid: Invalid
) -> Iterator[Diagnostic]:
    selector = kind.spec.get("variant_by")
    location = [*kind.location, "variant_by"]
    if selector is None:
        yield from _overlap_problems(variants, invalid)
        return
    if selector == discriminator:
        yield invalid(
            location,
            f"`{selector}` is the discriminator, which names the kind; a variant cannot be selected by it.",
            "Name another field; every note of the kind has the same discriminator value.",
        )
        return
    if not variants:
        yield invalid(
            location,
            "`variant_by` has no effect without `variants`.",
            f"Declare the variants under `variants:`, each named by a value of `{selector}`.",
        )
        return
    spec = kind.fields[selector]
    field_type = declared_type(spec)
    if field_type == "list":
        yield invalid(location, f"`{selector}` is a list, but a variant is selected by a single value.", None)
    elif field_type not in ("string", None):
        yield invalid(location, f"`{selector}` holds `{field_type}`, but variant names are text.", None)
    elif "enum" in spec or "values" in spec:
        yield invalid(
            location,
            f"`{selector}` declares its own allowed values, but its values are the names of the variants.",
            f"Remove `enum` or `values` from `{selector}`; a value naming no variant is reported as "
            "`schema/unknown-variant`.",
        )


def _selection_problems(
    variant: DeclaredShape, vocabularies: Mapping[str, Any], invalid: Invalid
) -> Iterator[Diagnostic]:
    selector = variant.kind_spec.get("variant_by")
    fixed = variant.spec.get("set")
    if selector is not None and fixed is not None:
        yield invalid(
            [*variant.location, "set"],
            f"`set` cannot be combined with `variant_by`: the variant is selected by `{selector}: {variant.variant}`.",
            "Remove `set`, or remove `variant_by` and give every variant a `set`.",
        )
    elif selector is None and fixed is None:
        yield invalid(
            variant.location,
            "the variant has no `set`, so no note can be selected as it.",
            "Add `set: {field: value}`, or select variants by a field's value with `variant_by` on the kind.",
        )
    elif fixed is not None:
        yield from _fixed_problems([*variant.location, "set"], fixed, variant.parent.fields, vocabularies, invalid)
    for name in variant.own_fields:
        if name in variant.selection:
            yield invalid(
                [*variant.location, "fields", name],
                f"`{name}` selects the variant, so the variant cannot redeclare it.",
                "Declare it on the kind only.",
            )


def _fixed_problems(
    location: list, fixed: dict, kind_fields: dict[str, dict], vocabularies: Mapping[str, Any], invalid: Invalid
) -> Iterator[Diagnostic]:
    for name, value in fixed.items():
        spec = kind_fields.get(name)
        if spec is None:
            yield invalid(
                [*location, name],
                f"`{name}` is not a field of the kind; a variant is selected by the kind's own fields.",
                suggestion(
                    str(name),
                    kind_fields,
                    f"Fields of the kind: {code_list(kind_fields)}."
                    if kind_fields
                    else "Declare it under the kind's `fields:`.",
                ),
            )
        elif is_list(spec):
            yield invalid([*location, name], f"`{name}` is a list, but `set` fixes single values.", None)
        elif problem := fixed_value_problem(spec, vocabularies, value):
            yield invalid([*location, name], problem, None)


def _overlap_problems(variants: list[DeclaredShape], invalid: Invalid) -> Iterator[Diagnostic]:
    """Variants one note could match, because no field both `set` to different values tells them apart."""
    for position, variant in enumerate(variants):
        for earlier in variants[:position]:
            if not variant.selection or not earlier.selection:
                continue
            if not any(
                field in variant.selection and not same_value(variant.selection[field], value)
                for field, value in earlier.selection.items()
            ):
                yield invalid(
                    [*variant.location, "set"],
                    f"a note could match both `{earlier.variant}` and `{variant.variant}`.",
                    "Give both variants a `set` field in common with different values, so each note is one variant.",
                )
                break


def _path_policy_problems(data: dict, invalid: Invalid) -> Iterator[Diagnostic]:
    for glob, policy in data.get("paths", {}).items():
        if policy.get("ignore") is True and len(policy) > 1:
            others = code_list(key for key in policy if key != "ignore")
            yield invalid(
                ["paths", glob],
                f"`ignore: true` cannot be combined with {others}.",
                "Ignored files are not notes, so no other policy applies to them; remove the other keys.",
            )
        for position, kind in enumerate(policy.get("kinds", [])):
            if kind not in data["kinds"]:
                yield invalid(
                    ["paths", glob, "kinds", position],
                    f"kind `{kind}` is not declared.",
                    f"Declared kinds: {code_list(sorted(data['kinds']))}.",
                )


def _check_problems(
    data: dict, check_codes: Mapping[str, Collection[str]], core_codes: Collection[str], invalid: Invalid
) -> Iterator[Diagnostic]:
    checks = data.get("checks", {})
    # A plugin declares no codes up front; it reports them under its own id.
    plugin_ids = sorted(check_id for check_id, config in checks.items() if "source" in config)
    check_ids = sorted(check_codes)
    for check_id in checks:
        if check_id not in check_codes and check_id not in plugin_ids:
            yield invalid(
                ["checks", check_id],
                f"unknown check `{check_id}`.",
                suggestion(
                    str(check_id),
                    check_ids,
                    f"Known checks: {code_list(check_ids)}. A plugin's check also needs `source`, its directory.",
                ),
            )
    profile_keys = sorted({*check_ids, *core_codes, *(code for codes in check_codes.values() for code in codes)})
    for name, severities in data.get("profiles", {}).items():
        for key in severities:
            if key not in profile_keys and str(key).split("/")[0] not in plugin_ids:
                yield invalid(
                    ["profiles", name, key],
                    f"unknown check or diagnostic code `{key}`.",
                    suggestion(
                        str(key),
                        [*profile_keys, *plugin_ids],
                        f"Profile keys are a check id ({code_list([*check_ids, *plugin_ids])}) or a diagnostic "
                        "code such as `schema/unknown-field`.",
                    ),
                )


def _optional_check_problems(
    optional_checks: Mapping[str, OptionalCheck],
    configs: Mapping[str, CheckConfig],
    shapes: list[DeclaredShape],
    invalid: Invalid,
) -> Iterator[Diagnostic]:
    for check_id, check in optional_checks.items():
        if (config := configs.get(check_id)) is None:
            continue
        params_problems = [
            invalid(["checks", check_id, "with", *problem.absolute_path], *schema_message(problem))
            for problem in schema_errors(check.params_schema, dict(config.params))
        ]
        yield from params_problems
        if config.enabled and not params_problems:
            yield from check.contract_problems(config.params, shapes, invalid)


def _location(path: Iterable[str | int]) -> str:
    return dotted(path) or CONTRACT_FILENAME
