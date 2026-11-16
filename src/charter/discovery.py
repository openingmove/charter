"""Finding the contract by searching upward, as git finds `.git`.

Every command that works on a knowledge base goes through here when `--config` is not given. Commands that
legitimately run without a contract (`init`, which writes one) skip it.
"""

import os
from collections.abc import Iterable
from pathlib import Path

from charter.contract import CONTRACT_FILENAME
from charter.diagnostics import Diagnostic, Severity

NO_CONTRACT = "contract/not-found"
MIXED_CONTRACTS = "usage/mixed-contracts"


def find_upward(start: Path, filename: str) -> Path | None:
    """The nearest file called `filename` in `start` or any folder above it, up to the filesystem root."""
    # Lexical, not resolved, so a symlinked checkout keeps the paths the user typed.
    folder = Path(os.path.abspath(start))
    for candidate in (folder, *folder.parents):
        found = candidate / filename
        if found.is_file():
            return found
    return None


def find_contract(start: Path) -> Path | None:
    """The nearest `charter.yaml` in `start` or any folder above it, up to the filesystem root."""
    return find_upward(start, CONTRACT_FILENAME)


def discover(files: Iterable[Path] | None = None) -> Path | list[Diagnostic]:
    """The contract for a run: searched upward from the working directory, or from the folders of `files`.
    Files that resolve to different contracts cannot be one run, so that is reported instead."""
    if not files:
        return find_contract(Path.cwd()) or [_none_found("in the working directory or any folder above it")]
    found = {file: find_contract(file.parent) for file in files}
    missing = [file for file, contract in found.items() if contract is None]
    if missing:
        return [_none_found(f"in any folder above `{file.as_posix()}`", file) for file in missing]
    contracts = set(found.values())
    if len(contracts) > 1:
        return [_mixed(file, contract) for file, contract in found.items()]
    return contracts.pop()


def _none_found(where: str, file: Path | None = None) -> Diagnostic:
    return Diagnostic(
        file.as_posix() if file else CONTRACT_FILENAME,
        None,
        Severity.ERROR,
        NO_CONTRACT,
        f"No `{CONTRACT_FILENAME}` found {where}.",
        "Run `charter init <folder>` to create a contract, or pass `--config PATH` to name one.",
    )


def _shown_relative_to_cwd(path: Path) -> str:
    """`path` as POSIX text relative to the working directory (`../x` when not below it). A path typed
    relative stays as typed. Absolute only when no relative form exists, e.g. another Windows drive."""
    if not path.is_absolute():
        return path.as_posix()
    # `Path.cwd()` is the resolved directory while a typed path is lexical (macOS /tmp -> /private/tmp), so try
    # lexical and resolved forms of both and keep the shortest.
    bases = {Path.cwd(), Path(os.path.realpath(Path.cwd()))}
    pwd = os.environ.get("PWD")
    if pwd and os.path.isabs(pwd) and os.path.realpath(pwd) == os.path.realpath(Path.cwd()):
        bases.add(Path(os.path.abspath(pwd)))
    forms = []
    for target in {path, Path(os.path.realpath(path))}:
        for base in bases:
            try:
                forms.append(Path(os.path.relpath(target, base)).as_posix())
            except ValueError:  # another drive on Windows: no relative form
                continue
    return min(forms, key=lambda form: (form.split("/").count(".."), len(form)), default=path.as_posix())


def path_under_contract(file: Path) -> str | None:
    """`file` in diagnostic form (relative to the folder of the contract found above it), or None when no
    contract is found. Mirrors `Contract.path_of`, but without loading the contract, so it never raises."""
    try:
        contract = find_contract(Path(os.path.abspath(file)).parent)
        if contract is None:
            return None
        # A link back to the contract folder (`x/link -> x`) makes the nearest contract `x/link/charter.yaml`;
        # `--config x/charter.yaml` would show `link/...`, so take the outermost folder holding the same file.
        for outer in contract.parent.parents:
            if (outer / CONTRACT_FILENAME).is_file() and (outer / CONTRACT_FILENAME).samefile(contract):
                contract = outer / CONTRACT_FILENAME
        for candidate in (Path(os.path.abspath(file)), file.resolve()):
            if candidate.is_relative_to(contract.parent):
                return candidate.relative_to(contract.parent).as_posix()
    except (OSError, RuntimeError, ValueError):
        pass
    return None


def _mixed(file: Path, contract: Path) -> Diagnostic:
    # Both paths share one base: the working directory, which the user typed the file relative to.
    shown = _shown_relative_to_cwd(file)
    return Diagnostic(
        shown,
        None,
        Severity.ERROR,
        MIXED_CONTRACTS,
        f"`{shown}` belongs to the contract `{_shown_relative_to_cwd(contract)}`; the files named do not share one contract.",
        "Validate the files of each knowledge base separately, or pass `--config PATH` to choose one contract.",
    )
