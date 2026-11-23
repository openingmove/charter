"""Reading a knowledge base as git holds it: a snapshot of its files, and what a change does to them."""

import datetime
import os
import posixpath
import re
import stat
import tempfile
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from charter.files import remove_tree
from charter.history import EditDelta, NoHistory
from charter.process import Finished, run_bounded
from charter.tree import Tree, plugin_name

# Generous: git's own output, never a plugin's, but a runaway must not exhaust memory.
_OUTPUT_LIMIT = 1024 * 1024 * 1024
_TIMEOUT_SECONDS = 120.0
_REGULAR, _EXECUTABLE, _SYMLINK = "100644", "100755", "120000"
# Enough for any real chain of links, and a stop for a loop of them.
_MAX_LINK_HOPS = 40
# Variables naming paths that git reads relative to its working directory.
_PATH_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR")
_ALTERNATES = "GIT_ALTERNATE_OBJECT_DIRECTORIES"


class GitError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        # What to do about it, when the generic "check that git works" would mislead.
        self.hint = hint


_NO_COMMIT = NoHistory("there is no commit yet to compare with")


class GitUnavailable(GitError):
    """git itself could not be started."""


class NotARepository(Exception):
    pass


class _Git:
    """git, run from one directory with one environment."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.environment = environment()

    def run(self, *args: str, stdin: bytes = b"") -> bytes:
        finished = self._run(args, stdin)
        if finished.returncode != 0 or finished.overflowed:
            stderr = finished.stderr.decode("utf-8", errors="replace").strip()
            reason = "did not finish in time" if finished.timed_out else stderr or "failed"
            raise GitError(f"`git {' '.join(args)}` {reason}.")
        return finished.stdout

    def require_work_tree(self) -> None:
        """Raises NotARepository outside a working tree, and GitError when git cannot tell, such as for a
        repository it refuses to use."""
        # Untranslated, so git's own words say whether this is a repository at all.
        finished = self._run(["rev-parse", "--is-inside-work-tree"], b"", {"LC_ALL": "C"})
        if finished.returncode != 0 and b"not a git repository" not in finished.stderr:
            self.run("rev-parse", "--is-inside-work-tree")
        if finished.returncode != 0 or finished.stdout.strip() != b"true":
            raise NotARepository()

    def has_head(self) -> bool:
        """Whether `HEAD` is a commit: False before the first one. Raises GitError when it names no readable one."""
        if self._run(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], b"").returncode == 0:
            return True
        unborn = self._run(["rev-parse", "--verify", "--quiet", "HEAD"], b"").returncode != 0
        if unborn and self._run(["symbolic-ref", "--quiet", "HEAD"], b"").returncode == 0:
            return False
        raise GitError("`HEAD` does not name a commit that git can read.")

    def commit_id(self, revision: str) -> str | None:
        """The id of the commit `revision` names; None when it names none."""
        found = self._run(["rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"], b"")
        return found.stdout.decode("ascii").strip() if found.returncode == 0 else None

    def holds_file(self, name: str) -> bool:
        """Whether the index or `HEAD` holds a file at `name`, relative to the directory git runs in. False
        outside a repository and for a folder."""
        # `./` makes the name relative to the directory git runs in, rather than to the top of the working tree.
        found = (self._run(["cat-file", "-t", f"{tree}:./{name}"], b"") for tree in ("", "HEAD"))
        return any(finished.stdout.strip() == b"blob" for finished in found)

    def objects(self, object_ids: Sequence[str]) -> list[bytes]:
        if not object_ids:
            return []
        output = self.run("cat-file", "--batch", stdin="".join(f"{i}\n" for i in object_ids).encode())
        contents, position = [], 0
        for object_id in object_ids:
            end = output.index(b"\n", position)
            header = output[position:end].split(b" ")
            if len(header) != 3:
                raise GitError(f"git could not read object {object_id}.")
            size = int(header[2])
            contents.append(output[end + 1 : end + 1 + size])
            position = end + 1 + size + 1
        return contents

    def _run(self, args: Sequence[str], stdin: bytes, overrides: Mapping[str, str] | None = None) -> Finished:
        return _run_git(args, self.base_dir, stdin, {**self.environment, **(overrides or {})})


@dataclass(frozen=True)
class _Blob:
    object_id: str
    executable: bool


class GitTree:
    """Files as git holds them, read from the repository on demand. A symbolic link to a file in the tree reads
    as that file, as it does in a checkout; any other link is left out."""

    def __init__(self, git: _Git, entries: Mapping[str, tuple[str, str]], holder: str = "commit"):
        """`entries` maps each path to its git mode and object id. `holder` names what holds them, in messages."""
        self.holder = holder
        self._git = git
        self._blobs = _resolved(git, entries)
        # Kept from the entries, which `_blobs` has resolved away: a link is told by its mode alone.
        self._links = [path for path, (mode, _) in entries.items() if mode == _SYMLINK]
        self._directories = {parent for path in self._blobs for parent in _parents(path)}
        self._contents: dict[str, bytes] = {}
        self._scratch: Path | None = None
        self._materialised: set[str] = set()

    def files(self, under: str, suffix: str = "") -> list[str]:
        prefix = "" if under == "." else f"{under}/"
        return sorted(path for path in self._blobs if path.startswith(prefix) and path.endswith(suffix))

    def listed(self, under: str) -> list[str]:
        return self.files(under)

    def read(self, paths: Iterable[str]) -> dict[str, bytes]:
        wanted = [path for path in dict.fromkeys(paths) if path in self._blobs]
        missing = list(dict.fromkeys(self._blobs[path].object_id for path in wanted) - self._contents.keys())
        self._contents.update(zip(missing, self._git.objects(missing), strict=True))
        return {path: self._contents[self._blobs[path].object_id] for path in wanted}

    def is_file(self, path: str) -> bool:
        return path in self._blobs

    def exists(self, path: str) -> bool:
        return path in self._blobs or path in self._directories

    def is_exact_file(self, path: str) -> bool:
        return path in self._blobs

    def is_directory(self, path: str) -> bool:
        return path == "." or path in self._directories

    def directory(self, path: str) -> Path:
        """The files at or below `path`, written out to a temporary directory that `close` removes."""
        if self._scratch is None:
            self._scratch = Path(tempfile.mkdtemp(prefix="charter-"))
        if path not in self._materialised:
            for file, content in self.read(self.files(path)).items():
                target = self._scratch / file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                if self._blobs[file].executable:
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self._materialised.add(path)
        return self._scratch / path

    def symlinks(self, path: str) -> list[str]:
        prefix = "" if path == "." else f"{path}/"
        names = (plugin_name(link.removeprefix(prefix)) for link in self._links if link.startswith(prefix))
        # The same names, in the same form, as the working copy's `tree.symlinks_in`.
        return sorted(name for name in names if name is not None)

    def close(self) -> list[Path]:
        """Removes the temporary directory; returns what could not be deleted."""
        leftover = remove_tree(self._scratch) if self._scratch is not None else []
        self._scratch = None
        self._materialised.clear()
        return leftover

    def answer(self, question: tuple[str, str]) -> object:
        """What the tree holds at a place `_Watched` noted: a file's blob, whether a path exists, or every blob
        under a directory."""
        kind, path = question
        if kind == "file":
            return self._blobs.get(path)
        if kind == "exists":
            return self.exists(path)
        if kind == "directory":
            return self.is_directory(path)
        if kind == "links":
            return tuple(self.symlinks(path))
        return tuple((file, self._blobs[file]) for file in self.files(path))


class _Watched:
    """A GitTree that notes each place it is asked about, with what it held there."""

    def __init__(self, tree: GitTree):
        self._tree = tree
        self.answers: dict[tuple[str, str], object] = {}

    def files(self, under: str, suffix: str = "") -> list[str]:
        # Noted as every file under `under`: a superset of what was asked for, so a reused answer stays sound.
        self._note("files", under)
        return self._tree.files(under, suffix)

    def listed(self, under: str) -> list[str]:
        self._note("files", under)
        return self._tree.listed(under)

    def read(self, paths: Iterable[str]) -> dict[str, bytes]:
        paths = list(paths)
        for path in paths:
            self._note("file", path)
        return self._tree.read(paths)

    def is_file(self, path: str) -> bool:
        self._note("file", path)
        return self._tree.is_file(path)

    def is_exact_file(self, path: str) -> bool:
        self._note("file", path)
        return self._tree.is_exact_file(path)

    def exists(self, path: str) -> bool:
        self._note("exists", path)
        return self._tree.exists(path)

    def is_directory(self, path: str) -> bool:
        self._note("directory", path)
        return self._tree.is_directory(path)

    def directory(self, path: str) -> Path:
        self._note("files", path)
        return self._tree.directory(path)

    def symlinks(self, path: str) -> list[str]:
        self._note("links", path)
        return self._tree.symlinks(path)

    @property
    def holder(self) -> str:
        return self._tree.holder

    def _note(self, kind: str, path: str) -> None:
        self.answers[(kind, path)] = self._tree.answer((kind, path))


_T = TypeVar("_T")


class ContentMemo(Generic[_T]):
    """Values computed from GitTrees, each reused for a later tree that holds the same content everywhere its
    computation looked, such as a contract that commits after it leave alone."""

    def __init__(self) -> None:
        self._known: list[tuple[dict[tuple[str, str], object], _T]] = []

    def get(self, tree: GitTree, compute: Callable[[Tree], _T]) -> _T:
        for answers, value in reversed(self._known):
            if all(tree.answer(question) == answer for question, answer in answers.items()):
                return value
        watched = _Watched(tree)
        value = compute(watched)
        self._known.append((watched.answers, value))
        return value


@dataclass(frozen=True)
class Change:
    # The files as they are after the change.
    tree: GitTree
    # Files the change adds, modifies or changes the type of.
    changed: frozenset[str]
    # The files the change modifies, retypes or deletes, as they were before it.
    before: GitTree
    # Why nothing comes before the change to compare it with, such as for a first commit.
    unjudged: NoHistory | None

    def edits(self) -> EditDelta | NoHistory:
        if self.unjudged is not None:
            return self.unjudged
        return EditDelta(self.before, self.tree, self.changed - set(self.before.files(".")))

    def close(self) -> list[Path]:
        return [*self.tree.close(), *self.before.close()]


def staged(base_dir: Path) -> Change:
    """What committing the staged content under `base_dir` would change. Raises NotARepository or GitError."""
    git = _Git(base_dir)
    git.require_work_tree()
    # Before the first commit, git compares the staged content with the empty tree.
    return _change(
        git, _staged_entries(git), _diff(git, "--cached"), None if git.has_head() else _NO_COMMIT, holder="index"
    )


def uncommitted(base_dir: Path, working: Tree, paths: Collection[str] | None = None) -> EditDelta | NoHistory:
    """What the working copy `working` changes since `HEAD`, under `base_dir` or in just `paths` (relative to
    it). The caller closes the delta's `before`. Raises NotARepository or GitError."""
    git = _Git(base_dir)
    if paths is not None and not paths:
        git.require_work_tree()
        return EditDelta(GitTree(git, {}), working, frozenset())
    pathspecs = [] if paths is None else ["--", *(f":(literal){path}" for path in paths)]
    # The usual case, a repository with a commit, needs only these two calls. `git diff` fails everywhere else,
    # outside a repository or before the first commit, and the probes below then say which it is.
    try:
        deltas = _diff(git, "HEAD", *pathspecs)
    except GitUnavailable:
        raise
    except GitError:
        git.require_work_tree()
        if not git.has_head():
            return _NO_COMMIT
        # A healthy repository: the diff failed for its own reason, which a second run would only repeat.
        raise
    untracked = frozenset(_records(git.run("ls-files", "--others", "--exclude-standard", "-z", *pathspecs)))
    added = untracked | {delta.path for delta in deltas if delta.status == "A"}
    return EditDelta(_before(git, deltas), working, added)


