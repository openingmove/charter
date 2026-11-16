# Migration plan

A skill-owned file: charter has no plan format. Establish writes it, `/charter:migrate` reads and updates it, and a fresh session resumes from it. Migrate relies on the exact headings and line shapes below, so keep them.

- **Owner**: Establish drafts the whole plan: `Folders`, `Dates` kind bullets, `Note fixes`, the `Section map` with `Agreed: no`, and every `Progress` line. Migrate reviews it with the human, corrects it, adds the `Dates` note bullets and their `Date` lines, and only then sets `Agreed: yes`. A plan from an older Establish may lack a `Section map` for a `migrate` folder; Migrate then drafts it the same way.
- **Location**: `<folder>/charter.migration-plan.md`, beside the draft `<folder>/charter.draft.yaml`.
- **Ignored by the draft**: the draft declares `"charter.migration-plan.md": {ignore: true}` under `paths:`, so charter never validates the plan as a note. Migrate removes that line from the draft before installing the contract, then deletes the plan and the draft.
- **Paths** are relative to `<folder>`. Write each inside backticks, with `/` as the separator on every platform and never `\`, and in Unicode normal form NFC (macOS can hand back NFD names: write the NFC form and match the file by its real name). A name that holds a backtick or the arrow ` -> ` cannot be written safely in a line: for a `TARGET`, choose another name; for an existing file, ask the human to rename it before the run.
- **Safe `TARGET` names** work on Windows, macOS and Linux: none of `< > : " / \ | ? *` or a control character in a name, no trailing dot or space, no whole name that is a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1` to `COM9`, `LPT1` to `LPT9`), and two paths that differ only in case or in normal form count as the same file, so give every `TARGET`, and every existing file, a distinct name when case and normal form are ignored.

## Template

````markdown
# Migration plan

## Draft contract

- Draft: `charter.draft.yaml`
- Folder: `.`
- Templates: `Templates/Story.md`, `Templates/Place.md`
- Git: new branch from main at 3f9c2ab

## Folders

- `archive`: leave as it is
- `recipes`: migrate in place
- `.`: migrate

## Dates

- `story`: field `created`, cutoff `2026-10-24`, latest `2026-10-23`
- `recipes/Focaccia.md`: `2024-05-09` (first commit)
- `recipes/Rye Loaf.md`: `2026-10-23` (modified, clamped from `2026-10-24`)
- `stories/Town history.md`: `2019-04-02` (given)

## Note fixes

- `recipes/Plain Baguette.md`: `status` `tesetd` -> `tested`
- `recipes/Focaccia.md`: remove `oven_temp_f`
- `bakes/2026-03-02 Rye Loaf.md`: rename field `rating` -> `score`
- `recipes/Rye Loaf.md`: retitle `Rye Bread` -> `Rye Loaf`
- `recipes/Rye Loaf.md`: rename file -> `recipes/Rye Bread.md`
- `recipes/Soda Bread.md`: add frontmatter `recipe`
- `recipes/Soda Bread.md`: set `status`=`draft`

## Section map

Agreed: no

### `town-history.md`

- `(intro)` -> `story`: `stories/Town history.md`
- `## The founding` -> `story`: `stories/The founding.md`
- `## Tarrow family` -> `person`: `people/Edmund Tarrow.md`

### `walking-tour.md`

- `paragraphs 1-4` -> `place`: `places/Quay Street.md`
- `paragraphs 5` -> `place`: `places/Mill Lane.md`

## Progress

- [ ] Way back made: branch `migrate-notes` from `main` at `3f9c2ab`
- [ ] Section map agreed
- [ ] Fix `recipes/Soda Bread.md`: add frontmatter `recipe`
- [ ] Date `recipes/Focaccia.md`: `2024-05-09`
- [ ] Date `recipes/Rye Loaf.md`: `2026-10-23`
- [ ] Created `stories/Town history.md`
- [ ] Created `stories/The founding.md`
- [ ] Created `people/Edmund Tarrow.md`
- [ ] Created `places/Quay Street.md`
- [ ] Created `places/Mill Lane.md`
- [ ] Source `town-history.md` checked complete, then removed or kept
- [ ] Source `walking-tour.md` checked complete, then removed or kept
- [ ] Fix `recipes/Focaccia.md`: remove `oven_temp_f`
- [ ] Fix `recipes/Soda Bread.md`: set `status`=`draft`
- [ ] Links updated with `charter sweep`
- [ ] Left folders have path policies in the draft
- [ ] `charter validate --config charter.draft.yaml --all` clean
- [ ] Contract installed with `charter init . --from charter.draft.yaml --agents`
- [ ] Plan and draft deleted
````

