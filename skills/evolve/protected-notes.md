# Protected notes

A protected note is under `edit: read-only`, `edit: create-only` or the protected-region check. Its text is guarded on purpose, so it changes only on the human's explicit word, given in this session.

## Agreement

1. List the protected notes in the plan's `Protected notes` section with `agreement: pending`.
2. Ask the human during the plan (step 5), after the shapes in [fallout.md](fallout.md) are offered and before any edit: which notes would change, what changes in each, and that charter will report each change as a violation until a commit records the decision with a `Charter-Allow` trailer. Ask per note or per set stated clearly ("the three decisions in `decisions/`"). A set covers exactly the notes it names.
3. Set `agreement: yes` or `no` on each covered bullet at once. A `no` means that note stays as it is: tell the human what that leaves failing and offer a shape that keeps it valid, such as the old value kept allowed.
4. A note that turns out to be protected later (step 7 validation reports `paths/*` or `protected-region/changed` on a note not listed) is restored with `git restore` if you edited it, added to the section as `pending` and asked about. Without git, undo the single edit by hand from the plan's fix line.

Nothing counts as agreement but a clear yes from the human for that note or set. Silence, an earlier yes to the plan as a whole and "do what you think best" do not.

## Edit the note

Edit a protected note only with `agreement: yes` recorded in the plan's `Protected notes` section, changing only what its fix line says. Then run `charter validate --config <draft> --format json`. The diagnostics on that note give the exact `code` and `path` pairs the commit must allow. Every trailer uses the code and path charter prints, as printed, and `charter validate --staged --commit-msg` confirms them. A frontmatter-only edit to a note with a protected region raises only its path-policy code (for example `paths/create-only`), never `protected-region/changed`, which a change to the body raises.

## Commit with trailers

Under git, and only after every yes above and after step 8 (so contract, rulebook and notes agree):

1. Ask the human whether you commit or they do. If they commit, give them the trailer lines below and the list of files, and stop here.
2. Write the message to a file outside the knowledge base (your scratch folder), with your file tool: a subject line, a blank line, then one final block of trailers, one per file and code, each `Charter-Allow: CODE PATH — REASON`. The reason is required: use the human's own words from the agreement. Separate `PATH` and `REASON` with an em dash.
3. Stage the notes, the contract file and the rulebook this run changed, by name: `git add -- PATH ...`.
4. Run `charter validate --staged --commit-msg FILE` (with `--config <contract>` when the contract is not the nearest `charter.yaml`). Done when it reports no `override/unused` or `override/invalid` and no error. Fix the trailer lines and run it again otherwise.
5. Run `git commit -F FILE`. A failing hook is reported, never skipped (no `--no-verify`).

This is the only commit Evolve makes. It never pushes, amends, rebases or resets, and it asks for no other commit pattern or message style. Without git, edit policies are skipped and there is nothing to commit.

When the edit-policy findings remain after a hand commit, `charter validate --range` over that commit judges it with its trailers; a plain `charter validate` reports the committed state clean.