def tracks(file: Path) -> bool:
    """Whether git's index or `HEAD` holds a file at `file` (relative to the working directory, or absolute).
    False outside a repository, where git is not installed, and for a folder."""
    absolute = Path(os.path.abspath(file))
    folder = next((parent for parent in absolute.parents if parent.is_dir()), None)
    if folder is None:
        return False
    try:
        return _Git(folder).holds_file(absolute.relative_to(folder).as_posix())
    except GitUnavailable:
        return False


def trailers(base_dir: Path, message: bytes) -> list[tuple[str, str]]:
    """The trailers of commit message `message` as git reads them, as (key, value) pairs: only the final
    trailer block, without comment lines or anything below a `--verbose` scissors line, continuation lines
    unfolded. Raises GitError."""
    # git honours the repository's own settings, such as `core.commentChar`, except that `Charter-Allow:` is
    # always written with a colon, whatever separators the repository declares for its own trailers.
    parsed = _Git(base_dir).run(
        "-c", "trailer.separators=:", "interpret-trailers", "--parse", stdin=message.replace(b"\r\n", b"\n")
    )
    return _trailer_pairs(parsed)


_LINE_END = re.compile(r"\r\n|\r|\n")


def _trailer_pairs(parsed: bytes) -> list[tuple[str, str]]:
    pairs = []
    # git writes messages as UTF-8 by default; a repository set to another `i18n.commitEncoding` is not
    # supported, and its non-ASCII text reads as replacement characters rather than failing the run.
    text = parsed.decode("utf-8", errors="replace")
    # Not `str.splitlines()`, which also breaks at U+2028, U+0085, FF and VT: a path may hold those. git ends
    # a trailer with LF; a CR still ends one, as it always has here.
    lines = _LINE_END.split(text)
    if lines[-1] == "":
        lines.pop()
    for line in lines:
        key, _, value = line.partition(":")
        pairs.append((key.strip(), value.strip()))
    return pairs


