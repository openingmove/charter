"""The `agents-include` check: agents find the generated rulebook, and it matches the contract."""

import posixpath
import re
from collections.abc import Iterator
from urllib.parse import unquote

from charter.checks import CheckRequest
from charter.contract import AGENTS_INCLUDE, Contract
from charter.diagnostics import Diagnostic, Severity
from charter.links import body_links
from charter.prose import blank_code_blocks, split_literals

MISSING_FILE = "agents-include/missing-file"
MISSING_LINK = "agents-include/missing-link"
STALE = "agents-include/stale"

# Ways an agent-instruction file points at a file besides an inline link: a reference definition
# (`[x]: CHARTER.md`), an autolink-style `<CHARTER.md>`, and Claude's `@CHARTER.md` import.
_REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*(<[^<>\n]*>|\S+)", re.MULTILINE)
_ANGLED = re.compile(r"<([^<>\s]+)>")
_IMPORT = re.compile(r"(?:^|(?<=\s))@(\S+)")


class AgentsIncludeCheck:
    id = AGENTS_INCLUDE
    codes = frozenset({MISSING_FILE, MISSING_LINK, STALE})

    def run(self, request: CheckRequest) -> Iterator[Diagnostic]:
        contract = request.contract
        # Even an explicit `enabled: true` has nothing to check without the agent layer.
        if not contract.agent_layer_on:
            return
        whole = contract.file in request.targets
        # Each problem is reported on its own file, so a run that names neither file judges neither: generating the
        # rulebook to compare is the costly part of a per-edit run.
        if whole or contract.agents_file in request.targets:
            if (problem := agents_problem(contract)) is not None:
                yield problem
        if whole or contract.docs_output in request.targets:
            # Deferred: the rulebook lists the built-in checks, this one among them.
            from charter.docs import staleness

            if (problem := staleness(contract)) is not None:
                yield problem


def agents_problem(contract: Contract) -> Diagnostic | None:
    """Why agents reading `agents.file` would not find the rulebook; None when it links to it."""
    agents_file, output = contract.agents_file, contract.docs_output
    if not contract.tree.exists(agents_file):
        return _agents_diagnostic(
            contract,
            MISSING_FILE,
            f"`{agents_file}` does not exist, so agents are not pointed at `{output}`.",
            f"Run `charter docs --link-agents` to create it pointing at `{output}`.",
        )
    text = agents_text(contract)
    if text is None:
        return unreadable_diagnostic(
            agents_file, f"`agents.file` names the text file agents read first; it must link to `{output}`."
        )
    if links_rulebook(contract, text):
        return None
    return _agents_diagnostic(
        contract,
        MISSING_LINK,
        f"`{agents_file}` does not link to `{output}`.",
        "Run `charter docs --link-agents` to add the line that imports it.",
    )


def _agents_diagnostic(contract: Contract, code: str, message: str, hint: str) -> Diagnostic:
    return Diagnostic(contract.agents_file, None, Severity.ERROR, code, message, hint)


def agents_text(contract: Contract) -> str | None:
    """The agents file's text; None when it is not a readable file."""
    content = contract.tree.read([contract.agents_file]).get(contract.agents_file)
    return None if content is None else decode_agent_text(content)


def decode_agent_text(content: bytes) -> str:
    """An agent file's text as an agent reads it: BOM dropped, undecodable bytes replaced."""
    return content.decode("utf-8-sig", errors="replace")


def unreadable_diagnostic(path: str, hint: str) -> Diagnostic:
    """The report for an agent file path held by something that is not a readable text file."""
    return Diagnostic(path, None, Severity.ERROR, MISSING_FILE, f"`{path}` is not a readable file.", hint)


def links_rulebook(contract: Contract, text: str) -> bool:
    """Whether the agents file's text points at the rulebook, in any syntax an agent follows, outside code."""
    return points_at(text, contract.agents_file, contract.docs_output)


def points_at(text: str, source: str, target: str) -> bool:
    """Whether `text`, the content of `source`, points at `target` (both POSIX, relative to one folder), outside code."""
    prose, _, _ = split_literals(blank_code_blocks(text.splitlines()))
    folder = posixpath.dirname(source)
    for destination in _destinations(prose):
        resolved = posixpath.normpath(posixpath.join(folder, destination))
        # As in the knowledge base, a Markdown link may leave out `.md`.
        if destination and target in (resolved, f"{resolved}.md"):
            return True
    return False


def _destinations(prose: list[str]) -> Iterator[str]:
    yield from (link.name for link in body_links(prose, 1, ("markdown",)))
    text = "\n".join(prose)
    for pattern in (_REFERENCE, _ANGLED, _IMPORT):
        for match in pattern.finditer(text):
            yield unquote(match.group(1).removeprefix("<").removesuffix(">").partition("#")[0])
