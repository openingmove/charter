"""Runs the enabled checks over the index and brings their diagnostics to the profile's severities."""

import datetime
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

from charter import index, overrides
from charter.checks import Check, CheckRequest, OverridableCheck
from charter.checks.agents_include import AgentsIncludeCheck
from charter.checks.external import PluginCheck
from charter.checks.filenames import FilenamesCheck
from charter.checks.ids import IdsCheck
from charter.checks.links import LinksCheck
from charter.checks.paths import PathsCheck
from charter.checks.protected_region import ProtectedRegionCheck
from charter.checks.residue import ResidueCheck
from charter.checks.schema import SchemaCheck
from charter.checks.structure import StructureCheck
from charter.checks.tags import TagsCheck
from charter.checks.updated_date import UpdatedDateCheck
from charter.contract import Contract, OptionalCheck, PluginSettings, load_contract, load_plugin_settings
from charter.diagnostics import PLUGIN_SKIPPED_PATH, Diagnostic
from charter.git import Change
from charter.history import History
from charter.index import Note
from charter.links import Resolver
from charter.profiles import Finding, Profile
from charter.tree import Tree

_PATHS = PathsCheck()
_UPDATED_DATE = UpdatedDateCheck()
_PROTECTED_REGION = ProtectedRegionCheck()
# Shipped checks that stay off until the contract enables them.
OPTIONAL_CHECKS: dict[str, OptionalCheck] = {check.id: check for check in (_UPDATED_DATE, _PROTECTED_REGION)}
# Checks that judge a change from its history alone, so they also judge each commit of a range.
HISTORY_CHECKS: tuple[Check, ...] = (_UPDATED_DATE,)
# Checks whose edit judgements a `Charter-Allow` trailer may overrule, so they are made with the commit message.
OVERRIDABLE_CHECKS: tuple[OverridableCheck, ...] = (_PATHS, _PROTECTED_REGION)
OVERRIDABLE = frozenset(code for check in OVERRIDABLE_CHECKS for code in check.overridable)
BUILTIN_CHECKS: tuple[Check, ...] = (
    SchemaCheck(),
    FilenamesCheck(),
    _PATHS,
    LinksCheck(),
    IdsCheck(),
    TagsCheck(),
    StructureCheck(),
    ResidueCheck(),
    AgentsIncludeCheck(),
    _UPDATED_DATE,
    _PROTECTED_REGION,
)
CHECK_CODES = {check.id: check.codes for check in BUILTIN_CHECKS}
CORE_CODES = index.CODES | overrides.CODES | {PLUGIN_SKIPPED_PATH}


def contract_at(config: Path, tree: Tree | None = None, *, write_plugins: bool = True) -> Contract:
    """The contract `config` names, read from `tree` (by default the working copy), validated against the checks
    there are. Without `write_plugins`, its plugins are judged but not written to disk, so they cannot be run.
    Raises ContractError."""
    return load_contract(
        config,
        check_codes=CHECK_CODES,
        core_codes=CORE_CODES,
        optional_checks=OPTIONAL_CHECKS,
        tree=tree,
        write_plugins=write_plugins,
    )


def plugin_settings_at(config: Path) -> PluginSettings:
    """What `charter plugin` manages in the contract `config` names, defaulting the built-in checks as
    `contract_at` does. Raises ContractError."""
    return load_plugin_settings(config, optional_checks=OPTIONAL_CHECKS)


# What a run targets: None for every note, the given files, or a change's files.
Targets = frozenset[str] | Change | None


def validate(
    contract: Contract,
    targets: Targets,
    profile: Profile,
    *,
    strict: bool,
    today: datetime.date,
    pending: Mapping[str, str] | None = None,
    per_edit: bool = False,
    history: History = None,
    overridable_checks: bool = True,
    announce_deferred: bool = True,
) -> list[Diagnostic]:
    """Diagnostics for `targets` (diagnostic-form paths), with `pending` notes in the index, as of `today`. For a
    change, the kinds its modified and deleted notes had before it count as touched too.

    `per_edit` marks a run that checks one edit as it happens (see `CheckRequest.per_edit`); `history` is what
    the run's change did to existing files (see `CheckRequest.history`). Without `overridable_checks` (git's
    pre-commit stage) the judgements of `OVERRIDABLE_CHECKS` are left to `overridable_findings`, at the
    commit-msg stage, and say so with an info each unless `announce_deferred` is off (a commit-msg hook is
    installed, so the note would only repeat what that hook is about to do).
    """
    built, request = _check_request(contract, targets, pending, per_edit=per_edit, history=history, today=today)
    findings = [Finding(d) for d in built.diagnostics if request.whole or d.path in request.targets]
    for check in (*BUILTIN_CHECKS, *map(PluginCheck, contract.plugins.values())):
        if contract.check_config(check.id).enabled:
            findings.extend(_findings(contract, check.id, check.run(request)))
    if overridable_checks:
        findings.extend(_overridable_findings(request))
    elif announce_deferred:
        for overridable in judging_edits(contract):
            findings.extend(_findings(contract, overridable.id, [overridable.deferred(contract)]))
    return profile.apply(findings, strict=strict)


def judging_edits(contract: Contract, targets: frozenset[str] | None = None) -> list[OverridableCheck]:
    """The enabled `OVERRIDABLE_CHECKS` that have edits to judge under `contract`, in just `targets` when given."""
    return [
        check
        for check in OVERRIDABLE_CHECKS
        if contract.check_config(check.id).enabled and check.judges_edits(contract, targets)
    ]


