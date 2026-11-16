"""`charter init`: a contract in a folder, and with `--agents` the agent layer too (rulebook and agent files).

Standalone by default: the contract alone. A draft contract (`--from`) takes the starter's place.
"""

import contextlib
import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

from charter import agent_files, checksedit, docs, yamlsource
from charter.contract import (
    CONTRACT_FILENAME,
    DEFAULT_AGENTS_FILE,
    DEFAULT_DOCS_OUTPUT,
    Contract,
    ContractError,
    declared_paths,
)
from charter.diagnostics import Diagnostic, Refused, Severity
from charter.files import replace_file, writing
from charter.validate import contract_at

STARTER_CONTRACT = """\
# The contract for this knowledge base: the kinds of note it holds, their fields and where they live.
# `charter validate` checks every Markdown file against it; `charter describe` explains it.
# Run `charter describe` for the rules as they stand, and see the charter documentation for every setting.

charter: 1                 # contract format version
root: .                    # the knowledge-base folder, relative to this file

# paths:                   # folders that are not notes
#   ".obsidian/**": {ignore: true}
#   "Templates/**": {ignore: true}

# A kind is a type of note. Every note's `kind` frontmatter field names its kind; the kind says which
# fields the note has (`fields`) and which folder and filename it lives at (`path`, where `{title}` is
# the note's title field). To start, replace `{}` below with the example kind (remove the leading `# `
# from its lines), then create a note with `charter new note "My first note"`.
kinds: {}
#   note:
#     description: "A plain note."
#     path: "Notes/{title}.md"
#     fields:
#       kind:  {type: string, required: true}
#       title: {type: string, required: true, matches_filename: true}
"""

# What `--agents` adds to a contract that lacks them, in the order they are written.
AGENT_SECTIONS = {
    "agents": f"{{file: {DEFAULT_AGENTS_FILE}}}",
    "docs": f"{{output: {DEFAULT_DOCS_OUTPUT}}}",
}

WRITE_FAILED = "init/write-failed"
BAD_DRAFT = "init/bad-draft"


@dataclass(frozen=True)
class Initialised:
    contract: Contract
    # The agent files written by `--agents` (None without it), and the sections `--agents` added to the contract.
    agents: list[agent_files.AgentFile] | None
    added: tuple[str, ...]


def initialise(folder: Path, *, agents: bool = False, draft: Path | None = None) -> Initialised:
    """Installs a contract at `folder`/charter.yaml: the starter, or the `draft`. With `agents`, also adds the
    `agents:` and `docs:` sections it lacks and writes the rulebook and agent files. Raises Refused.

    Every obstacle is reported before anything is written, and a failure midway undoes the rest, so a refused or
    failed init can simply be run again.
    """
    config = folder / CONTRACT_FILENAME
    source = _draft_bytes(draft) if draft is not None else STARTER_CONTRACT.encode("utf-8")
    docs_output, agents_file = _declared_paths(source)
    if problems := _obstacles(folder, config, (docs_output, agents_file) if agents else None):
        raise Refused(problems)
    new_folders = [path for path in (folder, *folder.parents) if not path.exists()]
    # Only what this call created is ever undone: a contract that appeared since the check is not ours to remove.
    created: Path | None = None
    before: dict[Path, bytes | None] = {}
    try:
        with writing(config.name, WRITE_FAILED):
            folder.mkdir(parents=True, exist_ok=True)
            # Exclusive creation: a contract that appeared since the check is still never overwritten.
            with config.open("xb") as stream:
                created = config
                stream.write(source)
        contract = _loaded(config, draft)
        added: tuple[str, ...] = ()
        written = None
        if agents:
            declared = {"agents": contract.agent_layer_on, "docs": contract.docs_declared}
            missing = {name: value for name, value in AGENT_SECTIONS.items() if not declared[name]}
            if missing:
                with writing(config.name, WRITE_FAILED):
                    replace_file(config, _with_sections(source, missing, draft))
                contract = _loaded(config, draft)
                added = tuple(missing)
            base = contract.base_dir
            if problems := _layer_obstacles(base, contract.docs_output, contract.agents_file):
                raise Refused(problems)
            touched = [
                base / contract.docs_output,
                base / contract.agents_file,
                base / agent_files.claude_path(contract.agents_file),
            ]
            # Anything else at these paths, such as a dangling symlink, was not init's to change, so is not restored.
            before = {
                path: path.read_bytes() if path.is_file() else None
                for path in touched
                if path.is_file() or not os.path.lexists(path)
            }
            new_folders += [folder for path in touched for folder in path.parents if not folder.exists()]
            docs.write_rulebook(contract, WRITE_FAILED)
            written = agent_files.write_agent_files(base, contract.docs_output, contract.agents_file, WRITE_FAILED)
    except BaseException:
        # Any failure, an interrupt included: a contract left behind would be refused as existing on the next run.
        _restore(created, before, new_folders)
        raise
    return Initialised(contract, written, added)


