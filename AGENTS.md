# AGENTS.md

Guide for AI agents and contributors working on charter.

If `AGENTS.private.md` exists in this repository, read it before making changes — it contains maintainer process rules that override this file.

## What charter is

A Python CLI that validates, scaffolds and documents Markdown knowledge bases against a declared contract (`charter.yaml`). See `README.md`.

## Ground rules

- **Cross-platform, always.** charter must run identically on Windows, macOS and Linux. No shell scripts (`.sh`, `.ps1`) in the product or its plugin contract; anything that must run is Python or a plain argv command list.
- **The contract is the source of truth.** Behaviour that a knowledge base can configure belongs in `charter.yaml`, not in code special-cases.
- **Editor-agnostic.** No editor (Obsidian or otherwise) defines what is valid. Editor-specific behaviour lives in optional resolvers/plugins.
- **Built-in rules and external plugins share one diagnostics model.** A built-in check must be expressible through the same interface an external plugin uses.
- **Tests first.** Behaviour changes come with tests; fixtures are small invented knowledge bases under `tests/fixtures/`.
- **Commit per logical change.** One commit covers every file touched by that change; unrelated changes go in separate commits.

## File-system-specific tests

Some tests depend on how the file system treats names: letter case, Unicode normal form, names Windows cannot hold. A test that cannot run on the local file system skips itself, so a passing local run does not prove the other platforms pass. Reproduce them before pushing:

- **Case-insensitive macOS.** Create a case-insensitive volume and run the suite on it: `hdiutil create -size 1g -fs APFS -volname CIVOL /tmp/civol.dmg`, `hdiutil attach /tmp/civol.dmg`, then `TMPDIR=/Volumes/CIVOL/t uv run pytest --basetemp=/Volumes/CIVOL/bt`.
- **Linux** keeps NFC and NFD spellings apart: `docker run --rm -v "$PWD":/w -w /w ghcr.io/astral-sh/uv:python3.13-bookworm uv run pytest`.
- **Windows** has no local route; read the Windows jobs of the pull request's CI run.

When a scenario cannot exist on a platform, skip with a probe and a reason, following the existing `pytest.skip("this file system …")` and `pytest.skip("git on this system refuses the name …")` convention.
