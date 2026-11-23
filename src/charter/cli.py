"""The `charter` command line. `main` is the in-process entry point: argv in, exit code out."""

import argparse
import codecs
import contextlib
import datetime
import errno
import os
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from charter import __version__, discovery, git
from charter.contract import (
    CONTRACT_FILENAME,
    Contract,
    ContractError,
    PluginSettings,
)
from charter.diagnostics import EXIT_CLEAN, EXIT_ERRORS, Diagnostic, Refused, Severity, code_list, exit_code
from charter.files import left_behind
from charter.history import EditDelta, History, NoHistory
from charter.lock import LOCK_FILENAME, PLUGINS_DIR, leftover_staging
from charter.output import FORMATS, render, render_draft
from charter.profiles import Profile, UnknownProfile, is_builtin_profile, profile_name, select_profile
from charter.scaffold import create
from charter.validate import (
    HISTORY_CHECKS,
    Targets,
    commit_findings,
    contract_at,
    judging_edits,
    overridable_findings,
    plugin_payload,
    plugin_settings_at,
    run_plugin,
    validate,
)

if TYPE_CHECKING:
    from charter import agent_files

# The output formats of commands whose modules load only when the command runs. A test pins each to its module's.
DESCRIBE_FORMATS = ("markdown", "json")
SWEEP_FORMATS = ("text", "json", "agent")
SURVEY_FORMATS = ("text", "json")
LISTING_FORMATS = ("text", "json")
# `new` reports a path and an outline, which have no JSON form yet.
NEW_FORMATS = ("text", "agent")
EXIT_USAGE = 2
# Sets the day runs are judged as of, `YYYY-MM-DD`, instead of the local date: for tests and reproducing a run.
TODAY_VARIABLE = "CHARTER_TODAY"


