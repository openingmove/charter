# Interview

Ask about the domain in the human's words. Fields, vocabularies, folders and YAML are your job to propose, and a question about them goes back as a proposal ("I would give each piece a composer and a difficulty; is that right?").

Ask one question at a time. Start from what the survey and the documents already answer, and ask only for what they leave open. In an empty folder a README or an idea paragraph counts as the first answer: read it, then confirm it back.

Cover these four, in order:

1. **What it holds.** What things will the knowledge base keep notes about? What does the human want to find in it a year from now?
2. **How things relate.** Which things belong to, follow, mention or depend on which others? When one thing refers to another, should a reader be able to jump straight to it?
3. **How many.** Roughly how many of each: a handful, dozens, hundreds? Do any have to be numbered, kept in sequence or dated?
4. **How they change.** Which things are written once and never changed, such as decisions or minutes? Which go through stages, such as draft, final, retired? Which folders must stay as they are?

Done when you can state, for each thing: what it is, what it links to, roughly how many, and whether and how it changes.

Answers become the draft this way:

| The human says | You propose |
|---|---|
| a thing they keep several of | a kind, a folder and a filename pattern |
| a thing that belongs to or follows another | a link field to that kind |
| a numbered or dated series | an `id` or `date` field and a path using it |
| stages | a field with a fixed list of values, and fields required only at some stages |
| never changes, written once | `edit: create-only` (new notes may be added) or `edit: read-only` (no files at all) for its folder |
| never changes, but later amendments are added below a marked line | the `protected-region` check on its kind |
| a file that is only ever appended to, inside a folder that never changes | no `edit:` value lifts the policy for one file: a file under an `edit: create-only` or `edit: read-only` glob cannot be appended to. An `ignore: true` rule for the file would lift it, but the file then stops being a note. Tell the human the file must move out of that folder |
| leave this folder alone | `untyped: allow` with `edit: read-only` for it |
| a recurring outline | a template |
