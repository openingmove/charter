"""`charter snapshot` and `charter snapshot restore`: a zip of a whole folder, and the way back.

Both run before any contract exists (Migrate takes a snapshot first), so neither loads or searches for one.

What a snapshot holds:
- Every file and every directory under the folder, empty directories included, dotfiles and `.git` and
  `.obsidian` too. There are no ignore rules: the point is a faithful way back.
- Nothing else. No manifest entry is added to the tree; the only metadata is the zip comment, a small JSON
  document naming the folder, which is how `restore ZIP` knows where to put it back.
- Paths are stored POSIX-style, relative to the folder, so one snapshot restores the same on every OS.
- Symlinks and other special files (sockets, fifos) are refused, listed, with nothing written: following one
  could pull in files from outside the folder, and storing one as a link would restore differently per OS.
- File modes are not kept, except the executable bit. Modification times are kept to the zip format's
  two-second resolution, read in the writing machine's local time zone. Contents are byte for byte.

Restore trusts nothing in the archive. Every entry is checked before anything is extracted, and one unsafe
entry (`..`, an absolute path, a drive letter, a backslash, a link, a duplicate) refuses the whole archive.
Files are extracted into a temporary sibling folder and swapped into place, so a failure leaves the target as it
was; with `--replace` the old target is moved aside and removed only once the new content is in place.
"""

import contextlib
import dataclasses
import datetime
import errno
import json
import os
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import time
import unicodedata
import uuid
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from charter.diagnostics import Diagnostic, Refused, Severity
from charter.files import remove_tree
from charter.pathpattern import windows_reserved

FORMAT_ID = "charter-snapshot/1"
# Colons would make the default name illegal on Windows.
STAMP_FORMAT = "%Y-%m-%dT%H%M%SZ"
# A module constant so tests can pose as Windows.
_ON_WINDOWS = os.name == "nt"
_WINDOWS_FORBIDDEN = re.compile(r'[<>:"|?*\x00-\x1f]')
_DRIVE = re.compile(r"^[A-Za-z]:")
_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Taken:
    archive: Path
    folder: Path
    files: int
    folders: int


@dataclass(frozen=True)
class Restored:
    target: Path
    files: int
    folders: int
    # True only when a folder with content was swapped out.
    replaced: bool
    # The hidden staging and old-target folders that could not be deleted.
    leftovers: list[Path] = field(default_factory=list)


def take(folder: Path, to: str | None = None) -> Taken:
    """Zip `folder` beside it, or at `to`: a `.zip` path, or a folder (existing, or ending in a separator) to put
    the default name in. `to` is the raw argument: `Path` would drop the trailing separator that says "folder".

    Raises Refused. Never overwrites a file and never writes inside `folder`."""
    if not folder.is_dir():
        raise _refuse(folder, "usage/folder-not-found", f"`{folder.as_posix()}` is not an existing folder.",
                      "snapshot takes the folder to save a copy of.", usage=True)
    source = folder.resolve()
    if not source.name:
        raise _refuse(folder, "usage/folder-not-found", "The root of a filesystem cannot be snapshotted.",
                      "Name the knowledge base's own folder.", usage=True)
    try:
        files, directories = _inventory(folder, source)
    except OSError as error:
        raise _refuse(Path(error.filename or folder), "snapshot/unreadable",
                      f"Could not read `{error.filename or folder}`: {error.strerror or error}.",
                      "Fix its permissions or move it out of the folder; nothing was written.") from None
    destination = Path(to) if to is not None else None
    # Absolute and symlink-free, so the printed restore command works from any directory.
    if destination is None:
        explicit, directory = None, source.parent
    elif to.endswith(("/", os.sep)) or destination.is_dir():
        explicit, directory = None, destination.resolve()
    else:
        directory = destination.parent.resolve()
        explicit = directory / destination.name
    _refuse_inside(source, explicit or directory, folder)
    comment = json.dumps({"format": FORMAT_ID, "folder": source.name}).encode("utf-8")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        archive = _write(source, files, directories, comment, explicit, directory)
    except OSError as error:
        raise _refuse(explicit or directory, "snapshot/write-failed", f"Could not complete the snapshot: {error}.",
                      "Nothing was kept; pick a writable location with --to.") from None
    return Taken(archive, source, len(files), len(directories))