def _use_utf8_streams() -> None:
    """Write stdout and stderr as UTF-8 with LF line endings, so output is byte-identical on every platform.

    Windows pipes use the ANSI code page unless Python's UTF-8 mode is on, and Windows text streams turn `\\n`
    into `\\r\\n`. A stream without `reconfigure` (pytest's capture streams can lack it) is left alone. The UTF-8
    guard covers the encoding only: on Linux and macOS it leaves an already-UTF-8 stream untouched. On Windows the
    newline is set to `\\n` on every reconfigurable stream, even one that is already UTF-8 (UTF-8 mode,
    `PYTHONIOENCODING=utf-8`), and that includes pytest's capture streams when they offer `reconfigure`.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if codecs.lookup(stream.encoding or "ascii").name != "utf-8":
            reconfigure(encoding="utf-8", newline="\n")
        elif os.name == "nt":
            reconfigure(newline="\n")


# What a process killed by SIGPIPE reports (128 + 13), used on every platform: the reader went away before the
# command finished writing, so its own exit status is unknown.
EXIT_BROKEN_PIPE = 141


def _pipe_closed(error: OSError) -> bool:
    # Windows reports a closed pipe on flush as EINVAL (22) instead of EPIPE.
    closed = (errno.EPIPE, errno.EINVAL) if os.name == "nt" else (errno.EPIPE,)
    return isinstance(error, BrokenPipeError) or error.errno in closed


def run(argv: list[str] | None = None) -> int:
    """The process entry point: `main`, except that a closed stdout (`charter ... | head`) ends quietly.

    The exit status is the command's own when it finished and only the final flush met the closed pipe, and
    `EXIT_BROKEN_PIPE` when the pipe closed while it was still writing.
    """
    code = EXIT_BROKEN_PIPE
    try:
        code = main(argv)
        sys.stdout.flush()
    except OSError as error:
        if not _pipe_closed(error):
            raise
        # Python flushes stdout again at exit and would raise again; point it at a sink first.
        with contextlib.suppress(OSError, ValueError):
            sink = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(sink, sys.stdout.fileno())
            finally:
                os.close(sink)
    return code


def main(argv: list[str] | None = None) -> int:
    _use_utf8_streams()
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        # argparse exits on --help (0) and on usage errors (2); report that as a return value.
        return stop.code if isinstance(stop.code, int) else EXIT_USAGE
    if getattr(args, "config", "") is None:
        files = getattr(args, "file", None) or None
        output_format = getattr(args, "format", "")
        output_format = output_format if output_format in FORMATS else "text"
        # A file that does not exist is the first thing to tell the user, before any contract question.
        # Kept for the run, so git is asked about each missing file once.
        args.deleted = _deleted_files(files or [])
        if files and (missing := _missing_files(None, files, args.deleted)):
            return _usage_error(missing, output_format)
        found = discovery.discover(files)
        if isinstance(found, list):
            return _usage_error(found, output_format)
        args.config = str(found)
    return args.handler(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="charter",
        description="Schemas, validation and scaffolding for Markdown knowledge bases.",
    )
    parser.add_argument("--version", action="version", version=f"charter {__version__}")
    commands = parser.add_subparsers(title="commands", required=True, metavar="COMMAND")

    validate_parser = commands.add_parser("validate", help="check the knowledge base against its contract")
    _add_config(validate_parser)
    _add_run_options(validate_parser).add_argument(
        "--range",
        metavar="A..B",
        help="check only edit policies, for each commit B has and A has not, against its parent and honouring "
        "its own Charter-Allow trailers (for CI)",
    )
    validate_parser.add_argument(
        "--commit-msg",
        type=Path,
        metavar="FILE",
        help="with --staged, the pending commit message: check only edit policies, honouring its Charter-Allow "
        "trailers (for a commit-msg hook); without it, --staged leaves edit policies out",
    )
    validate_parser.add_argument(
        "--commit-msg-installed",
        action="store_true",
        help="needs --staged; say a commit-msg hook is installed: leave out the infos saying edit policies wait "
        "for it (for a pre-commit hook shipped with its commit-msg partner)",
    )
    validate_parser.set_defaults(handler=_validate)

    new_parser = commands.add_parser("new", help="create a note from its kind's contract and template")
    _add_config(new_parser)
    new_parser.add_argument("kind", metavar="KIND[/VARIANT]", help="the kind of note, optionally with its variant")
    new_parser.add_argument("title", nargs="?", metavar="TITLE", help="the note's title")
    new_parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="a field value; repeat for more fields, or for more elements of a list field",
    )
    new_parser.add_argument("--dry-run", action="store_true", help="check the note and report it, writing nothing")
    new_parser.add_argument(
        "--format", choices=NEW_FORMATS, default="text", help="output format (default: text)"
    )
    new_parser.set_defaults(handler=_new)

    describe_parser = commands.add_parser("describe", help="explain the contract: kinds, fields, paths and checks")
    _add_config(describe_parser)
    describe_parser.add_argument(
        "kind", nargs="?", metavar="KIND[/VARIANT]", help="describe only this kind (with its variants) or variant"
    )
    describe_parser.add_argument(
        "--format", choices=DESCRIBE_FORMATS, default="markdown", help="output format (default: markdown)"
    )
    describe_parser.set_defaults(handler=_describe)

    sweep_parser = commands.add_parser(
        "sweep", help="list the notes that link to or mention a note, and the note's own links, before changing it"
    )
    _add_config(sweep_parser)
    sweep_parser.add_argument(
        "note",
        metavar="NOTE",
        help="the note: a file path from the working directory, or a name as a wikilink would give it "
        "(path from the knowledge-base root, filename or alias)",
    )
    sweep_parser.add_argument(
        "--format", choices=SWEEP_FORMATS, default="text", help="output format (default: text)"
    )
    sweep_parser.set_defaults(handler=_sweep)

    docs_parser = commands.add_parser("docs", help="write the generated rulebook (docs.output)")
    _add_config(docs_parser)
    docs_parser.add_argument(
        "--check", action="store_true", help="do not write the rulebook; fail if it is missing or out of date"
    )
    docs_parser.add_argument(
        "--link-agents",
        action="store_true",
        help="with an `agents:` section, also link the agents file (agents.file) to the rulebook, "
        "appending one line if it has no link",
    )
    docs_parser.set_defaults(handler=_docs)

    init_parser = commands.add_parser(
        "init",
        help=f"start a knowledge base: write a commented {CONTRACT_FILENAME} in FOLDER, and nothing else unless asked",
    )
    # No --config and no upward discovery: init creates the contract, at FOLDER/charter.yaml.
    init_parser.add_argument(
        "folder", nargs="?", type=Path, default=Path("."), metavar="FOLDER",
        help="the folder to install the contract in, created if missing (default: the working directory)",
    )
    init_parser.add_argument(
        "--from",
        dest="draft",
        type=Path,
        metavar="DRAFT",
        help="install this approved draft contract instead of the starter; refused, writing nothing, if it does not load",
    )
    init_parser.add_argument(
        "--agents",
        action="store_true",
        help="also add the `agents:` and `docs:` sections the contract lacks, write the rulebook, and link it "
        "from AGENTS.md (and CLAUDE.md where one exists)",
    )
    init_parser.set_defaults(handler=_init)

    survey_parser = commands.add_parser(
        "survey",
        help="report what the Markdown files in FOLDER hold (folders, frontmatter, filename shapes, headings, "
        "links); read-only, and needs no contract",
    )
    # No --config and no upward discovery: a survey runs before a contract exists, or beside a different one.
    survey_parser.add_argument("folder", type=Path, metavar="FOLDER", help="the folder to survey")
    survey_parser.add_argument(
        "--format", choices=SURVEY_FORMATS, default="text", help="output format (default: text)"
    )
    survey_parser.set_defaults(handler=_survey)

    snapshot_parser = commands.add_parser(
        "snapshot",
        help="zip a whole folder beside it (`snapshot FOLDER`), or put a snapshot back (`snapshot restore ZIP`); "
        "needs no contract",
        description="`charter snapshot FOLDER [--to PATH]` writes a zip of every file and folder under FOLDER, "
        "beside it by default, never inside it. `charter snapshot restore ZIP [--to FOLDER] [--replace]` unpacks "
        "one. A folder literally named `restore` is spelled `./restore`.",
    )
    # No --config and no upward discovery: a snapshot runs before a contract exists, and never loads one.
    snapshot_parser.add_argument(
        "words", nargs="+", metavar="FOLDER | restore ZIP",
        help="the folder to snapshot, or the word `restore` and the zip to restore",
    )
    snapshot_parser.add_argument(
        "--to", metavar="PATH",
        help="snapshot: where to write the zip (a .zip path, or an existing folder to put it in; default: beside "
        "FOLDER). restore: the folder to restore into (default: the recorded folder name, beside the zip)",
    )
    snapshot_parser.add_argument(
        "--replace", action="store_true",
        help="restore only: swap a non-empty target for the snapshot (the old content is removed after the restore succeeds)",
    )
    snapshot_parser.set_defaults(handler=_snapshot)

    plugin_parser = commands.add_parser("plugin", help="work with the knowledge base's external plugins")
    plugin_commands = plugin_parser.add_subparsers(title="plugin commands", required=True, metavar="COMMAND")
    run_parser = plugin_commands.add_parser(
        "run", help="run one plugin, whatever its triggers and hook say, or show the request it would receive"
    )
    _add_config(run_parser)
    run_parser.add_argument("plugin_id", metavar="ID", help="the plugin's check id")
    run_parser.add_argument(
        "--dump-input", action="store_true", help="write the plugin's request JSON to stdout instead of running it"
    )
    _add_run_options(run_parser)
    # None, not "text", so --dump-input can tell an explicit --format from none; _plugin_run supplies the default.
    run_parser.set_defaults(handler=_plugin_run, format=None)

    add_parser = plugin_commands.add_parser(
        "add",
        help=f"copy a plugin into {PLUGINS_DIR}/<id>/, enable it in charter.yaml and lock it in "
        f"{LOCK_FILENAME}; adding a locked plugin again replaces it",
    )
    _add_config(add_parser)
    origin = add_parser.add_mutually_exclusive_group(required=True)
    origin.add_argument(
        "--from", dest="git", metavar="URL@REF", help="a git repository and the branch, tag or commit to install"
    )
    origin.add_argument(
        "--dev",
        type=Path,
        metavar="PATH",
        help="a plugin's working copy, copied as it is now; add it again to pick up changes",
    )
    add_parser.set_defaults(handler=_plugin_add)

    list_parser = plugin_commands.add_parser(
        "list", help="list the plugins: installed ones and those used in place, with versions and sources"
    )
    _add_config(list_parser)
    _add_listing_format(list_parser)
    list_parser.set_defaults(handler=_plugin_list)

    info_parser = plugin_commands.add_parser(
        "info", help="show one plugin: its version, source, lock state and manifest"
    )
    _add_config(info_parser)
    info_parser.add_argument("plugin_id", metavar="ID", help="the plugin's check id")
    _add_listing_format(info_parser)
    info_parser.set_defaults(handler=_plugin_info)

    update_parser = plugin_commands.add_parser(
        "update",
        help=f"fetch a plugin installed from git again, at its ref or a new one, and refresh {LOCK_FILENAME}",
    )
    _add_config(update_parser)
    update_parser.add_argument("plugin_id", metavar="ID", help="the plugin's check id")
    update_parser.add_argument(
        "--ref", metavar="REF", help="the branch, tag or commit to move to (default: the one it was installed from)"
    )
    update_parser.set_defaults(handler=_plugin_update)

    for name, enabled in (("enable", True), ("disable", False)):
        toggle_parser = plugin_commands.add_parser(
            name, help=f"set checks.<id>.enabled to {'true' if enabled else 'false'} in charter.yaml"
        )
        _add_config(toggle_parser)
        toggle_parser.add_argument("plugin_id", metavar="ID", help="the plugin's check id")
        toggle_parser.set_defaults(handler=_plugin_toggle, enabled=enabled)

    remove_parser = plugin_commands.add_parser(
        "remove",
        help=f"remove a plugin's checks entry and, if charter installed it, its directory and {LOCK_FILENAME} entry",
    )
    _add_config(remove_parser)
    remove_parser.add_argument("plugin_id", metavar="ID", help="the plugin's check id")
    remove_parser.set_defaults(handler=_plugin_remove)
    return parser


def _add_listing_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=LISTING_FORMATS, default="text", help="output format (default: text)"
    )


def _add_config(parser: argparse.ArgumentParser, *, discover: bool = True) -> None:
    """`--config`; without it a command finds the nearest contract upward, unless it creates one (`init`)."""
    parser.add_argument(
        "--config",
        default=None if discover else CONTRACT_FILENAME,
        metavar="PATH",
        help=f"contract file (default: the nearest {CONTRACT_FILENAME} from the working directory upward)"
        if discover
        else f"contract file to create (default: ./{CONTRACT_FILENAME})",
    )


def _add_run_options(parser: argparse.ArgumentParser) -> argparse._MutuallyExclusiveGroup:
    """Adds the options that choose a run's targets and severities; returns the group of target options."""
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--all", action="store_true", help="target every note (default)")
    targets.add_argument(
        "--file", nargs="+", type=Path, metavar="PATH", help="target only these files (per-edit mode)"
    )
    targets.add_argument(
        "--staged",
        action="store_true",
        help="target the files staged in git, checking their staged content rather than the working copy",
    )
    parser.add_argument("--format", choices=FORMATS, default="text", help="output format (default: text)")
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="severity profile to apply instead of the automatic choice (also: CHARTER_PROFILE)",
    )
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    return targets