class InvalidRange(Exception):
    def __init__(self, problem: str, hint: str | None = None):
        super().__init__(problem)
        self.problem = problem
        self.hint = hint


class ShallowHistory(Exception):
    """The range needs history that a shallow clone left out."""

    def __init__(self, problem: str):
        super().__init__(problem)
        self.problem = problem


@dataclass(frozen=True)
class Commit:
    id: str
    # git's abbreviation of the id, for people to read.
    name: str
    # The day it was authored, in its author's time zone. Unlike the commit date, a rebase, cherry-pick or amend
    # keeps it, so the day the pre-commit hook judged the change stays the day CI judges it.
    authored: datetime.date
    parents: tuple[str, ...]
    trailers: tuple[tuple[str, str], ...]
    git: _Git = field(repr=False)

    def change(self) -> Change:
        """What the commit changes against its first parent. A merge changes only the files it leaves unlike every
        parent, such as a conflict resolution: the rest each parent's own commits changed. A file a merge changes
        that any parent has counts as changed, not added. The caller closes it."""
        entries = _commit_entries(self.git, self.id)
        if not self.parents:
            reason = f"commit {self.name} has no parent to compare it with"
            hint = "Nothing to fix: charter judges a commit's edits against its parent, and a root commit has none."
            return _change(self.git, entries, [], NoHistory(reason, hint))
        by_parent = [{d.path: d for d in _diff(self.git, parent, self.id)} for parent in self.parents]
        deltas = []
        for path, delta in by_parent[0].items():
            against = [deltas_of[path] for deltas_of in by_parent if path in deltas_of]
            if len(against) == len(by_parent):
                deltas.append(next((d for d in against if d.status != "A"), delta))
        return _change(self.git, entries, deltas, None)


