"""The plugin lifecycle under `charter plugin`: copying a plugin into `.charter/plugins/<id>/`, enabling it in
charter.yaml and locking it in charter.lock with its source and content hash; updating, enabling, disabling and
removing it again.
"""

import contextlib
import dataclasses
import functools
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from charter import checksedit
from charter.contract import PluginSettings
from charter.diagnostics import CORE_NAMESPACES, Diagnostic, Refused, Severity, code_list
from charter.files import append_lines, left_behind, remove_tree, replace_file, writing
from charter.lock import (
    IGNORED_NAMES,
    LOCK_FILENAME,
    PLUGINS_DIR,
    DevSource,
    GitSource,
    Locked,
    content_hash,
    is_vendored,
    lock_bytes,
    symlink_reason,
    symlinks_in,
    vendored_directory,
    write_lock,
)
from charter.pathpattern import segment_problem
from charter.plugin import MANIFEST_FILENAME, manifest_of
from charter.process import Finished, run_bounded
from charter.validate import CHECK_CODES

WRITE_FAILED = "plugin/write-failed"
# Python plugins leave bytecode beside their modules, which never belongs in the repository.
GITIGNORE = ".gitignore"
GITIGNORE_ENTRIES = ("__pycache__/",)
FETCH_FAILED = "plugin/fetch-failed"
SOURCE_MISMATCH = "plugin/source-mismatch"
# Long enough for git's own error, which comes last.
_GIT_ERROR_SHOWN = 1000
# Generous for a slow network; a fetch that hangs must still end.
_GIT_TIMEOUT_SECONDS = 600
_GIT_OUTPUT_LIMIT = 16 * 1024 * 1024
# Where a URL's authority (`scheme://user@host`) ends, or an scp-style `user@host:` prefix.
_AUTHORITY = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]*|^[^/@:]+@[^/:]+:")


@dataclass(frozen=True)
class Added:
    id: str
    version: str
    origin: str
    directory: str
    replaced: bool
    # Whether `checks.<id>` was added to charter.yaml.
    entry_added: bool
    # The `.gitignore` entries added because the plugin is Python (see GITIGNORE_ENTRIES).
    ignored: tuple[str, ...] = ()
    # Warnings for what could not be cleaned up; the command itself succeeded.
    warnings: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class Updated:
    added: Added
    previous: Locked
    source: GitSource
    # Whether the directory no longer matched the lock before the update.
    restored: bool
    # Whether charter runs the plugin: it has a `checks` entry, enabled.
    enabled: bool

    @property
    def changed(self) -> bool:
        return (self.previous.version, self.previous.source) != (self.added.version, self.source)


@dataclass(frozen=True)
class Removed:
    id: str
    # The plugin's directory, deleted with its lock entry; None for a plugin charter did not install.
    deleted: str | None
    # The `source` of a plugin charter did not install, left in place.
    kept: str | None
    # Whether charter.yaml had a `checks` entry to remove.
    unchecked: bool
    # Warnings for what could not be cleaned up; the command itself succeeded.
    warnings: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class _Copy:
    source: Path
    version: str
    origin: GitSource | DevSource


@contextlib.contextmanager
def _clone_folder(leftovers: list[Diagnostic]) -> Iterator[Path]:
    """A fresh folder to clone a plugin into, deleted on the way out. A warning for what cannot be deleted goes to
    `leftovers`, or onto the failure that ended the block, never a traceback of its own."""
    temporary = Path(tempfile.mkdtemp(prefix="charter-plugin-"))
    try:
        yield temporary / "checkout"
    except BaseException as failure:
        warnings = left_behind(remove_tree(temporary))
        if warnings and isinstance(failure, Refused):
            raise Refused([*failure.diagnostics, *warnings], usage=failure.usage) from None
        for warning in warnings:
            failure.add_note(f"{warning.message} {warning.hint}")
        raise
    leftovers.extend(left_behind(remove_tree(temporary)))


def _with_warnings(added: Added, warnings: list[Diagnostic]) -> Added:
    return dataclasses.replace(added, warnings=(*added.warnings, *warnings))


def add_from_git(settings: PluginSettings, given: str) -> Added:
    url, ref = _split_ref(settings, given)
    leftovers: list[Diagnostic] = []
    with _clone_folder(leftovers) as checkout:
        commit = _fetch(settings, url, ref, checkout)
        added = _install(settings, checkout, GitSource(url, ref, commit), given)
    return _with_warnings(added, leftovers)