@dataclass(frozen=True)
class _Run:
    contract: Contract
    targets: Targets
    history: History
    profile: Profile
    today: datetime.date


@contextlib.contextmanager
def _prepared_run(args: argparse.Namespace) -> Iterator[_Run | list[Diagnostic]]:
    """The contract, targets, history and profile `--config`, `--file`, `--staged` and `--profile` select, or the
    usage errors; what is read from git stays readable until the block ends."""
    config = Path(args.config)
    base_dir = config.resolve().parent
    with contextlib.ExitStack() as cleanup:
        change = None
        # Without the contract's directory there is no repository to ask, and loading reports the missing contract.
        if args.staged and base_dir.is_dir():
            try:
                change = git.staged(base_dir)
            except (git.NotARepository, git.GitError) as error:
                yield [_git_problem(config, error, "--staged")]
                return
            cleanup.callback(_close, change)
        yield _prepare_run(args, config, change, cleanup)


def _prepare_run(
    args: argparse.Namespace, config: Path, change: git.Change | None, cleanup: contextlib.ExitStack
) -> _Run | list[Diagnostic]:
    if change is not None and not change.tree.is_file(config.name) and config.is_file():
        return [_contract_not_staged(config)]
    today = _today(config)
    if isinstance(today, Diagnostic):
        return [today]
    try:
        contract = contract_at(config, tree=change.tree if change else None)
    except ContractError as error:
        return error.diagnostics
    except git.GitError as error:
        # Only a git tree raises it, e.g. a staged plugin's blob that git cannot read while writing it out.
        return [_git_problem(config, error, "--staged")]
    deleted = getattr(args, "deleted", None)
    if deleted is None:
        deleted = _deleted_files(args.file or [])
    if args.file and (missing := _missing_files(contract, args.file, deleted)):
        return missing
    try:
        profile = select_profile(contract, args.profile, "edit" if args.file else "commit", os.environ)
    except UnknownProfile as error:
        return [_unknown_profile(config, error)]
    if change is not None:
        return _Run(contract, change, change.edits(), profile, today)
    # A file outside the contract's directory cannot be a note, so it simply has nothing to report.
    targets = None if args.file is None else frozenset(filter(None, map(contract.path_of, args.file)))
    # A deleted note's kind is read from git, so a deleted target always asks it.
    history = _uncommitted(contract, targets, cleanup, needed=any(map(contract.path_of, deleted)))
    if isinstance(history, Diagnostic):
        return [history]
    return _Run(contract, targets, history, profile, today)


