# Changelog

Each release of charter has a section here, newest first. The section for a version is also the text of its GitHub release. Changes not yet released collect under "Unreleased".

## Unreleased

### Documentation

- The install command names `@main`, the branch that holds the latest release. [Install](docs/guide/Install.md) shows how to pin one release instead.
- [Plugins](docs/guide/Plugins.md) no longer describes the `needs: [body]` rule for linked notes as new. charter 0.2.0 already applied it.

## 0.2.1 - 2026-11-19

### Upgrade notes

- Upgrade the command line tool together with the plugin: `uv tool upgrade charter`. The plugin's new hooks run a `charter-hook` command. With an older command line tool, the contract guard is off without warning: Claude Code reports a hook error on each guarded call and goes on.

### Added

- **Zero-padded ids.** An `int` field takes `width: N`. Its value is written with at least `N` digits wherever it becomes text: the `{field}` part of a `path`, `matches_filename`, `{{field}}` in a template filled by `charter new`, and the id `charter sweep` looks for. Frontmatter keeps the number. See [Contract syntax](docs/guide/Contract-syntax.md).
- **The contract guard.** A contract opts in with `guard: true` under `agents:`. In Claude Code, the plugin's hooks (`hooks/hooks.json`) then stop a session from writing `charter.yaml` unless the human started Establish, Evolve or Migrate in that session. The hooks run the new `charter-hook` command. Establish offers to switch the guard on. See [The contract guard](docs/guide/Contract-guard.md).
- **`plugin/skipped-path`** (warning). A file whose name is not valid UTF-8 is left out of a plugin's request, and charter reports it under this code instead of failing the run.
- `charter describe --format json` has a `width` key on every field, and a top-level `guard` key (`true` when the contract guard is on) when it describes the whole contract.

### Changed

- **The user manual moved to `docs/guide/`**, one page per topic, and is mirrored to the repository's wiki. The README is now a short front page that links to it.
- `charter validate --range` no longer writes plugin files to disk. It reads each plugin's manifest and documentation from the commit it checks.
- A git failure while loading the contract for `charter validate --staged` or `charter plugin run --staged` is reported as `usage/git-failed` on `charter.yaml` (exit `2`).
- On Linux and macOS, when a plugin or other command charter runs exits, charter ends the child processes it left running.

### Documentation

- [Plugins](docs/guide/Plugins.md) now says that a `file`-scoped plugin must declare `needs: [body]` to get a linked note's `links`, `headings` and `tags`. Without it, those lists are empty and there is no error.
- The plain git hooks need a `python3` command on `PATH`. [Git hooks](docs/guide/Git-hooks.md) explains how to check this on Windows, where the python.org installer does not provide one, and how to fix it.
