# Reading the survey

`charter survey <folder> --format json` prints `charter-survey/1`. The README's "Surveying a folder" section describes every key.

## Starting point

Use `totals` (`files`, `with_frontmatter`):

- **Empty**: no Markdown files, or only a README. A README that describes an idea is the first interview answer.
- **Sparse**: Markdown files exist and fewer than half carry frontmatter (`with_frontmatter` under half of `files`), so there are no field conventions to read.
- **Mature**: at least half carry frontmatter. Folders, field names, values and filename shapes are the conventions to carry over.

A close call goes to the human: say the numbers and ask.

## What to read

- `folders[]`: `filename_shapes` suggest path patterns; `outline` suggests a template, but ask the template question for every kind even when `outline` is empty, as [templates.md](templates.md) says: prose with no shared headings leaves it empty, and the interview is then the only source of a kind's outline; `fields[]` gives how many files in the folder carry each field.
- `fields`: for each field, `files`, `types` and `values` (each with `count` and example `files`). Values are counted across all folders, so open the example files to see which kind uses a value.
- `links`: which of `wikilink` and `markdown` the notes use.
- `rulebooks` and `agent_files`: read every one. A hand-written rulebook states rules the files cannot show (allowed values, forbidden fields, append-only notes). Ask the human whether the new rulebook replaces it, and whether to keep or retire the old document.

## Large folders

When `totals.files` is over about 300, or the file list is too long to read, do not read every file.

1. Work by group: each entry of `folders[]`, and each `filename_shapes` entry inside it. Read three to five files of a group (its largest, its newest, one from the middle of the sorted list), and every file of a group under five. Tell the human which files you read and that the rest are inferred from the survey's counts.
2. Take the typo, partial-field and title calls from the survey's `fields` counts, which cover every file, and open only the example files they list.
3. Plan in batches. Only the groups you read and the human agreed may be `migrate` or `migrate in place`; mark the others `leave as it is` for this run and say they can be brought in later with `/charter:evolve`. Keep a `migrate` folder to about 30 source files per run, since every source needs a map and a completeness check.

## Finding judgement calls

Each of these is a question to the human, never a silent fix.

- **Likely typo.** A value with a low `count` that sits close in spelling to a common value (`tesetd` next to `tested`). Check any rulebook that lists the allowed values.
- **Field on only some notes.** A field whose `files` count in `folders[].fields` is lower than the folder's `files` (two recipes with `oven_temp_f`, one bake with `rating`). Is it intended, or stray? A rulebook that forbids extra fields settles the question for the human to confirm.
- **Title that differs from its filename.** `fields.title.values` pairs each title with an example file. Compare the title with the filename (when a title already contains the date, as in `2026-03-02 Rye Loaf`, the filename pattern is `{title}`, not `{date} {title}`). When `truncated` is true, only 20 values are listed: read the `title:` line of the remaining files.
- **One field name, different meanings.** The same field (`status`) holding different values in different folders. Check the example files; propose a separate vocabulary per kind and confirm.
- **Mixed types.** A field whose `types` lists more than one type.
- **Disagreement.** The rulebook says one thing and the survey shows another.

Done when you hold the list of judgement calls, each with the file paths that show it.