def _today(config: Path) -> datetime.date | Diagnostic:
    """The day a run is judged as of: the local date, unless `CHARTER_TODAY` gives one."""
    given = os.environ.get(TODAY_VARIABLE)
    if not given:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(given)
    except ValueError:
        return Diagnostic(
            config.name,
            None,
            Severity.ERROR,
            "usage/invalid-today",
            f"`{TODAY_VARIABLE}` is `{given}`, which is not a date.",
            f"Set `{TODAY_VARIABLE}` to a date such as `2024-03-05` (YYYY-MM-DD), or unset it to use today's.",
        )


def _uncommitted(
    contract: Contract, targets: frozenset[str] | None, cleanup: contextlib.ExitStack, *, needed: bool = False
) -> History | Diagnostic:
    """What the working copy changes in `targets` since the last commit, or why that cannot be known. git is
    asked only when `needed` or when something judges edits: an overridable check with edits to judge, a history
    check or a plugin that needs the earlier version."""
    if not (
        needed
        or judging_edits(contract, targets)
        or any(contract.check_config(check.id).enabled for check in HISTORY_CHECKS)
        or any("before" in p.needs for p in contract.plugins.values())
    ):
        return None
    try:
        edits = git.uncommitted(contract.base_dir, contract.tree, targets)
    except git.NotARepository:
        return NoHistory("the directory holding the contract is not in a git repository")
    except git.GitUnavailable as error:
        return NoHistory(error.message.rstrip("."))
    except git.GitError as error:
        return _git_failed(contract.file, error, "charter could not compare the working copy with the last commit")
    if isinstance(edits, EditDelta):
        cleanup.callback(_close, edits.before)
    return edits


def _validate(args: argparse.Namespace) -> int:
    message = None
    if args.commit_msg_installed and not args.staged:
        return _usage_error([_installed_without_staged(Path(args.config))], args.format)
    if args.commit_msg is not None:
        message = _commit_message(Path(args.config), args.commit_msg, staged=args.staged)
        if isinstance(message, Diagnostic):
            return _usage_error([message], args.format)
    if args.range is not None:
        return _validate_range(args)
    with _prepared_run(args) as run:
        if isinstance(run, list):
            return _usage_error(run, args.format)
        _report_left_behind(leftover_staging(run.contract.base_dir))
        if message is not None:
            try:
                trailers = git.trailers(run.contract.base_dir, message)
            except git.GitError as error:
                failed = _git_failed(run.contract.file, error, "charter could not read the commit message's trailers")
                return _usage_error([failed], args.format)
            diagnostics = overridable_findings(
                run.contract, run.history, run.profile, strict=args.strict, today=run.today, trailers=trailers
            )
        else:
            diagnostics = validate(
                run.contract,
                run.targets,
                run.profile,
                strict=args.strict,
                today=run.today,
                per_edit=args.file is not None,
                history=run.history,
                # git's pre-commit stage: edit policies wait for the message, at commit-msg.
                overridable_checks=not args.staged,
                announce_deferred=not args.commit_msg_installed,
            )
    render(diagnostics, args.format, sys.stdout, run.profile.name)
    return exit_code(diagnostics)


def _validate_range(args: argparse.Namespace) -> int:
    """Edit policies and history checks for each commit of the range, as the hooks would have judged it when it
    was made: by its own contract, its own trailers and the day it was authored."""
    config = Path(args.config)
    contracts: git.ContentMemo[Contract] = git.ContentMemo()
    diagnostics: list[Diagnostic] = []
    judged = False
    try:
        for commit in git.commit_range(config.resolve().parent, args.range):
            found = _commit_findings(args, config, commit, contracts)
            if found is not None:
                diagnostics += found
                judged = True
        # No commit's contract checked the profile, so the working copy's does.
        if not judged and (problems := _range_profile_problems(config, args.profile)):
            return _usage_error(problems, args.format)
    except git.InvalidRange as error:
        return _usage_error([_invalid_range(config, args.range, error)], args.format)
    except git.ShallowHistory as error:
        return _usage_error([_shallow_history(config, error)], args.format)
    except (git.NotARepository, git.GitError) as error:
        return _usage_error([_git_problem(config, error, "--range")], args.format)
    except Refused as refusal:
        return _usage_error(refusal.diagnostics, args.format)
    render(diagnostics, args.format, sys.stdout, profile_name(args.profile, "ci", os.environ))
    return exit_code(diagnostics)


def _commit_findings(
    args: argparse.Namespace, config: Path, commit: git.Commit, contracts: "git.ContentMemo[Contract]"
) -> list[Diagnostic] | None:
    """What the edit policies and history checks say about `commit`; None when charter did not govern it. Raises
    Refused when the commit's contract or the profile cannot be used, and GitError."""
    change = commit.change()
    try:
        if not change.tree.is_file(config.name):
            if change.before.is_file(config.name):
                raise Refused([_contract_deleted(config, commit)], usage=True)
            return None
        try:
            contract = contracts.get(
                change.tree,
                # --range runs no plugin, so none is written out of the commit.
                lambda tree: contract_at(config, tree=tree, write_plugins=False),
            )
            profile = select_profile(contract, args.profile, "ci", os.environ)
        except ContractError as error:
            raise Refused(_in_commit(error.diagnostics, commit), usage=True) from None
        except UnknownProfile as error:
            raise Refused(_in_commit([_unknown_profile(config, error)], commit), usage=True) from None
        return commit_findings(
            contract,
            change.edits(),
            profile,
            strict=args.strict,
            trailers=commit.trailers,
            commit=commit.name,
            authored=commit.authored,
        )
    finally:
        _close(change)