def restore(archive: Path, to: Path | None = None, *, replace: bool = False) -> Restored:
    """Unpack `archive` into `to`, or, without `to`, into the recorded folder name beside the archive.

    Raises Refused, having extracted nothing the target can see."""
    if not archive.is_file():
        raise _refuse(archive, "usage/file-not-found", f"`{archive.as_posix()}` is not an existing file.",
                      "snapshot restore takes the zip that `charter snapshot` wrote.", usage=True)
    with _archive_data(archive):
        bundle = zipfile.ZipFile(archive)
    with bundle:
        entries = _vet(bundle.infolist(), archive)
        target = to if to is not None else _recorded_target(bundle, archive)
        return _unpack(bundle, entries, archive, target, replace)


# A bogus offset makes seek fail with these, and a damaged bzip2 stream raises OSError without any errno.
_DAMAGE_ERRNOS = (None, errno.EINVAL, errno.EOVERFLOW)


@contextlib.contextmanager
def _archive_data(archive: Path) -> Iterator[None]:
    """Wrap ONLY the calls that make zipfile read or decode the archive (opening it, opening and reading an
    entry), never charter's own code. The set of errors zipfile and its decompressors raise for damaged input is
    open-ended (every Python release can add a decompressor error class), so any Exception here means the
    archive is not sound: `snapshot/corrupt`. The exception is an OSError that is a genuine failure of the
    operating system to read the file (EIO, EACCES, ...): that says nothing about the archive, so it is
    `snapshot/unreadable`. An OSError with no errno (bzip2 "Invalid data stream") or EINVAL/EOVERFLOW (a seek to a
    garbage offset) is the archive's fault."""
    try:
        yield
    except OSError as error:
        if error.errno in _DAMAGE_ERRNOS:
            raise _corrupt(archive, error) from None
        raise _refuse(archive, "snapshot/unreadable", f"Could not read `{archive.as_posix()}`: {error.strerror or error}.",
                      "Fix its permissions or copy it somewhere readable; nothing was extracted.") from None
    except Exception as error:
        raise _corrupt(archive, error) from None


def _corrupt(archive: Path, error: Exception) -> Refused:
    detail = "a file name in it is not valid UTF-8" if isinstance(error, UnicodeDecodeError) else str(error)
    return _refuse(archive, "snapshot/corrupt", f"`{archive.as_posix()}` is not a readable zip ({detail or type(error).__name__}).",
                   "Restore needs a complete zip written by `charter snapshot`. Nothing was extracted; "
                   "the target was left as it was.", usage=True)


def restore_command(taken: Taken) -> str:
    """The command line that puts `taken` back over its folder, every path absolute and quoted for this OS."""
    argv = ["charter", "snapshot", "restore", str(taken.archive), "--to", str(taken.folder), "--replace"]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


# --- taking ---


def _inventory(folder: Path, source: Path) -> tuple[list[Path], list[Path]]:
    """Every file and folder under `source`. Refused, listing them, if any cannot be stored so that restore
    brings it back; an OSError from reading the tree propagates."""
    files: list[Path] = []
    directories: list[Path] = []
    unsupported: list[str] = []
    folded: dict[str, str] = {}
    pending = [source]
    while pending:
        current = pending.pop()
        with os.scandir(current) as scan:
            children = sorted(scan, key=lambda entry: entry.name)
        for child in children:
            path = Path(child.path)
            name = path.relative_to(source).as_posix()
            problem = _name_problem(name, windows=_ON_WINDOWS)
            if problem is None:
                try:
                    name.encode("utf-8")
                except UnicodeEncodeError:
                    problem = "name is not valid UTF-8"
            if problem is None and _fold(name) in folded:
                problem = f"differs only in letter case or Unicode form from {folded[_fold(name)]!r}"
            folded.setdefault(_fold(name), name)
            if problem:
                unsupported.append(f"{name!r} ({problem})")
            if child.is_symlink():
                if not problem:
                    unsupported.append(f"{name!r} (symbolic link)")
            elif child.is_dir(follow_symlinks=False):
                directories.append(path)
                pending.append(path)
            elif child.is_file(follow_symlinks=False):
                files.append(path)
            elif not problem:
                unsupported.append(f"{name!r} (not a regular file)")
    if unsupported:
        shown = ", ".join(sorted(unsupported)[:5]) + (", ..." if len(unsupported) > 5 else "")
        raise _refuse(
            folder, "snapshot/unsupported-entry",
            f"`{folder.as_posix()}` holds {len(unsupported)} entries a snapshot cannot store so that restore "
            f"brings them back: {shown}.",
            "Rename the files and folders with unusable names, and replace symbolic links and special files with "
            "real files or folders (or move them out), then snapshot again; nothing was written.",
        )
    return sorted(files), sorted(directories)


