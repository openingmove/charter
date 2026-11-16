---
name: migrate
description: Bring a knowledge-base folder's existing files into line with a draft contract without losing any text, then install the contract. Start it yourself with /charter:migrate in Claude Code, or by the skill name migrate in another agent.
disable-model-invocation: true
---

# Migrate

Migrate one knowledge-base folder per run, from its migration plan, `<folder>/charter.migration-plan.md`, which `/charter:establish` writes. The plan format is in [../establish/migration-plan.md](../establish/migration-plan.md): read and update exactly that structure. Change no note before step 4 is done. Steps 2 to 4 write only the plan and the draft, and step 3 makes the way back (a branch or a snapshot zip). Tell the human the plan's and the draft's paths at every step.

`/charter:migrate` is how Claude Code starts this skill. In another agent, start the skill named `migrate` that agent's own way; where the text below names a skill, name it that way too.

Run every `charter` command from the knowledge-base folder, where the plan's paths resolve. A plan with a `- Source:` bullet (a new folder; [the plan format](../establish/migration-plan.md) says how) names the old documents by paths inside that source folder, which lies outside the knowledge base: read them with your file tools, run no `charter` command on them, and never change anything there. Pass the draft with `--config <draft>`, so each command works the same whether or not the folder already holds a `charter.yaml`. The draft is not in force: no edit policy or protected region guards the files while you migrate, so you add no `Charter-Allow` trailer.

## 1. Check charter

Run `charter --version`. It prints `charter X.Y.Z`. This skill needs 0.1.0 or newer.

If the command is missing or the version is older, stop and tell the human how to fix it, then start Migrate again. Missing: the README's "Install" section has the exact command, which is `uv tool install` with this repository's git URL or path. Too old: `uv tool upgrade charter`. Install nothing yourself.

Done when `charter --version` reports 0.1.0 or newer.

## 2. Open the plan

Ask which folder, unless the human named the plan. Read `charter.migration-plan.md` and the draft its `Draft contract` section names. Without a plan, stop and tell the human the plan comes from `/charter:establish`.

Read `Progress`. The first unticked line is where this run resumes; ticked lines are done and stay done, unless the human says the migration was undone or a ticked line's work is missing from the folder: then follow "Resuming after an undo" in [way-back.md](way-back.md) first.

Check that the draft's `paths:` holds `"charter.migration-plan.md": {ignore: true}` and add it if it is missing (a defensive check: Establish adds it), since validation against the draft reads the plan as a note without it. Run `charter validate --config <draft> --all --format json`. Exit 2 means the draft does not load: fix it with the human.

When a kind clearly needs a template and has none (its notes share an outline you can see in the sources, or the human described one), stop and tell the human to go back to `/charter:establish` for it, unless the draft records `# template: none` above that kind (the human already decided): a template added after the notes are moved makes a `structure` finding on every one of them. Establish's template files, listed in the plan's `Draft contract` section, are in place before Migrate starts.

When the draft has a kind with a `structure_cutoff`, note it: step 4 dates the undated notes of that kind ([dates.md](dates.md)). Leave the cutoff exactly as the draft has it.

With a `Source` bullet, check that the source folder exists and that every file the `Section map` names is in it; stop and tell the human when one is missing.

Done when you have told the human the folder, the plan and draft paths (and the source folder, when there is one), and the line you resume at.

## 3. Make a way back

Follow [way-back.md](way-back.md). The plan's `- Git:` bullet, when it has one, is the human's answer to Establish's git question: way-back.md says how it replaces the branch offer. When `Way back made` is already ticked, confirm that branch or snapshot is still there and skip the rest.

Done when the line `Way back made` is ticked with its detail and you have told the human the undo, in the form way-back.md gives.

## 4. Agree the map

Establish drafted the `Section map`, the `Agreed: no` line and the `Progress` lines (the plan format names it the owner); this step reviews and corrects them with the human, and drafts the map itself only for an older plan that lacks one for a `migrate` folder.

Skip when `Section map` says `Agreed: yes`, or, in a plan with no `Section map`, when `Section map agreed` is ticked. Otherwise first settle the dates: for each kind in the draft with a `structure_cutoff`, follow [dates.md](dates.md) to find a date for every undated note of the kind (existing notes, and the note each source becomes), clamp each to the day before the cutoff, and write them into the plan's `Dates` section, adding a `Date NOTE: DATE` Progress line for every bullet that names an existing note (the plan format gives the lines and their place). Then walk the human through the `Dates` first, with how each was found and which were clamped, and then the `Folders` states, every source's parts with the notes they become, and every `Note fixes` line, in plain language. Check that every paragraph of every migrated source lies in exactly one part (the coverage rule in the plan format), and fix the map with the human where it does not. The human may change any proposed date, or give one date for a folder; clamp the new value again.

Done when the human says yes to the dates and the whole map: set `Agreed: yes` and tick `Section map agreed`. A plan with no `Section map` has no `Agreed:` line: the yes is to the dates, the `Folders` states and the `Note fixes`, and you only tick the line. Without a yes, stop, edit nothing, and tell the human the way back from step 3 may be discarded.