def _range_profile_problems(config: Path, explicit: str | None) -> list[Diagnostic]:
    """Why the profile `--range` would apply is unknown to the working copy's contract, if it is not built in."""
    name = profile_name(explicit, "ci", os.environ)
    if is_builtin_profile(name):
        return []
    try:
        select_profile(contract_at(config), name, "ci", os.environ)
    except ContractError as error:
        return error.diagnostics
    except UnknownProfile as error:
        return [_unknown_profile(config, error)]
    return []


def _in_commit(diagnostics: list[Diagnostic], commit: git.Commit) -> list[Diagnostic]:
    return [replace(d, message=f"In commit {commit.name}: {d.message}") for d in diagnostics]


def _plugin_run(args: argparse.Namespace) -> int:
    unused = [name for name, given in _DUMP_INPUT_REFUSED if getattr(args, given)]
    args.format = args.format or "text"
    if args.dump_input and unused:
        return _usage_error([_dump_input_conflict(Path(args.config), unused)], args.format)
    with _prepared_run(args) as run:
        if isinstance(run, list):
            return _usage_error(run, args.format)
        if args.plugin_id not in run.contract.plugins:
            return _usage_error([_unknown_plugin(run.contract, args.plugin_id)], args.format)
        if args.dump_input:
            payload = plugin_payload(run.contract, args.plugin_id, run.targets, run.history, run.today)
            sys.stdout.write(payload + "\n")
            return EXIT_CLEAN
        diagnostics = run_plugin(
            run.contract, args.plugin_id, run.targets, run.history, run.profile, strict=args.strict, today=run.today
        )
    render(diagnostics, args.format, sys.stdout, run.profile.name)
    return exit_code(diagnostics)


def _close(tree: "git.Change | git.GitTree") -> None:
    _report_left_behind(left_behind(tree.close()))


def _report_left_behind(warnings: Iterable[Diagnostic]) -> None:
    """Cleanup that could not finish, now or in an earlier run, is a warning on stderr, so the command's output and
    exit code stay as they were."""
    if warnings := list(warnings):
        render(warnings, "text", sys.stderr)


def _plugin_add(args: argparse.Namespace) -> int:
    from charter import install  # only this command needs it

    def add(settings: PluginSettings) -> list[str]:
        if args.dev is not None:
            added = install.add_dev(settings, args.dev)
            then = f"After changing the working copy, add it again to copy the changes into `{added.directory}`."
        else:
            added = install.add_from_git(settings, args.git)
            then = (
                f"Commit `{added.directory}`, `{LOCK_FILENAME}` and `{settings.file}`, so CI runs the plugin "
                "without fetching it."
            )
        _report_left_behind(added.warnings)
        return [
            f"{'Replaced' if added.replaced else 'Added'} plugin `{added.id}` {added.version} from `{added.origin}` "
            f"to `{added.directory}`.",
            *([f"Enabled it as `checks.{added.id}` in `{settings.file}`."] if added.entry_added else []),
            f"Recorded its version, source and sha256 in `{LOCK_FILENAME}`.",
            *(f"Added `{entry}` to `{install.GITIGNORE}`, for the bytecode Python plugins leave behind." for entry in added.ignored),
            then,
        ]

    # Unlike the other plugin commands, `add` needs a valid contract to add to.
    return _change_plugins(args, add, strict=True)


def _plugin_update(args: argparse.Namespace) -> int:
    from charter import install  # only this command needs it

    def update(settings: PluginSettings) -> list[str]:
        updated = install.update(settings, args.plugin_id, args.ref)
        added, previous = updated.added, updated.previous
        _report_left_behind(added.warnings)
        if updated.changed:
            steps = [
                f"Updated plugin `{added.id}` from {previous.version} to {added.version}, `{added.origin}`, "
                f"in `{added.directory}`.",
                f"Recorded its version, source and sha256 in `{LOCK_FILENAME}`.",
            ]
        else:
            steps = [f"Plugin `{added.id}` is already at {added.version}, `{added.origin}`."]
            if updated.restored:
                steps.append(f"Restored `{added.directory}`, which no longer matched `{LOCK_FILENAME}`.")
        if updated.changed or updated.restored:
            steps.append(
                f"Commit `{added.directory}` and `{LOCK_FILENAME}`, so CI runs the plugin without fetching it."
            )
        if not updated.enabled:
            steps.append(f"It is not enabled in `{settings.file}`; `charter plugin enable {added.id}` runs it.")
        return steps

    return _change_plugins(args, update)


def _plugin_toggle(args: argparse.Namespace) -> int:
    from charter import install  # only this command needs it
    state = "enabled" if args.enabled else "disabled"

    def toggle(settings: PluginSettings) -> list[str]:
        if not install.set_enabled(settings, args.plugin_id, args.enabled):
            return [f"Plugin `{args.plugin_id}` is already {state}."]
        effect = "charter runs it again." if args.enabled else "charter no longer runs it."
        return [f"Set `checks.{args.plugin_id}.enabled` to {str(args.enabled).lower()} in `{settings.file}`: {effect}"]

    return _change_plugins(args, toggle)


