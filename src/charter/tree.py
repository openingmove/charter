"""Where charter reads a knowledge base's files from: the working copy, or a snapshot of it such as git's staged
content. Paths are in diagnostic form: POSIX, relative to the directory holding charter.yaml."""

import os
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Protocol

# Version-control internals are never part of a knowledge base, even when root is the repository.
_SKIPPED_DIRECTORIES = frozenset({".git"})
# Never part of a plugin: version control, the bytecode Python leaves beside modules it runs, files the OS drops into
# folders, tool caches and virtual environments. The one list of names a plugin's files leave out, for its content
# hash, its links and its copy alike. A name matches a file or directory at any depth, in exact letter case.
PLUGIN_IGNORED_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
    }
)


class Tree(Protocol):
    holder: str  # What holds the files, for messages: `working copy`, `commit` or `index`.

    def files(self, under: str, suffix: str = "") -> list[str]:
        """Every file at or below the directory `under` whose name ends with `suffix`, sorted."""
        ...

    def listed(self, under: str) -> list[str]:
        """Every name `files(under)` would give, sorted, without checking that each is a file: a broken link
        may be among them. Cheaper than `files` on a tree of many files that nothing reads."""
        ...

    def read(self, paths: Iterable[str]) -> dict[str, bytes]:
        """The contents of those of `paths` that are files that could be read."""
        ...

    def is_file(self, path: str) -> bool: ...

    def exists(self, path: str) -> bool: ...

    def is_exact_file(self, path: str) -> bool:
        """Whether `path` is a file whose every segment matches a real name in case, on any file system. Looks
        only at the directories along `path`, never beyond."""
        ...

    def is_directory(self, path: str) -> bool:
        """Whether `path` is a directory, or `.`. A git tree holds no empty directories, so there it means one
        with a file at or below it."""
        ...

    def directory(self, path: str) -> Path:
        """A directory on disk holding the tree's files at or below `path`, for a program to run from."""
        ...

    def symlinks(self, path: str) -> list[str]:
        """The symbolic links at or below the directory `path`, relative to it (POSIX, NFC, sorted), whatever
        `directory(path)` made of them: a commit's or the index's `directory` writes a link out as the file it
        leads to."""
        ...


class WorkingTree:
    holder = "working copy"

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def files(self, under: str, suffix: str = "") -> list[str]:
        found = []
        for directory, subdirectories, filenames in os.walk(self.base_dir / under):
            subdirectories[:] = [name for name in subdirectories if name not in _SKIPPED_DIRECTORIES]
            # Names are filtered before any file is stat-ed, so a big tree of other files costs only its listing.
            found += [Path(directory, name) for name in filenames if name.endswith(suffix)]
        return sorted(file.relative_to(self.base_dir).as_posix() for file in found if file.is_file())

    def listed(self, under: str) -> list[str]:
        found = []
        for directory, subdirectories, filenames in os.walk(self.base_dir / under):
            subdirectories[:] = [name for name in subdirectories if name not in _SKIPPED_DIRECTORIES]
            found += [Path(directory, name) for name in filenames]
        return sorted(file.relative_to(self.base_dir).as_posix() for file in found)

    def read(self, paths: Iterable[str]) -> dict[str, bytes]:
        contents = {}
        for path in paths:
            try:
                contents[path] = (self.base_dir / path).read_bytes()
            except OSError:
                pass
        return contents

    def is_file(self, path: str) -> bool:
        return (self.base_dir / path).is_file()

    def exists(self, path: str) -> bool:
        return (self.base_dir / path).exists()

    def is_exact_file(self, path: str) -> bool:
        try:
            found = exact_path(self.base_dir, path)
        except OSError:
            return False
        return found is not None and found.is_file()

    def is_directory(self, path: str) -> bool:
        return (self.base_dir / path).is_dir()

    def directory(self, path: str) -> Path:
        return self.base_dir / path

    def symlinks(self, path: str) -> list[str]:
        return symlinks_in(self.base_dir / path)


def plugin_name(relative: str) -> str | None:
    """The plugin-relative POSIX path `relative` in the one form charter compares plugin files in (Unicode NFC),
    or None when a segment of it is in PLUGIN_IGNORED_NAMES."""
    if not PLUGIN_IGNORED_NAMES.isdisjoint(relative.split("/")):
        return None
    return unicodedata.normalize("NFC", relative)


def plugin_files(directory: Path) -> Iterator[tuple[str, Path]]:
    """Each file and symbolic link in a plugin directory on disk, as its `plugin_name` and its path. Links are not
    followed."""
    for folder, folders, names in os.walk(directory):
        here = Path(folder)
        # os.walk lists a link to a directory among the folders but does not follow it.
        links = [name for name in folders if (here / name).is_symlink()]
        folders[:] = [name for name in folders if name not in PLUGIN_IGNORED_NAMES and name not in links]
        # A git worktree's `.git` is a file.
        for name in (*names, *links):
            file = here / name
            relative = plugin_name(file.relative_to(directory).as_posix())
            if relative is not None:
                yield relative, file


def symlinks_in(directory: Path) -> list[str]:
    """The `plugin_name`s of the symbolic links in a plugin directory on disk, sorted."""
    return sorted(relative for relative, file in plugin_files(directory) if file.is_symlink())


def exact_path(base: Path, relative: str, *, any_form: bool = False) -> Path | None:
    """The path of `relative` below `base` as the file system spells it, or None when a segment matches no name in
    its directory in letter case. With `any_form`, a segment also matches a name that differs only in Unicode form
    (NFC or NFD), as git reports names on macOS; an exact name wins. Raises OSError when a directory cannot be
    listed."""
    # A case-insensitive file system (macOS, Windows) opens a wrong-case path; a listing of each parent does not.
    current = base
    for segment in PurePosixPath(relative).parts:
        names = os.listdir(current)
        if segment in names:
            current = current / segment
            continue
        wanted = unicodedata.normalize("NFC", segment)
        matches = [name for name in names if any_form and unicodedata.normalize("NFC", name) == wanted]
        if not matches:
            return None
        current = current / matches[0]
    return current


def decode(data: bytes, encoding: str = "utf-8-sig") -> str:
    """`data` decoded with universal newlines, so CRLF text reads exactly like LF. Raises UnicodeDecodeError."""
    return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
