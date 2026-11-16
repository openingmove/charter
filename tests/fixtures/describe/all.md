# Kinds

## `recipe`

A dish worth cooking again.

- Path: `docs/Recipes/{id} {title}.md`.
- Template: `docs/Templates/Recipe.md`.
- Undeclared fields: an error.
- All `recipe` notes together: exactly 50 notes, `id` values run without gaps.
- Variants, each with its own section: a note with these values is the variant, not the plain kind.
  - `recipe/bread`: `method` is `bake`.

Create one with:

```
charter new recipe "TITLE" --set method=METHOD
```

A value that selects a variant creates that variant instead: use the variant's own command.

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `recipe` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `id` | yes | an integer, from 1 to 99; unique among `recipe` notes; `charter new` fills in the next free value |  |
| `title` | yes | a string; matches its part of the file name | The dish's name. |
| `stage` | yes | a string, one of `idea`, `tested`, `published`; default `idea` |  |
| `method` | yes | a string, one of `bake`, `fry`, `raw`; `bake` makes it `recipe/bread` |  |
| `serves` | no | an integer, from 1 to 12 |  |
| `code` | no | a string, matching `R\d+\|X` |  |
| `published_in` | when `stage` is `published` | a string |  |
| `tested_on` | no | a date (YYYY-MM-DD); allowed only when `stage` is `tested` or `published` |  |
| `added` | yes | a date (YYYY-MM-DD); `charter new` fills in today's date |  |

### Body outline

- `# {{title}}`: why it is worth cooking again
- `## Ingredients`
- `## Method`
- `## Variations` (optional)

## `recipe/bread`

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

### Fields

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

### Body outline

Start from the flour you have.

- `# {{title}}`
- `## Dough`
- `## Bake {{date}}` (repeat)

## `pantry`

- Path: `docs/Pantry/{shelf}/{title}.md`.
- Undeclared fields: allowed.
- Variants, each with its own section: a note with these values is the variant, not the plain kind.
  - `pantry/dry`: `shelf` is `dry`.
  - `pantry/cold`: `shelf` is `cold`.

Create one with:

```
charter new pantry "TITLE" --set shelf=SHELF
```

A value that selects a variant creates that variant instead: use the variant's own command.

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `pantry` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `title` | yes | a string |  |
| `stocks` | no | a list, each item a link, linking to `recipe` |  |
| `shelf` | yes | a string, one of `dry`, `cold`; `dry` makes it `pantry/dry`; `cold` makes it `pantry/cold` |  |

## `pantry/dry`

- Variant of `pantry`: a `pantry` note is this variant when `shelf` is `dry`.
- Path: `docs/Pantry/{shelf}/{title}.md`.
- Undeclared fields: allowed.

Create one with:

```
charter new pantry/dry "TITLE"
```

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `pantry` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `title` | yes | a string |  |
| `stocks` | no | a list, each item a link, linking to `recipe` |  |
| `shelf` | yes | always `dry`, which makes the note this variant |  |

## `pantry/cold`

- Variant of `pantry`: a `pantry` note is this variant when `shelf` is `cold`.
- Path: `docs/Fridge/{title}.md`.
- Undeclared fields: allowed.

Create one with:

```
charter new pantry/cold "TITLE"
```

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `pantry` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `title` | yes | a string |  |
| `stocks` | no | a list, each item a link, linking to `recipe` |  |
| `shelf` | yes | always `cold`, which makes the note this variant |  |

## `note`

- Path: none declared.
- Undeclared fields: an error.

`charter new` cannot create one: it has no path.

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `note` |  |
| `tags` | no | a list, each item a string | Free-form labels. |
| `title` | no | a string |  |
| `since` | no | a date (YYYY-MM-DD); default `2026-01-31` |  |

# Path policies

Globs are relative to the knowledge-base root, `docs`; the paths above are relative to the directory holding charter.yaml. Each key takes its value from the most specific matching glob.

| Glob | Policy |
|---|---|
| `Templates/**` | ignored: not notes, never validated |
| `Recipes/**` | only kinds `recipe` |
| `Recipes/Drafts/**` | files need no kind; links are not checked |

# Checks

| Check | Enabled | Severity | Codes |
|---|---|---|---|
| `schema` | yes | base | `schema/enum`, `schema/item-type`, `schema/missing-frontmatter`, `schema/missing-kind`, `schema/not-allowed`, `schema/pattern`, `schema/range`, `schema/required`, `schema/type`, `schema/unknown-field`, `schema/unknown-kind`, `schema/unknown-variant` |
| `filenames` | yes | base | `filenames/matches-filename`, `filenames/path`, `filenames/unsafe-value` |
| `paths` | yes | base | `paths/create-only`, `paths/edit-deferred`, `paths/edit-skipped`, `paths/kind-not-allowed`, `paths/read-only` |
| `links` | yes | warning | `links/ambiguous`, `links/missing-anchor`, `links/unresolved`, `links/wrong-kind` |
| `ids` | yes | base | `ids/count`, `ids/duplicate`, `ids/gap` |
| `tags` | no | base | `tags/not-allowed` |
| `structure` | yes | base | `structure/heading-order`, `structure/missing-heading`, `structure/repeated-heading` |
| `residue` | yes | base | `residue/guide`, `residue/placeholder` |
| `agents-include` | yes | base | `agents-include/missing-file`, `agents-include/missing-link`, `agents-include/stale` |
| `updated-date` | no | base | `updated-date/skipped`, `updated-date/stale` |
| `protected-region` | no | base | `protected-region/changed`, `protected-region/deferred`, `protected-region/skipped` |
