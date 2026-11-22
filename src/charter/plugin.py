"""External plugins: loading each `checks.<id>.source` directory's manifest and the check's parameters."""

import operator
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

import yaml

from charter import __version__, yamlsource
from charter.diagnostics import CORE_NAMESPACES, Diagnostic, code_list, suggestion
from charter.fields import Invalid
from charter.files import contract_relative
from charter.globs import compile_glob
from charter.lock import Locked, content_hash, is_vendored
from charter.schemacheck import errors as schema_errors
from charter.schematext import located_message, schema_message
from charter.tree import Tree, decode, exact_path

MANIFEST_FILENAME = "charter-plugin.yaml"
DEFAULT_TIMEOUT_MS = 10_000
# Interpreted by a shell or by one OS only, so a plugin started through one would not run everywhere.
_SHELL_SUFFIXES = (".sh", ".ps1", ".bat", ".cmd")
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh"})
_COMPARISONS: dict[str, Callable[[tuple[int, ...], tuple[int, ...]], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
}
_CLAUSE = re.compile(r"\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)\s*")

MANIFEST_SCHEMA = {
    "type": "object",
    "properties": {
        "charter_plugin": {"const": 1},
        "id": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "requires": {
            "type": "object",
            "properties": {"charter": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "run": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "scope": {"enum": ["file", "vault"]},
        "needs": {"type": "array", "items": {"enum": ["body", "before"]}, "uniqueItems": True},
        "triggers": {
            "type": "object",
            "properties": {
                "kinds": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "globs": {"type": "array", "items": {"type": "string", "minLength": 1}},
            },
            "additionalProperties": False,
        },
        "hook": {"type": "boolean"},
        "timeout_ms": {"type": "integer", "minimum": 1},
        "config_schema": {"type": "object"},
        "docs": {"type": "string", "minLength": 1},
    },
    "required": ["charter_plugin", "id", "version", "run"],
    "additionalProperties": False,
}

_Problem = tuple[str, str | None]
Scope = Literal["file", "vault"]
Need = Literal["body", "before"]


@dataclass(frozen=True)
class Triggers:
    kinds: frozenset[str]
    # Over paths relative to the knowledge-base root, as the protocol gives them.
    globs: tuple[re.Pattern[str], ...]

    def fire(self, kinds: Collection[str], paths: Iterable[str]) -> bool:
        """Whether a run touching these kinds and targeting these root-relative paths concerns the plugin."""
        return not self.kinds.isdisjoint(kinds) or any(glob.fullmatch(path) for path in paths for glob in self.globs)


@dataclass(frozen=True)
class Plugin:
    id: str
    version: str
    description: str | None
    # The plugin's directory in diagnostic form.
    source: str
    directory: Path
    run: tuple[str, ...]
    timeout_ms: int
    # `file`: the targets and the notes they link to; `vault`: every note.
    scope: Scope
    needs: frozenset[Need]
    # None when the plugin runs whatever the run touches.
    triggers: Triggers | None
    # False keeps the plugin out of per-edit (`--file`) runs.
    hook: bool
    # `checks.<id>.with`, already valid against the manifest's config_schema.
    params: Any
    # The line of `checks.<id>` in charter.yaml, where a failure to run is reported.
    line: int | None
    # The manifest's `docs` file: Markdown rules for agents and humans, with LF line endings.
    docs: str | None
    # The directory's content hash in charter.lock; None unless `plugin add` vendored the plugin here.
    sha256: str | None
    # Why the directory could not be written out of the tree (a full disk, a name the file system refuses);
    # set only on a stand-in that cannot run and is reported as `plugin/failed`.
    unavailable: str | None = None
    # The symbolic links a vendored plugin's directory holds, as the tree has them (the index entry's mode for a
    # staged plugin): the directory on disk may have resolved them. A plugin holding one is not run.
    links: tuple[str, ...] = ()

    @cached_property
    def modified(self) -> bool:
        """Whether a vendored plugin's directory differs from what was locked; hashed once per load."""
        return self.sha256 is not None and content_hash(self.directory) != self.sha256

    def runs_for_kind(self, kind: str) -> bool:
        """Whether runs touching notes of `kind` start the plugin, whatever paths they target."""
        return self.triggers is None or kind in self.triggers.kinds


def load_plugins(
    checks: Mapping[str, Mapping[str, Any]],
    builtin_ids: Collection[str],
    tree: Tree,
    node: yaml.Node,
    invalid: Invalid,
    locked: Mapping[str, Locked],
    *,
    builtins_with_params: Collection[str],
    kinds: Collection[str],
    write_out: bool = True,
) -> tuple[dict[str, Plugin], list[Diagnostic]]:
    """The enabled plugins `checks:` names with a `source`, and what is wrong with any of them or their parameters.
    Of the built-in checks, only `builtins_with_params` take `with`, which the contract checks itself.
    `kinds` are the contract's kind names, which a manifest's `triggers.kinds` must come from.

    `locked` is charter.lock's plugins by id. The lock covers only plugins vendored into `.charter/plugins/<id>`;
    a check whose `source` is elsewhere is a local-path plugin, whatever the lock says. Each plugin is read, hashed
    and run from its directory as `tree` holds it.

    Without `write_out`, no plugin directory is written to disk: the manifest and `docs` file are read from `tree`
    alone, and the plugins returned can be judged but never run, hashed or listed for links on disk.
    """
    plugins = {}
    problems: list[Diagnostic] = []
    for check_id, config in checks.items():
        params = config.get("with")
        if check_id in builtin_ids:
            problems.extend(_builtin_problems(check_id, config, invalid, check_id in builtins_with_params))
            continue
        if "source" not in config:
            continue
        if check_id in CORE_NAMESPACES:
            problems.append(
                invalid(
                    ["checks", check_id],
                    f"`{check_id}` is reserved for charter's own diagnostics, so no plugin can take it as its id.",
                    f"Give the plugin another id; reserved: {code_list(sorted(CORE_NAMESPACES))}.",
                )
            )
            continue
        # A disabled plugin is not read at all, so it may be absent, e.g. not yet installed on this machine.
        if config.get("enabled", True) is False:
            continue
        source = contract_relative(config["source"])
        if source is None:
            problems.append(
                invalid(
                    ["checks", check_id, "source"],
                    f"`{config['source']}` is outside the directory holding charter.yaml.",
                    "`source` is the plugin's directory, relative to charter.yaml, beside or below it.",
                )
            )
            continue
        if write_out:
            try:
                directory = tree.directory(source)
            except OSError as error:
                # Failing here would abort the whole run; the plugin alone fails, and the rest is still judged.
                plugins[check_id] = _unavailable(
                    check_id, source, error, yamlsource.line_of(node, ["checks", check_id])
                )
                continue
            read = _disk_reader(directory)
        else:
            # Why: a plugin that is never run needs no files on disk; `directory` is a placeholder no consumer may
            # read, like the stand-in's in `_unavailable`, and a path that does not exist.
            directory = Path(source)
            read = _tree_reader(tree, source)
        manifest_problems = _manifest_problems(manifest := _read_manifest(read), check_id)
        if not manifest_problems:
            manifest_problems = _trigger_kind_problems(manifest, kinds)
        docs = None
        if not manifest_problems and "docs" in manifest:
            docs = _read_docs(read, manifest["docs"])
            if isinstance(docs, tuple):
                manifest_problems = [docs]
        if manifest_problems:
            shown = _in_source(source, MANIFEST_FILENAME)
            problems.extend(
                invalid(["checks", check_id, "source"], f"plugin manifest `{shown}`: {message}", hint)
                for message, hint in manifest_problems
            )
            continue
        params_problems = list(_params_problems(check_id, manifest.get("config_schema"), params, invalid))
        if params_problems:
            problems.extend(params_problems)
            continue
        vendored = is_vendored(check_id, source, locked)
        plugins[check_id] = Plugin(
            id=check_id,
            version=manifest["version"],
            description=manifest.get("description"),
            source=source,
            directory=directory,
            run=tuple(manifest["run"]),
            timeout_ms=manifest.get("timeout_ms", DEFAULT_TIMEOUT_MS),
            scope=manifest.get("scope", "vault"),
            needs=frozenset(manifest.get("needs", [])),
            triggers=_triggers(manifest["triggers"]) if "triggers" in manifest else None,
            hook=manifest.get("hook", True),
            params=params if params is not None else {},
            line=yamlsource.line_of(node, ["checks", check_id]),
            docs=docs,
            sha256=locked[check_id].sha256 if vendored else None,
            links=tuple(tree.symlinks(source)) if vendored else (),
        )
    return plugins, problems


def _unavailable(check_id: str, source: str, error: OSError, line: int | None) -> Plugin:
    """A stand-in for a plugin whose directory could not be written out, which has no manifest to read."""
    # Why: the plugin never ran, so `directory`, `version`, `scope` and `run` are placeholders no consumer may
    # read; `directory` is a path that does not exist.
    return Plugin(
        id=check_id,
        version="",
        description=None,
        source=source,
        directory=Path(source),
        run=(),
        timeout_ms=DEFAULT_TIMEOUT_MS,
        scope="vault",
        needs=frozenset(),
        triggers=None,
        hook=True,
        params={},
        line=line,
        docs=None,
        sha256=None,
        unavailable=error.strerror or str(error),
    )


def _trigger_kind_problems(manifest: dict, kinds: Collection[str]) -> list[_Problem]:
    """A kind the contract does not declare never matches a note, so the plugin would silently never fire for it."""
    return [
        (
            f"`triggers.kinds` names `{kind}`, which charter.yaml does not declare.",
            suggestion(kind, kinds, f"Declared kinds: {code_list(sorted(kinds))}."),
        )
        for kind in manifest.get("triggers", {}).get("kinds", [])
        if kind not in kinds
    ]


def _triggers(declared: Mapping[str, list[str]]) -> Triggers:
    return Triggers(
        frozenset(declared.get("kinds", [])), tuple(compile_glob(glob) for glob in declared.get("globs", []))
    )


def _builtin_problems(
    check_id: str, config: Mapping[str, Any], invalid: Invalid, takes_params: bool
) -> Iterator[Diagnostic]:
    if "source" in config:
        yield invalid(
            ["checks", check_id, "source"],
            f"`{check_id}` is a built-in check, so it takes no `source`.",
            "Give the plugin its own check id, the `id` in its manifest.",
        )
    if "with" in config and not takes_params:
        yield invalid(
            ["checks", check_id, "with"],
            f"check `{check_id}` takes no parameters.",
            "Only plugins take `with`; remove it.",
        )


def manifest_of(directory: Path) -> dict | list[_Problem]:
    """The valid manifest in `directory`, whatever check id it would be enabled under, or what is wrong with it."""
    manifest = _read_manifest(_disk_reader(directory))
    return problems if (problems := _manifest_problems(manifest, None)) else manifest


# Reads the text of a file in a plugin's directory, by its path relative to that directory, with universal newlines
# and no byte order mark. Raises OSError or UnicodeDecodeError.
_Reader = Callable[[str], str]


def _disk_reader(directory: Path) -> _Reader:
    """Reads the files of `directory` from disk, by their exact letter case, as git and `--range` name them. A name
    matches a file in another Unicode form (NFC or NFD), as macOS git reports names."""

    def read(relative: str) -> str:
        # Why: macOS and Windows file systems ignore case, so `rules.md` would open `RULES.md` there and nowhere else.
        found = exact_path(directory, relative, any_form=True)
        if found is None:
            raise FileNotFoundError(str(directory / relative))
        return found.read_text(encoding="utf-8-sig")

    return read


def _in_source(source: str, relative: str) -> str:
    """The path of `relative`, a path in the plugin directory `source`, relative to the contract's directory."""
    return relative if source == "." else f"{source}/{relative}"


def _tree_reader(tree: Tree, source: str) -> _Reader:
    """Reads the files of the plugin directory `source` from `tree` itself, writing nothing to disk."""

    def read(relative: str) -> str:
        path = _in_source(source, relative)
        contents = tree.read([path])
        if path not in contents:
            raise FileNotFoundError(path)
        return decode(contents[path])

    return read


def _read_manifest(read: _Reader) -> dict | _Problem:
    """The manifest `read` gives as YAML data, or why it could not be read."""
    try:
        text = read(MANIFEST_FILENAME)
    except (OSError, UnicodeDecodeError) as error:
        reason = "is not valid UTF-8 text" if isinstance(error, UnicodeDecodeError) else "could not be read"
        return (
            f"the file {reason}.",
            f"`source` is the plugin's directory, relative to charter.yaml, holding `{MANIFEST_FILENAME}`.",
        )
    try:
        data, _ = yamlsource.parse(text)
    except yamlsource.YamlSyntaxError as syntax:
        return f"invalid YAML at line {syntax.line}: {syntax.message}.", None
    if not isinstance(data, dict):
        return "the manifest must be a YAML mapping.", None
    return data


def _read_docs(read: _Reader, name: str) -> str | None | _Problem:
    """The `docs` file's text without surrounding blank lines (None when empty), or why it could not be read."""
    hint = "`docs` is a Markdown file in the plugin's directory, relative to it."
    relative = contract_relative(name)
    if relative is None:
        return f"`docs` file `{name}` is outside the plugin's directory.", hint
    try:
        # Universal newlines and no byte order mark, so the rulebook is the same bytes whoever checked it out.
        lines = read(relative).splitlines()
    except (OSError, UnicodeDecodeError) as error:
        reason = "is not valid UTF-8 text" if isinstance(error, UnicodeDecodeError) else "could not be read"
        return f"`docs` file `{name}` {reason}.", hint
    filled = [number for number, line in enumerate(lines) if line.strip()]
    return "\n".join(lines[filled[0] : filled[-1] + 1]) if filled else None


def _manifest_problems(manifest: dict | _Problem, check_id: str | None) -> list[_Problem]:
    if isinstance(manifest, tuple):
        return [manifest]
    if shell := _shell_problem(manifest.get("run")):
        return [shell]
    problems = [located_message(problem) for problem in schema_errors(MANIFEST_SCHEMA, manifest)]
    if problems:
        return problems
    if check_id is not None and manifest["id"] != check_id:
        return [
            (
                f"its `id` is `{manifest['id']}`, but the check is `{check_id}`.",
                f"Name the check after the plugin: `checks.{manifest['id']}`.",
            )
        ]
    if "triggers" in manifest and not any(manifest["triggers"].values()):
        return [
            (
                "`triggers` names no kinds and no globs, so the plugin would never run.",
                "List the kinds or globs that should start the plugin, or leave out `triggers` to run it every time.",
            )
        ]
    requirement = manifest.get("requires", {}).get("charter")
    if requirement is not None and (unmet := _requirement_problem(requirement)) is not None:
        return [unmet]
    if "config_schema" in manifest:
        import jsonschema  # only a plugin with a `config_schema` needs the full validator

        try:
            jsonschema.Draft202012Validator.check_schema(manifest["config_schema"])
        except jsonschema.SchemaError as error:
            return [(f"`config_schema` is not a valid JSON Schema: {error.message}.", None)]
    return []


def _shell_problem(run: Any) -> _Problem | None:
    example = "`run: [uv, run, --script, check.py]`"
    if isinstance(run, str):
        return (
            "`run` is a command string, but plugins never run through a shell; it must be a list of arguments.",
            f"Write one list item per argument, for example {example}.",
        )
    if not (isinstance(run, list) and run and isinstance(run[0], str)):
        return None
    # The Windows reading of a path also splits at `/`, so it finds the program name on every OS.
    program = PureWindowsPath(run[0]).name.lower().removesuffix(".exe")
    if program in _SHELLS or program.endswith(_SHELL_SUFFIXES):
        return (
            (
                f"`run` starts a shell or shell script, `{run[0]}`; plugins never run through a shell, so they "
                "work on every OS."
            ),
            f"Write the plugin in a language with a cross-platform runner, for example {example}.",
        )
    return None


def _requirement_problem(requirement: str) -> _Problem | None:
    clauses = [_CLAUSE.fullmatch(clause) for clause in requirement.split(",")]
    if not all(clauses):
        return (
            f"`requires.charter` is `{requirement}`, which is not a version requirement.",
            "Write comparisons with `>=`, `>`, `<=`, `<`, `==` or `!=`, separated by commas, e.g. `>=1.0,<2`.",
        )
    current = _version(__version__)
    if all(_COMPARISONS[match[1]](*_padded(current, _version(match[2]))) for match in clauses):
        return None
    return (
        f"the plugin requires charter `{requirement}`, but this is charter {__version__}.",
        "Install a charter version the plugin supports, or a plugin version made for this charter.",
    )


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _padded(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    # So that 1.0 and 1.0.0 compare equal.
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def _params_problems(check_id: str, config_schema: dict | None, params: Any, invalid: Invalid) -> Iterator[Diagnostic]:
    if config_schema is None:
        if params is not None:
            yield invalid(
                ["checks", check_id, "with"],
                f"plugin `{check_id}` takes no parameters; its manifest has no `config_schema`.",
                "Remove `with`, or declare the parameters in the manifest's `config_schema`.",
            )
        return
    for problem in schema_errors(config_schema, params if params is not None else {}):
        yield invalid(["checks", check_id, "with", *problem.absolute_path], *schema_message(problem))
