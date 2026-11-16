"""Severities: a check's override, then the stage's profile, then a `Charter-Allow` trailer, then `--strict`."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from charter.contract import Contract, ProfileSeverities
from charter.diagnostics import RUN_FAILURES, Diagnostic, Severity

# Tuned for a branch + pull-request workflow, where CI on the pull request is the gate:
# work in progress warns about what is easy to leave half-done, CI enforces base severities.
_WORK_IN_PROGRESS: ProfileSeverities = {
    code: Severity.WARNING
    for code in ("schema/unknown-field", "schema/missing-frontmatter", "structure", "residue")
}
_BUILTIN_PROFILES: dict[str, ProfileSeverities] = {
    "edit": _WORK_IN_PROGRESS,
    "commit": _WORK_IN_PROGRESS,
    "ci": {},
}


class UnknownProfile(Exception):
    def __init__(self, name: str, available: list[str]):
        super().__init__(name)
        self.name = name
        self.available = available


@dataclass(frozen=True)
class Finding:
    """A diagnostic at its base severity, with what decides its final one."""

    diagnostic: Diagnostic
    # None for problems the core reports outside any check.
    check_id: str | None = None
    check_severity: Severity | None = None
    # A commit-message trailer allows it, so it is at most a warning.
    allowed: bool = False
    # A warning `--strict` leaves a warning: it records a human's decision rather than something to fix.
    strict_exempt: bool = False


@dataclass(frozen=True)
class Profile:
    name: str
    severities: ProfileSeverities
    # Built-in defaults only make diagnostics more lenient; a contract's profile sets exactly what it says.
    downgrade_only: bool

    def apply(self, findings: Iterable[Finding], *, strict: bool) -> list[Diagnostic]:
        """Each finding at its final severity; findings the profile turns off are dropped."""
        final = []
        for finding in findings:
            severity = self._severity(finding)
            if severity is None:
                continue
            if finding.allowed:
                severity = severity.capped_at(Severity.WARNING)
            if strict and severity is Severity.WARNING and not finding.strict_exempt:
                severity = Severity.ERROR
            final.append(replace(finding.diagnostic, severity=severity))
        return final

    def _severity(self, finding: Finding) -> Severity | None:
        if finding.diagnostic.code in RUN_FAILURES:
            return finding.diagnostic.severity
        base = finding.check_severity or finding.diagnostic.severity
        for key in (finding.diagnostic.code, finding.check_id):
            if key in self.severities:
                severity = self.severities[key]
                if severity is None or not self.downgrade_only:
                    return severity
                return base.capped_at(severity)
        return base


def profile_name(explicit: str | None, stage: str, environ: Mapping[str, str]) -> str:
    """The profile named explicitly or by CHARTER_PROFILE, else `ci` under CI=true, else the target mode's `stage`."""
    return explicit or environ.get("CHARTER_PROFILE") or ("ci" if environ.get("CI", "").lower() == "true" else stage)


def is_builtin_profile(name: str) -> bool:
    return name in _BUILTIN_PROFILES


def select_profile(contract: Contract, explicit: str | None, stage: str, environ: Mapping[str, str]) -> Profile:
    """The profile `profile_name` names, as `contract` defines it. Raises UnknownProfile."""
    name = profile_name(explicit, stage, environ)
    if name in contract.profiles:
        return Profile(name, contract.profiles[name], downgrade_only=False)
    if name in _BUILTIN_PROFILES:
        return Profile(name, _BUILTIN_PROFILES[name], downgrade_only=True)
    raise UnknownProfile(name, sorted({*_BUILTIN_PROFILES, *contract.profiles}))