def _draft_bytes(draft: Path) -> bytes:
    try:
        return draft.read_bytes()
    except OSError as error:
        raise Refused(
            [
                _problem(
                    draft.as_posix(),
                    BAD_DRAFT,
                    f"The draft contract `{draft.as_posix()}` could not be read: {error.strerror or error}.",
                    "`--from` takes the path of an approved draft contract file.",
                )
            ],
            usage=True,
        ) from None


def _loaded(config: Path, draft: Path | None) -> Contract:
    """The contract just written at `config`; a draft that does not load is refused as a usage error, with its
    problems reported against the draft's own path."""
    try:
        return contract_at(config)
    except ContractError as error:
        shown = draft.as_posix() if draft is not None else config.name
        raise Refused([_against(d, config, shown) for d in error.diagnostics], usage=True) from None


def _against(diagnostic: Diagnostic, config: Path, shown: str) -> Diagnostic:
    """`diagnostic` reported against the draft's own path, with what init adds to a missing `root`."""
    if diagnostic.path != config.name:
        return diagnostic
    hint = diagnostic.hint
    if diagnostic.message.startswith("root: directory"):
        hint = (
            f"{hint} The draft's root must exist inside the folder it is installed in: create it there, "
            "or install from the folder that holds the files."
        )
    return dataclasses.replace(diagnostic, path=shown, hint=hint)


def _with_sections(source: bytes, missing: dict[str, str], draft: Path | None) -> bytes:
    try:
        return checksedit.add_sections(source, missing)
    except checksedit.NotEditable:
        raise Refused(
            [
                _problem(
                    draft.as_posix() if draft else CONTRACT_FILENAME,
                    BAD_DRAFT,
                    f"{', '.join(f'`{name}:`' for name in missing)} could not be added to the contract without "
                    "changing what else it says.",
                    "`--agents` appends to a contract written as a block-style YAML mapping that does not end in a "
                    "`...` marker: write it that way, or add the sections yourself.",
                )
            ],
            usage=True,
        ) from None


def _declared_paths(source: bytes) -> tuple[str, str]:
    """The rulebook and agents file the contract names, for checking the obstacles before anything is written. A
    contract that cannot be read here fails to load later."""
    try:
        data, _ = yamlsource.parse(source.decode("utf-8-sig"))
    except (UnicodeDecodeError, yamlsource.YamlSyntaxError):
        data = None
    return declared_paths(data)


def _obstacles(folder: Path, config: Path, layer: tuple[str, str] | None) -> list[Diagnostic]:
    if folder.exists() and not folder.is_dir():
        return [
            _problem(
                folder.as_posix(),
                "init/no-folder",
                f"`{folder.as_posix()}` is not a folder.",
                "Pass the folder to install the knowledge base in, which is created if it does not exist.",
            )
        ]
    problems = []
    if config.exists():
        problems.append(
            _problem(
                CONTRACT_FILENAME,
                "init/exists",
                f"`{CONTRACT_FILENAME}` already exists; charter init never overwrites it.",
                "This folder already has a contract: edit it, or move it aside and run `charter init` again.",
            )
        )
    if layer is not None:
        problems += _layer_obstacles(folder, *layer)
    return problems


def _layer_obstacles(base: Path, docs_output: str, agents_file: str) -> list[Diagnostic]:
    problems = []
    if (base / docs_output).exists():
        problems.append(
            _problem(
                docs_output,
                "init/exists",
                f"`{docs_output}` already exists; charter init never overwrites it.",
                "This folder already has a rulebook: edit it, or move it aside and run `charter init` again.",
            )
        )
    for path in (agents_file, agent_files.claude_path(agents_file)):
        file = base / path
        if file.exists() and not (file.is_file() and os.access(file, os.R_OK | os.W_OK)):
            problems.append(
                _problem(
                    path,
                    "init/not-writable",
                    f"`{path}` is not a file charter init can add to.",
                    "Make it a readable, writable file, or remove it, and run `charter init` again.",
                )
            )
    return problems


def _restore(created: Path | None, before: dict[Path, bytes | None], new_folders: list[Path]) -> None:
    if created is not None:
        with contextlib.suppress(OSError):
            created.unlink()
    for path, content in before.items():
        with contextlib.suppress(OSError):
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
    # Deepest first, so each folder is empty by the time it is removed.
    for folder in sorted(set(new_folders), key=lambda folder: len(folder.parts), reverse=True):
        with contextlib.suppress(OSError):
            folder.rmdir()


def _problem(path: str, code: str, message: str, hint: str) -> Diagnostic:
    return Diagnostic(path, None, Severity.ERROR, code, message, hint)
