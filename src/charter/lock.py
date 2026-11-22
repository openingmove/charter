"""`charter.lock`: the plugins charter vendored, where each came from, and the content hash of its directory."""

import hashlib
import re
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from charter import yamlsource
from charter.diagnostics import Diagnostic, Severity
from charter.files import contract_relative, replace_file
from charter.schemacheck import errors as schema_errors
from charter.schematext import located_message
from charter.tree import decode, plugin_files

LOCK_FILENAME = "charter.lock"
# Where `charter plugin add` puts each plugin, as `<PLUGINS_DIR>/<id>`, relative to charter.yaml.
PLUGINS_DIR = ".charter/plugins"
# The name prefix of the folder in PLUGINS_DIR where `plugin add`, `update` and `remove` stage their change.
STAGING_PREFIX = ".staging-"
# A staging folder that an interrupted plugin command left behind.
PLUGIN_LEFTOVER_STAGING = "plugin/leftover-staging"
# What to do about a plugin that holds a symbolic link, for `plugin add` and for a run alike.
SYMLINK_HINT = "Ask the plugin's author to replace the link with the file it points to."
# git reads only this much of a file to decide whether it is binary.
_BINARY_SNIFF = 8000
_HEADER = "# Written by `charter plugin`; do not edit by hand.\n"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TEXT = {"type": "string", "minLength": 1}

# Open to keys it does not know, so a lock written by a later charter still loads.
LOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "charter_lock": {"const": 1},
        "plugins": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "version": _TEXT,
                    "source": {
                        "type": "object",
                        "properties": {"git": _TEXT, "ref": _TEXT, "commit": _TEXT, "dev": {"const": True}},
                    },
                    "sha256": {"type": "string"},
                },
                "required": ["version", "source", "sha256"],
            },
        },
    },
    "required": ["charter_lock"],
}


@dataclass(frozen=True)
class GitSource:
    git: str
    ref: str
    # What `ref` pointed at when the plugin was added; None in a lock written by hand without it.
    commit: str | None


@dataclass(frozen=True)
class DevSource:
    pass


@dataclass(frozen=True)
class Locked:
    version: str
    source: GitSource | DevSource
    sha256: str


class LockError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]):
        super().__init__("invalid lock")
        self.diagnostics = diagnostics


def parse_lock(content: bytes | None) -> dict[str, Locked]:
    """The plugins locked in charter.lock's `content`, by id; none without a lock. Raises LockError."""
    if content is None:
        return {}

    def problem(code: str, line: int | None, message: str) -> Diagnostic:
        hint = "`charter plugin add` writes the lock; restore it from version control or add the plugins again."
        return Diagnostic(LOCK_FILENAME, line, Severity.ERROR, code, message, hint)

    try:
        data, node = yamlsource.parse(decode(content))
    except UnicodeDecodeError:
        raise LockError([problem("contract/yaml", None, "The lock is not valid UTF-8 text.")]) from None
    except yamlsource.YamlSyntaxError as syntax:
        raise LockError([problem("contract/yaml", syntax.line, f"Invalid YAML: {syntax.message}.")]) from None
    problems = [
        problem("contract/invalid", yamlsource.line_of(node, list(error.absolute_path)), located_message(error)[0])
        for error in schema_errors(LOCK_SCHEMA, data)
    ]
    if not problems:
        problems = [
            problem("contract/invalid", yamlsource.line_of(node, location), message)
            for location, message in _entry_problems(data.get("plugins", {}))
        ]
    if problems:
        raise LockError(problems)
    return {plugin_id: _locked(entry) for plugin_id, entry in data.get("plugins", {}).items()}


def _entry_problems(plugins: Mapping[str, Any]) -> Iterator[tuple[list[str], str]]:
    for plugin_id, entry in plugins.items():
        source = entry["source"]
        if ("dev" in source) == ("git" in source) or ("git" in source and "ref" not in source):
            yield (
                ["plugins", plugin_id, "source"],
                f"plugins.{plugin_id}.source: needs `git` and `ref` for a plugin from git, or `dev: true` for a "
                "working copy.",
            )
        if not _SHA256.fullmatch(entry["sha256"]):
            yield (
                ["plugins", plugin_id, "sha256"],
                f"plugins.{plugin_id}.sha256: expected 64 lowercase hexadecimal digits, got `{entry['sha256']}`.",
            )


