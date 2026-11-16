# Templates

Detail of steps 6 and 9: section 1 is step 6 (asking, before anything is written), the rest is step 9. A template is the part of a kind a domain person can judge: a sample note, not YAML. Settle it before approval and before Migrate. It drives what `charter new` writes and which headings `structure` checks, and a template added after notes exist makes a `structure/missing-heading` finding on every old note (that is Evolve-with-fallout work).

## 1. Ask, per kind

Ask in domain terms, one kind at a time: "Does every meeting note have the same sections?", "Which ones?", "Is each section always there, or only sometimes?". Never mention YAML, `structure` or placeholders.

Ask it even when the survey found no outline. A sparse folder has no frontmatter, and `folders[].outline` is empty for plain prose, yet the interview and the section map you propose are the only source of structure. When `outline` is not empty, or the interview has named sections, offer those as the starting point.

"No template" is a valid answer: the kind's notes then start from frontmatter alone and `structure` has nothing to check. Record it as a YAML comment above the kind in the draft, `# template: none, the notes share no outline`. `charter init --from` copies the draft byte for byte, so the comment survives into the contract.

## 2. Write the file

For each yes, write `Templates/<Kind>.md` in the knowledge-base folder (a new file; no existing note changes), then in the draft name it in the kind, `template: Templates/<Kind>.md`, and add `"Templates/**": {ignore: true}` under `paths:` once, so charter never validates a template as a note. These rules are the CLI's own:

- Body only. Fields, defaults and `auto` values belong in the draft.
- `{{title}}`, or `{{FIELD}}` for any field the kind declares, and `{{date}}` (the day a note is created) are filled by `charter new`. A heading with a placeholder (`# {{title}}`) matches any text.
- `<!-- guide: ... -->` is a hint for whoever fills the note in; it goes on a heading's line or the line after it. `charter new` copies it, and `charter validate` reports it (`residue/guide`) in any note that still holds it.
- `<!-- optional -->` and `<!-- repeat -->` go on a heading's line or the line after it. A required heading must appear in every note, in the template's order.
- Placeholders and markers inside code are literal text.

**Make the headings optional when the notes come from loose prose.** If the existing notes are prose with no shared headings (a sparse start, or a kind the interview defined from scratch for such papers), put `<!-- optional -->` on every heading below `# {{title}}` (and on `# {{title}}` itself when notes that stay where they are lack a title heading), so a rigid template does not make every such note fail `structure` with `structure/missing-heading`. Required headings are for what the human said is always there. Tightening them later is an Evolve change.

### Worked example

A draft for the sparse example, with one kind that has a template and one that has none:

```yaml
charter: 1
root: .

paths:
  "README.md": {ignore: true}
  "Templates/**": {ignore: true}
  "archive/**": {untyped: allow, edit: read-only}

kinds:
  story:
    description: "One episode of the town's history."
    path: "stories/{title}.md"
    template: Templates/Story.md
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
  # template: none, the notes share no outline
  person:
    description: "Someone who shaped the town."
    path: "people/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
```

and its template, `Templates/Story.md`:

```markdown
# {{title}}
<!-- guide: one line on why this episode matters -->

## What happened <!-- optional -->

## Who was there <!-- optional -->

## Sources <!-- optional -->
```

## 3. Show it and pause

Show each template to the human as a sample note: the file's lines with the title filled in by hand in your message (do not run `charter new` to render it, which writes a note), next to the kind's "Body outline" in `charter describe --config <draft> KIND`. Tell them the file's path, say they may read it and edit the file themselves, or tell you what to change and you edit it. Then stop and wait until they say they are done. Do not go on while they have not answered.

## 4. Rerun the description

After the human's edits, and after any edit of yours, run `charter describe --config <draft>`. Exit 2 is a load error, reported as `contract/invalid` on `kinds.<kind>.template`. Tell the human in plain words which template and line, and fix it with them:

| Message says | Cause | Fix |
|---|---|---|
| `has frontmatter` | the file starts with a `---` block | delete the block; the draft declares the fields |
| `is not a field of` | a `{{name}}` that is no field of the kind (nor `{{date}}`) | declare the field in the draft, or change or remove the placeholder (in code it is literal) |
| `follows no heading` | an `<!-- optional -->` or `<!-- repeat -->` with no heading on its line or the line before | move it onto its heading, or delete it |
| `does not exist` | `template:` names a file that is not there | write the file, or correct the path (relative to `root`) |

Rerun until it exits 0. When the human decides a kind does not need its template after all, delete the file and the `template:` line, and record "no template" for the kind.

## 5. The hand-off

On the hand-off path the plan's `Draft contract` section lists the template files ([migration-plan.md](migration-plan.md)). The plan does not say which template section each part of the section map lands in: Migrate decides that at move time from the template, as [../migrate/moving.md](../migrate/moving.md) says. Establish never applies a template to an existing note.
