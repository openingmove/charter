# Contract syntax

`charter init` writes a starter contract (see [Starting a contract](Commands.md#starting-a-contract)).

Or put a `charter.yaml` next to your knowledge base yourself:

```yaml
charter: 1
root: docs                 # the knowledge base, relative to this file
discriminator: kind        # frontmatter field naming a note's kind (default: kind)

paths:                     # glob (relative to root) -> policy; the most specific glob wins, per key
  ".obsidian/**": {ignore: true}       # not notes: never indexed or validated
  "Books/**":     {kinds: [book]}      # only these kinds may live here
  "Archive/**":   {untyped: allow, edit: read-only}  # left alone: files need no kind, and none may be added, changed or deleted
  "Research/**":  {edit: create-only}  # new files may be added; existing files may not change or be deleted
  "Journal/**":   {sweep: false}       # left out of `charter sweep` results

kinds:
  book:
    fields:
      kind:   {type: string, required: true}
      title:  {type: string, required: true}
      pages:  {type: int}
      author: {type: link, required: true}
```

Field types are `string`, `int`, `number`, `bool`, `date` (`YYYY-MM-DD`), `link` and `list`. A field may also carry these rules:

```yaml
vocabularies:              # named value sets, shared across kinds
  stage: [idea, draft, locked, cut]

kinds:
  scene:
    fields:
      stage:   {enum: stage, required: true}              # a vocabulary; implies string
      size:    {values: [small, large]}                   # an inline value set
      tones:   {type: list, of: enum, values: [sweet, dark]}
      minute:  {type: int, range: [0, 60]}                # inclusive
      number:  {type: int, width: 4}                      # written 0001, stored as 1
      code:    {type: string, pattern: 'S\d{3}'}          # must match the whole value
      tags:    {type: list, of: string}
      reason:  {type: string, required_when: {stage: cut}}
      locked:  {type: date, allowed_when: {stage: [locked, cut]}}
      pager:   {type: string, allowed_when: {tags: urgent}}
```

- `of` sets the type of a list's elements. `enum`, `values`, `range` and `pattern` apply to each element of a list. On a list without `of`, a value set or `pattern` implies string elements, and `range` implies number elements.
- `width: N` (a positive whole number, on an `int` field only) zero pads the value to at least `N` digits wherever it becomes text: the `{field}` part of a `path`, the `matches_filename` comparison, `{{field}}` in a template filled by `charter new`, and the id `charter sweep` looks for in prose. With `width: 4`, `1` is written `0001` and `10000` stays `10000`; use `range` for a hard limit. A negative value keeps its minus sign in front of `N` digits: `-7` is written `-0007`. The padded text is the only correct spelling, so `1 Title.md` in a kind whose path pads `id` is misplaced. Frontmatter still holds the plain integer (`id: 1`): do not copy the padded text into it, because YAML reads `id: 0010` as the octal number 8 and `id: 0009` as text, a `schema/type` error. `range`, `unique`, `auto: next` and `collection` work on that integer. Changing `width` renames nothing: `validate` reports each note the change misplaces, and links must name the new file name exactly.
- `default: VALUE` and `auto` are what `charter new` writes when no value is given. `auto: today` fills a `date` field with the day the note is created; `auto: next` fills a `unique` `int` field with its smallest free value, counting from the `range` minimum (or 1). A field has at most one of them, and a `default` must be a value the field may hold.
- `required_when` and `allowed_when` take `{field: value-or-list}`. A condition holds when the field equals the value, or one of the listed values. When the condition names a list field, it holds when the list contains one of the values. A field with several conditions needs all of them to hold. A condition value the named field could never hold (wrong type, outside its allowed values, `range` or `pattern`, or, for a `variant_by` field the kind does not declare, not a variant name) is a contract error. An `allowed_when` field present while its conditions fail is an error. `required: true` cannot be combined with either; use `required_when` to require a field exactly when it is allowed.

In `paths:` globs, `*` and `?` match within one folder and `**` matches any number of folders. Either `/` or `\` separates folders. Policies resolve per key: each key (`ignore`, `kinds`, `edit`, …) takes its value from the most specific matching glob that sets it, so a narrower glob overrides only the keys it names. A glob is more specific when it has more literal (non-wildcard) characters; on a tie, the first declared wins. `ignore: true` cannot be combined with other keys on the same glob.

## Path patterns

A kind's `path` derives each note's file path from its own fields, so filenames and frontmatter cannot drift apart:

```yaml
kinds:
  decision:
    path: "Decisions/{id} {title}{status|suffix}.md"   # relative to root
    suffix: {deferred: " (Deferred)", dropped: " (Dropped)"}
    fields:
      id:     {type: int, required: true}
      title:  {type: string, required: true, matches_filename: true}
      status: {enum: status, required: true}
```

- A placeholder `{field}` renders the field's value: text as it is, numbers in plain decimal (`id: 007` is the number 7 and renders as `7`; `0.5` as `0.5`) unless an `int` field sets `width`, dates as `YYYY-MM-DD`, booleans as `true`/`false`. A value that does not match the field's declared type is left to `schema/type` and the path is not checked. Filters follow a `|` and apply left to right: `suffix` maps the value through the kind's `suffix:` table (nothing when unmapped or missing), `lower` lowercases, and `slug` lowercases, drops accents and joins words with `-` (`Storm at the Quay!` becomes `storm-at-the-quay`).
- A note whose path differs from the rendered one is a `filenames/path` error naming the expected path. Placeholders must name single-value fields of the kind that are `required: true`, unless rendered through `suffix`.
- `matches_filename: true` on a field requires its value to equal its `{field}` part of the path (`filenames/matches-filename`), which pinpoints a renamed file. The path must then contain the placeholder without filters. When the literal text between two such placeholders does not settle which part is which, the note gets `filenames/path` instead. A kind without `path` may still use `matches_filename`: the value must then equal the filename without `.md`, in whatever folder the note lives.
- Rendered paths must work on every platform. A value that would put `/` or `\`, a character Windows forbids (`<>:"|?*`), or a control character into the path, that leaves a file or folder name empty, `.` or `..`, ending in a dot or space, or a reserved Windows name (`CON`, `NUL`, `COM1`, …), is a `filenames/unsafe-value` error at that field; render such fields through `slug`, whose output is always safe. The same rules apply to the literal text of the pattern itself, checked when the contract loads (`contract/invalid`).
- The pattern may use `/` or `\` between folders and renders the same on every platform; Unicode composed and decomposed forms of the same name count as equal.

## Variants

A variant is a sub-shape of a kind with its own `path` and extra `fields`, so a related shape needs no separate kind:

```yaml
kinds:
  boat:
    path: "Boats/{title}.md"
    fields:
      title:      {type: string, required: true}
      propulsion: {values: [sail, motor, oar], required: true}
    variants:
      sailboat:
        set: {propulsion: sail}          # a note is this variant when every `set` value matches
        path: "Sailboats/{title} ({rig}).md"
        fields:
          rig: {values: [sloop, ketch], required: true}
  log:
    variant_by: log_type                 # the field's value names the variant
    fields:
      title: {type: string, required: true}
    variants:
      voyage: {path: "Logs/Voyages/{title}.md", fields: {boat: {type: link, to: boat}}}
      repair: {path: "Logs/Repairs/{title}.md"}
```

- A variant's fields are checked alongside its kind's; a variant field may redeclare a kind field, except one that selects the variant. A field neither declares is `schema/unknown-field`. A variant without its own `path` keeps the kind's.
- `set` names single-value fields of the kind, each with a value the field may hold. Variants selected by `set` must be mutually exclusive: every two of them must `set` some shared field to different values, so a note is never two variants at once. This is a deliberate rule, checked when the contract loads.
- With `variant_by`, a value naming no variant is `schema/unknown-variant`. If the kind does not declare the field, it is a required text field; if it does, it must be single-value text without `enum` or `values`, since the variant names are its allowed values. `variant_by` and `set` cannot be combined, and `variant_by` cannot name the discriminator itself.
- Kind, variant and field names must be text. YAML reads `1`, `yes`, `no`, `on` and `2026-01-01` as other types, so a contract that uses one as a name is `contract/invalid` until it is quoted (`"on":`).
- A variant's `path` may use a field its selection guarantees (its `set` fields or the `variant_by` field) without `required: true`.

## Unique fields and collections

Numbered sets stay complete and collision-free with `unique` fields and a kind's `collection`:

```yaml
kinds:
  thing:
    fields:
      id:    {type: int, required: true, unique: true, range: [1, 100]}
      title: {type: string, required: true, unique: true}
    collection: {count: 100, contiguous: id}
```

- A `unique` field's value must not appear on any other note of the kind, variants included. Each note sharing it gets `ids/duplicate` naming the others; uniqueness is judged against the whole knowledge base even under `--file`. A field `unique` in one variant but not another is one-sided: only notes of the variant that declares it `unique` are reported, though they are compared with every note of the kind. `unique` applies to single-value fields. Missing values, and values of the wrong type, are left to `schema`.
- `collection.count` is the number of notes the kind must have (`ids/count`). `collection.contiguous` names an `int` field of the kind whose values must run without gaps (`ids/gap`), from the field's `range` minimum if it has one, otherwise from its smallest value, up to its largest value (or the `range` maximum, past which values are `schema/range`). Every note of the kind counts, including notes of a variant and notes whose `variant_by` value names no variant. Both are reported at the `collection` in `charter.yaml`, and `--file` runs report them whenever one of the files is a note of the kind, a note of the kind deleted from the working copy that git still tracks (its kind is read from `HEAD`), or `charter.yaml` itself.

For a complete contract to read or try, see the example knowledge base in [`examples/garden`](../../examples/garden): four kinds (one with a variant), vocabularies, link fields, path policies, templates, a generated `CHARTER.md` and an `AGENTS.md` linking to it. Run `charter validate --all` from that folder.

## Links

Links are checked in every note's body and in its `link` fields, including notes without a kind. Each must resolve to exactly one file: an unresolved link and an ambiguous one are each reported. Links inside code (fenced, indented or inline) and HTML comments are ignored, as are URLs and backslash-escaped brackets.

```yaml
links:
  styles: [wikilink, markdown]       # which syntaxes count as links (default: both)
  resolve: [path, basename, alias]   # wikilink resolution order (default: this)
  check_anchors: false               # check `#heading` parts against the target's headings

paths:
  "Templates/**": {links: skip}      # notes here are not link-checked, but may still be linked to

kinds:
  book:
    fields:
      author:  {type: link, to: author}                   # must point at a note of this kind
      sources: {type: list, of: link, to: [book, paper]}
```

- **Markdown links** `[text](path)` are relative to the linking note's folder; `.md` may be omitted, and `%20` or `<…>` may hold spaces. A linked image `[![alt](img.png)](note.md)` checks both links. Reference-style links (`[text][ref]`) are not checked.
- **Wikilinks** `[[Target]]`, `[[Target|label]]`, `[[Target#Heading]]` resolve by the strategies in `resolve`, in order of precedence: the first strategy that matches anything decides, and later ones are not consulted. `path` is relative to `root`, `basename` is a filename (without `.md` for notes), `alias` is a value of a note's `aliases` frontmatter. Several matches from the deciding strategy make the link ambiguous; link by path to disambiguate. `basename` and `alias` never match files under an `ignore: true` path, though an explicit path may still name one.
- **Files outside `root`.** A Markdown link, or a wikilink written as a path (`[[../src/app.py]]`, relative to `root`), to an existing file beside or below `charter.yaml`'s directory resolves even when the file is outside `root`. Only existence is checked (no kind, no anchor), and the path must match in case on every platform. Names never reach outside `root`: `[[CLAUDE.md]]` matches under `root` only. A missing file, or a path that leaves `charter.yaml`'s directory, is `links/unresolved`. Only the named file is looked up, from the staged tree under `--staged`. A knowledge base inside a code repository can put `charter.yaml` at the repository root with `root` pointing at the vault folder. Existence follows symlinks and `.git` is not special, since the boundary is lexical like every contract path.
- A `link` field holds one link in either syntax, or a bare name resolved like a wikilink. A URL in a field with `to` is reported, since it cannot be a note of that kind.
- Headings are read as they render: HTML comments are not part of a heading's text, and a heading inside a comment is no heading. `#heading` anchors and the `structure` check both see headings this way.
- Matching is case-sensitive on every platform, so results do not depend on the file system. Paths use `/`; a `\` in a link path is not read as a folder separator. A link to a non-Markdown file (an image, a PDF) resolves when the file exists. A `.git` folder under `root` is never scanned.

## Tags

A tag allowlist keeps ad-hoc tags from proliferating:

```yaml
tags:
  allow: ["voyage/*", draft]         # every tag must match one of these globs
  inline: true                       # also check `#tags` in the body (default: false)
```

- Tags come from the `tags` frontmatter field (a list or a single value; since a tag holds no spaces, text with commas or spaces is split into several tags), on every note, including notes without a kind. With `inline: true`, `#tag` words in the body count too; those inside code, HTML comments or other words (`page#anchor`) do not.
- A leading `#` and trailing `/` are dropped, so `#voyage/` is the tag `voyage`. A name of only digits, `-` and `/` (`#123`, `#--`) is not a tag.
- Globs match tags level by level, as path globs match folders: `*` and `?` stay within one `/`-separated level and `**` spans any number of them, so `voyage/*` allows `voyage/north` but not `voyage` or `voyage/north/coast`. A tag with an empty level (`voyage//north`) matches no glob. Matching is case-sensitive.
- A tag no glob matches is `tags/not-allowed`. Without `tags.allow` no tag is reported; `allow: []` allows none.

## Templates

A kind, or a variant, may name a template: the body its notes start from and the outline they keep. Frontmatter belongs in `charter.yaml`, so a template is body only.

```yaml
paths:
  "Templates/**": {ignore: true}     # templates are not notes
kinds:
  recipe:
    template: Templates/Recipe.md    # relative to root
    variants:
      bread: {set: {method: bake}, template: Templates/Bread.md}
```

```markdown
# {{title}}
<!-- guide: one sentence on why this dish is worth making -->

## Ingredients

## Variations <!-- optional -->

## Notes from {{date}}
<!-- repeat -->
```

- `{{field}}` names a field of the kind or variant; `{{date}}` is the day a note is created. A variant without its own `template` keeps the kind's.
- The contract fails to load (exit `2`) when a template has frontmatter, a placeholder names no field, a marker follows no heading, or the file is missing.
- `<!-- optional -->` and `<!-- repeat -->` go on a heading's line or the line after it. An optional heading may be absent; a repeat heading may appear any number of times, its placeholders standing for any text.
- `structure` checks a note's headings against its template: each heading that is neither optional nor repeat must be present at the same level (`structure/missing-heading`), template headings must keep the template's order (`structure/heading-order`), and only repeat headings may appear more than once (`structure/repeated-heading`). Headings the template does not name are allowed.
- A heading with a placeholder (`# {{title}}`) matches any text, so it only counts where the template puts it: it takes the first suitable heading in sequence, and any other heading it would match is an extra heading. Order and repetition are judged by headings the template spells out.
- `residue` reports `<!-- guide: … -->` comments (`residue/guide`) and `{{placeholders}}` (`residue/placeholder`) left in any note, with or without a kind. To write about placeholders, put them in code.
- Placeholders, markers and headings inside code are literal text and do not count, and HTML comments are not part of a heading's text.

### Structure cutoff

A kind that adopts a template late has older notes that never followed it. Rather than lowering `structure` for the whole kind, which would also stop checking new notes, the kind may declare a cutoff:

```yaml
kinds:
  decision:
    template: Templates/Decision.md
    structure_cutoff: {field: created, date: 2026-01-01}
    fields:
      created: {type: date, required: true}
```

- A note of the kind whose `created` is before `2026-01-01` is a legacy note and is not judged on `structure`. A note dated on the cutoff day or later is judged as usual (the cutoff is inclusive).
- Only `structure` findings are exempt. Fields, links, residue, edit policies and every other check still judge a legacy note.
- A note whose date is missing, or is not a date (text, or a timestamp such as `2025-12-31T23:00:00`, which `type: date` does not accept), is not legacy: it gets its `schema` error and is judged on `structure` too, so a new note cannot escape by leaving its date out.
- The contract fails to load (exit `2`, `contract/invalid`, on the offending key) unless the kind has a `template`, `date` is an unquoted `YYYY-MM-DD` date, and `field` is a field of every note of the kind: declared on the kind or in `common_fields` as `type: date` and `required: true`. A field only a variant declares does not count, and a variant may not redeclare it as anything but a required date. Both keys are required, no others are allowed, and a kind has one cutoff.
- The verdict depends only on the note's own text and the contract, so `validate`, `--file`, `--staged` and `charter new` agree, and it works without version control. (`--range` judges history only, never `structure`.) A run prints nothing about the notes it skipped; `charter describe` and the rulebook state the cutoff for the kind.
- The cutoff is a value of the contract. Charter and its skills never move it; a person who wants a different date edits the contract by hand.
- Name a creation date such as `created`, not an update date such as `updated`: with an update date, editing a legacy note would move it past the cutoff and make it judged.
