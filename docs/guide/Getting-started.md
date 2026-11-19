# Getting started

## The core

charter works in a plain folder of Markdown. It needs no git, no AI agent and no CI. The commands:

| Command | What it does |
|---|---|
| `charter init [FOLDER]` | writes a commented starter `charter.yaml` in FOLDER, and nothing else |
| `charter new KIND "Title"` | creates a note at the path its kind renders, from the kind's template |
| `charter validate` | checks every note against the contract |
| `charter describe [KIND]` | explains the rules: kinds, fields, paths, checks |
| `charter sweep NOTE` | lists the notes that link to or mention NOTE, before you change it |

Two read-only tools support the [skills](Skills.md): `charter survey FOLDER` reports what a set of Markdown files holds before any contract exists, and `charter snapshot FOLDER` saves a zip of a folder you are about to change (`charter snapshot restore ZIP` puts it back).

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

charter finds the nearest `charter.yaml` above where you run it, as git finds `.git`, so you can run these from any folder inside the knowledge base. Exit codes are listed under [Severity profiles](Severity-profiles.md).

## Optional layers

The core stands alone. Three layers sit on top of it. They are strongly suggested, but each switches on only when you want it, and charter never nags about one you left off.

**Agent layer.** For AI agents that edit your notes. It is on when the contract declares an `agents:` section, and nowhere else. For an existing contract, add one line to `charter.yaml` and run `charter docs --link-agents`:

```yaml
agents: {file: AGENTS.md}
```

For a new knowledge base, run `charter init FOLDER --agents` instead. That works only on a new contract: it refuses a folder that already has a `charter.yaml`. The layer adds:

- the rulebook, `CHARTER.md`, generated from the contract. It holds the rules and a short "Working here" workflow for whoever edits a note, and it reads fine as a human reference too;
- the agent files: `AGENTS.md` in the knowledge-base folder, created or given one line (`read @CHARTER.md before creating or editing any note here`), and a `CLAUDE.md` beside it holding `@AGENTS.md` only where a `CLAUDE.md` already exists at or above that folder. Existing files are extended by that one line, never replaced;
- the `agents-include` check, which reports an agent file that does not point at the rulebook, and a rulebook that is out of date;
- optionally, `guard: true` under `agents:`, which in Claude Code stops a session writing `charter.yaml` unless the human started Evolve, Establish or Migrate in it. Details: [The contract guard](Contract-guard.md).

Without `agents:`, charter writes no agent file and never mentions agents. Details: [The agent rulebook](Agent-rulebook.md).

**Git layer.** Inside a git repository, charter also judges edit policies (`read-only`, `create-only`), `updated-date` and `protected-region` against history. Outside one, those checks are skipped with an info diagnostic (such as `paths/edit-skipped`) whenever a check actually has to run; `validate --file` asks git only when an edit policy covers a named file or `updated-date` or `protected-region` is on, so it reports nothing about git otherwise. `--staged` and `--range` are usage errors (exit `2`) there. Git hooks that run charter at commit time are part of this layer. They are opt-in per clone: see [Git hooks](Git-hooks.md).

**CI layer.** The charter GitHub Action checks pull requests and pushes. Add it to a workflow: see [GitHub Action](GitHub-Action.md). It checks one contract per use, through its `config` input, so a repository with several knowledge bases uses it once per contract.

Git hooks protect only the clone they are installed in. They are local configuration that never travels with the repository, so a collaborator or a fresh clone has none until they install them. CI is the only check guaranteed to cover every contributor. charter installs hooks only when you ask: `charter init` and the skills never set them up unasked.