def overridable_findings(
    contract: Contract,
    history: History,
    profile: Profile,
    *,
    strict: bool,
    today: datetime.date,
    trailers: Iterable[tuple[str, str]] = (),
) -> list[Diagnostic]:
    """Only what the enabled `OVERRIDABLE_CHECKS` say about `history` as of `today`, honouring the commit
    message's `trailers` (from `git.trailers`). Needs no index."""
    request = _history_request(contract, history, today)
    findings = overrides.allow(trailers, _overridable_findings(request), contract.file, OVERRIDABLE)
    return profile.apply(findings, strict=strict)


def commit_findings(
    contract: Contract,
    history: History,
    profile: Profile,
    *,
    strict: bool,
    trailers: Iterable[tuple[str, str]],
    commit: str,
    authored: datetime.date,
) -> list[Diagnostic]:
    """What the `OVERRIDABLE_CHECKS`, honouring the commit's own `trailers`, and the enabled history checks say about
    `history`, the change commit `commit`, authored on `authored`, made. Needs no index: the contract may be
    an earlier commit's with the same content, so nothing is read through its tree."""
    request = _history_request(contract, history, authored, commit)
    findings = overrides.allow(trailers, _overridable_findings(request), contract.file, OVERRIDABLE, commit)
    for check in HISTORY_CHECKS:
        if contract.check_config(check.id).enabled:
            findings.extend(_findings(contract, check.id, check.run(request)))
    return profile.apply(findings, strict=strict)


def _history_request(
    contract: Contract, history: History, today: datetime.date, commit: str | None = None
) -> CheckRequest:
    """A request without an index, for checks that judge `history` alone."""
    return CheckRequest(
        contract=contract,
        notes=(),
        targets=frozenset(),
        resolver=Resolver(contract.root_path, (), (), {}, contract.links.resolve),
        kinds=frozenset(),
        whole=False,
        per_edit=False,
        history=history,
        today=today,
        commit=commit,
    )


def _overridable_findings(request: CheckRequest) -> list[Finding]:
    contract = request.contract
    return [
        finding
        for check in OVERRIDABLE_CHECKS
        if contract.check_config(check.id).enabled
        for finding in _findings(contract, check.id, check.edit_diagnostics(request))
    ]


def plugin_payload(
    contract: Contract, plugin_id: str, targets: Targets, history: History, today: datetime.date
) -> str:
    """The request `validate` would send plugin `plugin_id` for `targets`, whether or not its triggers fire."""
    _, request = _check_request(contract, targets, None, per_edit=False, history=history, today=today)
    return PluginCheck(contract.plugins[plugin_id]).payload(request)


def run_plugin(
    contract: Contract,
    plugin_id: str,
    targets: Targets,
    history: History,
    profile: Profile,
    *,
    strict: bool,
    today: datetime.date,
) -> list[Diagnostic]:
    """Plugin `plugin_id`'s diagnostics for `targets`, run whatever its triggers and hook say."""
    _, request = _check_request(contract, targets, None, per_edit=False, history=history, today=today)
    diagnostics = PluginCheck(contract.plugins[plugin_id]).invoke(request)
    return profile.apply(_findings(contract, plugin_id, diagnostics), strict=strict)


def _findings(contract: Contract, check_id: str, diagnostics: Iterable[Diagnostic]) -> list[Finding]:
    severity = contract.check_config(check_id).severity
    return [Finding(d, check_id, severity) for d in diagnostics]


def _check_request(
    contract: Contract,
    targets: Targets,
    pending: Mapping[str, str] | None,
    *,
    per_edit: bool,
    history: History,
    today: datetime.date,
) -> tuple[index.Index, CheckRequest]:
    built = index.build_index(contract, pending)
    paths = targets.changed if isinstance(targets, Change) else targets
    # A whole run also targets the contract, where findings about a kind's notes taken together belong.
    if paths is None:
        selected = frozenset([contract.file, *(note.path for note in built.notes)])
    else:
        # A named file may differ in Unicode form from the listed note (a decomposed root); judge it as that note.
        # A path that is itself a note stays as named. So does a path that names a file of its own: a file system
        # that keeps both spellings apart (Linux, NTFS) holds two files, and the look-alike is not the one named.
        exact = {note.path for note in built.notes}
        listed: dict[str, str] = {}
        for note in built.notes:
            listed.setdefault(unicodedata.normalize("NFC", note.path), note.path)

        def judged(path: str) -> str:
            if path in exact or contract.tree.is_exact_file(path):
                return path
            return listed.get(unicodedata.normalize("NFC", path), path)

        selected = frozenset(judged(path) for path in paths)
    kinds = touched_kinds(contract, built.notes, selected)
    if isinstance(targets, Change):
        kinds |= index.kinds_before(contract, targets.before)
    request = CheckRequest(
        contract=contract,
        notes=built.notes,
        targets=selected,
        resolver=built.resolver,
        kinds=kinds,
        whole=paths is None,
        per_edit=per_edit,
        history=history,
        today=today,
    )
    return built, request


def touched_kinds(contract: Contract, notes: Iterable[Note], targets: frozenset[str]) -> frozenset[str]:
    """The kinds of the targeted notes; every kind when the contract itself is targeted."""
    if contract.file in targets:
        return frozenset(contract.kinds)
    kinds = (contract.kind_of(note.frontmatter) for note in notes if note.path in targets)
    return frozenset(kind.name for kind in kinds if kind is not None)
