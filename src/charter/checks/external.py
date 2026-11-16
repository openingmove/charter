"""An external plugin as a check: the run's index goes to its command as `charter-plugin/1` JSON on stdin,
and its diagnostics come back on stdout.

charter's diagnostic paths are relative to charter.yaml; the protocol's are relative to the knowledge-base
root, so paths are translated both ways here.
"""

import datetime
import json
import posixpath
from typing import Any

from charter import __version__
from charter.checks import CheckRequest
from charter.diagnostics import PLUGIN_FAILED, PLUGIN_MODIFIED, Diagnostic, Severity
from charter.files import contract_relative
from charter.history import EditDelta
from charter.index import Note
from charter.lock import LOCK_FILENAME, symlink_reason
from charter.plugin import Plugin
from charter.process import run_bounded
from charter.schemacheck import errors as schema_errors
from charter.schematext import located_message
from charter.tree import decode

PROTOCOL = "charter-plugin/1"
# Far beyond any real response, but keeps a runaway plugin from exhausting memory.
_OUTPUT_LIMIT = 16 * 1024 * 1024
# The end of stderr is where a traceback or error message usually is.
_STDERR_SHOWN = 2000

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "protocol": {"const": PROTOCOL},
        "diagnostics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "line": {"type": ["integer", "null"], "minimum": 1},
                    "severity": {"enum": [str(s) for s in Severity]},
                    "code": {"type": "string", "minLength": 1},
                    "message": {"type": "string", "minLength": 1},
                    "hint": {"type": ["string", "null"]},
                },
                "required": ["path", "severity", "code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["protocol", "diagnostics"],
    "additionalProperties": False,
}


class _Failed(Exception):
    def __init__(self, what: str, stderr: bytes = b""):
        super().__init__(what)
        self.what = what
        self.stderr = stderr


