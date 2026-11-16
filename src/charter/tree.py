"""Where charter reads a knowledge base's files from: the working copy, or a snapshot of it such as git's staged
content. Paths are in diagnostic form: POSIX, relative to the directory holding charter.yaml."""

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Protocol

# Version-control internals are never part of a knowledge base, even when root is the repository.
_SKIPPED_DIRECTORIES = frozenset({".git"})


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
        # A case-insensitive file system answers `is_file` for a wrong-case path; a listing of each parent does not.
        current = self.base_dir
        for segment in PurePosixPath(path).parts:
            try:
                if segment not in os.listdir(current):
                    return False
            except OSError:
                return False
            current = current / segment
        return current.is_file()

    def is_directory(self, path: str) -> bool:
        return (self.base_dir / path).is_dir()

    def directory(self, path: str) -> Path:
        return self.base_dir / path

    def symlinks(self, path: str) -> list[str]:
        # Imported here: lock reads this module for `decode`.
        from charter.lock import symlinks_in

        return symlinks_in(self.base_dir / path)


def decode(data: bytes, encoding: str = "utf-8-sig") -> str:
    """`data` decoded with universal newlines, so CRLF text reads exactly like LF. Raises UnicodeDecodeError."""
    return data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