def _fold(name: str) -> str:
    """The name as a case-insensitive volume sees it, so entries that would collide there are found."""
    return unicodedata.normalize("NFC", name).casefold()


def _refuse_inside(source: Path, destination: Path, folder: Path) -> None:
    # Resolve `..` and symlinks first: a lexical comparison is fooled by both. A destination that does not exist
    # yet cannot be resolved to the volume's real letter case, so compare its nearest existing ancestor with
    # `samefile`, which asks the filesystem.
    ancestor = destination.resolve()
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if any(_same_file(candidate, source) for candidate in (ancestor, *ancestor.parents)):
        raise _refuse(
            destination, "usage/snapshot-inside-folder",
            f"`{destination.as_posix()}` is inside `{folder.as_posix()}`; a snapshot cannot be written into the folder it copies.",
            "Leave out --to to write beside the folder, or choose a location outside it.", usage=True,
        )


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _write(source: Path, files: list[Path], directories: list[Path], comment: bytes, explicit: Path | None,
           destination_dir: Path) -> Path:
    if explicit is not None:
        try:
            return _create(explicit, source, files, directories, comment)
        except FileExistsError:
            raise _refuse(explicit, "snapshot/exists", f"`{explicit.as_posix()}` already exists; a snapshot never overwrites a file.",
                          "Choose another name with --to, or remove the old file yourself.") from None
    stamp = datetime.datetime.now(datetime.UTC).strftime(STAMP_FORMAT)
    for attempt in range(1, 1000):
        suffix = "" if attempt == 1 else f"-{attempt}"
        candidate = destination_dir / f"{source.name}-{stamp}{suffix}.zip"
        try:
            return _create(candidate, source, files, directories, comment)
        except FileExistsError:
            continue
    raise OSError("could not find an unused snapshot name")


def _create(archive: Path, source: Path, files: list[Path], directories: list[Path], comment: bytes) -> Path:
    # Exclusive create: a snapshot that already exists, even one made a moment ago, is never overwritten.
    bundle = zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED)
    try:
        with bundle:
            bundle.comment = comment
            for path in directories + files:
                name = path.relative_to(source).as_posix()
                info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
                if path.is_dir():
                    bundle.writestr(info, b"")
                else:
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with path.open("rb") as content, bundle.open(info, "w", force_zip64=True) as out:
                        shutil.copyfileobj(content, out, _COPY_CHUNK)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    return archive


# --- restoring ---


def _vet(infos: list[zipfile.ZipInfo], archive: Path) -> list[zipfile.ZipInfo]:
    """The entries, if every one is safe to extract; otherwise Refused naming the offenders."""
    taken: dict[str, str] = {}  # every spelling already seen, folded, with the spelling it was registered under
    problems: list[str] = []
    for info in infos:
        reason = _unsafe(info, windows=_ON_WINDOWS)
        spellings = _spellings(info)
        if reason is None:
            for name in spellings:
                earlier = taken.get(_fold(name.rstrip("/")))
                if earlier is not None:
                    reason = ("listed twice" if earlier == name.rstrip("/") else
                              f"differs only in letter case or Unicode form from {earlier!r}, "
                              "so it cannot restore on every volume")
                    break
        if reason is None:
            for name in spellings:
                taken.setdefault(_fold(name.rstrip("/")), name.rstrip("/"))
        else:
            problems.append(f"{info.orig_filename!r} ({reason})")
    if problems:
        shown = ", ".join(problems[:5]) + (", ..." if len(problems) > 5 else "")
        raise _refuse(
            archive, "snapshot/unsafe-archive",
            f"`{archive.as_posix()}` was refused, nothing extracted: {len(problems)} unsafe entries: {shown}.",
            "Only zips written by `charter snapshot` are safe to restore.", usage=True,
        )
    return infos


def _spellings(info: zipfile.ZipInfo) -> list[str]:
    """The names an entry goes by. zipfile keeps the archive's own spelling in `orig_filename` and rewrites it
    into `filename` (backslashes become slashes on Windows, the name is cut at a NUL, and since Python 3.12 a
    Unicode Path extra field replaces it), and extraction uses `filename`. Both are attack surface, so both are
    judged; they may differ in a legitimate archive (Info-ZIP writes the extra field for non-ASCII names). The
    field's name is judged as written too, since zipfile's rewrite would hide a backslash on Windows only."""
    return list(dict.fromkeys([info.orig_filename, info.filename, *_unicode_path(info)]))


