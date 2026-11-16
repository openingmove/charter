# Fallout

Fallout is what the draft contract reports and the current contract does not. This file says what counts, how to group it and which change shapes avoid it.

## The stale rulebook is not fallout

A contract with `docs:` makes the draft run report a stale rulebook, because it compares the rulebook the draft would generate with the file on disk. Step 8 regenerates that file, so the finding says nothing about the notes.

Drop a draft diagnostic from the fallout only when all three hold:

- `code` is `agents-include/stale` (agent layer on) or `docs/stale` (rulebook without it).
- `path` is the rulebook file: the contract's `docs.output`, `CHARTER.md` when unset.
- It has no `line`.

Drop at most one finding. Any other finding on the rulebook path, such as `agents-include/missing-link`, a stale code on another path or one with a line, stays fallout.

## Group the findings

Read `path`, `line`, `code` and `message` of each fallout diagnostic. Group by note (`path`), then by cause (`code` plus the part of `message` that names the field or value). The report to the human is a short list: the cause in plain words, then the notes it hits. Findings on the contract file or on no note belong to the draft: fix the draft and compare again.

## Cutoff notes are not fallout

When the change sets a structure cutoff ([dates.md](dates.md)), a note dated before it produces no `structure` finding under the draft, as under the current contract, so the comparison needs no special case. Notes with no date yet are the fallout: each reports a `schema` finding for the missing date and `structure` findings, and the plan's `Dates` section answers all of them at once.

## Which notes are protected

A note is protected when the current contract guards it:

- a `paths:` glob with `edit: read-only` or `edit: create-only` matches it;
- `checks.protected-region` is enabled and lists its kind.

Read these from the contract. A note you cannot place counts as protected until the human says otherwise.

## Shapes that avoid touching notes

Offer these before any fix, in this order, whichever applies to the request. Say which affected notes each one keeps untouched, and let the human choose.

1. **Keep the old value allowed alongside the new ones.** To split `draft` into `idea` and `trial`, add both and keep `draft`; notes move over later or never.
2. **Make a new field optional.** Declare it without `required: true`.
3. **Require a new field only where it applies.** Use `required_when` on the field.
4. **Add a kind instead of reshaping one.** Existing notes keep their kind.
5. **Narrow a rule to part of the knowledge base.** Scope it with a `paths:` glob so protected folders stay out.

When the human picks a shape, edit the draft and compare again (step 3). When none fits or the human wants the full change, the remaining fallout goes into the plan.

## Before a rename or a retitle

Run `charter sweep NOTE --format json` for each note the plan renames or retitles. Each `linked_from` entry is a note that must change too: add it to the plan as a fix, and to the protected list when it is protected.
