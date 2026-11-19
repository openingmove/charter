---
name: establish
description: Write the first charter contract for one knowledge-base folder (an empty repository, a few prose documents, or an established set of notes) through a short interview about the domain, and install it. Start it yourself with /charter:establish in Claude Code, or by the skill name establish in another agent.
disable-model-invocation: true
---

# Establish

Establish one knowledge-base folder per run. Write nothing before the human's yes in step 7. After it, write only the draft contract, `<folder>/charter.draft.yaml`, and the template files of step 9 (`Templates/<Kind>.md`, new files that are Establish's own), until step 12 or 13. Tell the human the draft's path at every step, and show its YAML whenever they ask.

This skill makes no commit and no push unless the human picked one in step 7. The repository's own `CLAUDE.md` or `AGENTS.md` may tell agents to commit and push after every change; that does not apply to this skill's files, because here the human decides what happens to git.

`/charter:establish` is how Claude Code starts this skill. In another agent, start the skill named `establish` that agent's own way; where the text below names a skill, name it that way too.

## 1. Check charter

Run `charter --version`. It prints `charter X.Y.Z`. This skill needs 0.1.0 or newer.

If the command is missing or the version is older, stop and tell the human how to fix it, then start Establish again. Missing: the "Install" page of the charter manual (`docs/guide/Install.md` in the charter repository) has the exact command, which is `uv tool install` with this repository's git URL or path. Too old: `uv tool upgrade charter`. Install nothing yourself.

Done when `charter --version` reports 0.1.0 or newer.

## 2. Pick the folder

Ask which folder holds, or will hold, the knowledge base. If the repository holds several, say each folder needs its own run of Establish, and do this one only.

Then ask: "build the knowledge base in the existing folder, or in a NEW folder, leaving the existing documents where they are?" In the existing folder, the contract and its files go into it. In a new folder, Establish writes a plan that sends the old documents you pick into the new folder, and `/charter:migrate` carries it out by copying them into notes; the existing folder is never changed. Say so at the question. If the human wants nothing brought in, the plan holds only the install lines. Ask for its name: that new directory is `<folder>` from here on, and the existing folder becomes a read-only source that Establish never writes to. Nothing is created yet: step 7 creates the new directory after the human's yes. If a folder of that name already exists, ask for another.

If `<folder>/charter.migration-plan.md` exists, a hand-off is under way: stop, tell the human to run `/charter:migrate`, which resumes at the first unticked line, and write nothing. The plan holds Migrate's progress, so Establish never overwrites it; only the human deletes it, after undoing the migration. This check comes first, so an adopted hand-off never offers adopt again.

