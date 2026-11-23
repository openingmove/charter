# Moving content

One section per kind of `Progress` line. Source prose moves verbatim: the same characters, in the same order, with no rewording, tidying or summarising. Rewording happens only when the human asks, as its own step after the move: add a `- [ ]` line for it to `Progress` and do it then. Edit with your file tools; use no shell redirection, script or OS-specific command.

## `Created TARGET`

1. Find the plan's parts that name `TARGET`, in source order. Several parts may share one target. With a `Source` bullet, read each source file at its path inside the source folder.
2. Run `charter new --config <draft> KIND "TITLE"`, with `KIND` from the map and `TITLE` the target's filename without `.md`. Add `--set FIELD=VALUE` for a field value the human gave, and `--set FIELD=DATE` for the date the plan's `Dates` section lists for `TARGET` (the kind's cutoff field), so the note is dated when it is created. Ask the human for any required value the source cannot supply, and invent none. When `charter new` refuses with an `ids/gap` finding on `charter.yaml` (it exits 1), the note's `id` would leave a gap in a `contiguous` collection, because a note with a lower `id` is not created yet: move the unticked `Created` line of each missing lower-`id` note above this one, and work those lines first. When no unticked line creates a missing `id`, or the gap stays, stop, tell the human, and leave the line unticked until they fix the plan or the draft. When it refuses with an `ids/count` finding, the note would push its kind's `collection` past its `count`: stop, tell the human, and leave the line unticked until they fix the plan or the draft.
3. Check the path charter printed is `TARGET`. If not, tell the human and fix the plan or the draft with them.
4. When `charter new` reports `new/exists` (it exits 1), run `charter validate --config <draft> --file TARGET`. A file with a `schema` or `filenames` finding (no frontmatter, wrong fields, another kind) was not made by `charter new` from this draft, or was broken after it did: tell the human what the validation reports and do not overwrite, move or delete it, and leave the line unticked until they say what to do (a different `TARGET` in the plan, or they remove or fix the file). Any other file looks like one `charter new` made in an earlier session or for an earlier part, though validation cannot prove who wrote it: read it, and when its body is not the template's body plus the prose of the earlier parts, tell the human and ask before adding anything; otherwise add only what is missing.
5. Copy each part's paragraphs from the source into the note, after what `charter new` wrote (the frontmatter, then the template's body), inside the template's sections when it has them. A source heading line whose words are the note's title is left out (the title carries it). When a part's heading differs from the note's title, ask the human once per note and do what they choose: keep the heading line (the default when in doubt, and nothing is lost); retitle, so the note's `title` takes the heading's words and the heading line is left out (when the filename follows the title, the `TARGET` changes: update the note's row in the `Section map` and its `Created` line, ticked or not, and have the human confirm the new `TARGET` before the move continues); or drop the heading line, which the completeness pass then lists for the human to confirm as dropped. Every other heading line stays, at whatever level fits the note.
6. Run `charter validate --config <draft> --file TARGET` and settle each finding with the human, except `links/unresolved`, which waits for the source check below.

Done when `charter new` printed `TARGET` (or reported `new/exists` for it on resume, with the note passing the checks of step 4), the note holds every paragraph of its parts and its validation shows nothing else. Tick the line only then: a note you wrote any other way does not count, however well it validates.

## `Source SRC checked complete, then removed or kept`

With a `Source` bullet in the plan, the source is read-only: follow step 1 below, then tick this line without asking and without sweeping, deleting or giving the source a path policy. It is kept. Skip steps 2 to 5.

When the source is already missing: with `Completeness of SRC checked` ticked, an earlier run deleted it, so tick this line; with that line unticked, stop and tell the human, who restores from the way back.

1. Follow [completeness.md](completeness.md). It ends with an empty list. Then insert the line `- [x] Completeness of `SRC` checked, list empty` above this one, before anything is deleted.
2. Ask the human whether to delete the source or keep it. Offer keeping, and keep it when they are unsure.
3. Kept: add `"SRC": {untyped: allow, edit: read-only}` under `paths:` in the draft, so the source stays as received and the finished contract validates clean.
4. Deleted: first run `charter sweep SRC --config <draft> --format json`. For each `linked_from` entry (`path`, `line` and the link as written in `raw`), open the note and point the link at the target that now holds the linked part (a link with a heading, `[[SRC#Heading]]`, goes to the target of that heading's part). Ask the human where a link should go when its content split over several targets. Report each `mentioned_in` entry (a plain-text name, not a link) and change none. Then delete the source. When the source is gone before you sweep it, `links/unresolved` in step 6 finds what is left.
5. A link inside a source that is still waiting its turn stays as written; when that source's targets exist and its own check is done, repoint the links that `charter validate --config <draft> --file TARGET` reports as `links/unresolved`. A repointed link changes a paragraph, so repoint after the check, never before.

Done when the source is deleted with its links repointed, or kept with its path policy (with a `Source` bullet: kept, and nothing under the source folder touched). Tick the line.

### Links in the new notes (a plan with a `Source` bullet)

A link in copied text that points at an old document is `links/unresolved` when you validate the new note, because the old document lies outside the knowledge base. After the source's completeness check, point each such link at the new note that holds the linked part (a link with a heading goes to the target of that heading's part), and ask the human when the content split over several targets. A link to a file that is not Markdown (an image, say) cannot resolve: list each one to the human, who decides, since Migrate copies no file.

## `Date NOTE: DATE`

Set the kind's cutoff field (the `Dates` kind bullet names it) in `NOTE`'s frontmatter to `DATE`, an unquoted `YYYY-MM-DD`, and touch nothing else in the note. Read the draft's cutoff first: a `DATE` on or after it means the plan is stale, so stop and compute the dates again as [dates.md](dates.md) says. Run `charter validate --config <draft> --file NOTE`.

Done when the note holds the date and its validation shows no `schema` or `structure` finding. Tick the line.

## `Fix NOTE: FIX`

Apply the fix to `NOTE` in place, with the frontmatter or heading edit the plan format's table describes, and touch nothing else in the note. For `rename file -> NEWPATH`, run `charter sweep NOTE --config <draft> --format json` first, write the note at `NEWPATH` with its content unchanged, delete the old path, and repoint each `linked_from` entry. Then run `charter validate --config <draft> --file NOTE` (or `NEWPATH`).

Done when the fix shows in the note and its validation shows nothing new. Tick the line.

## `Fix NOTE: add frontmatter KIND` and `Fix NOTE: set FIELD=VALUE`

These bring a note that stays where it is (a `migrate in place` folder) to fit the contract. No file moves and no part of a `Section map` is involved, so the completeness rule is its own: **the note's old text survives untouched below the new block.**

`add frontmatter`:

1. Read `NOTE` and keep its exact text. When it already starts with a frontmatter block (`---` on the first line), stop: the plan is stale, so tell the human and change nothing.
2. Run `charter describe --config <draft>` for the kind `KIND`: it gives the discriminator field and the order of the fields. Insert, at the very top of the file, a block that opens and closes with `---` and holds the discriminator field set to `KIND` and the `title`, which is the words the human gave, else the file name without `.md`. Keep the file's own line ending.
3. Read the file again. The text below the closing `---` must equal the text you kept, character for character: nothing reworded, trimmed, reflowed or dropped, and a heading line stays even when it repeats the title. Where it differs, put the original back and tell the human.

`set FIELD=VALUE`: add the field to the note's existing frontmatter block, in the order `charter describe` gives, with the value as the plan wrote it (a date unquoted, as `YYYY-MM-DD`). Touch nothing outside the block. When the note has no block yet, an `add frontmatter` line comes first in the plan; if it is missing, stop and tell the human.

Then run `charter validate --config <draft> --file NOTE`.

Done when the block is in place, the text below it is unchanged, and the validation shows no `schema` finding that a plan line still has to fix. Tick the line.

