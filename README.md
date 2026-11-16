# charter

Schemas, validation and scaffolding for Markdown knowledge bases.

`charter` reads a `charter.yaml` contract that declares the kinds of notes a knowledge base contains: their frontmatter fields, allowed values, where they live, how they are named, how they link to each other and what their body looks like. It then:

- **validates** the knowledge base against that contract (whole tree, staged files, or a single file),
- **scaffolds** new notes from per-kind templates (`charter new decision "Title"`),
- **describes** the rules to people and AI agents (`charter describe`, generated `CHARTER.md`),
- **sweeps** for notes affected by a change (`charter sweep <note>`),
- **runs plugins** for domain-specific checks, written in any language.

Editor-agnostic: plain Markdown with YAML frontmatter, Markdown links and/or `[[wikilinks]]`.

> **Beta.** charter is under active development. The command line, the contract format (`charter: 1`) and the skills may still change before 1.0; read the release notes before you upgrade, and pin a release tag in CI.
>
> Status: version 0.2.0, installed from this repository (not on PyPI). Delivered: the command line (`init`, `new`, `validate`, `describe`, `sweep`, `docs`, `survey`, `snapshot`, `plugin`), the optional agent, git and CI layers, and the Establish, Migrate and Evolve skills.

On this page: [The core](#the-core), [Optional layers](#optional-layers), [Install](#install), [Skills](#skills), then the reference, starting at [Usage](#usage).

## The core

charter works in a plain folder of Markdown. It needs no git, no AI agent and no CI. The commands:

| Command | What it does |
|---|---|
| `charter init [FOLDER]` | writes a commented starter `charter.yaml` in FOLDER, and nothing else |
| `charter new KIND "Title"` | creates a note at the path its kind renders, from the kind's template |
| `charter validate` | checks every note against the contract |
| `charter describe [KIND]` | explains the rules: kinds, fields, paths, checks |
| `charter sweep NOTE` | lists the notes that link to or mention NOTE, before you change it |

Two read-only tools support the skills below: `charter survey FOLDER` reports what a set of Markdown files holds before any contract exists, and `charter snapshot FOLDER` saves a zip of a folder you are about to change (`charter snapshot restore ZIP` puts it back).

A worked example. Run it in a scratch folder. First, a contract:

```
charter init novel
```

```
Wrote `novel/charter.yaml`.
Next: declare your kinds of note in `novel/charter.yaml`, then run `charter validate`.
```

Replace the starter's contents with one kind (the starter explains every line it holds):

```yaml
charter: 1
root: .

kinds:
  character:
    description: "A person in the story."
    path: "Characters/{title}.md"
    fields:
      kind:   {type: string, required: true}
      title:  {type: string, required: true, matches_filename: true}
      status: {values: [alive, dead], default: alive}
```

Then, from inside `novel`, create a note and check it:

```
charter new character "Mara"
```

```
Created `Characters/Mara.md` (character).
```

```
charter validate
```

```
No problems found (profile: commit).
```

Add a second note by hand, `Characters/Tomas.md`, with these six lines (no blank line after the closing `---`, so the body is line 6):

```
---
kind: character
title: Tomas
status: missing
---
Tomas is the brother of [[Mara]].
```

Now `charter validate` exits `1`:

```
Characters/Tomas.md
     4  error    schema/enum  Field `status` is `missing`, which is not in the allowed values.
        hint: Allowed values: `alive`, `dead`.

1 error, 0 warnings, 0 infos (profile: commit)
```

`charter describe` prints the rules, and `charter sweep Mara` finds the note that links to Mara:

```
Sweep of `Characters/Mara.md`

Linked from (1):
  Characters/Tomas.md:6  [[Mara]]

Mentioned in: none

Links to: none
```

charter finds the nearest `charter.yaml` above where you run it, as git finds `.git`, so you can run these from any folder inside the knowledge base. Exit codes are listed under [Severity profiles](#severity-profiles).

## Optional layers

The core stands alone. Three layers sit on top of it. They are strongly suggested, but each switches on only when you want it, and charter never nags about one you left off.

**Agent layer.** For AI agents that edit your notes. It is on when the contract declares an `agents:` section, and nowhere else. For an existing contract, add one line to `charter.yaml` and run `charter docs --link-agents`:

```yaml
agents: {file: AGENTS.md}
```

For a new knowledge base, run `charter init FOLDER --agents` instead. That works only on a new contract: it refuses a folder that already has a `charter.yaml`. The layer adds:

- the rulebook, `CHARTER.md`, generated from the contract. It holds the rules and a short "Working here" workflow for whoever edits a note, and it reads fine as a human reference too;
- the agent files: `AGENTS.md` in the knowledge-base folder, created or given one line (`read @CHARTER.md before creating or editing any note here`), and a `CLAUDE.md` beside it holding `@AGENTS.md` only where a `CLAUDE.md` already exists at or above that folder. Existing files are extended by that one line, never replaced;
- the `agents-include` check, which reports an agent file that does not point at the rulebook, and a rulebook that is out of date.

Without `agents:`, charter writes no agent file and never mentions agents. Details: [The agent rulebook](#the-agent-rulebook).

**Git layer.** Inside a git repository, charter also judges edit policies (`read-only`, `create-only`), `updated-date` and `protected-region` against history. Outside one, those checks are skipped with an info diagnostic (such as `paths/edit-skipped`) whenever a check actually has to run; `validate --file` asks git only when an edit policy covers a named file or `updated-date` or `protected-region` is on, so it reports nothing about git otherwise. `--staged` and `--range` are usage errors (exit `2`) there. Git hooks that run charter at commit time are part of this layer. They are opt-in per clone: see [Git hooks](#git-hooks).

**CI layer.** The charter GitHub Action checks pull requests and pushes. Add it to a workflow: see [GitHub Action](#github-action). It checks one contract per use, through its `config` input, so a repository with several knowledge bases uses it once per contract.

Git hooks protect only the clone they are installed in. They are local configuration that never travels with the repository, so a collaborator or a fresh clone has none until they install them. CI is the only check guaranteed to cover every contributor. charter installs hooks only when you ask: `charter init` and the skills never set them up unasked.

## Install

charter has two parts: the command line tool, and the skills that drive it. They install separately and release together from one version.

### The command line tool

charter needs Python 3.11 or later and installs with [uv](https://docs.astral.sh/uv/). It is not on PyPI yet, so install it from this repository, by git URL or from a local checkout:

```
uv tool install git+https://github.com/openingmove/charter
```

For a local checkout, give its path instead: `uv tool install /path/to/charter`, or `uv tool install C:\src\charter` on Windows.

Check it with `charter --version`. To upgrade:

```
uv tool upgrade charter
```

### The skills

The skills are described under [Skills](#skills). They install nothing on your system: the command line tool stays your decision, and each skill checks `charter --version` first and tells you what to run if it is missing or too old.

Pick one route for your agent. The repository is its own plugin marketplace (the plugin is named `charter`, in a marketplace named `charter`), and its skills sit in the `skills/` folder in the open Agent Skills format. The routes below name the repository's address, `openingmove/charter` on GitHub. While the repository is private, point a tool at a local checkout instead, as its own documentation allows. Claude Code, for example, reads a path as a local marketplace only when it starts with `./` or is absolute (a bare `name/name` means a GitHub repository).

**Claude Code**

```
/plugin marketplace add openingmove/charter
/plugin install charter@charter
```

This gives `/charter:establish`, `/charter:migrate` and `/charter:evolve`. Claude Code updates the plugin when the version changes.

**Codex** reads the same marketplace. Add it, then install `charter` from the plugin browser in a Codex session (`/plugins`):

```
codex plugin marketplace add openingmove/charter
```

**GitHub Copilot** (CLI and VS Code):

```
copilot plugin marketplace add openingmove/charter
copilot plugin install charter@charter
```

Copilot's marketplace list may also need the repository added to its settings.

Each tool changes its commands over time. If one of these is refused, see the tool's own documentation for adding a plugin marketplace.

**Gemini CLI** installs from the skills folder. Updating is manual: run the command again. A local checkout path or git URL works as Gemini's own documentation allows.

```
gemini skills install https://github.com/openingmove/charter.git --path skills
```

**Any other agent** installs through [skills.sh](https://skills.sh), which copies the skills into your project; update by hand. skills.sh's own documentation says which sources it accepts, such as a local checkout:

```
npx skills@latest add openingmove/charter
```

Do not install the same skills by two routes for one agent, or you will get each skill twice.

### Versions

The skills and the command line tool release together from one version. `plugin.json`'s `version` must equal `version` in `pyproject.toml` and `__version__` in `src/charter/__init__.py`, which `charter --version` prints (`tests/test_plugin_packaging.py` fails otherwise). Bump all three in one commit and tag that commit. After updating the skills, run `uv tool upgrade charter` so the two match.

## Skills

Three skills cover the life of a contract. Each one is started by you with a slash command, never by the agent on its own, so adopting charter or changing a contract is always a human decision.

- **Establish** (`/charter:establish`) writes the first contract for one knowledge-base folder, whether it is new and empty, a few loose documents, or an established set of notes. It asks whether to build in the existing folder or a new one (the old documents stay untouched, and Migrate copies the ones you pick into it), surveys what is there, interviews you about the domain (not about fields), proposes the kinds and asks per kind whether its notes share a fixed outline. Before writing anything it asks how to use git (new branch, pushed new branch, no commit, or commit to the current branch; never a default) and lists every file it will create, waiting for your yes. It then writes a template file for each outline (you read and edit it before approving) and installs the contract once you agree. When a contract already exists and notes do not fit it, it can adopt that contract and plan the fixes. Its example kinds are in `skills/establish/kinds/`.
- **Migrate** (`/charter:migrate`) brings existing files into line with a draft contract. It makes a way back first (a git branch with a clean start, or `charter snapshot`), moves prose verbatim, checks that every paragraph is kept before it deletes a source, and installs the contract last. For a new folder it reads the old documents from their own folder and leaves them as they are.
- **Evolve** (`/charter:evolve`) changes an established contract. It drafts the change, compares it with the current contract and, where notes would break, writes a per-note plan for you to agree before any edit, offering first a shape that touches no protected note. It edits a read-only, create-only or protected-region note only after you say so in the session, and then records that in a commit with `Charter-Allow` trailers (or hands you the exact lines).

Working within a knowledge base needs no skill. The generated rulebook carries the workflow, and an agent file points the agent at it.

## Usage

To start, run `charter init [FOLDER]`. FOLDER is where the contract goes (default: the current folder; it is created if missing). By default it writes one file and nothing else:

- `FOLDER/charter.yaml`, a minimal contract with `root: .`, comments explaining kinds, fields and paths, and an example kind to uncomment. It declares no `agents:` or `docs:` section, so charter works standalone: `validate`, `new`, `describe`, `sweep` and plugins need nothing more. `charter init` does not look for a contract above FOLDER.

Layers are switches, off until you ask (see [The agent rulebook](#the-agent-rulebook)):

- `--from DRAFT` installs an approved draft contract in place of the starter, byte for byte, keeping its own `root:`. A draft that does not load is refused with exit `2` and nothing is written.
- `--agents` adds the `agents:` and `docs:` sections the contract lacks (appended at the end, as text: the draft's comments, order and line endings stay as written; sections it already declares are not repeated), writes `CHARTER.md`, the rulebook generated from it, and links it from `AGENTS.md` the way `charter docs --link-agents` does (creating the file if needed, otherwise only appending one line; a `CLAUDE.md` beside it where one exists at or above). The two combine: `charter init FOLDER --from DRAFT --agents`.

`charter init` writes no `.gitignore`: the `__pycache__/` entry for the bytecode Python plugins leave behind is added by `charter plugin add`, the first time it vendors a Python plugin (once only, keeping the file's lines and line endings).

A freshly initialised knowledge base passes `charter validate`. `charter init` never overwrites anything: it checks every file first and refuses (exit `1`), listing every problem and writing nothing, if `charter.yaml` already exists, FOLDER is a file, or, with `--agents`, `CHARTER.md` already exists or `AGENTS.md` or `CLAUDE.md` is something it cannot add to (`init/exists`, `init/no-folder`, `init/not-writable`). If a write still fails partway (`init/write-failed`), it undoes what it wrote, so you can fix the cause and run it again. A missing or unloadable draft is a usage error (`init/bad-draft`, or the contract's own `contract/*` diagnostics, exit `2`). After editing the contract of an `--agents` knowledge base, run `charter docs` to bring `CHARTER.md` up to date.

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
      code:    {type: string, pattern: 'S\d{3}'}          # must match the whole value
      tags:    {type: list, of: string}
      reason:  {type: string, required_when: {stage: cut}}
      locked:  {type: date, allowed_when: {stage: [locked, cut]}}
      pager:   {type: string, allowed_when: {tags: urgent}}
```

- `of` sets the type of a list's elements. `enum`, `values`, `range` and `pattern` apply to each element of a list. On a list without `of`, a value set or `pattern` implies string elements, and `range` implies number elements.
- `default: VALUE` and `auto` are what `charter new` writes when no value is given. `auto: today` fills a `date` field with the day the note is created; `auto: next` fills a `unique` `int` field with its smallest free value, counting from the `range` minimum (or 1). A field has at most one of them, and a `default` must be a value the field may hold.
- `required_when` and `allowed_when` take `{field: value-or-list}`. A condition holds when the field equals the value, or one of the listed values. When the condition names a list field, it holds when the list contains one of the values. A field with several conditions needs all of them to hold. A condition value the named field could never hold (wrong type, outside its allowed values, `range` or `pattern`, or, for a `variant_by` field the kind does not declare, not a variant name) is a contract error. An `allowed_when` field present while its conditions fail is an error. `required: true` cannot be combined with either; use `required_when` to require a field exactly when it is allowed.

In `paths:` globs, `*` and `?` match within one folder and `**` matches any number of folders. Either `/` or `\` separates folders. Policies resolve per key: each key (`ignore`, `kinds`, `edit`, …) takes its value from the most specific matching glob that sets it, so a narrower glob overrides only the keys it names. A glob is more specific when it has more literal (non-wildcard) characters; on a tie, the first declared wins. `ignore: true` cannot be combined with other keys on the same glob.

Edit policies protect files from change, judged against git's last commit (`HEAD`). Under `edit: read-only`, adding a file, or changing or deleting one that `HEAD` has, is `paths/read-only`; under `edit: create-only`, changing or deleting a file is `paths/create-only`, while adding one is allowed (`charter new` adds a file, so it is refused under `read-only` and allowed under `create-only`). A change to a file's permissions alone (making it executable) counts as changing it. They apply to every file under `root`, not only notes, except files under `ignore: true`. `--staged --commit-msg FILE` judges what is staged against `HEAD` (see below); a plain run judges the working copy against `HEAD`, staged or not; `--file` judges only the named files, and asks git only when a policy covers one of them (otherwise it makes no git call, so it cannot report `paths/edit-skipped` or `usage/git-failed` for them). An untracked file counts as added, but a file that `.gitignore` excludes does not: git's untracked listing leaves it out, which is intended, as an ignored file is not in the index or any commit unless it is force-added (`git add -f`), and once it is tracked `--staged` and `--range` see it as added like any other. Before the first commit, outside a git repository, or where git is not installed, edit policies are skipped, with a `paths/edit-skipped` info on `charter.yaml`. Any other git failure, such as a repository git refuses to use or a `HEAD` naming a commit git cannot read, is a usage error (`usage/git-failed`, exit `2`), as for `--staged`.

A human can deliberately make an edit an edit policy forbids, such as fixing a typo in an archived note, by recording the decision in the commit message with a `Charter-Allow` trailer, one per file:

```
Fix a typo in the 2023 archive

Charter-Allow: paths/read-only docs/Archive/2023.md — typo in the budget table
```

The trailer names the diagnostic's code and path exactly as charter reports them (paths compare in Unicode NFC), then a separator (an em dash `—`, an en dash `–` or `--`, with whitespace around it; a single `-` is not one, being common in file names) and a reason, which is required. A path that itself holds a separator still works: the trailer allows the longest reported path it spells out, and only that one. A matching violation is still reported, as a warning naming the trailer, so an override is never silent. A trailer that matches no diagnostic, or repeats an earlier trailer for the same code and path, is an `override/unused` warning, which suggests the path you probably meant; a trailer without a code, path, separator or reason, or naming a code other than an edit policy's (`paths/read-only`, `paths/create-only`, and `protected-region/changed` from the optional check below), is an `override/invalid` error and allows nothing. charter reads trailers the way git does (`git interpret-trailers`): only from the message's final block of trailers, ignoring comment lines and anything below the scissors line of `git commit --verbose`, with continuation lines joined; the key is case-insensitive, and a CRLF message reads like an LF one. Agents never add a trailer unless the human asks for one; the generated rulebook tells them so.

Because the trailer lives in the commit message, edit policies are judged at git's `commit-msg` stage: `charter validate --staged --commit-msg FILE` checks only edit policies, honouring the trailers in `FILE`, while `charter validate --staged`, for the `pre-commit` stage, checks everything else and, when the contract declares an `edit` policy, says so with a `paths/edit-deferred` info, so a setup with only a pre-commit hook notices. The hooks this repository ships (below) pass `--commit-msg-installed`, because they come with their commit-msg partner, and the info is then left out of a commit's output; a bare `charter validate --staged` still prints it. `--commit-msg` needs `--staged`. CI judges commits the same way with `--range` (see below), reading each commit's own trailers. Trailers take effect only in those two; plain and `--file` runs report edit policies without them. `--strict` leaves an overridden violation and an `override/unused` warning as warnings: each records a human's decision rather than something to fix.

The optional `updated-date` check keeps a note's last-changed date honest. It is off until the contract switches it on:

```yaml
checks:
  updated-date: {enabled: true}                       # judges the `updated` field
  # updated-date: {enabled: true, with: {field: revised}}   # or the field your notes use
```

A note whose text changed since git's last commit (`HEAD`) must then have its date set to today, or to a date later than the one it had in `HEAD`; otherwise it is `updated-date/stale` (error), on the field's line, with the date to set as the hint. A missing date counts as stale; a value that is not a date is left to `schema`. Any change to the text counts, frontmatter included, but not a change to the file's permissions or line endings alone. Notes the change adds are not judged (`charter new` dates them), nor are notes of kinds that do not declare the field. "Today" is the local date of the machine running charter. The `CHARTER_TODAY` environment variable (`YYYY-MM-DD`) overrides it for every command that dates something (`validate`, `plugin run`, `new`). It is meant for tests and for reproducing a run; a value that is not a date is a usage error (`usage/invalid-today`, exit `2`). The field must be declared, as `type: date`, on at least one kind; anything else is a contract error (exit `2`). The check judges the same change edit policies do: the working copy against `HEAD` for a plain run, only the named files for `--file`, and what is staged for `--staged`, where it runs at the `pre-commit` stage (`--staged --commit-msg` does not repeat it). A `Charter-Allow` trailer cannot overrule it; lower its severity (`checks.updated-date.severity` or a profile) to make it advisory. Before the first commit, outside a git repository, or where git is not installed, it is skipped with an `updated-date/skipped` info on `charter.yaml`.

The optional `protected-region` check keeps records such as decisions append-only: their text, once committed, stays as it is, and they change only by gaining amendments at the end, under a marker heading. It is off until the contract switches it on, naming the kinds it protects and the heading:

```yaml
checks:
  protected-region: {enabled: true, with: {kinds: [decision], marker: "## Amendments (append-only)"}}
```

A note of those kinds that git's last commit (`HEAD`) has may then change only by adding lines at the end of its body, below the marker; anything else is `protected-region/changed` (error), on the first line that differs, or on no line when text was removed from the end. The message says whether the change touched the text above the marker, the marker itself, or the amendments already below it. Precisely: the body as it was must still begin the body as it is, line for line, so inserting a line between amendments, or extending the last line, is a change, not an append. A line's trailing whitespace, blank lines at the end of the body, a missing final newline, a byte-order mark and line endings (CRLF or LF) are not text, so an editor that strips or adds them changes nothing. One consequence: adding or removing a Markdown hard line break written as two trailing spaces is not seen as a change. The marker is found as an ATX heading (`#` to `######`), not as text: `##  Amendments (append-only) ##` reads as the same heading, though rewriting the committed marker line that way is still a change. A setext heading (text underlined with `===` or `---`) is not recognised, and a heading inside a code block or an HTML comment does not count. That includes a marker appended after a committed body that ends inside an unclosed code block or `<!--` comment: the marker lands inside it too, so close the block first (an edit that needs a trailer). A note that has no marker yet is protected whole: it may gain only the marker, at the end, with amendments beneath it. The frontmatter is not protected: fields such as `status` may change (`schema` and `updated-date` judge them). A kind's `path` follows its fields, so such a change can move the note. A protected note that is deleted while the change adds a note of the same kind whose body continues it (by the rule above) counts as moved and is judged clean; each added note continues at most one deleted note. Any other deletion of a protected note is `protected-region/changed`, on its old path. A protected note that is modified while its old or new content is not UTF-8 is `protected-region/changed` too, since what changed cannot be read. A deleted note whose committed text is not UTF-8 is judged as a deletion or a move like any other, comparing bytes: an added note of the same kind that repeats those bytes, plus any lines appended below the marker, counts as moved, and anything else says the change deletes it. Notes the change adds are not judged. A note is protected by the kind it had in `HEAD`, so changing its kind does not lift the protection. Whether a note is in scope, though, follows the contract as the change leaves it, as for edit policies: a change that also moves `root` or adds an `ignore: true` path policy covering the note lifts its protection in that change. The marker must be a Markdown ATX heading line and every kind must be declared; missing or unknown parameters are a contract error (exit `2`).

Like an edit policy, `protected-region` guards content a human may deliberately need to correct, so a `Charter-Allow: protected-region/changed PATH — REASON` trailer allows a violation, and it is judged where trailers are read: at the `commit-msg` stage (`--staged --commit-msg`) and per commit by `--range`. The `pre-commit` stage (`--staged`) leaves it to them, saying so with a `protected-region/deferred` info, which `--commit-msg-installed` leaves out as it does `paths/edit-deferred`. Plain and `--file` runs judge the working copy against `HEAD` (only the named files for `--file`), without trailers. Before the first commit, outside a git repository, or where git is not installed, it is skipped with a `protected-region/skipped` info on `charter.yaml`.

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

- A placeholder `{field}` renders the field's value: text as it is, numbers in plain decimal (`id: 007` is the number 7 and renders as `7`; `0.5` as `0.5`), dates as `YYYY-MM-DD`, booleans as `true`/`false`. A value that does not match the field's declared type is left to `schema/type` and the path is not checked. Filters follow a `|` and apply left to right: `suffix` maps the value through the kind's `suffix:` table (nothing when unmapped or missing), `lower` lowercases, and `slug` lowercases, drops accents and joins words with `-` (`Storm at the Quay!` becomes `storm-at-the-quay`).
- A note whose path differs from the rendered one is a `filenames/path` error naming the expected path. Placeholders must name single-value fields of the kind that are `required: true`, unless rendered through `suffix`.
- `matches_filename: true` on a field requires its value to equal its `{field}` part of the path (`filenames/matches-filename`), which pinpoints a renamed file. The path must then contain the placeholder without filters. When the literal text between two such placeholders does not settle which part is which, the note gets `filenames/path` instead. A kind without `path` may still use `matches_filename`: the value must then equal the filename without `.md`, in whatever folder the note lives.
- Rendered paths must work on every platform. A value that would put `/` or `\`, a character Windows forbids (`<>:"|?*`), or a control character into the path, that leaves a file or folder name empty, `.` or `..`, ending in a dot or space, or a reserved Windows name (`CON`, `NUL`, `COM1`, …), is a `filenames/unsafe-value` error at that field; render such fields through `slug`, whose output is always safe. The same rules apply to the literal text of the pattern itself, checked when the contract loads (`contract/invalid`).
- The pattern may use `/` or `\` between folders and renders the same on every platform; Unicode composed and decomposed forms of the same name count as equal.

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
- `collection.count` is the number of notes the kind must have (`ids/count`). `collection.contiguous` names an `int` field of the kind whose values must run without gaps (`ids/gap`), from the field's `range` minimum if it has one, otherwise from its smallest value, up to its largest value (or the `range` maximum, past which values are `schema/range`). Every note of the kind counts, including notes of a variant and notes whose `variant_by` value names no variant. Both are reported at the `collection` in `charter.yaml`, and `--file` runs report them whenever one of the files is a note of the kind, or `charter.yaml` itself.

For a complete contract to read or try, see the example knowledge base in [`examples/garden`](examples/garden): four kinds (one with a variant), vocabularies, link fields, path policies, templates, a generated `CHARTER.md` and an `AGENTS.md` linking to it. Run `charter validate --all` from that folder.

Then, from the directory holding `charter.yaml` or any folder below it (charter searches upward for the nearest `charter.yaml`, as git does for `.git`; `--file` searches from the named files' folders, and files that resolve to different contracts are a usage error):

```
charter validate                  # human-readable, grouped by file
charter validate --format json    # stable machine-readable output
charter validate --format agent   # one compact line per diagnostic
charter validate --config path/to/charter.yaml
charter validate --file docs/Books/Dune.md   # only these files (per-edit mode, quick enough to run after each edit)
charter validate --staged         # what is staged in git (for a pre-commit hook)
charter validate --staged --commit-msg .git/COMMIT_EDITMSG   # its edit policies (for a commit-msg hook)
charter validate --staged --commit-msg-installed   # the same, without the infos that edit policies wait for the commit-msg hook (for a pre-commit hook that has one)
charter validate --range origin/main..HEAD   # edit policies, updated-date and protected-region of each commit in a range (for CI)
charter validate --strict         # warnings fail too
```

`--staged` checks exactly what the next commit would hold, so unstaged scratch edits neither block nor mask it. It leaves edit policies to `--staged --commit-msg`, which a commit-msg hook runs once the message, with any `Charter-Allow` trailers, exists (see edit policies above). It targets the staged files and reads everything from git's staged content rather than the working copy: the notes, `charter.yaml`, its templates, the rulebook, the agents file, `charter.lock` and the plugins, which run from a temporary copy of their staged files and are checked against the staged lock. Files that are not staged, untracked ones included, are not part of the knowledge base it sees. A staged symbolic link to a file in the knowledge base reads as that file, as in a checkout; other links are left out. Deleting a note, or changing its kind, touches the kind it had, so a staged change that leaves a gap in a `contiguous` collection is reported. Content that git stores through a filter, such as Git LFS, is seen as git stores it (the pointer file), not as checked out. `--staged` needs `charter.yaml` staged; outside a git repository, or with the contract unstaged, it is a usage error (exit `2`).

`--range A..B` is for CI: it reaches the verdict the commit-msg hook reached, or would have, when each commit was made. It needs git 2.25 or newer (the end of this paragraph says why). It checks only edit policies and, when enabled, `updated-date` and `protected-region` (run `charter validate --all` for the rest), for each commit B has and A has not, oldest first, against that commit's parent, honouring the `Charter-Allow` trailers of that commit's message and no other's. So a trailer in one commit never excuses a violation in another, and a later commit that restores a protected file does not clear the commit that changed it: the fix is to rewrite that commit, or reword its message to add a trailer. Each commit is judged by the `charter.yaml` it holds itself, as the hook judged it by the staged contract; a commit without one, whose parent had none either, is skipped, as charter did not govern it. Its `root` must be a folder holding a file in that commit (or in the index, under `--staged`): a root with no files is reported as such, and a root that is a symlink is reported as a link a commit cannot follow, both exit `2`; those two messages describe the working copy, not the commit being checked. A commit whose contract is invalid, or that deletes the contract its parent had (`usage/contract-deleted`), is a usage error naming it (exit `2`). A `--profile` (or `CHARTER_PROFILE`) that is not built in must be declared in the contract of every commit judged. A merge commit is judged only on the files it leaves unlike every parent, such as a conflict resolution, against its first parent: the rest were changed, and judged, in the commits it merges; a file it changes that any parent has counts as changed, not added. A root commit has no parent to compare with, so it gets a `paths/edit-skipped` info (and `updated-date/skipped` or `protected-region/skipped`, when those checks are on). Diagnostics name the commit by git's abbreviated id. An empty side means `HEAD` (`origin/main..` is `origin/main..HEAD`); `A...B`, or anything other than two commits joined by `..`, is a usage error (`usage/invalid-range`, exit `2`), as is `--range` outside a git repository. A range with no commits is clean. For `updated-date`, "today" is the day the commit was authored, in its author's time zone, whatever the clock or `CHARTER_TODAY` says. So a note edited twice on one day passes in CI on any later day. The author date survives a rebase, cherry-pick or amend, and a "rebase and merge", which all reset the commit date, so a commit is judged as of the same day after them. One edge remains: the pre-commit hook judges the change a moment before git stamps the author date, so a commit made across midnight can be judged a day later in CI than by its hook. Fix it by setting the date to the day CI names and amending the commit (through `git rebase -i` if it is not the last one), which keeps its author date. `--range` needs git 2.25 or newer: it reads each author date with the `%as` placeholder, which older versions print as written, and charter then stops with `usage/git-failed`.

`--range` needs the history it compares: in a shallow clone, a range whose start, or a parent of one of its commits, is missing is a usage error (`usage/shallow-history`, exit `2`), never a silent pass. With GitHub's `actions/checkout`, set `fetch-depth: 0`. For a pull request, check `<base sha>..<head sha>`; for a push, `<before>..<after>` (`github.event.before`..`github.sha`). A push that creates a branch has an all-zero `before`, which charter rejects with a hint: check `origin/<default branch>..<after>` instead.

### Git hooks

Enforce the contract at commit time with [pre-commit](https://pre-commit.com), or with plain git hooks written in Python. Both run `charter validate --staged --commit-msg-installed` before the commit and `charter validate --staged --commit-msg FILE` once the message exists, so a `Charter-Allow` trailer can authorise an edit-policy violation. Install charter so the `charter` command is on `PATH`.

Install both hooks together. The pre-commit hook passes `--commit-msg-installed`, so it no longer warns that edit policies and `protected-region` wait for the commit-msg hook; with only the pre-commit hook installed, those checks are not judged at all and nothing says so.

Hooks are opt-in and protect only the clone they are installed in: `core.hooksPath` and `pre-commit install` are local configuration that never travels with the repository. `charter init` and the skills never install them unasked. CI (below) is the only check guaranteed to cover every contributor.

With pre-commit, add this to `.pre-commit-config.yaml` and run `pre-commit install --hook-type pre-commit --hook-type commit-msg`:

```yaml
repos:
  - repo: https://github.com/openingmove/charter
    rev: <release tag or commit>
    hooks:
      - id: charter
      - id: charter-commit-msg
```

Without pre-commit, copy this repository's `.githooks/` directory (`pre-commit` and `commit-msg`, two short Python scripts) into the repository holding `charter.yaml`, then point git at it:

```
git config core.hooksPath .githooks
```

The scripts start with `#!/usr/bin/env python3`, which git runs on Windows too (through Git for Windows), provided `python3` is on `PATH`; on Unix they must be executable (`chmod +x .githooks/*`, then commit them so the bit travels). Git runs hooks from the repository's top directory, so `charter.yaml` must sit there.

### GitHub Action

A composite action runs charter on pull requests and pushes: it sets up [uv](https://docs.astral.sh/uv/), installs charter at a ref, then runs `charter validate --all` and `charter validate --range` (both with `--profile ci`) and `charter docs --check`. All three run even if one fails, and the worst exit code decides the result. Make the job the required check on pull requests. For a contract with no rulebook (no `docs:` or `agents:` section) it skips the `docs --check` step.

```yaml
name: charter
on:
  pull_request:
  push:
    branches: [main]
jobs:
  charter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: openingmove/charter@v0.2.0
        with:
          ref: v0.2.0
```

Give `ref` the same tag as `uses`. `uses` picks the action's own files; `ref` picks the charter it installs, and without it that is `main`.

`fetch-depth: 0` is required: `--range` compares each commit with its parent, and in a shallow clone it stops with `usage/shallow-history` rather than pass. The range comes from the event: for a pull request `<base sha>..<head sha>`; for a push `<before>..<after>`; for a push that creates a branch (an all-zero `before`) `origin/<default branch>..<after>`. A push that deletes a branch, or an event with no commits such as `workflow_dispatch`, skips the range and says so.

Inputs, all optional: `ref` (the branch, tag or commit of charter to install, default `main`), `source` (the repository to install charter from) and `config` (the path to `charter.yaml` when it is not at the top of the repository). One use of the action checks one contract: a repository with several knowledge bases adds the action once per contract, each with its own `config`.

### Links

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

### Tags

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

### Templates

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

#### Structure cutoff

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

### Creating notes

`charter new` writes a note at the path its kind renders, with frontmatter in contract order and the template body:

```
charter new recipe "Soda Bread" --set method=bake      # --set method=bake selects the `bread` variant
charter new recipe/bread "Soda Bread"                  # or name the variant: its `set` values are filled in
charter new recipe "Soda Bread" --set tags=quick --set tags=easy   # a list field takes one element per --set
charter new recipe "Soda Bread" --dry-run              # check and report, write nothing
charter new recipe "Soda Bread" --format agent         # compact output
```

- The title goes to the kind's `title` field (or its one `matches_filename` field). `--set FIELD=VALUE` gives any other field; the value is read as the field's type (`--set id=7` is a number, text fields stay text). Fields not given take their `default` or `auto` value; a variant named with `kind/variant` fixes its `set` values (or its `variant_by` value).
- The template's `{{placeholders}}` are filled from the note's values and `{{date}}` with today; placeholders without a value stay for the author. The printed outline's headings are filled with the same values, `{{date}}` included.
- The note is validated in memory with the same checks as `charter validate`, at base severities apart from `residue` (a new note keeps its template's guidance), and written only if no error is found. Warnings are printed after the note is created.
- Every reason to refuse is reported at once: each required field without a value (with its type and allowed values, at its declaration in `charter.yaml`), an `auto: next` field with no free value, a path that already exists (`new` never overwrites a file), that a `paths:` policy ignores, or that lies under `edit: read-only` (`paths/read-only`, worded as `validate` words it for a file added there; the whole target path is tested, a folder built from the title included, and it needs no git history, so it holds with `--dry-run` and outside a git repository), a kind without `path`, and whatever the checks find. A note whose path cannot be rendered is checked where its pattern stands (`docs/Zones/{title}.md`), so a value that cannot be part of a path is reported alongside the note's other problems.
- A write that fails (`new/write-failed`, or `new/name-too-long` when the file system rejects the name's length) leaves no file or new folders behind.
- `--dry-run` checks the name's length only when the note's target folder already exists, because the file system reports a missing folder before it looks at a name's length; the real run still refuses with `new/name-too-long` and writes nothing.
- On success `new` prints the created path and the template's section outline. Refusals exit `1`; an unknown kind or variant, or a malformed `--set`, is a usage error (exit `2`).

### Describing the contract

`charter describe` explains the contract to whoever is about to write a note, human or agent:

```
charter describe                       # every kind and variant, the path policies and the checks
charter describe recipe                # one kind, with each of its variants
charter describe recipe/bread          # one variant
charter describe recipe --format json  # the same, as a stable JSON document (format `charter-describe/1`)
```

For each kind and variant it shows its `description`, its path pattern and template, and whether undeclared fields are allowed. A kind lists the field values that make a note one of its variants; a variant shows the values that select it as fixed. Then come each field (required or when, what a value must be, allowed values, range, pattern, link targets, `unique`, `default` and `auto`, and the field's `description`), the exact `charter new` command, giving only the values nothing else fills in (`charter new recipe "TITLE" --set method=METHOD`), and the body outline of its template with each section's `<!-- guide: … -->` text. Kinds, variants and fields take an optional one-line `description:` for this:

```yaml
kinds:
  recipe:
    description: "A dish worth cooking again."
    fields:
      title: {type: string, required: true, description: "The dish's name."}
```

Markdown is the default format. In JSON, rules are data (`values`, `range`, `pattern`, `to`, `fixed`, `selects`, outline entries with `optional` and `repeat`), and `unknown_fields` is the severity of an undeclared field, or `null` when they are allowed. `plugin_rules` holds [plugins'](#plugins) rule docs, and a plugin's entry in `checks` gives its `source` (`null` for a built-in check). An unknown kind or variant is a usage error (exit `2`), reported as a diagnostic in text or JSON.

### Surveying a folder

Before a contract exists, `charter survey FOLDER` reports what the Markdown files in FOLDER hold, as facts to draft a contract from:

```
charter survey notes                  # a readable summary
charter survey notes --format json    # a stable JSON document (format `charter-survey/1`)
```

It is read-only (it writes nothing) and needs no contract: it neither loads nor searches for one, so it works in a folder with none, and ignores a `charter.yaml` in or above FOLDER. It reads every `*.md` file below FOLDER except under `.git` and `.obsidian` (the `.md` extension and those folder names are matched case-sensitively, like the rest of charter); a symlinked folder is not entered and a symlinked file pointing outside FOLDER is skipped. A FOLDER that is not an existing folder is a usage error (exit `2`, `usage/folder-not-found`); a folder with no Markdown files is a valid, empty survey (exit `0`). A file that cannot be read in full never stops the survey: invalid frontmatter is reported with its error, and a file that is not UTF-8 is listed with a `problem`.

The JSON output is deterministic: keys and lists are sorted, paths are POSIX and relative to FOLDER, and there are no timestamps. Its keys, `format` first:

```
format        "charter-survey/1"
totals        {files, folders, with_frontmatter}
files[]       {path, folder ("." for FOLDER itself), has_frontmatter,
               frontmatter_error (text, or null when it parses or there is none),
               problem (null, "not valid UTF-8" or "could not be read"),
               fields {name: type}}
folders[]     {folder, files (directly inside), filename_shapes {shape: count},
               fields [{name, files carrying it}],
               outline {headings ["# {{title}}", "## Care", ...], files} or null}
fields        {name: {files (carrying it), types {type: files},
               values [{value, count, files (up to 3 example paths)}], distinct (total), truncated}}
links         {markdown|wikilink: {links, files}}
agent_files   [name]
rulebooks     [{path, reason: "filename" | "heading"}]
```

The rules it applies are deliberately simple:

- **Types** are `string`, `number`, `boolean`, `date` (a date or datetime), `list`, `mapping` and `null`. A field whose notes disagree lists each type with its file count, which is how a mixed-type field shows.
- **Values** count scalars, and the elements of lists, per occurrence; a mapping contributes its type only. At most 20 values are listed, most common first (then by value), with `distinct` the total and `truncated` true when some were left out. `1` and `"1"` are different values; dates are written as `YYYY-MM-DD`.
- **Filename shapes** replace each digit with `N` and each run of words with `word` (`index`), `kebab-title` (`use-postgres`), `snake_title` (`use_postgres`) or `Title` (anything else), keeping the extension: `0007-use-postgres.md` is `NNNN-kebab-title.md`.
- **Outline** of a folder is the most common sequence of headings (outside code and comments) among its files, with the number of files that share it; ties go to the sequence that sorts first. A leading level-1 heading, the note's title, is written `{{title}}` because titles differ per note.
- **Links** are counted by style, `wikilink` and `markdown`, in bodies outside code and in string frontmatter values; URLs are not counted.
- **Agent files** are files named `AGENTS.md`, `CLAUDE.md` or `GEMINI.md` (any case), at any depth. **Rulebook-like documents** are other files whose name, or first heading, contains `rulebook`, `convention(s)`, `style guide`, `rules` or `charter` as a word.

### Snapshots and restore

Before a change you may want to undo, `charter snapshot FOLDER` saves a zip of the whole folder, and `charter snapshot restore ZIP` puts it back. Both need no contract: they neither load nor search for one, so they work in a folder with none and ignore any `charter.yaml` in or above it. They use only Python's own zip support, so they behave the same on Windows, macOS and Linux.

```
charter snapshot notes                          # writes ../notes-2026-10-18T143005Z.zip (UTC; no colons, legal on Windows)
charter snapshot notes --to backups/before.zip  # writes exactly there (missing parent folders are created)
charter snapshot notes --to backups             # an existing folder: the timestamped name, inside it
charter snapshot restore backups/before.zip --to notes-restored
```

It prints where the snapshot went and the exact command that puts the folder back (every path spelled out and quoted for your shell), for example `charter snapshot restore '/work/notes-2026-10-18T143005Z.zip' --to /work/notes --replace`.

**What a snapshot holds.** Every file and every folder under FOLDER, empty folders included, with no ignore rules: `.git`, `.obsidian` and other dotfiles are all in, so the way back is faithful. Nothing is added to the tree (the only metadata is the zip comment, which records the folder's name). Paths are stored POSIX-style and relative to FOLDER, so a snapshot restores the same on every OS. Contents come back byte for byte; modification times are kept to the zip format's two-second resolution (read in the machine's local time zone); file modes are not kept, except the executable bit on POSIX. **Symlinks and other special files are refused**: following one could copy files from outside the folder, and storing one as a link restores differently per OS. A folder holding any is refused (exit `1`, `snapshot/unsupported-entry`), the offenders listed, with nothing written; replace them with real files first.

A folder is also refused, listing the names and writing nothing, if restore would refuse what it holds: a name with a backslash, a leading drive letter such as `C:note.md`, a name that is not valid UTF-8 (and on Windows, characters Windows forbids), or two names that differ only in letter case or Unicode form (`a.md` and `A.md`; they could not restore on a case-insensitive volume). Rename them and run the snapshot again. An unreadable file or folder is refused too (`snapshot/unreadable`, or `snapshot/write-failed`), naming the path, and leaves no partial zip.

**Symlinks and special files, and how to proceed.** There is no option to skip them yet: a snapshot that silently left them out would not bring everything back, so any symlink, socket, fifo or device inside FOLDER makes `charter snapshot` stop. Move the link out of the folder, or replace it with a real file or folder (or delete it), then snapshot again.

**Where it goes.** By default beside FOLDER, never inside it. `--to PATH` is the zip's path, or an existing folder (or a path ending in a separator) to put the timestamped name in. A destination inside FOLDER is refused (exit `2`, `usage/snapshot-inside-folder`), after resolving `..` and symlinks. A snapshot never overwrites a file: two snapshots in the same second get `-2`, `-3`, ... after the timestamp, and an explicit `--to` that exists is refused (exit `1`, `snapshot/exists`).

**Restoring.** `charter snapshot restore ZIP [--to FOLDER] [--replace]` restores into FOLDER, or, without `--to`, into the folder name recorded in the zip, beside the zip. (A zip charter did not write records none, so it needs `--to`.) A missing target is created; an empty one is filled; a non-empty one is refused (exit `1`, `snapshot/target-not-empty`) unless you pass `--replace`. Restoring is all-or-nothing as far as the filesystem allows: everything is first extracted into a temporary sibling folder, and only when that succeeded is it moved into place. With `--replace` the old folder is moved aside first and deleted only after the new one is in place, and put back if the swap fails. `--replace` refuses (exit `1`, `snapshot/target-holds-input`) a target that contains the zip or the working directory.

**Hostile or damaged archives.** Every entry is checked before anything is extracted, and one bad entry refuses the whole archive (exit `2`, `snapshot/unsafe-archive`, nothing written): a `..` component, an absolute path, a drive letter, a backslash (never normalised: snapshots contain none), a symlink entry, an encrypted entry, a duplicate, and, on Windows, characters Windows cannot use in a name. A file that is not a zip, or is truncated, fails its checksums, has a damaged or unsupported compressed stream, or holds a file name flagged as UTF-8 that is not valid UTF-8, is a usage error (exit `2`, `snapshot/corrupt`), not a traceback; a zip that cannot be opened at all (permissions) is `snapshot/unreadable` (exit `1`); either way nothing is extracted; a failure while extracting leaves the target untouched. Restore sets no limit on the archive's size or number of entries: the zip is a local file you chose, and a full disk makes the restore fail and clean up its temporary folder. Letter-case duplicates (`a.md` and `A.md`) are refused as well, so every snapshot restores on case-insensitive volumes. If deleting the temporary `.NAME.charter-restore-*` folder or the replaced `.NAME.charter-old-*` folder fails after a successful restore, a `files/leftover` warning names the folder to remove, and the exit code stays `0`; a failed restore names such a folder in its hint; if a swap fails and the old folder cannot be moved back, the error gives that folder's exact path, where the old content is intact.

**A folder named `restore`.** `charter snapshot restore` means the restore subcommand. To snapshot a folder with that name, spell it `./restore`.

### Sweeping for dependents

Before changing a fact in a note, `charter sweep` lists every note that may repeat or rely on it:

```
charter sweep "Soda Bread"                  # by filename, alias, or path from root, as a wikilink names it
charter sweep docs/Recipes/Soda\ Bread.md   # or by a file path from the working directory
charter sweep "Soda Bread" --format json    # a stable JSON document (format `charter-sweep/1`)
charter sweep "Soda Bread" --format agent   # compact, one entry per line
```

- **Linked from:** each link to the note from another note's body or `link` field, with its line and field. An ambiguous link that may mean the note is listed too, flagged with its candidates; links in code or HTML comments do not count.
- **Mentioned in:** each body line of another note that names it, outside code, HTML comments and the links already listed: its `title`, its filename (without `.md`) or an `aliases` value, as whole words, ignoring case (`Straße` matches `STRASSE`) and Unicode normal form. A name may wrap across the lines of a paragraph; the line it starts on is reported. Its `id` counts after its kind's name or `#` (`recipe 12`, `#12`); an id with a letter in it (`12a`) counts on its own too, but a bare number is too common in prose to mean the note.
- **Links to:** the note's own links, each with what it resolves to, or `unresolved` or `ambiguous`.
- Notes under a `sweep: false` path policy appear in none of these lists, though such a note can itself be swept. Notes charter cannot read (invalid frontmatter, not UTF-8) are listed as not searched.
- `--format text` (the default) groups the lists under headings; `--format json` is the stable machine form; `--format agent` prints one entry per line (`linked-from`, `mentioned-in`, `links-to`, `unsearched`).
- An existing file path wins over a wikilink name. A name that matches no note, or several, is a usage error (exit `2`) with a "did you mean" hint or the candidates; so is a file that is not a note (not Markdown, ignored, or outside `root`).

### The agent rulebook

charter works without any of this. A contract that declares neither `docs:` nor `agents:` is a standalone knowledge base: `charter docs` is a usage error (exit `2`) telling you to declare one, nothing is generated, and no agent file is expected.

`charter docs` writes the whole description to a rulebook file for agents to read at the start of every session, under a "generated — do not edit" header and a "Working here" workflow addressed to whoever edits a note: read the rules, create notes with `charter new`, run `charter validate --file` after each edit, run `charter sweep` before changing a fact, never change the contract to make a note pass (stop and tell the human, who may run the Evolve skill), never add a `Charter-Allow:` trailer unless the human asks, and the contract wins over other guidance about a document. A `docs:` section turns the rulebook on by itself; an `agents:` section turns on the agent layer, which implies the rulebook at its default path. Point your agent-instruction file at it:

```yaml
agents:
  file: AGENTS.md            # must link to the rulebook (default: AGENTS.md)
docs:
  output: CHARTER.md         # the generated rulebook (default: CHARTER.md)
```

Both paths are relative to `charter.yaml`, beside or below it. `agents.file` is the one file that must point at the rulebook; it is not the same as `agent_files:`, the list of filenames (default `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) that need no kind wherever they sit. Entries are bare file names matched at any depth; one containing `/` or `\` fails at load with `contract/invalid`, and a specific path takes an `untyped: allow` path policy instead. The rulebook and `agents.file` need no kind either, and links to them resolve even when they sit outside `root`, like any file beside or below `charter.yaml` (see Links).

```
charter docs                 # write the rulebook (left untouched when already up to date)
charter docs --check         # write nothing; exit 1 if the rulebook is missing or out of date (CI)
charter docs --link-agents   # also add one line importing the rulebook to agents.file, creating the file if missing, and a CLAUDE.md beside it importing it where a CLAUDE.md exists at or above (needs `agents:`; exit 2 without it)
charter docs --check --link-agents   # link, then check, without writing the rulebook
```

The rulebook is always written with LF line endings and in contract order, so it is byte-identical on every platform; `--check` ignores line endings, so a checkout with CRLF endings still counts as up to date. `--link-agents` is the one command that edits a file you wrote: it adds a single line (`read @CHARTER.md before creating or editing any note here`), in the file's own line endings, only when the file does not point at the rulebook yet, and changes nothing else. Where a `CLAUDE.md` exists in the knowledge-base folder or any folder above it, Claude Code ignores `AGENTS.md`, so it also creates or extends a `CLAUDE.md` beside `agents.file` holding `@AGENTS.md`; it never creates a `CLAUDE.md` where none exists at or above. "Above" means every folder up to the filesystem root, as Claude Code loads ancestor `CLAUDE.md` files, so a stray `CLAUDE.md` far above the repository counts. A file write that fails is reported as `docs/write-failed` (exit `1`).

The `agents-include` check is on only when the contract declares `agents:`. A contract whose `agents.file` and `docs.output` name the same file, however the path is spelled, fails to load (`contract/invalid`). The check reports a missing or unreadable `agents.file`, including a folder at that path (`agents-include/missing-file`; `charter docs --link-agents` reports the same code and exits `1`, leaving that path untouched, but has already written the rulebook, while with `--check` nothing is written), one that does not point at the rulebook (`agents-include/missing-link`), and a missing or out-of-date rulebook (`agents-include/stale`). Any of these, outside code, points at the rulebook, whatever `links.styles` says: an inline link `[rules](CHARTER.md)`, a reference definition `[rules]: CHARTER.md`, `<CHARTER.md>`, or an import line `@CHARTER.md`. Without `agents:` the check is off and agents are never mentioned: a missing or out-of-date rulebook (`docs:` declared, no `agents:`) is `docs/stale` instead, and `charter docs --check` exits `1` for it.

### Severity profiles

Every diagnostic has a base severity. A profile then adjusts it for the stage charter runs in, so work in progress warns while CI enforces. charter picks the profile automatically: `--file` uses `edit`, plain `charter validate` and `--staged` (with or without `--commit-msg`) use `commit`, and `--range` and any run with `CI=true` use `ci`. `--profile NAME` or the `CHARTER_PROFILE` environment variable forces one, including a custom name declared under `profiles:`. The output names the active profile.

The built-in `edit` and `commit` profiles downgrade `schema/unknown-field`, `schema/missing-frontmatter`, `structure` and `residue` to warnings; `ci` keeps base severities. That suits a branch + pull-request workflow where CI on the pull request is the gate. Declaring a profile replaces its built-in default:

```yaml
profiles:
  commit: {}                         # commits straight to main: enforce base severities
  review: {schema: warning, schema/type: error}   # keys: a diagnostic code or a check id; a code wins

checks:
  paths: {severity: warning}         # base severity of every diagnostic of the check
  schema: {enabled: false}           # turn a check off
```

Profile values are `error`, `warning`, `info` or `off`. A key must be a check id or a diagnostic code one of the checks reports. Built-in defaults only ever lower a severity; a declared profile sets exactly what it says. `--strict` turns the remaining warnings into errors, except those a `Charter-Allow` trailer accounts for (an allowed violation, `override/unused`). An unknown profile name, or a `--file` path that does not exist, is a usage error (exit `2`) reported as a diagnostic in the requested format.

Each diagnostic carries `path`, `line`, `severity`, `code`, `message` and `hint`. Paths are relative to the directory holding `charter.yaml`.

Exit codes: `0` clean (warnings allowed unless `--strict`), `1` errors found, `2` contract or usage error, `3` a plugin failed to run (see below).

When stdout is closed early (`charter validate | head`) charter stops quietly with no traceback. It exits `141` (the status of a process killed by SIGPIPE, on every platform) if the pipe closed while it was still writing, and with its own exit code if only the final flush met the closed pipe. A closed stderr is not handled. The console script now points at `charter.cli:run`, so an existing install needs `uv tool install --reinstall` (or an upgrade that regenerates the script) to get this.

### Plugins

A plugin is a check for rules only your knowledge base has, written in any language. It is a directory holding a `charter-plugin.yaml` manifest and the plugin's code; the contract enables it under its id with `source`, the directory relative to `charter.yaml` and beside or below it:

```yaml
checks:
  word-limit:
    source: tools/word-limit
    with: {max_words: 800}            # parameters, checked against the manifest's config_schema
```

```yaml
# tools/word-limit/charter-plugin.yaml
charter_plugin: 1
id: word-limit                        # the check id that enables it
version: 0.1.0
description: "Notes stay under a word limit."
requires: {charter: ">=0.1,<2"}       # optional; comparisons with >=, >, <=, <, ==, != joined by commas
run: ["uv", "run", "--script", "check.py"]
scope: file                           # optional; file = the targets and the notes they link to, vault (default) = every note
needs: [body, before]                 # optional; also send each note's body text, and the earlier version of changed files
triggers: {kinds: [recipe], globs: ["Recipes/**"]}  # optional; run only when the run touches one of these
hook: true                            # optional; false = leave out of per-edit runs (`validate --file`)
timeout_ms: 10000                     # optional; 10 seconds by default
config_schema:                        # optional JSON Schema for `with`; without one, the plugin takes no parameters
  type: object
  properties: {max_words: {type: integer, minimum: 1}}
  required: [max_words]
docs: RULES.md                        # optional; Markdown rules shown by `charter describe` and in the rulebook
```

A plugin's `docs` file, relative to its directory and inside it, explains its rules in prose. `charter describe` and the rulebook end with a `# Plugin rules` section holding each enabled plugin's description and docs, for every plugin that has either. A leading front-matter block is left out of the rulebook: a first line of `---`, then only blank, `#` comment, `key: value`, `- item` or indented lines, then a closing `---` line (a `...` or indented closer is not recognised). Any other document, including one that opens with a thematic break, is left as written. Headings in the docs (`#` or underlined, indented up to three spaces, which they keep, or not, outside code and HTML comments) are moved down to sit below the plugin's own heading; Markdown has six heading levels, so any pushed deeper stay at level 6. `charter describe KIND` shows only the plugins that run for that kind (no `triggers`, or the kind among `triggers.kinds`). The check table lists enabled plugins after the built-in checks. The docs are read with any line endings and byte order mark, so the rulebook stays byte-identical on every platform, and editing them makes `charter docs --check` report the rulebook out of date.

`run` is a list of arguments, started without a shell in the plugin's directory, so a plugin runs the same on Windows, macOS and Linux. A command string is rejected, and so is a program that is a shell (`sh`, `bash`, `zsh`, `cmd`, `powershell`, `pwsh` and the like) or a script ending in `.sh`, `.ps1`, `.bat` or `.cmd`. Python plugins declare their dependencies inline ([PEP 723](https://peps.python.org/pep-0723/)) and run with `uv run --script`, which needs no setup step. The contract fails to load (exit `2`) when `source` leaves the directory holding `charter.yaml`, a manifest is missing or invalid, its `id` differs from the check's or is one of charter's own code namespaces (`contract`, `docs`, `files`, `index`, `init`, `new`, `plugin`, `snapshot`, `usage`), its `requires.charter` excludes the running charter, its `docs` file is missing or outside its directory, or `with` does not match `config_schema`. A plugin with `enabled: false` is not read at all.

**Plugins run code.** `charter validate`, `charter new` and `charter plugin run` start enabled plugins' commands with your permissions, so only run charter on knowledge bases you trust, as you would their build scripts.

The plugin reads one JSON request on stdin and writes one JSON response on stdout, protocol `charter-plugin/1`. Paths in both are relative to the knowledge-base root (`root`):

```json
{
  "protocol": "charter-plugin/1",
  "charter_version": "0.2.0",
  "plugin": {"id": "word-limit", "version": "0.1.0"},
  "params": {"max_words": 800},
  "mode": "file",
  "root": "notes",
  "targets": ["Recipes/Bread.md"],
  "today": "2024-03-05",
  "index": {
    "notes": [
      {"path": "Recipes/Bread.md", "kind": "recipe", "variant": null, "frontmatter": {"kind": "recipe"},
       "links": [{"raw": "[[Flour]]", "target": "Ingredients/Flour.md", "field": null, "line": 9}],
       "headings": [{"level": 2, "text": "Method", "line": 12}], "tags": ["baking"],
       "body": "# Bread\n…"}
    ]
  }
}
```

```json
{"protocol": "charter-plugin/1",
 "diagnostics": [{"path": "Recipes/Bread.md", "line": 12, "severity": "error", "code": "word-limit/too-long",
                  "message": "The note has 950 words; the limit is 800.", "hint": "Split it into two notes."}]}
```

`targets` are the notes this run selected. `today` is the day the run judges as of, `YYYY-MM-DD`: the local date, or `CHARTER_TODAY` when set. Use it rather than the plugin's own clock, so the plugin agrees with charter. A `vault`-scoped plugin's `index` holds every note; a `file`-scoped plugin's holds the targets and the notes they link to, except on a whole run, which gives it every note too. `mode` says which it got: `file` or `vault`. A note's `body`, the text after its frontmatter, is there only when the manifest `needs: [body]`. So are the `links`, `headings` and `tags` of the notes a `file`-scoped plugin is sent only because a target links to them: without `needs: [body]` those keys are there but empty, so charter does not have to read those notes' bodies. The targets, and every note of a `vault` run or a whole run, carry them whatever the `needs`.

With `needs: [before]` the request also holds what the run's change did, as edit policies judge it (`--staged`: the staged change; otherwise the working copy since `HEAD`, for `--file` only the named files):

```json
"before": {"available": true, "reason": null,
           "files": [{"path": "Recipes/Bread.md", "status": "modified", "content": "---\nkind: recipe\n…"},
                     {"path": "Recipes/Rolls.md", "status": "added", "content": null}]}
```

`files` lists every file under the root, other than ignored ones, that the change added, modified (a permission change included) or deleted, sorted by path; `content` is the file's text before the change, with line endings normalised to `\n`, and `null` for an added file or one that is not UTF-8 text. Where there is no earlier version, `available` is `false`, `files` is empty and `reason` says why (outside a git repository, say).

`triggers` keep a plugin from running when a run doesn't concern it: it runs when the run touches one of its `kinds` (every kind on a whole run) or targets a note whose root-relative path matches one of its `globs`. Each of `kinds` must be a kind the contract declares (a variant name is not a kind), or the contract is in error. Without `triggers` it always runs; `triggers` naming no kinds and no globs is a contract error. A plugin with `hook: false` is left out of per-edit runs, `charter validate --file` and `charter new`, so a slow or whole-vault check doesn't stall a per-edit run or an agent; whole runs include it. A file-scoped plugin's index on `validate --file charter.yaml` is empty, as no note is targeted.

`charter plugin run <id>` runs one plugin on its own, whatever its triggers and hook say, and reports its diagnostics; it takes `validate`'s `--all`, `--file`, `--staged`, `--format`, `--profile` and `--strict`. With `--dump-input` it writes the exact request the plugin would receive to stdout instead of running it, so you can replay it against the plugin while developing; it then takes no `--format` (the request is always JSON), `--profile` or `--strict`.

A diagnostic's `line` and `hint` may be omitted or `null`, and its `code` starts with the plugin's id. Plugin diagnostics join the others: `checks.<id>.severity` and profiles (by the plugin's id or one of its codes) adjust them as for built-in checks. Paths must be POSIX and inside the root. A plugin that exits non-zero, outlives `timeout_ms`, writes more than 16 MB, writes something other than a valid response, or answers with another protocol is reported as `plugin/failed` on its `checks` entry, with the end of its stderr, and charter exits `3`; `charter new` then writes nothing. No severity setting or profile turns that off; `enabled: false` does. The same goes for a plugin that `validate --staged` (or `plugin run <id> --staged`) cannot write out of the index to a temporary directory, for example on a full disk or because of a file name the file system refuses: it is reported as `plugin/failed` naming the cause, and everything else is still judged. `validate --range` no longer fails on such a plugin, but it does not run plugin checks.

#### Installing plugins from git

```
charter plugin add --from https://example.com/word-limit.git@v1.0.0
```

`charter plugin add --from <git-url>@<ref>` fetches the plugin at a branch, tag or commit and copies it into `.charter/plugins/<id>/`, named after its manifest's `id`. The plugin's manifest must be at the root of the repository. The ref follows the last `@` after the URL's host, so `https://user@host/repo.git` alone has no ref and is refused. git runs without prompting for credentials or host keys, and gives up after 10 minutes. Commit that directory: CI and everyone else then run the plugin without fetching anything. `add` enables the plugin as `checks.<id>` in `charter.yaml`, written in the contract's own style and leaving the rest as it was, and records it in `charter.lock`:

```yaml
# Written by `charter plugin`; do not edit by hand.
charter_lock: 1
plugins:
  word-limit:
    version: 1.0.0
    source:
      git: https://example.com/word-limit.git
      ref: v1.0.0
      commit: 3f1c…            # what the ref pointed at when added
    sha256: 9f2c…              # of the installed directory's contents
```

`validate`, `new` and `plugin run` refuse to run a locked plugin whose directory no longer matches its `sha256`, so what runs is what was reviewed: it is reported as `plugin/modified` on its `checks` entry, and charter exits `3`, whatever the profile. A symbolic link in the directory is reported the same way, naming the link, in the working copy and, for `validate --staged`, in the index (found by its entry mode, not from the files written out for the plugin). The lock covers only plugins in `.charter/plugins/<id>`: a check whose `source` is elsewhere is a local-path plugin, and it is not checked against the lock. In a lock entry, `commit` is optional, and charter ignores keys it does not know, so a lock written by a later charter still loads. Adding a locked plugin again replaces it, from the same or another ref. `add` refuses a plugin whose manifest is invalid, whose `id` is a built-in check or one of charter's namespaces, that holds a symbolic link (`plugin/symlink`; a link reads differently on each OS and may point outside the plugin), or whose `checks.<id>` or directory already exists without being in the lock. If the plugin takes parameters, `add` installs it and then reports that `checks.<id>.with` must still give them (exit `1`).

When the plugin holds a Python file, `add` also makes sure `.gitignore` (beside `charter.yaml`) ignores `__pycache__/`, appending the line only if it is missing, in the file's own line endings.

`--dev <path>` installs a plugin's working copy instead, for developing it against a real knowledge base: the directory is copied as it is, without `.git` or `__pycache__`, and the lock records `source: {dev: true}` with the copy's `sha256`. Run `charter plugin add --dev <path>` again to refresh the copy after changing the working copy.

The `sha256` is the same on Windows, macOS and Linux, however git checked the files out. It is the SHA-256 of one line per file, in path order: the file's path relative to the plugin directory (POSIX separators, Unicode NFC), a NUL byte, the hex SHA-256 of its content, and a line feed. Content counts CRLF as LF in any file with no NUL byte in its first 8000 bytes (git's own test for binary), since `core.autocrlf` and `eol` attributes may convert line endings on checkout. A symbolic link anywhere in the directory makes it a mismatch. File modes, empty directories, and anything named `.git` or `__pycache__` are left out, so bytecode a Python plugin leaves behind is not a modification.

#### Managing plugins

Every step of a plugin's life is a command, so nobody edits `.charter/plugins/` or `charter.lock` by hand:

```
charter plugin list                        # each plugin: version, enabled or disabled, source
charter plugin info word-limit             # one plugin: source and commit, lock state, manifest
charter plugin update word-limit --ref v1.1.0
charter plugin disable word-limit
charter plugin enable word-limit
charter plugin remove word-limit
```

- `list` and `info` show every `checks.<id>` with a `source`, enabled or not, and every plugin in `charter.lock`. They take `--format json`. `info` also says whether an installed plugin's directory still matches its `sha256`, and what is wrong with a manifest it cannot read.
- `update <id>` fetches a plugin installed with `--from` again, at the ref it was installed from (picking up new commits on a branch) or at `--ref`, replaces its directory, and rewrites its lock entry, both or neither. It leaves `charter.yaml` as it is, so a disabled plugin stays disabled. The ref must hold the same plugin `id`. Updating also restores a directory that no longer matches the lock. A plugin installed with `--dev` is refreshed with `charter plugin add --dev` instead, and one used in place from its `source` has nothing to update.
- `enable <id>` and `disable <id>` set `checks.<id>.enabled`. `enable` on a plugin in the lock that has no `checks.<id>` adds that entry again.
- `remove <id>` removes `checks.<id>` and, for a plugin charter installed, its directory and lock entry. Either all of these change or none do; if a write fails and something cannot be put back, the error says where the previous plugin directory was kept. A rollback puts `charter.yaml` and `charter.lock` back only while each still holds what this command wrote; if someone edited one meanwhile, it is left as edited and the error names it (`plugin/write-failed`). `checks:` goes too when the plugin was its only entry. Settings elsewhere that name the plugin, such as profile entries, stay and are reported if they no longer apply. `charter.lock` stays, as `plugins: {}`, after its last plugin is removed. The directory of a plugin used in place is left where it is.
- `add`, `update` and `remove` refuse, changing nothing, a plugin that `charter.lock` lists while `checks.<id>.source` points anywhere but `.charter/plugins/<id>` (`plugin/source-mismatch`): charter runs it from that other place, so the vendored copy is not the one in use. The message names the recorded and the expected `source`; edit `source` back, or delete the lock entry by hand. `add` also needs a contract that loads, so a `source` that makes it invalid (a missing directory, an absolute path) is reported as `contract/invalid`, exit 2, before anything is changed. A check with another `source` that the lock does not list is a plugin used in place and is handled as before.

These commands edit `charter.yaml` the way `add` does: in its own style, leaving everything else as it was, or not at all. They need only `checks:` and the lock to be valid, so you can still disable, update or remove a plugin that made the rest of the contract invalid. Afterwards they report anything the contract still needs, and exit `1` if it needs something.

### More diagnostic codes

The sections above explain most codes where they arise. These are the rest, so that every code charter can emit is named in this README (a test keeps it so).

| Code | Meaning |
|---|---|
| `contract/not-found` | No contract at the `--config` path, or none above the working directory (exit `2`). |
| `contract/yaml` | The contract or lock is not valid UTF-8 text or not valid YAML. |
| `docs/stale` | The rulebook is missing or out of date and the contract has no `agents:` layer (see The agent rulebook). |
| `usage/no-rulebook` | `charter docs` on a contract with neither `docs:` nor `agents:`; declare either one. |
| `usage/no-agent-layer` | `charter docs --link-agents` on a contract without `agents:`. |
| `index/unreadable`, `index/invalid-frontmatter` | A Markdown file that cannot be read, or whose frontmatter is not a YAML mapping between two `---` lines. |
| `schema/missing-kind`, `schema/unknown-kind` | A note names no kind, or one the contract does not declare. |
| `schema/required`, `schema/not-allowed` | A required field is missing, or a field is present where `allowed_when` forbids it. |
| `schema/item-type`, `schema/pattern` | A list item has the wrong type, or a value does not match the field's `pattern`. |
| `links/ambiguous`, `links/missing-anchor`, `links/wrong-kind` | A link matches several notes, points at a heading the target lacks, or a `link` field targets a note of the wrong kind. |
| `paths/kind-not-allowed` | A note's kind is not allowed by the path policy covering it. |
| `new/exists`, `new/ignored-path`, `new/name-too-long` | `charter new` would overwrite a file, place the note where a `paths:` policy ignores it, or needs a file name or path the file system rejects as too long. |
| `new/missing-field`, `new/no-free-value`, `new/no-path`, `new/unplaceable` | `charter new` lacks a required value, has no free `ids` value in the range, the kind has no `path`, or the `path` cannot be rendered from the values given. |
| `usage/unknown-kind`, `usage/unknown-variant`, `usage/no-title-field` | `charter new` names a kind or variant that is not declared, or gives a title to a kind without a `title` field. |
| `usage/invalid-set`, `usage/repeated-set`, `usage/conflicting-set` | A `--set` that is not `FIELD=VALUE`, is repeated for a single value, or conflicts with the title or `auto` value. |
| `usage/unknown-note`, `usage/ambiguous-note`, `usage/not-a-note` | `charter sweep` names no note, several, or a file that is not a note. |
| `usage/file-not-found`, `usage/file-unreadable` | A `--file` or `--commit-msg` path that does not exist, or a commit message file that cannot be read. |
| `usage/commit-msg-without-staged`, `usage/commit-msg-installed-without-staged`, `usage/contract-not-staged`, `usage/not-a-git-repository` | `--commit-msg` or `--commit-msg-installed` without `--staged`, `--staged` with a contract git does not hold, or `--staged`/`--range` outside a git working tree. |
| `usage/conflicting-options`, `usage/unknown-profile`, `usage/mixed-contracts` | Options that cannot be combined, a profile that is neither built in nor declared, or `--file` paths under different contracts. |
| `usage/snapshot-arguments` | `charter snapshot` words that fit neither `snapshot FOLDER` nor `snapshot restore ZIP`. |
| `usage/no-recorded-folder` | `snapshot restore` of a zip charter did not write needs `--to`. |
| `snapshot/restore-failed`, `snapshot/target-in-the-way` | The restore could not complete (the target was left as it was), or the target exists and is not a folder. |
| `usage/unknown-plugin`, `usage/invalid-source`, `usage/not-updatable` | A plugin command names a plugin that does not exist, a source that is not a git URL followed by `@` and a ref, a `--dev` path that is not a directory, a ref that is not a branch, tag or commit name, or a plugin that was not installed from git. |
| `plugin/exists`, `plugin/invalid-manifest`, `plugin/fetch-failed`, `plugin/write-failed` | `charter plugin add` finds the plugin's name taken, its manifest invalid, cannot fetch it from git, or cannot write it. |
| `plugin/source-mismatch` | `charter plugin add`, `update` or `remove` finds a plugin that `charter.lock` lists but whose `checks.<id>.source` is not `.charter/plugins/<id>`, so charter runs it from elsewhere. Nothing is changed; edit `source` back, or delete the lock entry by hand. |
| `files/leftover` | A temporary folder could not be fully deleted: the `.staging-*` folder of `charter plugin add`, `update` or `remove`, the folder `charter plugin add --from` and `update` clone a plugin into, the temporary copy `--staged` and `--range` runs make of plugin files, or the staging and set-aside folders of `charter snapshot restore`. A warning on stderr naming the path to delete; the command's output and exit code are unchanged. A restore that fails names the leftover in its refusal's hint instead. charter clears read-only files and retries a few times first. |

## Development

```
uv sync
uv run pytest
```

Tests drive the CLI in-process against small invented knowledge bases under `tests/fixtures/` and compare `--format json` output with each fixture's `expected.json`. After an intentional output change, regenerate with `uv run pytest --update-golden` and review the diff.