Otherwise, if `<folder>/charter.yaml` exists, the folder already has a contract, and changing it is `/charter:evolve`. Run `charter validate --config <folder>/charter.yaml --all --strict --format json` and decide: exit 2 (the contract does not load) means show the human the load error and stop, and so does output with no diagnostic of severity `error` or `warning` (every note already fits; this is step 11's rule), since there is nothing here for Establish to do. Use `--strict` and read the diagnostics, never the plain exit code: under the default profile a note with no frontmatter is a warning and the exit code is still 0. Any `error` or `warning` means notes that do not fit the contract the human wrote: offer to adopt it, which keeps that contract as it is and plans the fixes to the notes, and follow [adopt.md](adopt.md) if the human says yes. On a no, stop. A `charter.yaml` inside the existing folder does not stop a run that builds a NEW folder: that folder is only a read-only source. If the draft exists (and there is no plan), ask whether to resume from it or overwrite it.

Done when you have told the human the folder (and, for a new folder, the existing folder as its source) and the draft path.

## 3. Survey

Run `charter survey <source> --format json` and read it with [survey.md](survey.md). `<source>` is the existing folder: `<folder>` itself, unless step 2 chose a new folder. Read the documents it lists too: every rulebook-like document, every agent file, and enough of the other files to know what they are about.

A folder of hundreds of files is read by sampling, as the "Large folders" section of survey.md says.

Done when you have told the human the starting point (empty, sparse or mature) with the numbers behind it, and the human agrees.

## 4. Interview

Follow [interview.md](interview.md): ask about the domain, never about fields, vocabularies or YAML.

Done when you can restate the answers in the human's words and the human confirms them.

## 5. Put each judgement call to the human

List every value that looks like a typo, every field only some notes carry, every title that differs from its filename, and every rule that a hand-written rulebook and the files disagree on ([survey.md](survey.md) says how to find them). Ask about each one, one at a time, and record each answer as a fix for a note, a declaration in the draft, or a decision about the old rulebook (keep it, or retire it). A note that has no frontmatter, or lacks a value for a required field, gets the fixes `add frontmatter` and `set FIELD=VALUE` (plan format: Note fixes) and its folder is `migrate in place`: nothing moves. A hand-written rulebook named `CHARTER.md` collides with the file `charter init` generates, and `charter init` never overwrites (`init/exists`). When one exists, ask whether the human keeps theirs, in which case the draft names another place for charter's rulebook (`docs: {output: NAME}`, written into the draft), or retires it, in which case the human moves or renames it themselves before the install. Record the answer. Drift is the human's decision, so decide none of it yourself.

Done when every call has an answer.

## 6. Propose the contract

Read the packaged example kinds in [kinds/](kinds/) for well-formed shapes: ADR, decision record, concept note, meeting note, glossary, research note. They inform your proposal; the human never picks from them. Propose the kinds, fields, links, folders and filenames the answers call for, in plain words, and write no file yet. For a new folder, also agree which documents of the existing folder are brought in and which are left behind; step 13 turns that into the plan. Contract syntax: the charter manual's "Contract syntax" page (`docs/guide/Contract-syntax.md`) and the example kinds.

Then settle the template question for each kind, as section 1 of [templates.md](templates.md) says: ask in domain terms whether its notes share a fixed outline ("No template" is a valid answer and is recorded). Step 9 writes the files.

Done when the human has agreed the kinds and said, for each kind, whether it gets a template, which fixes the list of files step 7 shows.

## 7. Choose how to write, and confirm

Find out whether the knowledge-base folder lies inside a git repository, with read-only commands only: `git rev-parse --is-inside-work-tree`, run in the folder (in its parent when a new folder does not exist yet), prints `true` inside one; then `git remote` lists the configured remotes. Also read the starting point before anything switches: `git branch --show-current` (empty on a detached HEAD, where the commit hash alone is the start) and `git rev-parse HEAD`, and keep both as START and COMMIT. Anything else means no repository.

In a repository, ask how to write, and offer exactly these. There is never a default, and never recommend (d):

- (a) a new local branch only;
- (b) a new branch pushed to the remote, offered only when a remote is configured;
- (c) write the files and leave them uncommitted;
- (d) commit to the current branch.

Not in a repository: skip the question, say that nothing is committed anywhere, and record `no repository`.

Then stop, and list every file this run will create, with its path, together with the git answer:

- the new directory itself, when step 2 chose one;
- `charter.draft.yaml`;
- one `Templates/<Kind>.md` per kind that got a yes in step 6;
- then, depending on the check of step 11, which can run only once the draft exists: either `charter.yaml`, the rulebook `CHARTER.md`, `AGENTS.md` (created, or given one added line) and `CLAUDE.md` when init creates one, with the draft deleted afterwards; or `charter.migration-plan.md`. A new folder always takes the second alternative: its old documents are what the plan carries over.

Mark a listed draft, template or plan that already exists as overwritten. Never list the contract or the rulebook as overwritten: they need a free name (step 5). If a `Templates/` folder already holds files (Obsidian's templates plugin uses one by default), list them as staying, overwrite none, and give a template whose name is taken another name. If step 12 will add a line to an `AGENTS.md` or `CLAUDE.md` that the folder already holds, and no clean commit holds that file, list a snapshot zip beside the folder too (step 12). Then wait for the human's yes. A no, or no answer, stops the run with nothing written: create no directory and no branch.

After the yes, create the new directory when step 2 chose one, then act on the answer before the first write: for (a) and (b), `git switch -c <name>` with a name the human gives; for (c) and (d), nothing. (a) and (c) commit nothing. (b) commits the listed files on the new branch only and pushes that branch (with `git push -u <remote> <name>`; ask which remote when there are several). (d) commits the listed files on the current branch and pushes nothing. A commit is made once, at the end of step 12 or 13, with `git add -- <the listed files>` (stage only the listed files that exist at that moment: the draft deleted in step 12 was never tracked, and the alternative not taken was never written) and `git commit -m "Establish the knowledge-base contract"`.

Done when the human has said yes to the file list and the git answer, and the directory and branch the answer needs exist.

## 8. Write the draft

Write the draft with `root: .`, and under `paths:`:

- `"README.md": {ignore: true}` and the same for every rulebook-like document;
- `untyped: allow` with `edit: read-only` for each folder to leave alone;
- `".obsidian/**": {ignore: true}` when the folder holds an `.obsidian` folder, and the same for any other editor or tool folder of Markdown that is not a note (`charter validate` reads every Markdown file under the root, though `charter survey` skips `.obsidian`);
- the rulebook's name, `docs: {output: NAME}`, when step 5 kept a hand-written `CHARTER.md`.

These rules cover the files inside `<folder>`; in a new folder the source lies outside it and needs none. Templates are step 9.

Declare every field the human decided to keep. Run `charter validate --config <draft> --all --format json`. Exit 2 means the draft does not load: fix it and run again.

Done when the draft loads (exit 0 or 1).

## 9. Settle the templates

Follow [templates.md](templates.md): for each kind, record the answer of step 6 (a "No template" is recorded as templates.md says), write `Templates/<Kind>.md` for each yes and name it in the kind, keep the templates folder ignored by a path rule, make the headings optional when the notes come from loose prose, show each template as a sample note beside `charter describe --config <draft>`, and pause until the human has read it and edited the file if they wish. Then rerun `charter describe --config <draft>` and fix any load error with the human.

Write templates only as new files in the knowledge-base folder: this step never changes an existing note.

For each kind that has a template and existing notes (files in the folder that the kind will cover, even if they lack frontmatter today), also propose a structure cutoff, so the old notes are not judged on a template they never followed:

- Add `structure_cutoff: {field: FIELD, date: DAY}` to the kind. `DAY` is today, the migration day, as an unquoted `YYYY-MM-DD` date in the local calendar. Prefer a creation date the notes already carry (`created`, `date`) for `FIELD`, and never an update date such as `updated`, because editing a legacy note would move it past the cutoff. When no note carries a date, use `created`.
- Make sure `FIELD` is declared for every note of the kind, on the kind or in `common_fields`, as `type: date` and `required: true`. The contract fails to load (`contract/invalid`) without that, without the template, or with a quoted date.
- Propose none for a kind with no template, or with no existing notes. A kind has one cutoff.

Run `charter validate --config <draft> --all --format json`. Exit 2 means the draft does not load: fix it and run again.

Done when every kind has a template or a recorded "no template", the human has said they are done with the templates, and the draft loads (exit 0 or 1).

## 10. Get approval

1. Summarise each kind in plain language: what it is, which folder and filename it gets, and how the kinds link to each other.
2. Ask for reactions and revise the draft until the human is satisfied. For each cutoff, say in plain words: "notes dated before DAY are old notes, exempt from the template's headings; notes dated on or after it must follow the template", and say the human may give a different date now, before approval. Write the date they give.
3. Run `charter describe --config <draft>` and show the result. The rulebook agents read is a fixed "Working here" workflow followed by this same description, so these are the rules agents will be told (each kind's body outline is its template), and say in one line which kinds have no template, so that decision is visible. `charter init` generates the rulebook in step 12.
4. Ask for a yes.

Done when the human says yes to the final `describe` output. Without a yes, stop and leave the draft in place.

## 11. Check the files against the draft

Run `charter validate --config <draft> --all --format json`. The files fit when no diagnostic has severity `error` or `warning` and the human has no note fix on record from step 5. A new folder always goes to step 13, even with nothing to bring in, because the plan carries the install.

Done when you have decided: fits, go to step 12; otherwise go to step 13.

## 12. Install

`charter init --agents` creates `AGENTS.md` and `CLAUDE.md` when they are missing, and adds one line to one that exists, which is an edit of the human's file. Check first. For each of the two that exists, a way back must exist before the edit: in a repository, `git status --porcelain -- <file>` prints nothing, so the committed copy is the way back; otherwise run `charter snapshot <folder>` (the zip beside the folder that step 7 listed), tell the human where it went and the restore command it printed, and say the restore command runs from outside the folder. When the human declines both, install without `--agents` and say that the agent files are not written.

Run `charter init <folder> --from <draft> --agents`, then delete the draft with your file tools (when you have none, ask the human to delete it). The template files from step 9 stay where they are: the installed contract names them. Run `charter validate --config <folder>/charter.yaml --all` and `charter docs --config <folder>/charter.yaml --check`.

Done when both exit 0 and you have told the human which files were written: `charter.yaml`, the rulebook `CHARTER.md`, `AGENTS.md` (created, or given one added line), and `CLAUDE.md` when init reports creating one. Name the template files written in step 9 too, as already in place.

If the human retired an old rulebook, tell them which line of the agent file points at it and that they may remove it. Edit nothing of theirs.

Offer the contract guard, as [guard.md](guard.md) says.

Then make the commit step 7 describes, if the human picked one, and go to step 14.

## 13. Hand off to Migrate

Write `<folder>/charter.migration-plan.md` as [migration-plan.md](migration-plan.md) defines it. Establish owns the plan's first draft, all of it, so that Migrate has only to review it with the human. Write, from the survey, the draft's findings and the step 5 answers (note fixes, folder states, the old-rulebook decision):

- `Draft contract`: the draft and the folder, the template files from step 9 (`- Templates:`), and the git answer of step 7 (`- Git:`; for a new branch, `new branch from START at COMMIT`, with the values read in step 7 before the switch).
- `Folders`, one state per folder, and `Note fixes` for each fix on record from step 5.
- When the draft has a cutoff, add the `Dates` section: one kind bullet per cutoff, copied from the draft. Migrate fills in each undated note's date and shows it before writing anything.
- `Section map`: read each file in a folder marked `migrate`, split it into parts as migration-plan.md says, and name for each part the kind and the `TARGET` path of the note it becomes, using the kind's folder and filename pattern. Check the coverage rule (every paragraph in exactly one part) before writing it. Put `Agreed: no` on its own line.
- `Progress`, every line, in the order migration-plan.md gives: `Way back made` (empty), `Section map agreed`, one `Created` line per distinct target, one `Source` line per file in the map, one `Fix` line per note fix, `Links updated`, the path-policy line, the validate line, the install line, an `Old rulebook` line when the human retired one, and `Plan and draft deleted`. Tick only `Left folders have path policies`, and only when the draft already holds them. Leave `Section map agreed` and `Agreed:` as they are written: the interview is not the human's agreement to the map, and only Migrate sets them, after walking the human through it.

Install nothing: no existing file changes before Migrate has made a way back. The template files are new files, already written.

For a new folder, the plan's `Draft contract` also holds `- Source:`, the existing folder as a path from `<folder>` (such as `../docs`), written as migration-plan.md's "New folder" section says. Then `Folders` and the `Section map` name the old documents by their paths inside that source, and nothing else in the plan refers to it. The plan has no `migrate in place` folder and no `Note fixes`, because `<folder>` holds no notes yet. Name its path in your last message, and say that the existing folder stays untouched as a read-only source, which Migrate reads and never changes.

Add `"charter.migration-plan.md": {ignore: true}` under `paths:` in the draft, so `charter validate --config <draft>` never reads the plan as a note.

Offer the contract guard, as [guard.md](guard.md) says: on a yes it goes into the draft.

Tell the human to run `/charter:migrate`, naming the plan and draft paths, and to keep both files. A skill started by the human cannot start another skill, so say it in those words.

Done when the plan and draft exist at the named paths and the human has the command. Then make the commit step 7 describes, if the human picked one, and go to step 14.

## 14. Mention the layers

- Git hooks, offered once as an option: they check each commit and protect only this clone. If the human wants them, follow the charter manual's "Git hooks" page (`docs/guide/Git-hooks.md`). They need the contract installed, so after a hand-off that means after Migrate finishes. They run from the repository's top directory, so say so when the folder is not the repository root.
- CI, the backstop that covers collaborators: the charter GitHub Action, added to a workflow as the charter manual's "GitHub Action" page (`docs/guide/GitHub-Action.md`) describes, with `config: <folder>/charter.yaml` (once per knowledge base) and `fetch-depth: 0`.

Done when you have said both and stopped.

## Limits

A cutoff, once the human has approved the draft, is the human's. Establish proposes it once and does nothing about it afterwards: a human who wants a different date edits the contract by hand.

This skill writes the draft, the template files of step 9, the plan and, in step 12, the files `charter init` writes, and no other file, all of them listed to the human in step 7 first. Template files are new files in the knowledge-base folder, never changes to an existing note. It never touches an existing note: notes change only in Migrate, once a way back exists. It never writes into the existing folder when the human chose a new one. When the human switches the contract guard on, its line goes into `charter.yaml` or the draft, and the rulebook is regenerated: files already on that list.

It makes no commit and no push beyond the human's answer in step 7, and runs no other command that changes git history.
