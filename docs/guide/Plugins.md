# Plugins

A plugin is a check for rules only your knowledge base has, written in any language. It is a directory holding a `charter-plugin.yaml` manifest and the plugin's code; the contract enables it under its id with `source`, the directory relative to `charter.yaml` and beside or below it:

```yaml
checks:
  word-limit:
    source: tools/word-limit
    with: {max_words: 800}            # parameters, checked against the manifest's config_schema
```

```yaml
# tools/word-limit/charter-plugin.yaml
charter_plugin: 1
id: word-limit                        # the check id that enables it
version: 0.1.0
description: "Notes stay under a word limit."
requires: {charter: ">=0.1,<2"}       # optional; comparisons with >=, >, <=, <, ==, != joined by commas
run: ["uv", "run", "--script", "check.py"]
scope: file                           # optional; file = the targets and the notes they link to, vault (default) = every note
needs: [body, before]                 # optional; body = each note's body text, and the links, headings and tags of linked notes (see below); before = the earlier version of changed files
triggers: {kinds: [recipe], globs: ["Recipes/**"]}  # optional; run only when the run touches one of these
hook: true                            # optional; false = leave out of per-edit runs (`validate --file`)
timeout_ms: 10000                     # optional; 10 seconds by default
config_schema:                        # optional JSON Schema for `with`; without one, the plugin takes no parameters
  type: object
  properties: {max_words: {type: integer, minimum: 1}}
  required: [max_words]
docs: RULES.md                        # optional; Markdown rules shown by `charter describe` and in the rulebook
```

A plugin's `docs` file, relative to its directory and inside it, explains its rules in prose. `charter describe` and the rulebook end with a `# Plugin rules` section holding each enabled plugin's description and docs, for every plugin that has either. A leading front-matter block is left out of the rulebook: a first line of `---`, then only blank, `#` comment, `key: value`, `- item` or indented lines, then a closing `---` line (a `...` or indented closer is not recognised). Any other document, including one that opens with a thematic break, is left as written. Headings in the docs (`#` or underlined, indented up to three spaces, which they keep, or not, outside code and HTML comments) are moved down to sit below the plugin's own heading; Markdown has six heading levels, so any pushed deeper stay at level 6. `charter describe KIND` shows only the plugins that run for that kind (no `triggers`, or the kind among `triggers.kinds`). The check table lists enabled plugins after the built-in checks. The docs are read with any line endings and byte order mark, so the rulebook stays byte-identical on every platform, and editing them makes `charter docs --check` report the rulebook out of date.