def add_dev(settings: PluginSettings, working_copy: Path) -> Added:
    if not working_copy.is_dir():
        raise Refused(
            [
                _problem(
                    settings,
                    "usage/invalid-source",
                    f"`{working_copy.as_posix()}` is not a directory.",
                    f"--dev takes the plugin's directory, the one holding `{MANIFEST_FILENAME}`.",
                )
            ],
            usage=True,
        )
    return _install(settings, working_copy, DevSource(), working_copy.as_posix())


def update(settings: PluginSettings, plugin_id: str, ref: str | None) -> Updated:
    """Fetches a plugin installed from git again, at `ref` or the ref it was installed from. charter.yaml is left
    as it is, so a disabled plugin stays disabled."""
    locked = settings.locked.get(plugin_id)
    # Before the fetch, and before `not-updatable`, which would otherwise answer for a plugin used elsewhere.
    refuse_foreign_source(settings, plugin_id)
    if locked is None or not isinstance(locked.source, GitSource):
        if plugin_id not in settings.plugin_ids:
            raise Refused([unknown_plugin(settings, plugin_id)], usage=True)
        how = (
            "was installed from a working copy, so add it again with `charter plugin add --dev <path>`"
            if locked is not None
            else f"is used in place from `{settings.checks[plugin_id].source}`, where it is kept up to date"
        )
        raise Refused(
            [
                _problem(
                    settings,
                    "usage/not-updatable",
                    f"Plugin `{plugin_id}` was not installed from git, so it cannot be updated: it {how}.",
                    "`update` fetches plugins installed with `charter plugin add --from`.",
                )
            ],
            usage=True,
        )
    source = locked.source
    if ref is not None and not _usable_ref(ref):
        raise Refused(
            [_problem(settings, "usage/invalid-source", f"`{ref}` is not a branch, tag or commit name.", None)],
            usage=True,
        )
    ref = ref or source.ref
    restored = content_hash(settings.base_dir / vendored_directory(plugin_id)) != locked.sha256
    leftovers: list[Diagnostic] = []
    with _clone_folder(leftovers) as checkout:
        fetched = GitSource(source.git, ref, _fetch(settings, source.git, ref, checkout))
        added = _install(settings, checkout, fetched, f"{source.git}@{ref}", plugin_id)
    config = settings.check_config(plugin_id)
    enabled = config.source is not None and config.enabled
    return Updated(_with_warnings(added, leftovers), locked, fetched, restored, enabled)


def set_enabled(settings: PluginSettings, plugin_id: str, enabled: bool) -> bool:
    """Sets `checks.<id>.enabled`, adding `checks.<id>` to enable a locked plugin that has none. Whether anything
    changed."""
    if plugin_id not in settings.plugin_ids:
        raise Refused([unknown_plugin(settings, plugin_id)], usage=True)
    config = settings.checks.get(plugin_id)
    if config is None:
        if not enabled:
            return False
        what = f"`checks.{plugin_id}` could not be added to"
        edit = functools.partial(checksedit.add_check, check_id=plugin_id, source=vendored_directory(plugin_id))
    else:
        if config.enabled is enabled:
            return False
        what = f"`checks.{plugin_id}.enabled` could not be set in"
        edit = functools.partial(checksedit.set_enabled, check_id=plugin_id, enabled=enabled)
    edited = _edited_checks(settings, what, edit)
    with writing(settings.file, WRITE_FAILED):
        replace_file(settings.base_dir / settings.file, edited)
    return True


def remove(settings: PluginSettings, plugin_id: str) -> Removed:
    """Removes a plugin's `checks` entry and, for one charter installed, its directory and lock entry: all of
    them or, when something cannot be changed, none."""
    if plugin_id not in settings.plugin_ids:
        raise Refused([unknown_plugin(settings, plugin_id)], usage=True)
    refuse_foreign_source(settings, plugin_id)
    edited = None
    if plugin_id in settings.checks:
        edit = functools.partial(checksedit.remove_check, check_id=plugin_id)
        edited = _edited_checks(settings, f"`checks.{plugin_id}` could not be removed from", edit)
    warnings = _commit(settings, plugin_id, None, edited)
    installed = plugin_id in settings.locked
    kept = None if installed else settings.checks[plugin_id].source
    return Removed(
        plugin_id, vendored_directory(plugin_id) if installed else None, kept, edited is not None, tuple(warnings)
    )


