---
name: evolve
description: Change a charter contract (a new kind, field, value or path rule) after checking what the change would break, and fix the notes it breaks with the human's agreement. Start it yourself with /charter:evolve in Claude Code, or by the skill name evolve in another agent.
disable-model-invocation: true
---

# Evolve

Change the contract only as the human asks. The current contract stays in force until step 8; edit the draft, never the contract, before then. Edit no note before step 6. Tell the human the draft's path and, once it exists, the plan's path at every step.

`/charter:evolve` is how Claude Code starts this skill. In another agent, start the skill named `evolve` that agent's own way; where the text below names a skill, name it that way too.

Run every `charter` command from the contract's folder. Charter prints paths relative to it, and the plan uses them.

## 1. Check charter

Run `charter --version`. It prints `charter X.Y.Z`. This skill needs 0.1.0 or newer.

If the command is missing or the version is older, stop and tell the human how to fix it, then start Evolve again. Missing: the README's "Install" section has the exact command, which is `uv tool install` with this repository's git URL or path. Too old: `uv tool upgrade charter`. Install nothing yourself.

Done when `charter --version` reports 0.1.0 or newer.

## 2. Draft, or resume

Find the contract: the nearest `charter.yaml` in the working folder or above it, the one charter itself would use. Read it and run `charter describe` for the current rules.

When `charter.evolve-plan.txt` sits beside the contract, an earlier run left work: read its `Progress` per [plan.md](plan.md), tell the human where it stands, and continue at the first unticked `Progress` line, in the step that line belongs to. The draft named in the plan must still exist, unless `Contract replaced` is ticked. Notes already fixed fail the current contract on purpose: for the finish check, the baseline is every current finding on a note the plan does not name.

Otherwise copy the contract to `charter.draft.yaml` in the same folder: `root:` and templates resolve relative to the contract's folder, so the draft must sit beside it. If the contract has another name, copy that file beside itself and pass it with `--config` in every current-contract command below too. Apply the human's requested change to the draft only. Ask if the request is ambiguous.

When the change adds a kind's first template to a kind that already has notes, set a structure cutoff and its date field as part of the same change, as [dates.md](dates.md) says. In no other case set one, and leave every cutoff already in the contract as it is.

Done when `charter validate --config <draft> --format json` loads the draft (exit 0 or 1; exit 2 means the draft is broken, so fix it) and you have told the human the draft's path.

## 3. Compare fallout

Run both and read the JSON `diagnostics`:

- `charter validate --format json` (current contract)
- `charter validate --config <draft> --format json`

A diagnostic is the same finding when `path`, `line`, `code` and `message` all match. Fallout is every draft diagnostic with no match in the current list, except the stale rulebook ([fallout.md](fallout.md) says exactly which finding).

When the change set a cutoff, expect a `schema/required` and a `structure/missing-heading` finding for every existing note without a date: an undated note is not legacy. That is the fallout the plan's `Dates` answer, not a surprise ([fallout.md](fallout.md), "Cutoff notes are not fallout"). Say so when you report it.

Done when you have the fallout list, which may be empty. With none, go to step 8.

## 4. Choose a shape

Group the fallout by note and by cause, as [fallout.md](fallout.md) says. Name which affected notes the current contract protects with an edit policy or the protected-region check, and offer the shapes in fallout.md that avoid touching them. Let the human choose. A new shape means editing the draft and returning to step 3.

Done when the fallout is empty (go to step 8) or the human has said which remaining fallout they accept.

## 5. Write the plan and agree it

Write `charter.evolve-plan.txt` beside the contract, in the format [plan.md](plan.md) gives. When the change set a cutoff, first find a date for every undated note of the kind as [dates.md](dates.md) says and put them in the plan's `Dates` section, adding a `Date NOTE: DATE` Progress line for every bullet that names an existing note. Then add every affected note with its proposed fix, the per-note decisions, the protected notes, and the progress list. Ask the human only about genuine per-note judgement, such as which of two new values a note takes. Never ask them to write YAML.

Ask for explicit agreement on each protected note as [protected-notes.md](protected-notes.md) says, per note or per set stated clearly, and record `agreement: yes` or `no` in the plan's `Protected notes` section at once.

Show the plan in plain language, the proposed dates first (how each was found, which were clamped, and the cutoff date, which the human may still give differently now), with `charter describe --config <draft> <kind>` for each kind it touches. Tick `Plan agreed` on a clear yes to the whole plan.

Without a yes, stop with every note untouched. Leave the plan and the draft in place, tell the human both paths, that they resume by starting Evolve again or may delete them, and that neither belongs in a commit.

Done when `Plan agreed` is ticked, every decision is decided and every protected note is marked `yes` or `no`.

## 6. Make a way back

Follow [way-back.md](way-back.md).

Done when `Way back made` is ticked with its detail and the human has the undo.

## 7. Fix the notes

Work the unticked `Date` and `Fix` lines in the order [plan.md](plan.md) gives. Check first whether the note already holds the fix's target (a stopped run may have edited it): if so, tick the line and move on. Run `charter sweep NOTE` before a rename or retitle. Edit a protected note only when its `Protected notes` bullet says `agreement: yes`; a `no` or `pending` note stays as it is. Tick each line the moment its edit is made. Then run `charter validate --config <draft> --format json`.

Done when every `Fix` line is ticked or is a protected note still marked `no`, and the draft validation shows nothing left except the stale rulebook, the baseline findings and the edit-policy or protected-region findings on notes whose edit protected-notes.md covers. A note fixed in one pass can still fail a rule: fix it again or put it to the human.

## 8. Replace the contract

Tell the human in plain language what the change does and show `charter describe --config <draft> <kind>` for each kind it touches. Without a yes, stop and leave the draft (and the plan, if one exists) in place. A yes to the plan in step 5 covers this when the same description was shown there.

Replace the contract file with the draft's content, delete the draft with your file tools (when you have none, ask the human), run `charter docs` (with `--config <contract>` when the contract is not the nearest `charter.yaml`), and tick `Contract replaced` and `Rulebook regenerated` when a plan exists.

Done when `charter docs --check` exits 0.

## 9. Commit protected-note edits

Skip when no protected note changed. Otherwise follow [protected-notes.md](protected-notes.md): the commit with `Charter-Allow` trailers, or the exact lines for the human to use.

Done when the commit exists, or the human has the trailer lines.

## 10. Finish

Run `charter validate --format json` and `charter docs --check`, each with `--config <contract>` when the contract is not the nearest `charter.yaml`. Delete the plan with your file tools (when you have none, ask the human), tell the human the undo from way-back.md, and run none of it.

Done when `charter docs --check` exits 0 and `charter validate` shows nothing beyond the baseline from step 3 (the current contract's findings). Tell the human those findings are pre-existing. With a protected note changed and not yet committed, the edit-policy findings on it are expected; say they clear after the commit. Any other finding: report it and stop.

## Limits

The cutoff Evolve sets is fixed once the contract is replaced. This skill never edits a cutoff already in the contract, and a human who wants a different date edits the contract by hand.

This skill edits the contract, its rulebook and the notes the agreed plan names. It adds a `Charter-Allow` trailer only after the human's explicit yes for that note, in a commit that yes allowed. It never pushes, merges, rebases, amends or resets, creates a branch unasked, or sets a commit pattern, and it installs nothing.