def _plugin_remove(args: argparse.Namespace) -> int:
    from charter import install  # only this command needs it

    def remove(settings: PluginSettings) -> list[str]:
        removed = install.remove(settings, args.plugin_id)
        _report_left_behind(removed.warnings)
        return [
            f"Removed plugin `{removed.id}`.",
            *([f"Deleted `{removed.deleted}` and its entry in `{LOCK_FILENAME}`."] if removed.deleted else []),
            *([f"Removed `checks.{removed.id}` from `{settings.file}`."] if removed.unchecked else []),
            *([f"Left `{removed.kept}` in place: charter did not install it."] if removed.kept else []),
        ]

    return _change_plugins(args, remove)


def _change_plugins(
    args: argparse.Namespace, change: Callable[[PluginSettings], list[str]], *, strict: bool = False
) -> int:
    """Runs a `charter plugin` command that changes the knowledge base, then reports whether the contract can
    be used as it now stands. `strict` refuses to start on an invalid contract."""
    config = Path(args.config)
    try:
        if strict:
            settings = contract_at(config)
        else:
            settings = plugin_settings_at(config)
        steps = change(settings)
    except ContractError as error:
        return _usage_error(error.diagnostics, "text")
    except Refused as refusal:
        render(refusal.diagnostics, "text", sys.stdout)
        return EXIT_USAGE if refusal.usage else exit_code(refusal.diagnostics)
    sys.stdout.write("".join(f"{step}\n" for step in steps))
    try:
        contract_at(config)
    except ContractError as error:
        sys.stdout.write("The contract needs attention before charter can use it:\n")
        render(error.diagnostics, "text", sys.stdout)
        return EXIT_ERRORS
    return EXIT_CLEAN


def _plugin_list(args: argparse.Namespace) -> int:
    from charter import inventory  # only this command needs it
    try:
        settings = plugin_settings_at(Path(args.config))
    except ContractError as error:
        return _usage_error(error.diagnostics, args.format)
    _report_left_behind(leftover_staging(settings.base_dir))
    plugins = inventory.listing(settings)
    if args.format == "json":
        sys.stdout.write(inventory.to_json({"plugins": plugins}))
    else:
        sys.stdout.write(inventory.listing_text(plugins, settings.file))
    return EXIT_CLEAN


def _plugin_info(args: argparse.Namespace) -> int:
    from charter import install, inventory  # only this command needs it
    try:
        settings = plugin_settings_at(Path(args.config))
    except ContractError as error:
        return _usage_error(error.diagnostics, args.format)
    if args.plugin_id not in settings.plugin_ids:
        return _usage_error([install.unknown_plugin(settings, args.plugin_id)], args.format)
    plugin = inventory.details(settings, args.plugin_id)
    sys.stdout.write(inventory.to_json(plugin) if args.format == "json" else inventory.details_text(plugin))
    return EXIT_CLEAN


def _new(args: argparse.Namespace) -> int:
    today = _today(Path(args.config))
    if isinstance(today, Diagnostic):
        return _usage_error([today], args.format)
    try:
        contract = contract_at(Path(args.config))
    except ContractError as error:
        return _usage_error(error.diagnostics, args.format)
    written = not args.dry_run
    try:
        draft = create(contract, args.kind, args.title, args.set, today=today, write=written)
    except Refused as refusal:
        render(refusal.diagnostics, args.format, sys.stdout)
        return EXIT_USAGE if refusal.usage else exit_code(refusal.diagnostics)
    render_draft(draft.path, draft.shape, draft.outline, args.format, sys.stdout, written=written)
    if draft.warnings:
        render(list(draft.warnings), args.format, sys.stdout)
    return EXIT_CLEAN


def _describe(args: argparse.Namespace) -> int:
    from charter import description  # only this command needs it

    # Problems are diagnostics, which have no Markdown form; text is their human-readable one.
    diagnostics_format = "json" if args.format == "json" else "text"
    try:
        contract = contract_at(Path(args.config))
        described = description.build_description(contract, args.kind)
    except (ContractError, Refused) as error:
        return _usage_error(error.diagnostics, diagnostics_format)
    render_description = description.to_json if args.format == "json" else description.to_markdown
    sys.stdout.write(render_description(described))
    return EXIT_CLEAN


def _sweep(args: argparse.Namespace) -> int:
    from charter import sweep  # only this command needs it
    try:
        swept = sweep.find(contract_at(Path(args.config)), args.note)
    except (ContractError, Refused) as error:
        return _usage_error(error.diagnostics, args.format)
    sys.stdout.write(sweep.RENDERERS[args.format](swept))
    return EXIT_CLEAN


def _docs(args: argparse.Namespace) -> int:
    from charter import agent_files, docs  # only this command needs it
    try:
        contract = contract_at(Path(args.config))
    except ContractError as error:
        return _usage_error(error.diagnostics, "text")
    if not contract.rulebook_generated:
        return _usage_error([_no_rulebook(contract)], "text")
    if args.link_agents and not contract.agent_layer_on:
        return _usage_error([_no_agent_layer(contract)], "text")
    output = contract.docs_output
    try:
        if not args.check:
            written = docs.write_rulebook(contract)
            sys.stdout.write(f"Wrote `{output}`.\n" if written else f"`{output}` is up to date.\n")
        if args.link_agents:
            sys.stdout.write(_agent_file_lines(agent_files.write_agent_files(contract.base_dir, output, contract.agents_file, docs.WRITE_FAILED)))
    except Refused as refusal:
        render(refusal.diagnostics, "text", sys.stdout)
        return EXIT_ERRORS
    if args.check:
        if (stale := docs.staleness(contract)) is not None:
            render([stale], "text", sys.stdout)
            return EXIT_ERRORS
        sys.stdout.write(f"`{output}` is up to date.\n")
    return EXIT_CLEAN