`run` is a list of arguments, started without a shell in the plugin's directory, so a plugin runs the same on Windows, macOS and Linux. A command string is rejected, and so is a program that is a shell (`sh`, `bash`, `zsh`, `cmd`, `powershell`, `pwsh` and the like) or a script ending in `.sh`, `.ps1`, `.bat` or `.cmd`. The plugin gets charter's environment, with git's path variables made absolute: `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_COMMON_DIR` and each directory in `GIT_ALTERNATE_OBJECT_DIRECTORIES`. A git hook may set them relative to the top of the working tree, where they would name nothing from the plugin's directory. When only `GIT_DIR` is set, charter also sets `GIT_WORK_TREE` to the working tree git finds, so a plugin can run git on the repository from its own directory. Python plugins declare their dependencies inline ([PEP 723](https://peps.python.org/pep-0723/)) and run with `uv run --script`, which needs no setup step. The contract fails to load (exit `2`) when `source` leaves the directory holding `charter.yaml`, a manifest is missing or invalid, its `id` differs from the check's or is one of charter's own code namespaces (`contract`, `docs`, `files`, `index`, `init`, `new`, `plugin`, `snapshot`, `usage`), its `requires.charter` excludes the running charter, its `docs` file is missing or outside its directory, or `with` does not match `config_schema`. The manifest and `docs` file names match in letter case on every platform, as in git: `docs: rules.md` does not find a file `RULES.md`, even on a case-insensitive file system. A plugin with `enabled: false` is not read at all.

**Plugins run code.** `charter validate`, `charter new` and `charter plugin run` start enabled plugins' commands with your permissions, so only run charter on knowledge bases you trust, as you would their build scripts.

The plugin reads one JSON request on stdin and writes one JSON response on stdout, protocol `charter-plugin/1`. Paths in both are relative to the knowledge-base root (`root`):

```json
{
  "protocol": "charter-plugin/1",
  "charter_version": "0.2.1",
  "plugin": {"id": "word-limit", "version": "0.1.0"},
  "params": {"max_words": 800},
  "mode": "file",
  "root": "notes",
  "targets": ["Recipes/Bread.md"],
  "today": "2024-03-05",
  "index": {
    "notes": [
      {"path": "Recipes/Bread.md", "kind": "recipe", "variant": null, "frontmatter": {"kind": "recipe"},
       "links": [{"raw": "[[Flour]]", "target": "Ingredients/Flour.md", "field": null, "line": 9}],
       "headings": [{"level": 2, "text": "Method", "line": 12}], "tags": ["baking"],
       "body": "# Bread\n…"}
    ]
  }
}
```

```json
{"protocol": "charter-plugin/1",
 "diagnostics": [{"path": "Recipes/Bread.md", "line": 12, "severity": "error", "code": "word-limit/too-long",
                  "message": "The note has 950 words; the limit is 800.", "hint": "Split it into two notes."}]}
```

`targets` are the notes this run selected. `today` is the day the run judges as of, `YYYY-MM-DD`: the local date, or `CHARTER_TODAY` when set. Use it rather than the plugin's own clock, so the plugin agrees with charter. A `vault`-scoped plugin's `index` holds every note; a `file`-scoped plugin's holds the targets and the notes they link to, except on a whole run, which gives it every note too. `mode` says which it got: `file` or `vault`. A note's `body`, the text after its frontmatter, is there only when the manifest `needs: [body]`. `needs: [body]` also fills in the `links`, `headings` and `tags` of the notes a `file`-scoped plugin gets only because a target links to them. Without it those keys are there but empty, so charter does not have to read those notes' bodies. The targets, and every note of a `vault` run or a whole run, carry their `links`, `headings` and `tags` whatever the `needs`.

With `needs: [before]` the request also holds what the run's change did, as edit policies judge it (`--staged`: the staged change; otherwise the working copy since `HEAD`, for `--file` only the named files):

```json
"before": {"available": true, "reason": null,
           "files": [{"path": "Recipes/Bread.md", "status": "modified", "content": "---\nkind: recipe\n…"},
                     {"path": "Recipes/Rolls.md", "status": "added", "content": null}]}
```

`files` lists every file under the root, other than ignored ones, that the change added, modified (a permission change included) or deleted, sorted by path; `content` is the file's text before the change, with line endings normalised to `\n`, and `null` for an added file or one that is not UTF-8 text. Where there is no earlier version, `available` is `false`, `files` is empty and `reason` says why (outside a git repository, say).

Every path in the request is valid UTF-8. A file whose name is not valid UTF-8 (git, and file systems such as Linux's, accept any bytes) is not sent: it is left out of `targets`, `index` and `before`, and the other files of the run are still sent. charter reports each such file as `plugin/skipped-path` (warning) on the file, naming the plugin, with each byte that is not valid UTF-8 written as `\xNN`. `checks.<id>.severity` and profiles adjust it as they do the plugin's own diagnostics. `--dump-input` leaves out the same files. `globs` and `kinds` in `triggers` match only the files the plugin would be sent: a glob or a kind that matches nothing but such a file does not start the plugin, and charter still reports the file as `plugin/skipped-path`. To have the plugin check the file, rename it to a valid UTF-8 name. A `Charter-Allow` trailer cannot name such a file either, as the escaped form is not its real name.

`triggers` keep a plugin from running when a run doesn't concern it: it runs when the run touches one of its `kinds` (every kind on a whole run) or targets a note whose root-relative path matches one of its `globs`. Each of `kinds` must be a kind the contract declares (a variant name is not a kind), or the contract is in error. Without `triggers` it always runs; `triggers` naming no kinds and no globs is a contract error. A plugin with `hook: false` is left out of per-edit runs, `charter validate --file` and `charter new`, so a slow or whole-vault check doesn't stall a per-edit run or an agent; whole runs include it. A file-scoped plugin's index on `validate --file charter.yaml` is empty, as no note is targeted.

`charter plugin run <id>` runs one plugin on its own, whatever its triggers and hook say, and reports its diagnostics; it takes `validate`'s `--all`, `--file`, `--staged`, `--format`, `--profile` and `--strict`. With `--dump-input` it writes the exact request the plugin would receive to stdout instead of running it, so you can replay it against the plugin while developing; it then takes no `--format` (the request is always JSON), `--profile` or `--strict`.

A diagnostic's `line` and `hint` may be omitted or `null`, and its `code` starts with the plugin's id. Plugin diagnostics join the others: `checks.<id>.severity` and profiles (by the plugin's id or one of its codes) adjust them as for built-in checks. Paths must be POSIX and inside the root. A plugin that exits non-zero, outlives `timeout_ms`, writes more than 16 MB, writes something other than a valid response, or answers with another protocol is reported as `plugin/failed` on its `checks` entry, with the end of its stderr, and charter exits `3`; `charter new` then writes nothing. No severity setting or profile turns that off; `enabled: false` does. The same goes for a plugin that `validate --staged` (or `plugin run <id> --staged`) cannot write out of the index to a temporary directory, for example on a full disk or because of a file name the file system refuses: it is reported as `plugin/failed` naming the cause, and everything else is still judged. A plugin file that git itself cannot read from the index, such as a missing object, is a usage error instead (`usage/git-failed`, exit `2`). `validate --range` does not run plugin checks, so it does not write plugins out either: it reads each commit's plugin manifests and `docs` files from git, and a broken manifest is still an invalid contract in that commit.

## Installing plugins from git

```
charter plugin add --from https://example.com/word-limit.git@v1.0.0
```

`charter plugin add --from <git-url>@<ref>` fetches the plugin at a branch, tag or commit and copies it into `.charter/plugins/<id>/`, named after its manifest's `id`. The plugin's manifest must be at the root of the repository. The ref follows the last `@` after the URL's host, so `https://user@host/repo.git` alone has no ref and is refused. git runs without prompting for credentials or host keys, and gives up after 10 minutes. Commit that directory: CI and everyone else then run the plugin without fetching anything. `add` enables the plugin as `checks.<id>` in `charter.yaml`, written in the contract's own style and leaving the rest as it was, and records it in `charter.lock`:

```yaml
# Written by `charter plugin`; do not edit by hand.
charter_lock: 1
plugins:
  word-limit:
    version: 1.0.0
    source:
      git: https://example.com/word-limit.git
      ref: v1.0.0
      commit: 3f1c…            # what the ref pointed at when added
    sha256: 9f2c…              # of the installed directory's contents
```

`validate`, `new` and `plugin run` refuse to run a locked plugin whose directory no longer matches its `sha256`, so what runs is what was reviewed: it is reported as `plugin/modified` on its `checks` entry, and charter exits `3`, whatever the profile. A symbolic link in the directory is reported the same way, naming the link, in the working copy and, for `validate --staged`, in the index (found by its entry mode, not from the files written out for the plugin). The lock covers only plugins in `.charter/plugins/<id>`: a check whose `source` is elsewhere is a local-path plugin, and it is not checked against the lock. In a lock entry, `commit` is optional, and charter ignores keys it does not know, so a lock written by a later charter still loads. Adding a locked plugin again replaces it, from the same or another ref. `add` refuses a plugin whose manifest is invalid, whose `id` is a built-in check or one of charter's namespaces, that holds a symbolic link (`plugin/symlink`; a link reads differently on each OS and may point outside the plugin), or whose `checks.<id>` or directory already exists without being in the lock. If the plugin takes parameters, `add` installs it and then reports that `checks.<id>.with` must still give them (exit `1`).

When the plugin holds a Python file, `add` also makes sure `.gitignore` (beside `charter.yaml`) ignores `__pycache__/`, appending the line only if it is missing, in the file's own line endings.

`--dev <path>` installs a plugin's working copy instead, for developing it against a real knowledge base: the directory is copied as it is, without `.git` or `__pycache__`, and the lock records `source: {dev: true}` with the copy's `sha256`. Run `charter plugin add --dev <path>` again to refresh the copy after changing the working copy.

The `sha256` is the same on Windows, macOS and Linux, however git checked the files out. It is the SHA-256 of one line per file, in path order: the file's path relative to the plugin directory (POSIX separators, Unicode NFC), a NUL byte, the hex SHA-256 of its content, and a line feed. Content counts CRLF as LF in any file with no NUL byte in its first 8000 bytes (git's own test for binary), since `core.autocrlf` and `eol` attributes may convert line endings on checkout. A symbolic link anywhere in the directory makes it a mismatch. File modes, empty directories, and anything named `.git` or `__pycache__` are left out, so bytecode a Python plugin leaves behind is not a modification.

## Managing plugins

Every step of a plugin's life is a command, so nobody edits `.charter/plugins/` or `charter.lock` by hand:

```
charter plugin list                        # each plugin: version, enabled or disabled, source
charter plugin info word-limit             # one plugin: source and commit, lock state, manifest
charter plugin update word-limit --ref v1.1.0
charter plugin disable word-limit
charter plugin enable word-limit
charter plugin remove word-limit
```

- `list` and `info` show every `checks.<id>` with a `source`, enabled or not, and every plugin in `charter.lock`. They take `--format json`. `info` also says whether an installed plugin's directory still matches its `sha256`, and what is wrong with a manifest it cannot read.
- `update <id>` fetches a plugin installed with `--from` again, at the ref it was installed from (picking up new commits on a branch) or at `--ref`, replaces its directory, and rewrites its lock entry, both or neither. It leaves `charter.yaml` as it is, so a disabled plugin stays disabled. The ref must hold the same plugin `id`. Updating also restores a directory that no longer matches the lock. A plugin installed with `--dev` is refreshed with `charter plugin add --dev` instead, and one used in place from its `source` has nothing to update.
- `enable <id>` and `disable <id>` set `checks.<id>.enabled`. `enable` on a plugin in the lock that has no `checks.<id>` adds that entry again.
- `remove <id>` removes `checks.<id>` and, for a plugin charter installed, its directory and lock entry. Either all of these change or none do; if a write fails and something cannot be put back, the error says where the previous plugin directory was kept. `checks:` goes too when the plugin was its only entry. Settings elsewhere that name the plugin, such as profile entries, stay and are reported if they no longer apply. `charter.lock` stays, as `plugins: {}`, after its last plugin is removed. The directory of a plugin used in place is left where it is.
- When `add`, `update` or `remove` fails part-way, its rollback puts `charter.yaml` and `charter.lock` back only while each still holds what that command wrote. If someone edited one meanwhile, it is left as edited and the error names it (`plugin/write-failed`).
- `add`, `update` and `remove` refuse, changing nothing, a plugin that `charter.lock` lists while `checks.<id>.source` points anywhere but `.charter/plugins/<id>` (`plugin/source-mismatch`): charter runs it from that other place, so the vendored copy is not the one in use. The message names the recorded and the expected `source`; edit `source` back, or delete the lock entry by hand. `add` also needs a contract that loads, so a `source` that makes it invalid (a missing directory, an absolute path) is reported as `contract/invalid`, exit 2, before anything is changed. A check with another `source` that the lock does not list is a plugin used in place and is handled as before.

These commands edit `charter.yaml` the way `add` does: in its own style, leaving everything else as it was, or not at all. They need only `checks:` and the lock to be valid, so you can still disable, update or remove a plugin that made the rest of the contract invalid. Afterwards they report anything the contract still needs, and exit `1` if it needs something.