class PluginCheck:
    # A plugin declares no codes up front; profiles may name any code under its id.
    codes: frozenset[str] = frozenset()

    def __init__(self, plugin: Plugin):
        self.plugin = plugin
        self.id = plugin.id

    def run(self, request: CheckRequest) -> list[Diagnostic]:
        plugin = self.plugin
        if request.per_edit and not plugin.hook:
            return []
        if plugin.triggers is not None and not plugin.triggers.fire(request.kinds, _target_paths(request)):
            return []
        return self.invoke(request)

    def invoke(self, request: CheckRequest) -> list[Diagnostic]:
        """The plugin's diagnostics, or a single `plugin/failed` when it crashes, hangs or breaks the protocol.

        A locked plugin whose directory no longer matches its hash is not run at all: `plugin/modified`.
        """
        plugin = self.plugin
        if plugin.unavailable is not None:
            what = f"could not be run: its files in `{plugin.source}` could not be written out ({plugin.unavailable})."
            return [self._failure(request, _Failed(what))]
        # A link is reported instead of the hash mismatch it causes, in the same words whether it is in the
        # working copy or in the index.
        if plugin.links:
            reasons = [f"`{plugin.source}` {symlink_reason(link)}" for link in plugin.links]
        elif plugin.modified:
            reasons = [f"the files in `{plugin.source}` no longer match the sha256 recorded for it in `{LOCK_FILENAME}`."]
        else:
            reasons = []
        if reasons:
            return [
                Diagnostic(
                    request.contract.file,
                    plugin.line,
                    Severity.ERROR,
                    PLUGIN_MODIFIED,
                    f"Plugin `{self.id}` was not run: {reason}",
                    f"Restore `{plugin.source}` from version control, or install the plugin again with "
                    "`charter plugin add`.",
                )
                for reason in reasons
            ]
        try:
            return self._diagnostics(request)
        except _Failed as failure:
            return [self._failure(request, failure)]

    def payload(self, request: CheckRequest) -> str:
        """The `charter-plugin/1` request, as the JSON text the plugin reads on stdin."""
        return json.dumps(self._request(request), ensure_ascii=False, default=_json_value)

    def _diagnostics(self, request: CheckRequest) -> list[Diagnostic]:
        root = request.contract.root_path
        stdout, stderr = self._spawn(self.payload(request).encode("utf-8"))
        try:
            response = json.loads(stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise _Failed(f"did not write a JSON response on stdout: {error}.", stderr) from None
        broken = f"did not follow `{PROTOCOL}`:"
        if problems := schema_errors(_RESPONSE_SCHEMA, response):
            from jsonschema.exceptions import best_match  # only a malformed response needs it

            raise _Failed(f"{broken} {located_message(best_match(problems))[0]}", stderr)
        diagnostics = []
        for item in response["diagnostics"]:
            if not item["code"].startswith(f"{self.id}/"):
                raise _Failed(f"{broken} code `{item['code']}` is not under the plugin's id, `{self.id}/`.", stderr)
            # Backslashes and drives would read differently on each OS; the protocol's paths are POSIX.
            path = None if "\\" in item["path"] else contract_relative(item["path"])
            if path is None:
                raise _Failed(
                    f"{broken} path `{item['path']}` is not a POSIX path inside the knowledge-base root.", stderr
                )
            diagnostics.append(
                Diagnostic(
                    posixpath.normpath(posixpath.join(root, path)),
                    item.get("line"),
                    Severity(item["severity"]),
                    item["code"],
                    item["message"],
                    item.get("hint"),
                )
            )
        return diagnostics

    def _request(self, request: CheckRequest) -> dict[str, Any]:
        root = request.contract.root_path
        plugin = self.plugin

        def parts(note: Note) -> dict[str, Any]:
            return {
                "links": [
                    {
                        "raw": link.raw,
                        "target": _local(request, link.target) if link.target is not None else None,
                        "field": link.field,
                        "line": link.line,
                    }
                    for link in note.links
                ],
                "headings": [{"level": h.level, "text": h.text, "line": h.line} for h in note.headings],
                "tags": [tag.name for tag in note.tags],
            }

        def note(note: Note, parsed: bool) -> dict[str, Any]:
            shape = request.contract.shape_of(note.frontmatter)
            return {
                "path": _local(request, note.path),
                "kind": shape.kind.name if shape is not None else None,
                "variant": shape.variant.name if shape is not None and shape.variant is not None else None,
                "frontmatter": note.frontmatter,
                # Reading the parsed parts parses the body; a note sent without them stays unparsed.
                **(parts(note) if parsed else {"links": [], "headings": [], "tags": []}),
                **({"body": note.body} if "body" in plugin.needs else {}),
            }

        whole = plugin.scope == "vault" or request.whole
        targets = list(request.target_notes())
        if whole:
            notes = request.notes
        else:
            linked = {link.target for target in targets for link in target.links if link.target is not None}
            wanted = {*(target.path for target in targets), *linked}
            # A link may resolve to a file that is not a note (an image, the rulebook); only notes are indexed.
            notes = tuple(n for n in request.notes if n.path in wanted)
        # The targets are parsed for the run anyway, and so is every note of a whole run; only the notes a file-scope
        # plugin is sent for being linked to wait for it to declare that it reads bodies.
        parsed = {n.path for n in notes} if whole or "body" in plugin.needs else {t.path for t in targets}
        return {
            "protocol": PROTOCOL,
            "charter_version": __version__,
            "plugin": {"id": plugin.id, "version": plugin.version},
            "params": plugin.params,
            "mode": "vault" if whole else "file",
            "root": root,
            "targets": _target_paths(request),
            "today": request.today.isoformat(),
            "index": {"notes": [note(n, n.path in parsed) for n in notes]},
            **({"before": _before(request)} if "before" in plugin.needs else {}),
        }

    def _spawn(self, payload: bytes) -> tuple[bytes, bytes]:
        plugin = self.plugin
        try:
            finished = run_bounded(
                plugin.run, plugin.directory, payload, timeout=plugin.timeout_ms / 1000, limit=_OUTPUT_LIMIT
            )
        except OSError as error:
            raise _Failed(f"could not start `{plugin.run[0]}`: {error.strerror or error}.") from None
        if finished.timed_out:
            raise _Failed(f"did not finish within {plugin.timeout_ms} ms.", finished.stderr)
        if finished.overflowed:
            raise _Failed(f"wrote more than {_OUTPUT_LIMIT // (1024 * 1024)} MB to stdout or stderr.", finished.stderr)
        if finished.returncode != 0:
            raise _Failed(f"exited with status {finished.returncode}.", finished.stderr)
        return finished.stdout, finished.stderr

    def _failure(self, request: CheckRequest, failure: _Failed) -> Diagnostic:
        text = failure.stderr.decode("utf-8", errors="replace").strip()
        if len(text) > _STDERR_SHOWN:
            text = "…" + text[-_STDERR_SHOWN:]
        return Diagnostic(
            request.contract.file,
            self.plugin.line,
            Severity.ERROR,
            PLUGIN_FAILED,
            f"Plugin `{self.id}` {failure.what}" + (f" Its stderr:\n{text}" if text else ""),
            f"Fix the plugin, or turn it off with `checks.{self.id}.enabled: false` in charter.yaml.",
        )


def _local(request: CheckRequest, path: str) -> str:
    """`path`, in diagnostic form, as the protocol gives it: relative to the knowledge-base root."""
    return posixpath.relpath(path, request.contract.root_path)


def _before(request: CheckRequest) -> dict[str, Any]:
    """The files the run's change touched in the knowledge base, each with its content before the change."""
    history = request.history
    if not isinstance(history, EditDelta):
        reason = history.reason if history is not None else "this run compares nothing with an earlier version"
        return {"available": False, "reason": reason, "files": []}
    touched = [path for path in history.touched() if request.contract.holds(path)]
    contents = history.before.read(touched)
    return {
        "available": True,
        "reason": None,
        "files": [
            {"path": _local(request, path), "status": history.status(path), "content": _text(contents.get(path))}
            for path in touched
        ],
    }


def _text(content: bytes | None) -> str | None:
    if content is None:
        return None
    try:
        return decode(content)
    except UnicodeDecodeError:
        return None


def _target_paths(request: CheckRequest) -> list[str]:
    return [_local(request, note.path) for note in request.target_notes()]


def _json_value(value: Any) -> str:
    # YAML reads unquoted dates and timestamps as Python objects; JSON has no type for them.
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)