def refuse_foreign_source(settings: PluginSettings, plugin_id: str) -> None:
    """Refuses to add, update or remove a locked plugin whose `checks.<id>.source` is anywhere but the directory
    `plugin add` installs it in: charter runs the plugin from that other place, so changing the vendored copy
    would leave what runs untouched, or delete a copy that is not the one in use. Nothing is repaired; the
    contract and lock are the user's to edit."""
    config = settings.checks.get(plugin_id)
    if plugin_id not in settings.locked or config is None or config.source is None:
        return
    if is_vendored(plugin_id, config.source, settings.locked):
        return
    expected = vendored_directory(plugin_id)
    raise Refused([
        _problem(
            settings,
            SOURCE_MISMATCH,
            f"Plugin `{plugin_id}` is in `{LOCK_FILENAME}` as installed in `{expected}`, but "
            f"`checks.{plugin_id}.source` in `{settings.file}` is `{config.source}`, so charter runs the plugin "
            "from there and not from the copy this command would change.",
            f"Edit `source` back to `{expected}`, or delete the `{plugin_id}` entry under `plugins:` in "
            f"`{LOCK_FILENAME}` by hand if the plugin is meant to live at `{config.source}`; then run this "
            "command again.",
        )
    ])


def unknown_plugin(settings: PluginSettings, plugin_id: str) -> Diagnostic:
    known = settings.plugin_ids
    return _problem(
        settings,
        "usage/unknown-plugin",
        f"`{plugin_id}` is not a plugin: no `checks.{plugin_id}` in `{settings.file}` has a `source`, and "
        f"`{LOCK_FILENAME}` does not list it.",
        f"Plugins: {code_list(known)}." if known else "This knowledge base has no plugins.",
    )


# _one_per_path recognises the accurate diagnostic by this hint prefix.
_KEPT_HINT = "Its previous contents are kept at"