The example shows every form; a real plan holds only the lines it needs.

## Headings

The H2 names are fixed: `Draft contract`, `Folders`, `Section map`, `Progress`, and the optional `Dates` and `Note fixes`. `Dates` is present only when a kind in the draft has a `structure_cutoff` (see below); it sits right after `Folders`, so the human sees the proposed dates first. `Note fixes` is present only when there is at least one fix, and sits between `Dates` and `Section map`. `Section map` is present only when a folder is marked `migrate`.

## `## Draft contract`

Two bullets, `- Draft: ` and `- Folder: `, each followed by one backticked path, and, only when step 9 of Establish wrote template files, a `- Templates: ` bullet: every template file, each path in backticks, separated by commas. Migrate passes the draft to charter with `--config`.

Establish adds one more:

- `- Git: `, the human's answer to Establish's git question, starting with one of `new branch`, `new branch pushed`, `uncommitted`, `commit to current branch` or `no repository`. With the first two, the value continues ` from START at COMMIT`, the branch (or, on a detached HEAD, the commit hash alone) and the commit Establish started from, read before it switched, so Migrate can state the undo. Establish has already created and switched to that branch, so the current branch is the one to stay on. A plan without a `Git` bullet (written by an older Establish) means ask now: Migrate puts the branch question to the human itself.

- `- Source: `, present only when the knowledge base is a NEW folder and the old documents lie in another one: the path of that existing folder, relative to `<folder>`, in backticks. See "New folder" below.
- `- Contract: adopted`, present only when Establish adopted a hand-written `charter.yaml` ([adopt.md](adopt.md)). The draft is then a copy of the installed contract, so Migrate installs nothing (the `Contract installed` line stays unticked until Migrate has checked that `charter.yaml` equals the draft), and the plan has no `Section map` and no `migrate` folder.

The template files are Establish's own, like the draft and the plan: new files, written before Migrate starts, so Migrate's clean-state check does not count them as uncommitted work. The plan does not say which template section each part of the `Section map` lands in. Migrate decides that at move time from the template.

## `## Folders`

One bullet per folder that holds Markdown the draft does not ignore entirely (a templates folder under `"Templates/**": {ignore: true}` gets none), shape `` - `FOLDER`: STATE ``, with the knowledge-base folder itself as `.`. `STATE` is exactly one of:

- `migrate`: files here are restructured; each source file is listed in the section map.
- `migrate in place`: files stay where they are and are not restructured; only the `Note fixes` that name them apply. Use it for a folder that already fits the draft apart from those fixes, and for one that fits with no fix at all: it is never `leave as it is`, which would freeze notes the contract should keep editable.
- `leave as it is`: Migrate never edits it. The draft already holds its path policy (`untyped: allow` with `edit: read-only`), so the finished contract validates clean without touching it. A root folder (`.`) holding only ignored files (a README, a hand-written rulebook, an agent file) uses this state too: the draft ignores those files, so there is nothing to migrate.

## `## Dates`

Present only when the draft has a kind with a `structure_cutoff` ([../migrate/dates.md](../migrate/dates.md) says what that is and how dates are found). Establish writes the first kind of bullet; Migrate adds the note bullets before it asks the human to agree the map. Nothing is written to a note until the human has agreed them.

- **Kind bullet**, one per kind with a cutoff, copied from the draft: `` - `KIND`: field `FIELD`, cutoff `DAY`, latest `LATEST` ``. `LATEST` is the day before `DAY`. The plan only records the cutoff; it never changes it.
- **Note bullet**, one per note of such a kind that has no date: `` - `NOTE`: `DATE` (SOURCE) ``. `NOTE` is an existing note, or the `TARGET` of a note the section map creates. `DATE` is an unquoted `YYYY-MM-DD`, never later than `LATEST`. `SOURCE` is `first commit`, `modified` or `given`, and a clamped value reads `(SOURCE, clamped from `ORIGINAL`)`.

