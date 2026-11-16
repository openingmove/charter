# `recipe/bread`

A recipe that rises.

- Variant of `recipe`: a `recipe` note is this variant when `method` is `bake`.
- Path: `docs/Recipes/{id} {title}.md`.
- Template: `docs/Templates/Bread.md`.
- Undeclared fields: an error.
- All `recipe` notes together: exactly 50 notes, `id` values run without gaps.

Create one with:

```
charter new recipe/bread "TITLE" --set proof_hours=PROOF_HOURS
```

## Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `recipe` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `id` | yes | an integer, from 1 to 99; unique among `recipe` notes; `charter new` fills in the next free value |  |
| `title` | yes | a string; matches its part of the file name | The dish's name. |
| `stage` | yes | a string, one of `idea`, `tested`, `published`; default `idea` |  |
| `method` | yes | always `bake`, which makes the note this variant |  |
| `serves` | no | an integer, from 1 to 12 |  |
| `code` | no | a string, matching `R\d+\|X` |  |
| `published_in` | when `stage` is `published` | a string |  |
| `tested_on` | no | a date (YYYY-MM-DD); allowed only when `stage` is `tested` or `published` |  |
| `added` | yes | a date (YYYY-MM-DD); `charter new` fills in today's date |  |
| `proof_hours` | yes | a number |  |

## Body outline

Start from the flour you have.

- `# {{title}}`
- `## Dough`
- `## Bake {{date}}` (repeat)