def commit_range(base_dir: Path, revisions: str) -> list[Commit]:
    """The commits of `revisions`, `A..B`: those B has and A has not, an empty side meaning `HEAD`, as git's
    `rev-list` gives them, parents before children. Raises NotARepository, GitError, InvalidRange or
    ShallowHistory."""
    git = _Git(base_dir)
    git.require_work_tree()
    start, separator, end = revisions.partition("..")
    if not separator:
        raise InvalidRange("is not a range of commits")
    if ".." in end:
        raise InvalidRange("holds more than one `..`")
    if end.startswith("."):
        raise InvalidRange("is a symmetric difference, which also holds the commits only its start has")
    start_id, end_id = (_commit_id(git, side or "HEAD") for side in (start, end))
    listing = git.run("rev-list", "--reverse", "--topo-order", "--format=%h %as %P", end_id, f"^{start_id}")
    lines = listing.decode("ascii").splitlines()
    ids = [line.removeprefix("commit ") for line in lines[::2]]
    described = [line.split() for line in lines[1::2]]
    for (name, _, *parents), content in zip(described, git.objects(ids), strict=True):
        # git hides the parents of a commit at a shallow clone's edge; the commit itself still names them.
        recorded = [line for line in content.partition(b"\n\n")[0].splitlines() if line.startswith(b"parent ")]
        if len(recorded) != len(parents):
            raise ShallowHistory(f"commit {name}'s parents are not in this shallow clone")
    return [
        Commit(commit_id, name, _author_day(name, day), tuple(parents), found, git)
        for commit_id, (name, day, *parents), found in zip(ids, described, _commit_trailers(git, ids), strict=True)
    ]