def _commit(
    settings: PluginSettings, plugin_id: str, copy: _Copy | None, contract: bytes | None
) -> list[Diagnostic]:
    """Puts a copy of `copy.source` in the plugin's directory and locks it or, without `copy`, deletes the
    directory and lock entry of a locked plugin; then writes `contract` as charter.yaml. When a write fails,
    what was already changed is put back, so all of it happens or none of it does. Returns warnings for staging
    that could not be deleted afterwards."""
    if copy is None and plugin_id not in settings.locked:
        if contract is not None:
            with writing(settings.file, WRITE_FAILED):
                replace_file(settings.base_dir / settings.file, contract)
        return []
    relative = vendored_directory(plugin_id)
    target = settings.base_dir / relative
    lock_file = settings.base_dir / LOCK_FILENAME
    created = [d for d in (target.parent, target.parent.parent) if not d.exists()]
    with writing(relative, WRITE_FAILED):
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=target.parent))
    new, previous = staging / "new", staging / "previous"
    kept = f"{PLUGINS_DIR}/{staging.name}/{previous.name}"
    existed = os.path.lexists(target)
    lock_before = lock_file.read_bytes() if lock_file.is_file() else None
    contract_file = settings.base_dir / settings.file
    contract_before = contract_file.read_bytes() if contract is not None and contract_file.is_file() else None
    written_lock: bytes | None = None

    # The undo reads what is on disk instead of what was recorded, so an interrupt between a step and any
    # bookkeeping still rolls back exactly what happened, and a step that never ran is left alone.
    def take_new_out() -> None:
        if copy is not None and not new.exists() and os.path.lexists(target) and (os.path.lexists(previous) or not existed):
            target.rename(new)

    def put_previous_back() -> None:
        if os.path.lexists(previous):
            previous.rename(target)

    # A file is put back only while it holds exactly what this command wrote (or what it started with, when the
    # write never ran). Anything else is someone's edit, which stays. Reading and then writing leaves a small
    # window for an edit in between; this narrows it and does not close it.
    def restore_lock() -> None:
        current = lock_file.read_bytes() if lock_file.is_file() else None
        if current == lock_before:
            return
        if written_lock is None or current != written_lock:
            raise _EditedMeanwhile
        if lock_before is None:
            lock_file.unlink()
        else:
            replace_file(lock_file, lock_before)

    def restore_contract() -> None:
        if contract is None or contract_before is None:
            return
        current = contract_file.read_bytes() if contract_file.is_file() else None
        if current == contract_before:
            return
        if current != contract:
            raise _EditedMeanwhile
        replace_file(contract_file, contract_before)

    undo = [
        _undoing(relative, take_new_out),
        _undoing(relative, put_previous_back, kept),
        _undoing(LOCK_FILENAME, restore_lock),
        _undoing(settings.file, restore_contract),
    ]
    try:
        locked = {other: entry for other, entry in settings.locked.items() if other != plugin_id}
        with writing(relative, WRITE_FAILED):
            if copy is not None:
                shutil.copytree(copy.source, new, ignore=shutil.ignore_patterns(*IGNORED_NAMES))
                sha256 = content_hash(new)
                # The source was checked for links, so the copy holds none and has a hash.
                assert sha256 is not None
                locked[plugin_id] = Locked(copy.version, copy.origin, sha256)
            if existed:
                target.rename(previous)
            if copy is not None:
                new.rename(target)
        with writing(LOCK_FILENAME, WRITE_FAILED):
            written_lock = lock_bytes(locked)
            write_lock(settings.base_dir, locked)
        if contract is not None:
            with writing(settings.file, WRITE_FAILED):
                replace_file(contract_file, contract)
    except BaseException as failure:
        # Any exception, an interrupt included, must leave the knowledge base as it was. Every step runs even
        # if another one fails, so one failed step does not strand the rest.
        unrestored = _one_per_path(problem for step in undo if (problem := step()) is not None)
        if unrestored and isinstance(failure, Refused):
            # The staging directory may hold the only copy of the previous plugin directory.
            raise Refused([*failure.diagnostics, *unrestored]) from None
        if unrestored:
            for problem in unrestored:
                failure.add_note(f"{problem.message} {problem.hint}")
        else:
            # A staging folder that is left behind also keeps its parent, which `_remove_if_empty` leaves alone.
            warnings = left_behind(remove_tree(staging), settings.base_dir)
            _remove_if_empty(created)
            if warnings and isinstance(failure, Refused):
                raise Refused([*failure.diagnostics, *warnings], usage=failure.usage) from None
            for warning in warnings:
                failure.add_note(f"{warning.message} {warning.hint}")
        raise
    return left_behind(remove_tree(staging), settings.base_dir)


def _remove_if_empty(directories: list[Path]) -> None:
    """Removes the directories this call had to create, innermost first, so an undone add leaves no trace."""
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            return


def _one_per_path(problems: Iterable[Diagnostic]) -> list[Diagnostic]:
    """One diagnostic per path. Two failed undo steps on a directory both name it; the one whose hint says where
    the previous copy is kept is the accurate one, since it is the only copy left."""
    chosen: dict[str, Diagnostic] = {}
    for problem in problems:
        held = chosen.get(problem.path)
        if held is None or (problem.hint or "").startswith(_KEPT_HINT):
            chosen[problem.path] = problem
    return list(chosen.values())


class _EditedMeanwhile(Exception):
    """A file this command changed, or meant to, holds something else now, so rolling back would overwrite it."""


def _undoing(shown: str, action: Callable[[], object], kept: str | None = None) -> Callable[[], Diagnostic | None]:
    """A rollback step: runs `action`, and reports `shown` as not restored when it fails."""

    def step() -> Diagnostic | None:
        try:
            action()
        except _EditedMeanwhile:
            return Diagnostic(
                shown,
                None,
                Severity.ERROR,
                WRITE_FAILED,
                f"`{shown}` could not be put back as it was after the failure: it was changed by something else "
                "while this command ran.",
                f"It was left as it is now; check `{LOCK_FILENAME}` by hand or restore it from version control. "
                "For a plugin installed with `--from` that the lock still lists, `charter plugin update <id>` "
                "writes its entry again; it fetches the plugin again, so a branch ref can bring in new commits."
                if shown == LOCK_FILENAME
                else "It was left as it is now; check that it says what you want.",
            )
        except BaseException as error:  # an interrupt during the undo must not skip the other steps
            reason = getattr(error, "strerror", None) or str(error) or type(error).__name__
            return Diagnostic(
                shown,
                None,
                Severity.ERROR,
                WRITE_FAILED,
                f"`{shown}` could not be put back as it was after the failure: {reason}.",
                f"{_KEPT_HINT} `{kept}`; move them back to `{shown}`."
                if kept is not None
                else f"Restore `{shown}` from version control.",
            )
        return None

    return step


