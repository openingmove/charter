# Commands

## Starting a contract

To start, run `charter init [FOLDER]`. FOLDER is where the contract goes (default: the current folder; it is created if missing). By default it writes one file and nothing else:

- `FOLDER/charter.yaml`, a minimal contract with `root: .`, comments explaining kinds, fields and paths, and an example kind to uncomment. It declares no `agents:` or `docs:` section, so charter works standalone: `validate`, `new`, `describe`, `sweep` and plugins need nothing more. `charter init` does not look for a contract above FOLDER.

Layers are switches, off until you ask (see [The agent rulebook](Agent-rulebook.md)):

- `--from DRAFT` installs an approved draft contract in place of the starter, byte for byte, keeping its own `root:`. A draft that does not load is refused with exit `2` and nothing is written.
- `--agents` adds the `agents:` and `docs:` sections the contract lacks (appended at the end, as text: the draft's comments, order and line endings stay as written; sections it already declares are not repeated), writes `CHARTER.md`, the rulebook generated from it, and links it from `AGENTS.md` the way `charter docs --link-agents` does (creating the file if needed, otherwise only appending one line; a `CLAUDE.md` beside it where one exists at or above). The two combine: `charter init FOLDER --from DRAFT --agents`.

`charter init` writes no `.gitignore`: the `__pycache__/` entry for the bytecode Python plugins leave behind is added by `charter plugin add`, the first time it vendors a Python plugin (once only, keeping the file's lines and line endings).

A freshly initialised knowledge base passes `charter validate`. `charter init` never overwrites anything: it checks every file first and refuses (exit `1`), listing every problem and writing nothing, if `charter.yaml` already exists, FOLDER is a file, or, with `--agents`, `CHARTER.md` already exists or `AGENTS.md` or `CLAUDE.md` is something it cannot add to (`init/exists`, `init/no-folder`, `init/not-writable`). If a write still fails partway (`init/write-failed`), it undoes what it wrote, so you can fix the cause and run it again. A missing or unloadable draft is a usage error (`init/bad-draft`, or the contract's own `contract/*` diagnostics, exit `2`). After editing the contract of an `--agents` knowledge base, run `charter docs` to bring `CHARTER.md` up to date.

## Validating

Then, from the directory holding `charter.yaml` or any folder below it (charter searches upward for the nearest `charter.yaml`, as git does for `.git`; `--file` searches from the named files' folders, and files that resolve to different contracts are a usage error):

```
charter validate                  # human-readable, grouped by file
charter validate --format json    # stable machine-readable output
charter validate --format agent   # one compact line per diagnostic
charter validate --config path/to/charter.yaml
charter validate --file docs/Books/Dune.md   # only these files (per-edit mode, quick enough to run after each edit)
charter validate --staged         # what is staged in git (for a pre-commit hook)
charter validate --staged --commit-msg .git/COMMIT_EDITMSG   # its edit policies (for a commit-msg hook)
charter validate --staged --commit-msg-installed   # the same, without the infos that edit policies wait for the commit-msg hook (for a pre-commit hook that has one)
charter validate --range origin/main..HEAD   # edit policies, updated-date and protected-region of each commit in a range (for CI)
charter validate --strict         # warnings fail too
```

`--file` takes existing files, relative to the working directory or absolute. It also takes a file deleted from the working copy that git still tracks, in the index or in `HEAD`, and judges the deletion as `--staged` does: an edit policy that covers it reports it as deleted, and a deleted note touches the kind it had in `HEAD`, so a gap it leaves in a `contiguous` collection is reported. A missing path that git does not track, a folder, or any missing path outside a git repository is a usage error (`usage/file-not-found`, exit `2`).

`--staged` checks exactly what the next commit would hold, so unstaged scratch edits neither block nor mask it. It leaves edit policies to `--staged --commit-msg`, which a commit-msg hook runs once the message, with any `Charter-Allow` trailers, exists (see [edit policies](Edit-policies.md)). It targets the staged files and reads everything from git's staged content rather than the working copy: the notes, `charter.yaml`, its templates, the rulebook, the agents file, `charter.lock` and the plugins, which run from a temporary copy of their staged files and are checked against the staged lock. Files that are not staged, untracked ones included, are not part of the knowledge base it sees. A staged symbolic link to a file in the knowledge base reads as that file, as in a checkout; other links are left out. Deleting a note, or changing its kind, touches the kind it had, so a staged change that leaves a gap in a `contiguous` collection is reported. Content that git stores through a filter, such as Git LFS, is seen as git stores it (the pointer file), not as checked out. `--staged` needs `charter.yaml` staged; outside a git repository, or with the contract unstaged, it is a usage error (exit `2`).

`--range A..B` is for CI: it reaches the verdict the commit-msg hook reached, or would have, when each commit was made. It needs git 2.25 or newer (the end of this paragraph says why). It checks only edit policies and, when enabled, `updated-date` and `protected-region` (run `charter validate --all` for the rest), for each commit B has and A has not, oldest first, against that commit's parent, honouring the `Charter-Allow` trailers of that commit's message and no other's. So a trailer in one commit never excuses a violation in another, and a later commit that restores a protected file does not clear the commit that changed it: the fix is to rewrite that commit, or reword its message to add a trailer. Each commit is judged by the `charter.yaml` it holds itself, as the hook judged it by the staged contract; a commit without one, whose parent had none either, is skipped, as charter did not govern it. Its `root` must be a folder holding a file in that commit (or in the index, under `--staged`): a root with no files is reported as such, and a root that is a symlink is reported as a link a commit cannot follow, both exit `2`; those two messages describe the working copy, not the commit being checked. A commit whose contract is invalid, or that deletes the contract its parent had (`usage/contract-deleted`), is a usage error naming it (exit `2`). A `--profile` (or `CHARTER_PROFILE`) that is not built in must be declared in the contract of every commit judged. A merge commit is judged only on the files it leaves unlike every parent, such as a conflict resolution, against its first parent: the rest were changed, and judged, in the commits it merges; a file it changes that any parent has counts as changed, not added. A root commit has no parent to compare with, so it gets a `paths/edit-skipped` info (and `updated-date/skipped` or `protected-region/skipped`, when those checks are on). Diagnostics name the commit by git's abbreviated id. An empty side means `HEAD` (`origin/main..` is `origin/main..HEAD`); `A...B`, or anything other than two commits joined by `..`, is a usage error (`usage/invalid-range`, exit `2`), as is `--range` outside a git repository. A range with no commits is clean. For `updated-date`, "today" is the day the commit was authored, in its author's time zone, whatever the clock or `CHARTER_TODAY` says. So a note edited twice on one day passes in CI on any later day. The author date survives a rebase, cherry-pick or amend, and a "rebase and merge", which all reset the commit date, so a commit is judged as of the same day after them. One edge remains: the pre-commit hook judges the change a moment before git stamps the author date, so a commit made across midnight can be judged a day later in CI than by its hook. Fix it by setting the date to the day CI names and amending the commit (through `git rebase -i` if it is not the last one), which keeps its author date. `--range` needs git 2.25 or newer: it reads each author date with the `%as` placeholder, which older versions print as written, and charter then stops with `usage/git-failed`.

`--range` needs the history it compares: in a shallow clone, a range whose start, or a parent of one of its commits, is missing is a usage error (`usage/shallow-history`, exit `2`), never a silent pass. With GitHub's `actions/checkout`, set `fetch-depth: 0`. For a pull request, check `<base sha>..<head sha>`; for a push, `<before>..<after>` (`github.event.before`..`github.sha`). A push that creates a branch has an all-zero `before`, which charter rejects with a hint: check `origin/<default branch>..<after>` instead.

## Creating notes

`charter new` writes a note at the path its kind renders, with frontmatter in contract order and the template body:

```
charter new recipe "Soda Bread" --set method=bake      # --set method=bake selects the `bread` variant
charter new recipe/bread "Soda Bread"                  # or name the variant: its `set` values are filled in
charter new recipe "Soda Bread" --set tags=quick --set tags=easy   # a list field takes one element per --set
charter new recipe "Soda Bread" --dry-run              # check and report, write nothing
charter new recipe "Soda Bread" --format agent         # compact output
```

- The title goes to the kind's `title` field (or its one `matches_filename` field). `--set FIELD=VALUE` gives any other field; the value is read as the field's type (`--set id=7` is a number, text fields stay text). Fields not given take their `default` or `auto` value; a variant named with `kind/variant` fixes its `set` values (or its `variant_by` value).
- The template's `{{placeholders}}` are filled from the note's values and `{{date}}` with today; placeholders without a value stay for the author. The printed outline's headings are filled with the same values, `{{date}}` included.
- The note is validated in memory with the same checks as `charter validate`, at base severities apart from `residue` (a new note keeps its template's guidance), and written only if no error is found. Warnings are printed after the note is created.
- Every reason to refuse is reported at once: each required field without a value (with its type and allowed values, at its declaration in `charter.yaml`), an `auto: next` field with no free value, a path that already exists (`new` never overwrites a file), that a `paths:` policy ignores, or that lies under `edit: read-only` (`paths/read-only`, worded as `validate` words it for a file added there; the whole target path is tested, a folder built from the title included, and it needs no git history, so it holds with `--dry-run` and outside a git repository), a kind without `path`, and whatever the checks find. A note whose path cannot be rendered is checked where its pattern stands (`docs/Zones/{title}.md`), so a value that cannot be part of a path is reported alongside the note's other problems.
- A write that fails (`new/write-failed`, or `new/name-too-long` when the file system rejects the name's length) leaves no file or new folders behind.
- `--dry-run` checks the name's length only when the note's target folder already exists, because the file system reports a missing folder before it looks at a name's length; the real run still refuses with `new/name-too-long` and writes nothing.
- On success `new` prints the created path and the template's section outline. Refusals exit `1`; an unknown kind or variant, or a malformed `--set`, is a usage error (exit `2`).

## Describing the contract

`charter describe` explains the contract to whoever is about to write a note, human or agent:

```
charter describe                       # every kind and variant, the path policies and the checks
charter describe recipe                # one kind, with each of its variants
charter describe recipe/bread          # one variant
charter describe recipe --format json  # the same, as a stable JSON document (format `charter-describe/1`)
```

For each kind and variant it shows its `description`, its path pattern and template, and whether undeclared fields are allowed. A kind lists the field values that make a note one of its variants; a variant shows the values that select it as fixed. Then come each field (required or when, what a value must be, allowed values, range, pattern, link targets, `unique`, `default` and `auto`, and the field's `description`), the exact `charter new` command, giving only the values nothing else fills in (`charter new recipe "TITLE" --set method=METHOD`), and the body outline of its template with each section's `<!-- guide: … -->` text. Kinds, variants and fields take an optional one-line `description:` for this:

```yaml
kinds:
  recipe:
    description: "A dish worth cooking again."
    fields:
      title: {type: string, required: true, description: "The dish's name."}
```

Markdown is the default format. In JSON, rules are data (`values`, `range`, `pattern`, `to`, `fixed`, `selects`, outline entries with `optional` and `repeat`), and `unknown_fields` is the severity of an undeclared field, or `null` when they are allowed. `plugin_rules` holds [plugins'](Plugins.md) rule docs, and a plugin's entry in `checks` gives its `source` (`null` for a built-in check). An unknown kind or variant is a usage error (exit `2`), reported as a diagnostic in text or JSON.

## Surveying a folder

Before a contract exists, `charter survey FOLDER` reports what the Markdown files in FOLDER hold, as facts to draft a contract from:

```
charter survey notes                  # a readable summary
charter survey notes --format json    # a stable JSON document (format `charter-survey/1`)
```

It is read-only (it writes nothing) and needs no contract: it neither loads nor searches for one, so it works in a folder with none, and ignores a `charter.yaml` in or above FOLDER. It reads every `*.md` file below FOLDER except under `.git` and `.obsidian` (the `.md` extension and those folder names are matched case-sensitively, like the rest of charter); a symlinked folder is not entered and a symlinked file pointing outside FOLDER is skipped. A FOLDER that is not an existing folder is a usage error (exit `2`, `usage/folder-not-found`); a folder with no Markdown files is a valid, empty survey (exit `0`). A file that cannot be read in full never stops the survey: invalid frontmatter is reported with its error, and a file that is not UTF-8 is listed with a `problem`.

The JSON output is deterministic: keys and lists are sorted, paths are POSIX and relative to FOLDER, and there are no timestamps. Its keys, `format` first:

```
format        "charter-survey/1"
totals        {files, folders, with_frontmatter}
files[]       {path, folder ("." for FOLDER itself), has_frontmatter,
               frontmatter_error (text, or null when it parses or there is none),
               problem (null, "not valid UTF-8" or "could not be read"),
               fields {name: type}}
folders[]     {folder, files (directly inside), filename_shapes {shape: count},
               fields [{name, files carrying it}],
               outline {headings ["# {{title}}", "## Care", ...], files} or null}
fields        {name: {files (carrying it), types {type: files},
               values [{value, count, files (up to 3 example paths)}], distinct (total), truncated}}
links         {markdown|wikilink: {links, files}}
agent_files   [name]
rulebooks     [{path, reason: "filename" | "heading"}]
```

The rules it applies are deliberately simple:

- **Types** are `string`, `number`, `boolean`, `date` (a date or datetime), `list`, `mapping` and `null`. A field whose notes disagree lists each type with its file count, which is how a mixed-type field shows.
- **Values** count scalars, and the elements of lists, per occurrence; a mapping contributes its type only. At most 20 values are listed, most common first (then by value), with `distinct` the total and `truncated` true when some were left out. `1` and `"1"` are different values; dates are written as `YYYY-MM-DD`.
- **Filename shapes** replace each digit with `N` and each run of words with `word` (`index`), `kebab-title` (`use-postgres`), `snake_title` (`use_postgres`) or `Title` (anything else), keeping the extension: `0007-use-postgres.md` is `NNNN-kebab-title.md`.
- **Outline** of a folder is the most common sequence of headings (outside code and comments) among its files, with the number of files that share it; ties go to the sequence that sorts first. A leading level-1 heading, the note's title, is written `{{title}}` because titles differ per note.
- **Links** are counted by style, `wikilink` and `markdown`, in bodies outside code and in string frontmatter values; URLs are not counted.
- **Agent files** are files named `AGENTS.md`, `CLAUDE.md` or `GEMINI.md` (any case), at any depth. **Rulebook-like documents** are other files whose name, or first heading, contains `rulebook`, `convention(s)`, `style guide`, `rules` or `charter` as a word.

## Snapshots and restore

Before a change you may want to undo, `charter snapshot FOLDER` saves a zip of the whole folder, and `charter snapshot restore ZIP` puts it back. Both need no contract: they neither load nor search for one, so they work in a folder with none and ignore any `charter.yaml` in or above it. They use only Python's own zip support, so they behave the same on Windows, macOS and Linux.

```
charter snapshot notes                          # writes ../notes-2026-10-18T143005Z.zip (UTC; no colons, legal on Windows)
charter snapshot notes --to backups/before.zip  # writes exactly there (missing parent folders are created)
charter snapshot notes --to backups             # an existing folder: the timestamped name, inside it
charter snapshot restore backups/before.zip --to notes-restored
```

It prints where the snapshot went and the exact command that puts the folder back (every path spelled out and quoted for your shell), for example `charter snapshot restore '/work/notes-2026-10-18T143005Z.zip' --to /work/notes --replace`.

**What a snapshot holds.** Every file and every folder under FOLDER, empty folders included, with no ignore rules: `.git`, `.obsidian` and other dotfiles are all in, so the way back is faithful. Nothing is added to the tree (the only metadata is the zip comment, which records the folder's name). Paths are stored POSIX-style and relative to FOLDER, so a snapshot restores the same on every OS. Contents come back byte for byte; modification times are kept to the zip format's two-second resolution (read in the machine's local time zone); file modes are not kept, except the executable bit on POSIX. **Symlinks and other special files are refused**: following one could copy files from outside the folder, and storing one as a link restores differently per OS. A folder holding any is refused (exit `1`, `snapshot/unsupported-entry`), the offenders listed, with nothing written; replace them with real files first.

A folder is also refused, listing the names and writing nothing, if restore would refuse what it holds: a name with a backslash, a leading drive letter such as `C:note.md`, a name that is not valid UTF-8 (and on Windows, characters Windows forbids), or two names that differ only in letter case or Unicode form (`a.md` and `A.md`; they could not restore on a case-insensitive volume). Rename them and run the snapshot again. An unreadable file or folder is refused too (`snapshot/unreadable`, or `snapshot/write-failed`), naming the path, and leaves no partial zip.

**Symlinks and special files, and how to proceed.** There is no option to skip them yet: a snapshot that silently left them out would not bring everything back, so any symlink, socket, fifo or device inside FOLDER makes `charter snapshot` stop. Move the link out of the folder, or replace it with a real file or folder (or delete it), then snapshot again.

**Where it goes.** By default beside FOLDER, never inside it. `--to PATH` is the zip's path, or an existing folder (or a path ending in a separator) to put the timestamped name in. A destination inside FOLDER is refused (exit `2`, `usage/snapshot-inside-folder`), after resolving `..` and symlinks. A snapshot never overwrites a file: two snapshots in the same second get `-2`, `-3`, ... after the timestamp, and an explicit `--to` that exists is refused (exit `1`, `snapshot/exists`).

**Restoring.** `charter snapshot restore ZIP [--to FOLDER] [--replace]` restores into FOLDER, or, without `--to`, into the folder name recorded in the zip, beside the zip. (A zip charter did not write records none, so it needs `--to`.) A missing target is created; an empty one is filled; a non-empty one is refused (exit `1`, `snapshot/target-not-empty`) unless you pass `--replace`. Restoring is all-or-nothing as far as the filesystem allows: everything is first extracted into a temporary sibling folder, and only when that succeeded is it moved into place. With `--replace` the old folder is moved aside first and deleted only after the new one is in place, and put back if the swap fails. `--replace` refuses (exit `1`, `snapshot/target-holds-input`) a target that contains the zip or the working directory.

**Hostile or damaged archives.** Every entry is checked before anything is extracted, and one bad entry refuses the whole archive (exit `2`, `snapshot/unsafe-archive`, nothing written): a `..` component, an absolute path, a drive letter, a backslash (never normalised: snapshots contain none), a symlink entry, an encrypted entry, a duplicate, and, on Windows, characters Windows cannot use in a name. A file that is not a zip, or is truncated, fails its checksums, has a damaged or unsupported compressed stream, or holds a file name flagged as UTF-8 that is not valid UTF-8, is a usage error (exit `2`, `snapshot/corrupt`), not a traceback; a zip that cannot be opened at all (permissions) is `snapshot/unreadable` (exit `1`); either way nothing is extracted; a failure while extracting leaves the target untouched. Restore sets no limit on the archive's size or number of entries: the zip is a local file you chose, and a full disk makes the restore fail and clean up its temporary folder. Letter-case duplicates (`a.md` and `A.md`) are refused as well, so every snapshot restores on case-insensitive volumes. If deleting the temporary `.NAME.charter-restore-*` folder or the replaced `.NAME.charter-old-*` folder fails after a successful restore, a `files/leftover` warning names the folder to remove, and the exit code stays `0`; a failed restore names such a folder in its hint; if a swap fails and the old folder cannot be moved back, the error gives that folder's exact path, where the old content is intact.

**A folder named `restore`.** `charter snapshot restore` means the restore subcommand. To snapshot a folder with that name, spell it `./restore`.

## Sweeping for dependents

Before changing a fact in a note, `charter sweep` lists every note that may repeat or rely on it:

```
charter sweep "Soda Bread"                  # by filename, alias, or path from root, as a wikilink names it
charter sweep docs/Recipes/Soda\ Bread.md   # or by a file path from the working directory
charter sweep "Soda Bread" --format json    # a stable JSON document (format `charter-sweep/1`)
charter sweep "Soda Bread" --format agent   # compact, one entry per line
```

- **Linked from:** each link to the note from another note's body or `link` field, with its line and field. An ambiguous link that may mean the note is listed too, flagged with its candidates; links in code or HTML comments do not count.
- **Mentioned in:** each body line of another note that names it, outside code, HTML comments and the links already listed: its `title`, its filename (without `.md`) or an `aliases` value, as whole words, ignoring case (`Straße` matches `STRASSE`) and Unicode normal form. A name may wrap across the lines of a paragraph; the line it starts on is reported. Its `id` counts after its kind's name or `#` (`recipe 12`, `#12`); an id with a letter in it (`12a`) counts on its own too, but a bare number is too common in prose to mean the note.
- **Links to:** the note's own links, each with what it resolves to, or `unresolved` or `ambiguous`.
- Notes under a `sweep: false` path policy appear in none of these lists, though such a note can itself be swept. Notes charter cannot read (invalid frontmatter, not UTF-8) are listed as not searched.
- `--format text` (the default) groups the lists under headings; `--format json` is the stable machine form; `--format agent` prints one entry per line (`linked-from`, `mentioned-in`, `links-to`, `unsearched`).
- An existing file path wins over a wikilink name. A name that matches no note, or several, is a usage error (exit `2`) with a "did you mean" hint or the candidates; so is a file that is not a note (not Markdown, ignored, or outside `root`).
