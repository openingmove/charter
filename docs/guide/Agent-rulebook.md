# The agent rulebook

charter works without any of this. A contract that declares neither `docs:` nor `agents:` is a standalone knowledge base: `charter docs` is a usage error (exit `2`) telling you to declare one, nothing is generated, and no agent file is expected.

`charter docs` writes the whole description to a rulebook file for agents to read at the start of every session, under a "generated — do not edit" header and a "Working here" workflow addressed to whoever edits a note: read the rules, create notes with `charter new`, run `charter validate --file` after each edit, run `charter sweep` before changing a fact, never change the contract to make a note pass (stop and tell the human, who may run the Evolve skill), never add a `Charter-Allow:` trailer unless the human asks, and the contract wins over other guidance about a document. A `docs:` section turns the rulebook on by itself; an `agents:` section turns on the agent layer, which implies the rulebook at its default path. Point your agent-instruction file at it:

```yaml
agents:
  file: AGENTS.md            # must link to the rulebook (default: AGENTS.md)
docs:
  output: CHARTER.md         # the generated rulebook (default: CHARTER.md)
```

Both paths are relative to `charter.yaml`, beside or below it. `agents.file` is the one file that must point at the rulebook; it is not the same as `agent_files:`, the list of filenames (default `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) that need no kind wherever they sit. Entries are bare file names matched at any depth; one containing `/` or `\` fails at load with `contract/invalid`, and a specific path takes an `untyped: allow` path policy instead. The rulebook and `agents.file` need no kind either, and links to them resolve even when they sit outside `root`, like any file beside or below `charter.yaml` (see [Links](Contract-syntax.md#links)).

```
charter docs                 # write the rulebook (left untouched when already up to date)
charter docs --check         # write nothing; exit 1 if the rulebook is missing or out of date (CI)
charter docs --link-agents   # also add one line importing the rulebook to agents.file, creating the file if missing, and a CLAUDE.md beside it importing it where a CLAUDE.md exists at or above (needs `agents:`; exit 2 without it)
charter docs --check --link-agents   # link, then check, without writing the rulebook
```

The rulebook is always written with LF line endings and in contract order, so it is byte-identical on every platform; `--check` ignores line endings, so a checkout with CRLF endings still counts as up to date. `--link-agents` is the one command that edits a file you wrote: it adds a single line (`read @CHARTER.md before creating or editing any note here`), in the file's own line endings, only when the file does not point at the rulebook yet, and changes nothing else. Where a `CLAUDE.md` exists in the knowledge-base folder or any folder above it, Claude Code ignores `AGENTS.md`, so it also creates or extends a `CLAUDE.md` beside `agents.file` holding `@AGENTS.md`; it never creates a `CLAUDE.md` where none exists at or above. "Above" means every folder up to the filesystem root, as Claude Code loads ancestor `CLAUDE.md` files, so a stray `CLAUDE.md` far above the repository counts. A file write that fails is reported as `docs/write-failed` (exit `1`).

The `agents-include` check is on only when the contract declares `agents:`. A contract whose `agents.file` and `docs.output` name the same file, however the path is spelled, fails to load (`contract/invalid`). The check reports a missing or unreadable `agents.file`, including a folder at that path (`agents-include/missing-file`; `charter docs --link-agents` reports the same code and exits `1`, leaving that path untouched, but has already written the rulebook, while with `--check` nothing is written), one that does not point at the rulebook (`agents-include/missing-link`), and a missing or out-of-date rulebook (`agents-include/stale`). Any of these, outside code, points at the rulebook, whatever `links.styles` says: an inline link `[rules](CHARTER.md)`, a reference definition `[rules]: CHARTER.md`, `<CHARTER.md>`, or an import line `@CHARTER.md`. Without `agents:` the check is off and agents are never mentioned: a missing or out-of-date rulebook (`docs:` declared, no `agents:`) is `docs/stale` instead, and `charter docs --check` exits `1` for it.