For a created note, the date is that of the source file it comes from.

## `## Note fixes`

One bullet per fix, shape `` - `NOTE`: FIX ``, where `NOTE` is the path of an existing note in a folder marked `migrate` or `migrate in place`, and `FIX` is exactly one of:

| Fix | Shape | Meaning |
|---|---|---|
| change a value | `` `FIELD` `OLD` -> `NEW` `` | the field's value `OLD` becomes `NEW` |
| remove a field | `` remove `FIELD` `` | delete the field from the frontmatter |
| rename a field | `` rename field `OLD` -> `NEW` `` | the field keeps its value under a new name |
| retitle | `` retitle `OLD` -> `NEW` `` | the `title` field and the `#` heading change; the file stays |
| rename a file | `` rename file -> `NEWPATH` `` | the file moves; links to it are updated with `charter sweep` |
| add frontmatter | `` add frontmatter `KIND` `` | a note with no frontmatter block gets one at the top, for the kind `KIND`; the text below it is not touched |
| set a field | `` set `FIELD`=`VALUE` `` | the field is added to the frontmatter with the value the human gave; the note must already have a frontmatter block (a preceding `add frontmatter` line, or its own) |

A field the human wants to keep needs no fix line: the draft declares it.

`add frontmatter` and `set` are how a note that stays where it is comes to fit the contract: they belong to folders marked `migrate in place`, with no file moved and no `Section map` part, and Migrate checks them with their own completeness rule (see `moving.md`). Give a note one `add frontmatter` line, then a `set` line for each required field whose value the human gave; a required field with no value is asked about, never invented.

## `## Section map`

`Agreed: no` or `Agreed: yes` on its own line. When a `Section map` is present, Migrate edits nothing until it reads `Agreed: yes`, and sets it only after the human agrees the whole map.

One `###` subsection per source file in a folder marked `migrate`, headed `` ### `SOURCE` ``. Its bullets have the shape `` - `PART` -> `KIND`: `TARGET` ``, in source order, where `KIND` is the target note's kind and `TARGET` its path. Several parts may share a target; a source may produce several targets. A source uses one form of `PART`, not both.

**Heading form**, when the source has headings that split it sensibly. `PART` is `(intro)` or a heading line copied exactly, hashes included (`## The founding`).

- A section is a heading line and everything below it up to the next heading line of any level, so every heading, subsections included, is a part of its own.
- `(intro)` is everything above the first heading, frontmatter excluded.

**Paragraph form**, when the source has no usable headings. `PART` is `paragraphs N` or `paragraphs N-M`.

- Count the body only: frontmatter, if any, is not counted.
- A paragraph is a run of lines between blank lines; one fenced code block is one paragraph, blank lines inside it included; a heading line is a paragraph.
- Number from 1 at the first paragraph of the body. `N-M` includes both ends.

**Coverage.** Every paragraph of every migrated source appears in exactly one `PART`: none missing, none twice. The Migrate completeness pass depends on this, so check it before asking for agreement.

## `## Progress`

A checklist, one `- [ ] ` line per step. Migrate ticks a line by changing it to `- [x] `; a session resumes at the first unticked line. Line shapes:

- `` - [ ] Way back made: DETAIL ``: fixed; Migrate fills in `DETAIL` and writes every value in backticks, the commit included: `` branch `NAME` from `START` at `COMMIT` ``, `` commit `COMMIT` on `START` `` or `` snapshot `PATH`, restore with `COMMAND` ``. Filled in and ticked: ``- [x] Way back made: branch `migrate-notes` from `main` at `3f9c2ab` ``.
- `- [ ] Section map agreed`: fixed, and present in every plan. With a `Section map` it is ticked once `Agreed: yes` is set. A plan with only `migrate in place` and `leave as it is` folders has no map, and the line records the human's yes to the `Folders` states, the `Dates` and the `Note fixes` instead; there is no `Agreed:` line to set.
- `` - [ ] Created `TARGET` ``: one per distinct target in the section map.
- `` - [ ] Source `SOURCE` checked complete, then removed or kept ``: one per source file.
- `` - [ ] Fix `NOTE`: FIX ``: one per `Note fixes` bullet, with the same text after the colon.
- `` - [ ] Date `NOTE`: `DATE` ``: one per `Dates` note bullet for a note that already exists, with the same date. Whoever writes the `Dates` note bullets adds these lines in the same edit. They come first among the work lines, right after `Section map agreed` and any `Fix` line that adds frontmatter (a note needs its frontmatter block before it can hold a date), and before every `Created`, `Source` and other `Fix` line, because a fix may need the field. A created note takes its date when it is created, so it has no `Date` line.
- `- [ ] Links updated with `charter sweep``, `- [ ] Left folders have path policies in the draft` (Establish ticks it when the draft already has them), `` - [ ] `charter validate --config DRAFT --all` clean ``, `` - [ ] Contract installed with `charter init FOLDER --from DRAFT --agents` ``, `- [ ] Plan and draft deleted`: fixed, in this order, last.
- `` - [ ] Old rulebook `PATH`: tell the human which agent-file lines to remove ``: present only when the human chose to retire a hand-written rulebook. Migrate does it after installing, and edits no file of theirs.

Order: `Way back made`, `Section map agreed`, the `add frontmatter` `Fix` lines, the `Date` lines, then `Created`, `Source` and `Fix` lines, `Links updated`, the path-policy line, the validate line, the install line, `Old rulebook` and `Plan and draft deleted`. Establish writes all of them, ticks only the path-policy line when the draft already holds the policies, and leaves `Way back made` empty for Migrate to fill in.

Migrate may add lines and keeps the existing ones.

## New folder: the Source bullet

Establish builds the knowledge base in a new folder, leaves the existing documents where they are, and hands the plan to Migrate. The plan is written in `<folder>`, the new folder, and Migrate runs every `charter` command from there; the existing folder is the **source root**.

````markdown
## Draft contract

- Draft: `charter.draft.yaml`
- Folder: `.`
- Source: `../docs`
- Git: new branch from main at 3f9c2ab

## Folders

- `.`: migrate
- `archive`: leave as it is

## Section map

Agreed: no

### `town-history.md`

- `(intro)` -> `story`: `stories/Town history.md`
- `## The founding` -> `story`: `stories/The founding.md`
````

The rules, and only these, change when the `Source` bullet is present:

- **Paths.** The `Source` value is the only path that may start with `..`, and it uses `/` on every platform. `Folders` bullets and the `###` source headings of the `Section map` are relative to the source root (`.` is the source root itself). `TARGET`s, `Dates` and `Progress` paths stay relative to `<folder>`.
- **States.** A `Folders` bullet is `migrate` or `leave as it is`. There is no `migrate in place` and no `Note fixes`, because `<folder>` holds no notes before the migration.
- **The source is read-only.** Migrate reads source files with its file tools and copies their text into new notes made by `charter new`. It never edits, moves or deletes anything under the source root, runs no `charter sweep` for it, and gives it no path policy (the source lies outside the contract's root). A `Source ... checked complete, then removed or kept` line therefore always ends as kept, with no question to the human.
- **Links.** The new notes are validated alone, so a link in copied text that points at an old document is `links/unresolved`. Migrate points it at the new note that holds the linked part, by hand; a link to a file that is not Markdown (an image) is put to the human, since Migrate copies no file.
- **No folder state to settle.** `Left folders have path policies` is ticked by Establish: the source needs none.

## Evolve's use of this format

`/charter:evolve` writes the same plan, without a section map, to `charter.evolve-plan.txt`, with its own `Progress` lines, a `- Change:` bullet in `Draft contract` and the optional sections `Decisions` and `Protected notes` between `Note fixes` and `Progress`. Migrate ignores them. Its `Dates` section uses the shapes above and sits in the same place, after `Folders`. They are defined in `skills/evolve/plan.md`.