def _edited_checks(settings: PluginSettings, what: str, edit: Callable[[bytes], bytes]) -> bytes:
    """charter.yaml's bytes after `edit`, or Refused saying `what` could not be done to it."""
    try:
        return edit((settings.base_dir / settings.file).read_bytes())
    except checksedit.NotEditable:
        raise Refused([
            _problem(
                settings,
                WRITE_FAILED,
                f"{what} `{settings.file}` without changing what else it says.",
                "Simplify how `checks:` is written, for example so that it does not end in a multi-line value, "
                "then run this command again.",
            )
        ]) from None


def _split_ref(settings: PluginSettings, given: str) -> tuple[str, str]:
    """`<git-url>@<ref>` as (url, ref). The `@` must follow the URL's host, so `https://user@host/repo` and
    `git@host:repo` alone are URLs without a ref."""
    authority = _AUTHORITY.match(given)
    at = given.rfind("@", authority.end() if authority else 0)
    url, ref = (given[:at], given[at + 1 :]) if at >= 0 else (given, "")
    if not url or url.endswith((":", "/")) or not _usable_ref(ref):
        raise Refused(
            [
                _problem(
                    settings,
                    "usage/invalid-source",
                    f"`{given}` is not a git URL followed by `@` and a ref.",
                    "Write the repository and the branch, tag or commit to install, e.g. "
                    "`https://example.com/word-limit.git@v1.0.0`.",
                )
            ],
            usage=True,
        )
    return url, ref


def _usable_ref(ref: str) -> bool:
    # git forbids `:` in a ref, and one starting with `-` would read as an option.
    return bool(ref) and ":" not in ref and not ref.startswith("-")


def _fetch(settings: PluginSettings, url: str, ref: str, checkout: Path) -> str:
    """Checks `ref` of `url` out into `checkout` and returns its commit."""
    _git(settings, ["clone", "--quiet", "--no-checkout", "--", url, str(checkout)], Path.cwd(), f"clone `{url}`")
    # A tag, a commit or the default branch resolves as given; other branches exist only as remote branches.
    for candidate in (ref, f"origin/{ref}"):
        found = _run_git(["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"], checkout)
        if found.returncode == 0:
            commit = found.stdout.decode().strip()
            break
    else:
        raise Refused([
            _problem(
                settings,
                FETCH_FAILED,
                f"`{ref}` is not a branch, tag or commit of `{url}`.",
                "Check the ref after `@`.",
            )
        ])
    # The files as committed, whatever this machine's line-ending settings; the content hash ignores them anyway.
    checkout_args = ["-c", "core.autocrlf=false", "checkout", "--quiet", "--detach", commit]
    _git(settings, checkout_args, checkout, f"check out `{ref}`")
    return commit


def _git(settings: PluginSettings, args: Sequence[str], cwd: Path, action: str) -> None:
    try:
        finished = _run_git(args, cwd)
    except OSError as error:
        raise Refused([
            _problem(
                settings,
                FETCH_FAILED,
                f"git could not be started: {error.strerror or error}.",
                "Install git and make sure it is on PATH.",
            )
        ]) from None
    if finished.timed_out:
        what = f"git did not {action} within {_GIT_TIMEOUT_SECONDS} seconds."
    elif finished.returncode != 0:
        text = finished.stderr.decode("utf-8", errors="replace").strip()
        if len(text) > _GIT_ERROR_SHOWN:
            text = "…" + text[-_GIT_ERROR_SHOWN:]
        what = f"git could not {action}" + (f":\n{text}" if text else ".")
    else:
        return
    raise Refused([_problem(settings, FETCH_FAILED, what, "Check the URL, and that this machine can reach it.")])


def _run_git(args: Sequence[str], cwd: Path) -> Finished:
    # Nobody may be there to answer a credential or host-key prompt, so git must fail instead of asking.
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    environment.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    argv = ["git", "-c", "credential.interactive=never", *args]
    return run_bounded(argv, cwd, b"", timeout=_GIT_TIMEOUT_SECONDS, limit=_GIT_OUTPUT_LIMIT, env=environment)