## 5. Move the content

Work the unticked `Progress` lines in order, down to the line before `Links updated`, following [moving.md](moving.md) for each kind of line. Make every new note with `charter new --config <draft> KIND "TITLE"`, never by writing the file yourself: it places the note, applies the filename pattern and the template body and orders the frontmatter by the contract. Add the prose after what it wrote. Tick a line in the plan, with `- [x]`, the moment its work is done, before starting the next.

Done when every line above `Links updated` is ticked.

## 6. Settle links, left folders and validation

1. Repoint each link that `charter validate --config <draft> --all --format json` reports as `links/unresolved`, as [moving.md](moving.md) says (with a `Source` bullet, in the new notes only, and without `charter sweep`), and tick `Links updated`.
2. With a `Source` bullet, skip this item: the source lies outside the contract's root and needs no rule, and Establish ticked the line. Otherwise give each `leave as it is` folder except `.` `"<folder>/**": {untyped: allow, edit: read-only}` under `paths:` in the draft, where it is missing (the root `.` holds only ignored files, so `./**` would match nothing and it gets no rule), and tick `Left folders have path policies`.
3. Run `charter validate --config <draft> --all --format json`, put each judgement call to the human, and run it again until the findings left are the expected ones below. Tick the validate line.

A note dated before the cutoff reports no `structure` finding, so any `structure/` finding on a dated note is real: check its date is the one in the plan and before the cutoff.

Expected findings: `paths/read-only` or `paths/create-only` on files this migration changed. Validating against the draft compares edit policies with git's last commit, which predates the migration. Report them to the human, fix none, add no trailer. A commit is judged by the contract in its own tree, so for a contract Migrate installed, tell the human to commit the migrated notes first, without `charter.yaml` (that commit's tree holds no contract, so charter does not judge it), and the contract, the rulebook and the agent files second. For a plan with `- Contract: adopted` the contract is already in the parent commit, so that order does not help: the only route is a `Charter-Allow` trailer in the commit message. The trailer is the human's call, and you never add one. Git hooks are installed after the migration: a pre-commit hook that is already installed stops the notes-first commit (`usage/contract-not-staged`), and the human then commits notes and contract together with the trailer. Never suggest bypassing a hook.

Done when steps 1 to 3 are ticked and no finding of severity `error` or `warning` is left except the expected ones.

## 7. Install

This is the only step that expects no `charter.yaml` in the folder, unless the plan says `- Contract: adopted`.

1. Read the `Way back made` line and keep its undo for step 8: the plan is deleted below.
2. Install, unless `Contract installed` is ticked. A plan with `- Contract: adopted` has nothing to install: the draft is a copy of the installed `charter.yaml`. Check that `charter.yaml` equals the draft apart from the plan-ignore line, stop and tell the human if it does not, and otherwise tick the line and run no `charter init`. When `charter.yaml` already exists, a previous run may have installed it: treat it as that run's when it equals the draft apart from the plan-ignore line and the `agents:` and `docs:` sections `charter init --agents` adds, and tick the line; any other `charter.yaml` is a different installed contract, so stop and tell the human that replacing it is `/charter:evolve`'s job. Otherwise remove the plan-ignore line from the draft (the installed contract keeps no rule for a file about to go), run `charter init . --from <draft> --agents`, and tick the line. If it refuses with `init/exists` for the rulebook or the contract, it overwrites nothing: stop and tell the human, who moves the file aside or has the draft name another rulebook with `docs: {output: NAME}`.
3. When the plan has an `Old rulebook` line, tell the human which line of the agent file points at it and that they may remove it, edit nothing of theirs, and tick it.
4. Tick `Plan and draft deleted`, then delete the plan and the draft with your file tools (on resume, delete whichever is left). When you have no delete tool, ask the human to delete them.
5. Run `charter validate --config charter.yaml --all` and `charter docs --config charter.yaml --check`.

Done when `charter docs --check` exits 0 and `charter validate` shows nothing but the expected findings from step 6. Report any other output and stop.

## 8. State the undo

Say the undo you kept in step 7, in the form way-back.md gives, and run nothing of it. When step 6 reported expected edit-policy findings, repeat the commit route from there (the two-commit order, or the trailer for an adopted plan).

Done when you have said it.

## Limits

The cutoff is the contract's: this skill never edits one, and a human who wants a different date edits the contract by hand.

This skill edits the files the plan names and the draft. With a `Source` bullet it never edits, moves, deletes or gives a path policy to anything under the source folder: the source is read-only. It never writes a new note for a `Created` line other than with `charter new`, and never overwrites a file at a `Created` line's target that `charter new` did not make. Note fixes and the rename move of an existing note are not new notes; they follow moving.md. It creates a branch only when the human said yes to the offer (a recorded `new branch` or `new branch pushed` means Establish already made it), and it never commits for the human, merges, pushes, rebases, amends or resets, and it asks for no commit pattern: when and how often to commit is the human's.