def _author_day(name: str, text: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        # An older git does not know `%as` and prints it as written.
        raise GitError(
            f"git gave `{text}` as the author date of commit {name}, not a day (`YYYY-MM-DD`); "
            "--range needs git 2.25 or newer.",
            "Upgrade git to 2.25 or newer; CI runners often carry an older one.",
        ) from None


def _commit_id(git: _Git, revision: str) -> str:
    if set(revision) == {"0"} and len(revision) in (40, 64):
        raise InvalidRange(
            f"starts at `{revision}`, the id git gives for what a new branch was before it was pushed",
            "For a push that creates a branch, check the commits it adds to the default branch instead: "
            "`--range origin/<default branch>..<pushed commit>`.",
        )
    # A leading dash would read as an option.
    if not revision.startswith("-") and (found := git.commit_id(revision)) is not None:
        return found
    if git.run("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise ShallowHistory(f"`{revision}` is not in this shallow clone")
    raise InvalidRange(f"names `{revision}`, which is not a commit in this repository")


def _commit_trailers(git: _Git, ids: Sequence[str]) -> list[tuple[tuple[str, str], ...]]:
    """Each commit's trailers, as `trailers` reads a message, from one git call."""
    if not ids:
        return []
    output = git.run(
        "-c",
        "trailer.separators=:",
        "log",
        "--no-walk=unsorted",
        "--stdin",
        "--format=%H%x00%(trailers:only,unfold)%x00",
        stdin="".join(f"{i}\n" for i in ids).encode(),
    )
    fields = output.split(b"\0")
    found = {key.strip().decode("ascii"): _trailer_pairs(value) for key, value in zip(fields[::2], fields[1::2])}
    return [tuple(found[i]) for i in ids]


def _commit_entries(git: _Git, commit: str) -> dict[str, tuple[str, str]]:
    listing = git.run("ls-tree", "-r", "-z", commit)
    return {path: (mode, object_id) for (mode, _, object_id), path in _listed(listing)}


@dataclass(frozen=True)
class _Delta:
    old_mode: str
    old_id: str
    status: str
    path: str


def _change(
    git: _Git,
    after: Mapping[str, tuple[str, str]],
    deltas: list[_Delta],
    unjudged: NoHistory | None,
    holder: str = "commit",
) -> Change:
    tree = GitTree(git, after, holder)
    changed = frozenset(delta.path for delta in deltas if delta.status != "D" and tree.is_file(delta.path))
    return Change(tree, changed, _before(git, deltas), unjudged)


def _before(git: _Git, deltas: list[_Delta]) -> GitTree:
    return GitTree(git, {delta.path: (delta.old_mode, delta.old_id) for delta in deltas if delta.status != "A"})


def _staged_entries(git: _Git) -> dict[str, tuple[str, str]]:
    # Unmerged paths have no single staged content; git refuses to commit them anyway.
    return {
        path: (mode, object_id)
        for (mode, object_id, stage), path in _listed(git.run("ls-files", "--stage", "-z"))
        if stage == "0"
    }


def _listed(output: bytes) -> Iterator[tuple[list[str], str]]:
    """The space-separated details and the path of each record of an `ls-files --stage` or `ls-tree` listing."""
    for record in _records(output):
        details, _, path = record.partition("\t")
        yield details.split(" "), path


def _diff(git: _Git, *arguments: str) -> list[_Delta]:
    """`git diff` with `arguments` (revisions, then any pathspecs), file by file, under the directory git runs in."""
    raw = git.run("diff", "--raw", "-z", "--no-renames", "--no-abbrev", "--relative", *arguments)
    records = _records(raw)
    deltas = []
    for status_line, path in zip(records[::2], records[1::2], strict=True):
        old_mode, _, old_id, _, status = status_line.removeprefix(":").split(" ")
        deltas.append(_Delta(old_mode, old_id, status, path))
    return deltas


def _resolved(git: _Git, entries: Mapping[str, tuple[str, str]]) -> dict[str, _Blob]:
    blobs = {
        path: _Blob(object_id, mode == _EXECUTABLE)
        for path, (mode, object_id) in entries.items()
        if mode in (_REGULAR, _EXECUTABLE)
    }
    links = [path for path, (mode, _) in entries.items() if mode == _SYMLINK]
    targets = git.objects([entries[path][1] for path in links])
    pointing = {link: target.decode("utf-8", errors="surrogateescape") for link, target in zip(links, targets)}
    for link in links:
        if (target := _link_target(link, pointing, blobs)) is not None:
            blobs[link] = blobs[target]
    return blobs


def _link_target(link: str, pointing: Mapping[str, str], files: Mapping[str, _Blob]) -> str | None:
    """The file in the tree that `link` leads to through any chain of links; None when it leads nowhere in it."""
    path = link
    for _ in range(_MAX_LINK_HOPS):
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), pointing[path]))
        if posixpath.isabs(target) or target == ".." or target.startswith("../"):
            return None
        if target in files:
            return target
        if target not in pointing:
            return None
        path = target
    return None