def _install(
    settings: PluginSettings, source: Path, origin: GitSource | DevSource, shown: str, updating: str | None = None
) -> Added:
    """Installs the plugin in `source`; `updating` names the plugin it must be when updating one, which leaves
    charter.yaml as it is."""
    manifest = manifest_of(source)
    if not isinstance(manifest, list) and updating not in (None, manifest["id"]):
        hint = "Update to a ref of the same plugin, or install this one with `charter plugin add`."
        manifest = [(f"its `id` is `{manifest['id']}`, but the plugin being updated is `{updating}`.", hint)]
    if not isinstance(manifest, list) and (unusable := _id_problem(manifest["id"])) is not None:
        manifest = [(unusable, "The plugin needs another id to be installed here.")]
    if isinstance(manifest, list):
        prefix = f"plugin manifest `{MANIFEST_FILENAME}` of `{shown}`:"
        raise Refused([_problem(settings, "plugin/invalid-manifest", f"{prefix} {m}", h) for m, h in manifest])
    if links := symlinks_in(source):
        raise Refused([
            _problem(
                settings,
                "plugin/symlink",
                f"`{shown}` {symlink_reason(link)}",
                "Ask the plugin's author to replace the link with the file it points to.",
            )
            for link in links
        ])
    plugin_id = manifest["id"]
    refuse_foreign_source(settings, plugin_id)
    relative = vendored_directory(plugin_id)
    target = settings.base_dir / relative
    replaced = plugin_id in settings.locked
    entry_added = updating is None and plugin_id not in settings.checks
    if not replaced and (plugin_id in settings.checks or os.path.lexists(target)):
        taken = f"`checks.{plugin_id}` in `{settings.file}`" if plugin_id in settings.checks else f"`{relative}`"
        raise Refused([
            _problem(
                settings,
                "plugin/exists",
                f"Plugin `{plugin_id}` cannot be added: {taken} already exists and is not in `{LOCK_FILENAME}`.",
                "Remove it first, or rename it, if the plugin should replace it.",
            )
        ])
    edited = None
    if entry_added:
        add = functools.partial(checksedit.add_check, check_id=plugin_id, source=relative)
        edited = _edited_checks(settings, f"`checks.{plugin_id}` could not be added to", add)
    # Before the copy, so a .gitignore that cannot be written refuses the install; one written before a failing
    # copy stays, which is harmless, as adding the entry again does nothing.
    ignored = _ignore_bytecode(settings.base_dir) if _is_python(source) else ()
    warnings = _commit(settings, plugin_id, _Copy(source, manifest["version"], origin), edited)
    return Added(plugin_id, manifest["version"], shown, relative, replaced, entry_added, ignored, tuple(warnings))


def _is_python(plugin: Path) -> bool:
    return any(
        file.is_file() and file.suffix == ".py" and not IGNORED_NAMES.intersection(file.relative_to(plugin).parts)
        for file in plugin.rglob("*.py")
    )


def _ignore_bytecode(base: Path) -> tuple[str, ...]:
    """Adds the entries `.gitignore` lacks, keeping its line endings and every line; returns those added."""
    gitignore = base / GITIGNORE
    with writing(GITIGNORE, WRITE_FAILED):
        existing = gitignore.read_bytes() if gitignore.exists() else b""
        present = {line.strip() for line in existing.decode("utf-8-sig", errors="replace").splitlines()}
        missing = tuple(entry for entry in GITIGNORE_ENTRIES if entry not in present)
        if missing:
            append_lines(gitignore, missing)
    return missing


def _id_problem(plugin_id: str) -> str | None:
    if plugin_id in CHECK_CODES:
        return f"its `id`, `{plugin_id}`, is a built-in check."
    if plugin_id in CORE_NAMESPACES:
        return f"its `id`, `{plugin_id}`, is reserved for charter's own diagnostics."
    if (problem := segment_problem(plugin_id)) is not None:
        return f"its `id`, `{plugin_id}`, {problem}, so it cannot name the plugin's directory."
    return None


def _problem(settings: PluginSettings, code: str, message: str, hint: str | None = None) -> Diagnostic:
    return Diagnostic(settings.file, None, Severity.ERROR, code, message, hint)
