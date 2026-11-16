"""Paths and files charter works with: contract-relative paths, and writes that report failures as diagnostics."""

import contextlib
import os
import posixpath
import secrets
import shutil
import stat
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path, PureWindowsPath

from charter.diagnostics import FILES_LEFTOVER, Diagnostic, Refused, Severity

# A lock held by a program that is closing can last a moment; a longer wait would only stall the command.
_REMOVE_ATTEMPTS = 4
_REMOVE_PAUSE_SECONDS = 0.1


@contextlib.contextmanager
def writing(path: str, code: str) -> Iterator[None]:
    """Turns an OSError while writing `path` (diagnostic form) into Refused with `code`."""
    try:
        yield
    except OSError as error:
        raise Refused([
            Diagnostic(
                path,
                None,
                Severity.ERROR,
                code,
                f"`{path}` could not be written: {error.strerror or error}.",
                "Check that the path is a file, or a place for one, that can be written to.",
            )
        ]) from None


def append_lines(file: Path, lines: Iterable[str]) -> None:
    """Appends `lines` to `file`, creating it if missing, in the file's own line endings."""
    existing = file.read_bytes() if file.exists() else b""
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    ending = b"" if not existing or existing.endswith(b"\n") else newline
    file.write_bytes(existing + ending + b"".join(line.encode() + newline for line in lines))


def replace_file(path: Path, data: bytes) -> None:
    """Writes `data` to `path` all at once: readers, and a write that fails midway, never leave it half-written."""
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    # os.open applies the umask to 0o666, so the file gets the permissions any new file would.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def contract_relative(path: str) -> str | None:
    """`path` in diagnostic form, or None when it is absolute or leaves the directory holding charter.yaml."""
    posix = path.replace("\\", "/")
    normal = posixpath.normpath(posix)
    # A drive (`C:`) makes a path absolute or drive-relative on Windows, whichever platform reads the contract.
    if PureWindowsPath(path).drive or posixpath.isabs(posix) or normal == ".." or normal.startswith("../"):
        return None
    return normal


def remove_tree(path: Path) -> list[Path]:
    """Deletes the directory `path` and everything in it, clearing the read-only bit of what blocks the delete
    and trying again a few times, as a file another program is closing may be released in a moment. Returns what
    is still there, which is empty when `path` is gone (or never existed)."""
    stuck: list[Path] = []
    for attempt in range(_REMOVE_ATTEMPTS):
        if attempt:
            time.sleep(_REMOVE_PAUSE_SECONDS)
        stuck = []
        _rmtree(path, stuck)
        if not os.path.lexists(path):
            return []
    remaining = [p for p in stuck if os.path.lexists(p)]
    # A folder cannot go while a file in it stays; the file is the one to name.
    return [p for p in remaining if not any(p in other.parents for other in remaining)] or [path]


def _rmtree(root: Path, stuck: list[Path]) -> None:
    def unblock(function: Callable[..., object], failing: str, _error: object) -> None:
        blocked = Path(failing)
        # Deleting a file needs the folder holding it to be writable, which is the read-only part on POSIX.
        for place in (blocked, blocked.parent) if blocked != root else (blocked,):
            with contextlib.suppress(OSError):
                mode = place.lstat().st_mode
                if not stat.S_ISLNK(mode):
                    place.chmod(mode | stat.S_IRWXU)
        # Only a delete can be retried as it stands; a failure to list or open a folder is left to the next
        # attempt, now that the bits are fixed.
        try:
            if function not in (os.unlink, os.rmdir):
                raise OSError
            function(failing)
        except OSError:
            stuck.append(blocked)

    if sys.version_info >= (3, 12):
        shutil.rmtree(root, onexc=unblock)
    else:  # `onerror` is deprecated from 3.12, and `onexc` does not exist before it
        shutil.rmtree(root, onerror=lambda function, failing, info: unblock(function, failing, info[1]))


def left_behind(paths: Iterable[Path], base: Path | None = None) -> list[Diagnostic]:
    """A warning for each of `paths` that `remove_tree` could not delete, shown relative to `base` when it is
    inside it."""
    warnings = []
    for path in paths:
        try:
            shown = path.relative_to(base).as_posix() if base is not None else path.as_posix()
        except ValueError:
            shown = path.as_posix()
        warnings.append(
            Diagnostic(
                shown,
                None,
                Severity.WARNING,
                FILES_LEFTOVER,
                f"`{shown}` could not be deleted and was left behind.",
                "Delete it yourself; a file in it may be read-only or still open in another program.",
            )
        )
    return warnings