_UNICODE_PATH = 0x7075


def _unicode_path(info: zipfile.ZipInfo) -> list[str]:
    """The name in the entry's Unicode Path extra field as written, when zipfile reads that field (3.12+): version
    1, and a checksum that matches the header's name."""
    if sys.version_info < (3, 12):
        return []
    try:
        header = info.orig_filename.encode("utf-8" if info.flag_bits & 0x800 else "cp437")
    except UnicodeEncodeError:
        return []
    extra = info.extra
    while len(extra) >= 4:
        kind, size = struct.unpack("<HH", extra[:4])
        data, extra = extra[4 : 4 + size], extra[4 + size :]
        if kind == _UNICODE_PATH and len(data) >= 5:
            version, checksum = struct.unpack("<BL", data[:5])
            if version == 1 and checksum == zlib.crc32(header):
                try:
                    name = data[5:].decode("utf-8")
                except UnicodeDecodeError:
                    return []
                return [name] if name else []
    return []


def _unsafe(info: zipfile.ZipInfo, *, windows: bool) -> str | None:
    for name in _spellings(info):
        problem = _name_problem(name, windows=windows)
        if problem:
            if name != info.orig_filename:
                problem += f"; its Unicode path extra field names {name!r}"
            return problem
    if info.flag_bits & 0x1:
        return "encrypted"
    mode = info.external_attr >> 16
    if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
        return "not a regular file or folder"
    return None