def _init(args: argparse.Namespace) -> int:
    from charter import init  # only this command needs it
    try:
        result = init.initialise(args.folder, agents=args.agents, draft=args.draft)
    except Refused as refusal:
        render(refusal.diagnostics, "text", sys.stdout)
        return EXIT_USAGE if refusal.usage else EXIT_ERRORS
    contract = result.contract
    where = (args.folder / CONTRACT_FILENAME).as_posix()
    steps = [f"Wrote `{where}` from the draft." if args.draft else f"Wrote `{where}`."]
    if result.agents is None:
        steps.append(
            "Next: run `charter validate`."
            if args.draft
            else f"Next: declare your kinds of note in `{where}`, then run `charter validate`."
        )
    else:
        if result.added:
            steps.append(f"Added {' and '.join(f'`{name}:`' for name in result.added)} to `{where}`.")
        steps += [
            f"Wrote `{(args.folder / contract.docs_output).as_posix()}`.",
            *_agent_file_lines(result.agents, args.folder).splitlines(),
        ]
        steps.append(
            "Next: run `charter validate`."
            if args.draft
            else f"Next: declare your kinds of note in `{where}`, then run `charter docs` and `charter validate`."
        )
    sys.stdout.write("".join(f"{step}\n" for step in steps))
    return EXIT_CLEAN


def _snapshot(args: argparse.Namespace) -> int:
    from charter import snapshot  # only this command needs it
    # The bare word `restore` is the subcommand; a folder of that name is `./restore`, which is not that word.
    restoring = args.words[0] == "restore"
    problem = None
    if restoring and len(args.words) != 2:
        problem = "`snapshot restore` takes one ZIP. (For a folder named `restore`, write `./restore`.)"
    elif not restoring and len(args.words) != 1:
        problem = "`snapshot` takes one FOLDER."
    elif not restoring and args.replace:
        problem = "--replace only applies to `snapshot restore`."
    if problem:
        return _usage_error([Diagnostic("snapshot", None, Severity.ERROR, "usage/snapshot-arguments", problem)], "text")
    try:
        if restoring:
            restored = snapshot.restore(Path(args.words[1]), Path(args.to) if args.to else None, replace=args.replace)
            sys.stdout.write(
                f"Restored {restored.files} files and {restored.folders} folders into `{restored.target}`"
                f"{' (replacing what was there)' if restored.replaced else ''}.\n"
            )
            _report_left_behind(left_behind(restored.leftovers))
            return EXIT_CLEAN
        taken = snapshot.take(Path(args.words[0]), args.to)
    except Refused as refusal:
        render(refusal.diagnostics, "text", sys.stdout)
        return EXIT_USAGE if refusal.usage else EXIT_ERRORS
    quoted = snapshot.restore_command(taken)
    sys.stdout.write(
        f"Snapshot of `{taken.folder}` ({taken.files} files, {taken.folders} folders) written to `{taken.archive}`.\n"
        f"To put it back, replacing the folder as it is now:\n  {quoted}\n"
    )
    return EXIT_CLEAN


def _survey(args: argparse.Namespace) -> int:
    from charter import survey  # only this command needs it
    if not args.folder.is_dir():
        return _usage_error(
            [
                Diagnostic(
                    args.folder.as_posix(),
                    None,
                    Severity.ERROR,
                    "usage/folder-not-found",
                    f"`{args.folder.as_posix()}` is not an existing folder.",
                    "survey takes the folder whose Markdown files it should report on.",
                )
            ],
            "text" if args.format == "text" else "json",
        )
    result = survey.survey(args.folder)
    sys.stdout.write(survey.to_json(result) if args.format == "json" else survey.to_text(result))
    return EXIT_CLEAN


def _agent_file_lines(files: "list[agent_files.AgentFile]", folder: Path = Path()) -> str:
    """One line per agent file; `folder` (the working directory by default) is what the written paths show from."""
    from charter.agent_files import Outcome  # only the commands that write agent files need it

    linked = {
        Outcome.CREATED: "Created `{file}` with a link to `{target}`.",
        Outcome.APPENDED: "Linked `{target}` from `{file}`.",
        Outcome.ALREADY: "`{file}` already points at `{target}`.",
    }
    imported = {
        Outcome.CREATED: "Created `{file}` importing `{target}`.",
        Outcome.APPENDED: "Added an import of `{target}` to `{file}`.",
        Outcome.ALREADY: "`{file}` already points at `{target}`.",
    }
    return "".join(
        (imported if file.imports else linked)[file.outcome].format(
            file=(folder / file.path).as_posix(), target=file.target
        )
        + "\n"
        for file in files
    )


def _usage_error(diagnostics: list[Diagnostic], output_format: str) -> int:
    render(diagnostics, output_format, sys.stdout)
    return EXIT_USAGE


def _deleted_files(files: list[Path]) -> frozenset[Path]:
    """The files missing from the working copy that git still tracks: `--file` judges them as deletions."""
    return frozenset(file for file in files if not file.exists() and git.tracks(file))


def _missing_files(contract: Contract | None, files: list[Path], deleted: frozenset[Path]) -> list[Diagnostic]:
    """One diagnostic per nonexistent file that is not one of the `deleted` files git still tracks. Before
    discovery has run there is no loaded contract: the nearest one above the file sets the path form, as typed if
    none."""
    return [
        Diagnostic(
            (contract.path_of(file) if contract else discovery.path_under_contract(file)) or file.as_posix(),
            None,
            Severity.ERROR,
            "usage/file-not-found",
            f"`{file.as_posix()}` is not an existing file.",
            "--file takes paths to existing files, or to deleted files git still tracks, relative to the working "
            "directory or absolute.",
        )
        for file in files
        if not file.is_file() and file not in deleted
    ]


