# The Evolve plan

Evolve edits existing notes in place, so its plan is the Migrate plan format without a section map: [../establish/migration-plan.md](../establish/migration-plan.md) gives the exact grammar for `Draft contract`, `Folders` (every affected folder is `migrate in place`), `Note fixes` and `Progress`. Follow it, with the additions below. A fresh session resumes from this file alone.

## Location

`charter.evolve-plan.txt` beside the contract and the draft, with a path in `Draft contract` that is relative to that folder.

The extension is `.txt` on purpose: charter validates every `.md` file under `root` as a note, so a Markdown plan in the folder would be a finding, and a dot-folder holding one is scanned the same way. A `.txt` file is never read as a note, so `charter validate` gives the same result with and without the plan (checked against the real CLI). The text inside is Markdown. The draft needs no `ignore` rule, and the current contract stays as it is.

One exception: a path policy with `edit: read-only` or `edit: create-only` over the whole root reports any new file, plan and draft included. Those findings appear in both the current and the draft run, so they are not fallout; tell the human they are the plan's own files.

## Template

````markdown
# Evolve plan

## Draft contract

- Draft: `charter.draft.yaml`
- Folder: `.`
- Change: split the recipe status `draft` into `idea` and `trial`

## Folders

- `recipes`: migrate in place
- `decisions`: migrate in place

## Dates

- `recipe`: field `created`, cutoff `2026-10-24`, latest `2026-10-23`
- `recipes/Rye Loaf.md`: `2026-10-23` (modified, clamped from `2026-10-24`)
- `recipes/Seeded Crackers.md`: `2025-11-02` (first commit)

## Decisions

- `recipes/Rye Loaf.md`: status `draft`; choose `idea` or `trial`; decided: `trial`
- `recipes/Seeded Crackers.md`: status `draft`; choose `idea` or `trial`; decided: pending

## Note fixes

- `recipes/Rye Loaf.md`: `status` `draft` -> `trial`
- `decisions/Test new recipes on Mondays.md`: `status` `draft` -> `idea`

## Protected notes

- `decisions/Test new recipes on Mondays.md`: `paths/create-only`; agreement: pending

## Progress

- [ ] Plan agreed
- [ ] Way back made: branch `evolve-fields` from `main` at `3f9c2ab`
- [ ] Date `recipes/Rye Loaf.md`: `2026-10-23`
- [ ] Date `recipes/Seeded Crackers.md`: `2025-11-02`
- [ ] Fix `recipes/Rye Loaf.md`: `status` `draft` -> `trial`
- [ ] Fix `decisions/Test new recipes on Mondays.md`: `status` `draft` -> `idea`
- [ ] Contract replaced with the draft
- [ ] Rulebook regenerated with `charter docs`
- [ ] Protected-note commit made, or trailer lines given to the human
````

## What Evolve adds

Evolve adds one bullet and two optional sections to the Migrate format. Migrate ignores them. It also uses the Migrate format's optional `Dates` section, for the one change that sets a structure cutoff (see below).

- `Draft contract` gains a `` - Change: `` bullet, followed by one plain sentence naming the change. Evolve ignores the `- Git:` bullet that Establish writes into a migration plan: it offers its own branch in [way-back.md](way-back.md) and does not read Establish's git answer.
- `Decisions` and `Protected notes` sit between `Note fixes` and `Progress`, in that order.

- `## Decisions`: one bullet per note whose fix needs the human, shape `` - `NOTE`: CAUSE; choose `A` or `B`; decided: `X` `` where `X` is the chosen option or `pending`. Write a `Note fixes` line for a note only once its decision is made. Ask about each note, or about a set stated clearly ("every recipe becomes `idea`"), and record the answer in the bullet.
- `## Protected notes`: one bullet per affected note under an edit policy or the protected-region check, shape `` - `NOTE`: CODES; agreement: pending|yes|no ``. `CODES` are the diagnostic codes its edit will raise, `paths/read-only`, `paths/create-only` or `protected-region/changed`. [protected-notes.md](protected-notes.md) says when the agreement changes.

A protected note's `Note fixes` line is written like any other, and its `Fix` progress line stays unticked until its agreement is `yes`.

## Dates

Present only when the change adds a kind's first template to a kind that already has notes, so that a cutoff and its required date field are set ([dates.md](dates.md)). `Dates` sits right after `Folders`, ahead of `Note fixes`, with the bullet shapes `../establish/migration-plan.md` gives: a kind bullet (`` - `KIND`: field `FIELD`, cutoff `DAY`, latest `LATEST` ``) and one note bullet per existing note of the kind that has no date. Show these to the human with the rest of the plan, before any note is edited. A protected note's date bullet is covered by its `Protected notes` agreement.

## Progress lines

Evolve's list differs from Migrate's fixed one, and has no `Section map agreed` line (that is Migrate's rule; `Plan agreed` takes its place): `Plan agreed`, `Way back made`, one `` Date `NOTE`: `DATE` `` line per `Dates` note bullet (the same date; add them when you write the `Dates` section; dating comes first because a fix may need the field), one `Fix` line per `Note fixes` bullet (same text after the colon), then `Contract replaced with the draft`, `Rulebook regenerated with `charter docs``, `Protected-note commit made, or trailer lines given to the human` (only when a protected note changed). Ticking and resuming follow migration-plan.md. The end of step 10 (plan deleted) is the final record, so no line tracks it.

Tick `Contract replaced with the draft` right after the contract file takes the draft's content. Before it the draft must exist; after it the draft is gone and later steps use the contract.

On resume, read a `Fix` line's target before applying it: when the note already holds the target (a prior session edited it and stopped before ticking), tick the line and skip the edit.
