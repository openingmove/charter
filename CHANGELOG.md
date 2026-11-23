# Changelog

Each release of charter has a section here, newest first. The section for a version is also the text of its GitHub release. Changes not yet released collect under "Unreleased".

## Unreleased

### Changed

- `charter validate --file` now takes a file deleted from the working copy that git still tracks, in the index or in `HEAD`, and judges the deletion as `--staged` does: under the edit policies, and against the kind the note had, so a gap it leaves in a `contiguous` collection is reported. An editor or agent hook can now report the deletion of a protected file (`paths/read-only`, `paths/create-only`). A missing path that git does not track, and any missing path outside a git repository, is still `usage/file-not-found` (exit `2`). See [Validating](docs/guide/Commands.md#validating).
- When `charter-hook` crashes, it prints one line, `charter-hook EVENT: ERROR`, instead of a traceback, and exits `1`. Claude Code reports a hook error and goes on. It never exits `2`, which would block the call.
- Establish checks, before it asks for approval, that every kind the migration plan will create notes for has a `path`. Migrate creates those notes with `charter new`, which cannot create a note of a kind with no path. Establish tells the human about each such kind.
- Establish tells the human that a file which is only ever appended to cannot stay in a folder under `edit: create-only` or `edit: read-only`: the file must move out of that folder.
- `charter plugin list` and `validate` now warn about a `.charter/plugins/.staging-*` folder that an interrupted `charter plugin add`, `update` or `remove` left behind (`plugin/leftover-staging`). Its `previous/` may hold the only copy of a plugin's previous directory. The warning goes to stderr and names the folder; output and exit code are unchanged. charter never deletes the folder: check it, then delete it yourself. See [Plugins](docs/guide/Plugins.md).

### Fixed

- A plugin's manifest and `docs` file names now match in letter case in every `validate` mode, as they already did under `--range`. On a case-insensitive file system (macOS, Windows), `docs: rules.md` found a file `RULES.md` in a plain or `--staged` run. Such a reference is now `contract/invalid`, as under `--range`. `charter plugin add`, `update`, `list` and `info` now also refuse a plugin whose manifest file name differs in letter case. A name still matches a file that differs only in Unicode form (NFC or NFD). See [Plugins](docs/guide/Plugins.md).
- The contract guard no longer lets an `mv` of a guarded `charter.yaml` through when charter cannot check the target, for example an overlong name or the home folder of an unknown user (`~nosuchuser`).
- The contract guard now fails closed. A `charter.yaml` whose guard charter cannot read, such as YAML nested too deep to parse, counts as guarded. A call that names `charter.yaml` but that charter cannot split or resolve is denied, with a reason that says charter could not check it. An error on one file no longer hides a guarded contract elsewhere in the same command. See [The contract guard](docs/guide/Contract-guard.md).
- The contract guard no longer lets a write to a guarded `charter.yaml` through when it cannot check for the session's marker, for example because the state folder cannot be read or the session id cannot be encoded. It denies the call, with a reason that names the error. A call that writes no guarded contract is never blocked by a file system error. See [The contract guard](docs/guide/Contract-guard.md).
- A plugin run from a git hook can now use git. A hook can set `GIT_DIR`, `GIT_INDEX_FILE` and the other git path variables relative to the top of the working tree, and the plugin got them unchanged, so from its own directory they named nothing. charter now gives the plugin these variables as absolute paths, and sets `GIT_WORK_TREE` when only `GIT_DIR` is set. See [Plugins](docs/guide/Plugins.md).
- A plugin triggered by `kinds` no longer starts, with no targets, when the only staged note of that kind has a name that is not valid UTF-8. charter still reports `plugin/skipped-path` for that note. See [Plugins](docs/guide/Plugins.md).
- A plugin that holds symbolic links now gets one `plugin/modified` that names every link, instead of one per link. Its hint now matches `charter plugin add`: ask the plugin's author to replace the link with the file it points to. Reinstalling the plugin would be refused for the same reason. A link no longer hides other changes: when the plugin's files also differ from its `sha256` in another way, a second `plugin/modified` reports the mismatch. A link that takes the place of a locked file also counts as a mismatch, because the file is missing from the hash. See [Plugins](docs/guide/Plugins.md).
- A file that the OS or a tool drops into a vendored plugin no longer makes it `plugin/modified`. charter now leaves `.DS_Store`, `Thumbs.db`, `desktop.ini`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.venv` and `venv` out of a plugin's `sha256`, as it already did `.git` and `__pycache__`. `charter plugin add --dev` no longer copies them. The `sha256` of a plugin that holds none of these names does not change. See [Plugins](docs/guide/Plugins.md).
- A modified or unavailable plugin whose trigger matches only a path that is not valid UTF-8 now reports `plugin/modified` or `plugin/failed`, as it does when its trigger matches a path it would be sent. See [Plugins](docs/guide/Plugins.md).

### Documentation

- [The contract guard](docs/guide/Contract-guard.md) names the marker file it writes for a session: `sessions/<sha256 of the session id>.json` in the per-user state folder.

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