def _locked(entry: Mapping[str, Any]) -> Locked:
    source = entry["source"]
    typed = DevSource() if "dev" in source else GitSource(source["git"], source["ref"], source.get("commit"))
    return Locked(entry["version"], typed, entry["sha256"])


def vendored_directory(plugin_id: str) -> str:
    return f"{PLUGINS_DIR}/{plugin_id}"


def leftover_staging(base_dir: Path) -> list[Diagnostic]:
    """A warning for each staging folder in PLUGINS_DIR. Only an interrupted plugin command leaves one, and its
    `previous/` may hold the only copy of a plugin's previous directory, so charter reports it and never deletes it."""
    try:
        names = sorted(entry.name for entry in (base_dir / PLUGINS_DIR).iterdir())
    except OSError:
        return []
    return [
        Diagnostic(
            shown,
            None,
            Severity.WARNING,
            PLUGIN_LEFTOVER_STAGING,
            f"`{shown}` was left behind by an interrupted `charter plugin add`, `update` or `remove`.",
            "Its `previous/` folder may hold the only copy of a plugin's previous directory. Check it, then delete "
            "the folder yourself; charter never deletes it.",
        )
        for shown in (f"{PLUGINS_DIR}/{name}" for name in names if name.startswith(STAGING_PREFIX))
    ]


def is_vendored(plugin_id: str, source: str | None, locked: Mapping[str, Locked]) -> bool:
    """Whether the lock covers a plugin: it is locked, and its `checks` entry, if it has one, uses the directory
    `plugin add` installed it in. A `source` anywhere else is a plugin used in place, whatever the lock says."""
    return plugin_id in locked and (source is None or contract_relative(source) == vendored_directory(plugin_id))


def lock_bytes(plugins: Mapping[str, Locked]) -> bytes:
    """What `write_lock` writes for `plugins`."""
    data = {
        "charter_lock": 1,
        "plugins": {
            plugin_id: {"version": entry.version, "source": _source_data(entry.source), "sha256": entry.sha256}
            for plugin_id, entry in sorted(plugins.items())
        },
    }
    return (_HEADER + yamlsource.dump(data)).encode("utf-8")


def write_lock(directory: Path, plugins: Mapping[str, Locked]) -> None:
    replace_file(directory / LOCK_FILENAME, lock_bytes(plugins))


def _source_data(source: GitSource | DevSource) -> dict[str, Any]:
    if isinstance(source, DevSource):
        return {"dev": True}
    data = {"git": source.git, "ref": source.ref}
    return data if source.commit is None else {**data, "commit": source.commit}


def symlink_reason(links: Sequence[str]) -> str:
    """Why a plugin may not hold the symbolic `links` (relative to the plugin), for `plugin add` and for a run."""
    named = ", ".join(f"`{link}`" for link in links)
    held = f"a symbolic link, {named}" if len(links) == 1 else f"symbolic links, {named}"
    return f"holds {held}; a plugin may not, as links read differently on each OS and may point outside the plugin."


def content_hash(directory: Path, leaving_out: Collection[str] = ()) -> str | None:
    """The sha256 of a plugin directory, the same on every OS and checkout; None when it holds a symbolic link,
    which no plugin may (a link's target reads differently on each OS, and may lie outside the plugin).

    It covers each file's path relative to `directory` (POSIX, Unicode NFC) and its bytes, in path order.
    Git may check text files out with CRLF line endings (`core.autocrlf`, `eol` attributes), so CRLF counts as
    LF in any file with no NUL byte in its first 8000 bytes, git's own test for binary. Names in
    `tree.PLUGIN_IGNORED_NAMES`, empty directories (git does not track them) and file modes (Windows has none) are
    left out, and so are the paths in `leaving_out` (relative, NFC), such as links already reported.
    """
    digest = hashlib.sha256()
    for relative, file in sorted(plugin_files(directory)):
        if relative in leaving_out:
            continue
        if file.is_symlink():
            return None
        content = file.read_bytes()
        if b"\0" not in content[:_BINARY_SNIFF]:
            content = content.replace(b"\r\n", b"\n")
        digest.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(content).hexdigest().encode() + b"\n")
    return digest.hexdigest()