def _installed_without_staged(config: Path) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/commit-msg-installed-without-staged",
        "--commit-msg-installed says a commit-msg hook judges the edit policies of the commit being made, so it "
        "needs --staged to say what that commit holds.",
        "Add --staged, as a pre-commit hook does: `charter validate --staged --commit-msg-installed`.",
    )


def _commit_message(config: Path, file: Path, *, staged: bool) -> bytes | Diagnostic:
    if not staged:
        return Diagnostic(
            config.name,
            None,
            Severity.ERROR,
            "usage/commit-msg-without-staged",
            "--commit-msg gives the message of the commit being made, so it needs --staged to say what that "
            "commit holds.",
            "Add --staged, as a commit-msg hook does: `charter validate --staged --commit-msg FILE`.",
        )
    if not file.is_file():
        return Diagnostic(
            file.as_posix(),
            None,
            Severity.ERROR,
            "usage/file-not-found",
            f"`{file.as_posix()}` is not an existing file.",
            "--commit-msg takes the file holding the commit message, as git passes it to a commit-msg hook.",
        )
    try:
        return file.read_bytes()
    except OSError as error:
        return Diagnostic(
            file.as_posix(),
            None,
            Severity.ERROR,
            "usage/file-unreadable",
            f"`{file.as_posix()}` could not be read: {error.strerror or error}.",
            "Check that the commit message file is readable.",
        )


# Options that shape the diagnostics or their rendering, which `--dump-input` never produces. `format` is still
# None here when the flag was not given, so an explicit `--format text` counts.
_DUMP_INPUT_REFUSED = (("--format", "format"), ("--profile", "profile"), ("--strict", "strict"))


def _no_rulebook(contract: Contract) -> Diagnostic:
    from charter import docs  # only this command needs it
    return Diagnostic(
        contract.file,
        None,
        Severity.ERROR,
        docs.NO_RULEBOOK,
        f"{contract.file} declares no rulebook to write.",
        f"Add a `docs:` section to {contract.file} (`docs: {{output: CHARTER.md}}`) to name where it goes; "
        "an `agents:` section also produces one, at the default path.",
    )


def _no_agent_layer(contract: Contract) -> Diagnostic:
    return Diagnostic(
        contract.file,
        None,
        Severity.ERROR,
        "usage/no-agent-layer",
        f"--link-agents needs the agent layer, and {contract.file} does not declare it.",
        f"Add an `agents:` section to {contract.file} (`agents: {{file: AGENTS.md}}`) to turn it on.",
    )


def _dump_input_conflict(config: Path, unused: list[str]) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/conflicting-options",
        f"--dump-input runs no plugin and always writes JSON, so {' and '.join(unused)} would have no effect.",
        f"Leave out {' and '.join(unused)}, or --dump-input to run the plugin.",
    )


def _unknown_plugin(contract: Contract, plugin_id: str) -> Diagnostic:
    enabled = sorted(contract.plugins)
    return Diagnostic(
        contract.file,
        None,
        Severity.ERROR,
        "usage/unknown-plugin",
        f"`{plugin_id}` is not an enabled plugin: no enabled `checks.{plugin_id}` in charter.yaml has a `source`.",
        f"Enabled plugins: {code_list(enabled)}." if enabled else "This contract has no enabled plugins.",
    )


def _contract_not_staged(config: Path) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/contract-not-staged",
        f"`{config.name}` is not staged, so --staged has no contract to validate what is staged against.",
        f"`git add {config.name}`, or leave out --staged to validate the working copy.",
    )


class _GitOption(NamedTuple):
    validates: str
    reads: str
    outside_hint: str


_GIT_OPTIONS = {
    "--staged": _GitOption(
        "what is staged in git",
        "what is staged",
        "Run it inside a git repository, or leave out --staged to validate the working copy.",
    ),
    "--range": _GitOption(
        "commits in git", "the range's commits", "Run it inside the git repository holding the commits."
    ),
}


def _git_problem(config: Path, error: git.NotARepository | git.GitError, option: str) -> Diagnostic:
    described = _GIT_OPTIONS[option]
    if isinstance(error, git.NotARepository):
        return Diagnostic(
            config.name,
            None,
            Severity.ERROR,
            "usage/not-a-git-repository",
            f"{option} validates {described.validates}, but the directory holding the contract is not in a git "
            "working tree.",
            described.outside_hint,
        )
    return _git_failed(config.name, error, f"{option} could not read {described.reads}")


def _invalid_range(config: Path, revisions: str, error: git.InvalidRange) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/invalid-range",
        f"`{revisions}` {error.problem}.",
        error.hint
        or "--range takes `A..B`, the commits B has and A has not, such as `origin/main..HEAD`; an empty side "
        "means `HEAD`.",
    )


def _shallow_history(config: Path, error: git.ShallowHistory) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/shallow-history",
        f"--range compares each commit with its parent, but {error.problem}.",
        "Fetch the history the range needs: `fetch-depth: 0` with actions/checkout, or `git fetch --unshallow`.",
    )


def _contract_deleted(config: Path, commit: git.Commit) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/contract-deleted",
        f"Commit {commit.name} deletes `{config.name}`, so there is no contract to judge its edits by.",
        f"Rewrite the commit so that it keeps `{config.name}`; to stop using charter, remove its CI check too.",
    )


def _git_failed(path: str, error: git.GitError, failed: str) -> Diagnostic:
    return Diagnostic(
        path,
        None,
        Severity.ERROR,
        "usage/git-failed",
        f"{failed}: {error.message}",
        error.hint or "Check that git works in this repository: `git status` should succeed.",
    )


def _unknown_profile(config: Path, error: UnknownProfile) -> Diagnostic:
    return Diagnostic(
        config.name,
        None,
        Severity.ERROR,
        "usage/unknown-profile",
        f"Profile `{error.name}` is neither built in nor declared under `profiles:`.",
        f"Available profiles: {code_list(error.available)}.",
    )