def _parents(path: str) -> Iterator[str]:
    while (path := posixpath.dirname(path)) != "":
        yield path


def _records(output: bytes) -> list[str]:
    return [record.decode("utf-8", errors="surrogateescape") for record in output.split(b"\0") if record]


def _run_git(args: Sequence[str], cwd: Path, stdin: bytes, environment: Mapping[str, str]) -> Finished:
    try:
        return run_bounded(
            ["git", *args], cwd, stdin, timeout=_TIMEOUT_SECONDS, limit=_OUTPUT_LIMIT, env=environment
        )
    except OSError as error:
        raise GitUnavailable(f"git could not be run: {error.strerror or error}.") from None


def environment() -> dict[str, str]:
    """charter's environment, with git's paths made absolute: a commit hook runs at the top of the working tree
    and may set them relative to it, but charter runs git from the directory holding charter.yaml, and plugins from
    their own directories."""
    environment = dict(os.environ)
    for name in _PATH_VARIABLES:
        if environment.get(name):
            environment[name] = os.path.abspath(environment[name])
    if environment.get(_ALTERNATES):
        directories = environment[_ALTERNATES].split(os.pathsep)
        environment[_ALTERNATES] = os.pathsep.join(os.path.abspath(d) for d in directories if d)
    if "GIT_DIR" in environment and "GIT_WORK_TREE" not in environment:
        # With GIT_DIR alone, git finds the working tree from where it runs: `core.worktree`, or that directory.
        found = _run_git(["rev-parse", "--show-toplevel"], Path.cwd(), b"", environment)
        if found.returncode == 0 and (top := found.stdout.decode("utf-8", errors="surrogateescape").strip()):
            environment["GIT_WORK_TREE"] = top
    return environment
