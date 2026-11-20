"""Which files a shell command may write: the contract guard's best effort for a `Bash` tool call.

It reads the command as a POSIX shell would split it and knows the common ways to write a named file: a redirect,
`tee`, an in-place `sed` or `perl`, `mv`, `cp`, `rm`, `truncate`, `dd of=`, `git checkout`, `git restore`, `git rm`,
`git mv`, and inline code (`python -c`, `sh -c`) that names it. A command it cannot split counts as writing every file
it names. Reads (`cat`, `grep`, `charter validate --config`, `git diff`) write nothing. It is not a shell parser:
a write it does not know, such as a script file that opens the contract, goes unseen.
"""

import os
import re
import shlex
from collections.abc import Callable, Iterator
from pathlib import Path

# Tokens that end one simple command and start the next.
_SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "{", "}", "!"}
# Commands that only run the rest of the line as another command.
_WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec", "xargs", "doas"}
# Commands that write every file they name.
_WRITE_ALL = {"tee", "rm", "unlink", "truncate", "touch", "shred"}
# Commands that write the last file they name, or the file of a source's name inside it when it is a folder.
_WRITE_LAST = {"cp", "mv", "install", "ln", "rsync"}
# Interpreters whose inline code (`-c`, `-e`) is opaque: naming a file there counts as writing it. Python matches
# with any version suffix (`python`, `python3`, `python3.13`).
_PYTHON = re.compile(r"python(\d+(\.\d+)?)?")
_INTERPRETERS = {"node", "ruby", "perl", "deno", "bun", "php", "pwsh", "powershell"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_GIT_WRITES = {"checkout", "restore", "rm", "mv"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A Git Bash drive path, `/c/kb`: Claude Code runs Bash through Git Bash on Windows.
_MSYS_DRIVE = re.compile(r"/([A-Za-z])(?=/|$)")


def native(path: str, *, windows: bool = os.name == "nt") -> str:
    """`path` with a Git Bash drive (`/c/kb`) spelled as Windows does (`c:/kb`) on Windows; unchanged elsewhere.

    Without this, Windows reads `/c/kb` as the folder `c/kb` on the session's own drive, and the guard sees no
    contract there.
    """
    if windows and (drive := _MSYS_DRIVE.match(path)):
        return f"{drive.group(1)}:{path[drive.end() :] or '/'}"
    return path


def resolve(base: Path, path: str) -> Path:
    """The file `path` names, as a tool call or a command run from `base` spells it."""
    return base / Path(native(path)).expanduser()
_NAMED_PATH = re.compile(r"""[^\s'"`;|&<>(),]+""")


def written(command: str, cwd: Path, wanted: Callable[[str], bool]) -> Iterator[Path]:
    """The paths, among those `wanted` accepts, that `command` run from `cwd` may write."""
    try:
        tokens = _split(command)
    except ValueError:
        # Unbalanced quotes: no reliable reading, so every wanted name counts.
        yield from (resolve(cwd, word) for word in _NAMED_PATH.findall(command) if wanted(word))
        return
    for segment, here in _segments(tokens, cwd):
        for path in _segment_writes(segment, here, wanted):
            if wanted(path):
                yield resolve(here, path)


def _split(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _segments(tokens: list[str], cwd: Path) -> Iterator[tuple[list[str], Path]]:
    """Each simple command with the folder it runs in, following `cd DIR`."""
    here, segment = cwd, []
    for token in [*tokens, ";"]:
        if token not in _SEPARATORS:
            segment.append(token)
            continue
        if segment[:1] == ["cd"] and len(segment) == 2:
            here = resolve(here, segment[1])
        elif segment:
            yield segment, here
        segment = []


def _segment_writes(segment: list[str], cwd: Path, wanted: Callable[[str], bool]) -> Iterator[str]:
    words: list[str] = []
    tokens = iter(segment)
    for token in tokens:
        if set(token) <= set("<>&|0123456789") and ">" in token:
            if (target := next(tokens, None)) is not None:
                yield target
        elif set(token) <= set("<0123456789") and "<" in token:
            next(tokens, None)
        else:
            words.append(token)
    yield from _command_writes(words, cwd, wanted)


def _command_writes(words: list[str], cwd: Path, wanted: Callable[[str], bool]) -> Iterator[str]:
    while words and (_ASSIGNMENT.match(words[0]) or words[0] in _WRAPPERS):
        words = words[1:]
    if words[:2] == ["uv", "run"]:
        words = words[2:]
    if not words:
        return
    name = words[0].replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")
    args = words[1:]
    operands = [arg for arg in args if not arg.startswith("-")]
    if name in _WRITE_ALL:
        yield from operands
    elif name in _WRITE_LAST and operands:
        *sources, target = operands
        if name == "mv":
            # A move also removes its sources.
            yield from sources
        yield target
        if _is_dir(resolve(cwd, target)):
            yield from (f"{target.rstrip('/')}/{Path(source).name}" for source in sources)
    elif name == "dd":
        yield from (arg[3:] for arg in args if arg.startswith("of="))
    elif name in ("sed", "perl") and any(arg.startswith("-i") or arg == "--in-place" or _perl_i(arg) for arg in args):
        yield from operands
    elif name == "git" and operands[:1] and operands[0] in _GIT_WRITES:
        yield from operands[1:]
    elif (name in _INTERPRETERS or _PYTHON.fullmatch(name)) and any(
        arg in ("-c", "-e", "--eval") for arg in args
    ):
        yield from (word for arg in args for word in _NAMED_PATH.findall(arg) if wanted(word))
    elif name in _SHELLS and "-c" in args:
        code = args[args.index("-c") + 1] if args.index("-c") + 1 < len(args) else ""
        yield from (str(path) for path in written(code, cwd, wanted))


def _is_dir(path: Path) -> bool:
    # A target the system cannot check, such as an overlong name, is no folder; the sources already yielded stand.
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _perl_i(arg: str) -> bool:
    # Bundled single-letter switches such as `-pi` or `-pie`.
    return arg.startswith("-") and not arg.startswith("--") and "i" in arg[1:]