def _name_problem(name: str, *, windows: bool) -> str | None:
    """Why a stored path cannot be extracted safely and identically everywhere; the one rule set for both
    taking and restoring, so a snapshot is never made that restore would refuse."""
    if "\\" in name:
        return "backslash in the path"
    if "\x00" in name:
        return "NUL in the path"
    if name.startswith("/") or _DRIVE.match(name):
        return "absolute path"
    parts = name.rstrip("/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "empty, `.` or `..` path component"
    if windows and any(_WINDOWS_FORBIDDEN.search(part) or part.endswith((".", " ")) for part in parts):
        return "a character Windows cannot use in a name"
    # A write to `NUL` or `CON` goes to the device, so the file would be lost while restore reports success.
    if windows and any(windows_reserved(part) for part in parts):
        return "a name Windows reserves for a device"
    return None


def _recorded_target(bundle: zipfile.ZipFile, archive: Path) -> Path:
    try:
        recorded = json.loads(bundle.comment.decode("utf-8"))
        name = recorded["folder"]
        valid = recorded["format"] == FORMAT_ID and isinstance(name, str)
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid or not name or name in (".", "..") or any(c in name for c in "/\\\x00") or _DRIVE.match(name):
        raise _refuse(
            archive, "usage/no-recorded-folder",
            f"`{archive.as_posix()}` does not record which folder it came from.",
            "Say where to restore it with --to FOLDER.", usage=True,
        )
    return archive.resolve().parent / name


def _unpack(bundle: zipfile.ZipFile, entries: list[zipfile.ZipInfo], archive: Path, target: Path,
            replace: bool) -> Restored:
    target = Path(os.path.abspath(target))
    state = _existing_state(target, archive, replace)
    staging = target.parent / f".{target.name}.charter-restore-{uuid.uuid4().hex[:8]}"
    aside = target.parent / f".{target.name}.charter-old-{uuid.uuid4().hex[:8]}"
    try:
        # Inside the handler: an unwritable or file-blocked parent and a full disk surface here as OSError.
        target.parent.mkdir(parents=True, exist_ok=True)
        # Plain mkdir, not mkdtemp: the folder becomes the target and should get the umask's permissions, not 0700.
        staging.mkdir()
        files, folders = _extract(bundle, entries, staging, archive)
        _swap(staging, target, aside, swap_out=state != "missing")
    except BaseException as error:
        # The staging folder may never have been created; remove_tree is a quiet success then. The aside folder
        # is left alone: after a failure it is either back in place or the only copy of the old content.
        stuck = remove_tree(staging)
        if isinstance(error, OSError):
            error = _refuse(target, "snapshot/restore-failed", f"Could not restore: {error}.",
                            "The target was left as it was.")
        if not isinstance(error, Refused):
            raise
        raise _naming_leftovers(error, stuck) from None
    # On success the staging folder has become the target, so only a failed rename leaves it.
    stuck = remove_tree(staging) + remove_tree(aside)
    return Restored(target, files, folders, state == "occupied", stuck)


def _naming_leftovers(refusal: Refused, leftovers: list[Path]) -> Refused:
    """`refusal`, its hint also asking for `leftovers` to be removed."""
    if not leftovers:
        return refusal
    first, *rest = refusal.diagnostics
    named = ", ".join(f"`{path.as_posix()}`" for path in leftovers)
    hint = f"{(first.hint or '').rstrip('.')}; also remove {named} yourself."
    return Refused([dataclasses.replace(first, hint=hint), *rest], usage=refusal.usage)


def _swap(staging: Path, target: Path, aside: Path, *, swap_out: bool) -> None:
    """Move `staging` to `target`, the old target going to `aside` first. On any failure, even an interrupt, the
    old target is put back; if that fails too, Refused says where the old content is."""
    try:
        if swap_out:
            target.rename(aside)
        staging.rename(target)
    except BaseException:
        if aside.exists() and not target.exists():
            try:
                aside.rename(target)
            except OSError as error:
                raise _refuse(
                    target, "snapshot/restore-failed",
                    f"Could not restore, and could not put the old `{target.as_posix()}` back ({error}). "
                    f"Its content is intact in `{aside.as_posix()}`.",
                    f"Rename `{aside.as_posix()}` to `{target.as_posix()}` to get it back.",
                ) from None
        raise


def _existing_state(target: Path, archive: Path, replace: bool) -> str:
    """"missing", "empty" or "occupied" (a folder with content, only with `replace`); Refused if the target is
    in the way."""
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise _refuse(target, "snapshot/target-in-the-way", f"`{target.as_posix()}` exists and is not a folder.",
                      "Restore to a path that does not exist, or to an empty folder.")
    if not target.exists():
        return "missing"
    occupied = any(target.iterdir())
    if occupied and not replace:
        raise _refuse(target, "snapshot/target-not-empty", f"`{target.as_posix()}` is not empty; restore would overwrite it.",
                      "Restore to another folder with --to, or add --replace to swap this one for the snapshot.")
    resolved = target.resolve()
    for path, what in ((archive.resolve(), "the zip being restored"), (Path.cwd().resolve(), "the working directory")):
        if path == resolved or resolved in path.parents:
            raise _refuse(target, "snapshot/target-holds-input", f"`{target.as_posix()}` holds {what}, which restoring over it would delete.",
                          "Run the command from elsewhere, and keep the zip outside the folder.")
    return "occupied" if occupied else "empty"


def _extract(bundle: zipfile.ZipFile, entries: list[zipfile.ZipInfo], staging: Path,
             archive: Path) -> tuple[int, int]:
    files = folders = 0
    directories: list[tuple[Path, zipfile.ZipInfo]] = []
    for info in entries:
        path = staging.joinpath(*PurePosixPath(info.filename).parts)
        if info.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            directories.append((path, info))
            folders += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with _archive_data(archive):
            content = bundle.open(info)
        with content, path.open("xb") as out:
            while chunk := _read_entry(content, archive):
                out.write(chunk)
        _apply_attributes(path, info)
        files += 1
    # After the contents, deepest first: adding a file changes its folder's modification time.
    for path, info in sorted(directories, key=lambda pair: len(pair[0].parts), reverse=True):
        _apply_attributes(path, info, executable=False)
    return files, folders


def _read_entry(content: zipfile.ZipExtFile, archive: Path) -> bytes:
    """The next chunk of an entry. Reading is kept apart from writing the target so that a read error is judged
    as archive data (see `_archive_data`) and only a failed write is `snapshot/restore-failed`."""
    with _archive_data(archive):
        return content.read(_COPY_CHUNK)


def _apply_attributes(path: Path, info: zipfile.ZipInfo, *, executable: bool = True) -> None:
    with contextlib.suppress(OSError, OverflowError, ValueError):
        stamp = time.mktime((*info.date_time, 0, 0, -1))
        os.utime(path, (stamp, stamp))
    mode = info.external_attr >> 16
    if executable and mode & 0o100:
        current = path.stat().st_mode
        # Execute wherever read is allowed, like `chmod +x`.
        with contextlib.suppress(OSError):
            path.chmod(current | ((current & 0o444) >> 2))


def _refuse(path: Path, code: str, message: str, hint: str, *, usage: bool = False) -> Refused:
    return Refused([Diagnostic(path.as_posix(), None, Severity.ERROR, code, message, hint)], usage=usage)
