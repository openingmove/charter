# Kinds

## `log`

A dated log entry.

- Path: `notes/{title}.md`.
- Template: `notes/Templates/Log.md`.
- Structure cutoff: a note whose `created` is before 2026-01-01 is a legacy note and is not checked against the template's headings; every other note, one without a valid date included, is.
- Undeclared fields: an error.

Create one with:

```
charter new log "TITLE" --set created=CREATED
```

### Fields

| Field | Required | Value | Description |
|---|---|---|---|
| `kind` | yes | names the kind: always `log` |  |
| `title` | yes | a string; matches its part of the file name |  |
| `created` | yes | a date (YYYY-MM-DD) |  |
| `related` | no | a link |  |

### Body outline

- `# {{title}}`
- `## Summary`
- `## Details`

# Path policies

Globs are relative to the knowledge-base root, `notes`; the paths above are relative to the directory holding charter.yaml. Each key takes its value from the most specific matching glob.

| Glob | Policy |
|---|---|
| `Templates/**` | ignored: not notes, never validated |

# Checks

| Check | Enabled | Severity | Codes |
|---|---|---|---|
| `schema` | yes | base | `schema/enum`, `schema/item-type`, `schema/missing-frontmatter`, `schema/missing-kind`, `schema/not-allowed`, `schema/pattern`, `schema/range`, `schema/required`, `schema/type`, `schema/unknown-field`, `schema/unknown-kind`, `schema/unknown-variant` |
| `filenames` | yes | base | `filenames/matches-filename`, `filenames/path`, `filenames/unsafe-value` |
| `paths` | yes | base | `paths/create-only`, `paths/edit-deferred`, `paths/edit-skipped`, `paths/kind-not-allowed`, `paths/read-only` |
| `links` | yes | base | `links/ambiguous`, `links/missing-anchor`, `links/unresolved`, `links/wrong-kind` |
| `ids` | yes | base | `ids/count`, `ids/duplicate`, `ids/gap` |
| `tags` | yes | base | `tags/not-allowed` |
| `structure` | yes | base | `structure/heading-order`, `structure/missing-heading`, `structure/repeated-heading` |
| `residue` | yes | base | `residue/guide`, `residue/placeholder` |
| `updated-date` | no | base | `updated-date/skipped`, `updated-date/stale` |
| `protected-region` | no | base | `protected-region/changed`, `protected-region/deferred`, `protected-region/skipped` |
