# charter

charter keeps a Markdown knowledge base true to a declared contract. Humans and AI agents both edit the knowledge base; charter is how the agent learns the rules and how breaking them is caught.

## Language

### The knowledge base

**Knowledge base**:
The directory tree of Markdown notes that one contract governs.
_Avoid_: vault (an Obsidian word), docs folder

**Note**:
A Markdown file in the knowledge base that is not ignored.

**Kind**:
A type of note, named by a frontmatter field, with its own fields, path and template.
_Avoid_: note type, schema

**Contract**:
The `charter.yaml` file, with the templates it names, that declares every kind and rule of a knowledge base.
_Avoid_: schema, config, rulebook

**Structure cutoff**:
A date a kind may declare, with the date field it is read from. Notes of the kind dated before it are legacy notes; notes dated on or after it must follow the kind's template.
_Avoid_: grandfather date, legacy flag

**Legacy note**:
A note dated before its kind's structure cutoff. It is exempt from the template's headings and from nothing else.
_Avoid_: old note, unmigrated note

**Vocabulary**:
A named set of values a field may hold.
_Avoid_: enum (that is the field rule that uses one), taxonomy

**Rulebook**:
The `CHARTER.md` file generated from the contract for agents to read.
_Avoid_: contract (the rulebook is derived, never edited)

**Agent file**:
An instruction file an agent harness loads on its own, such as `AGENTS.md` or `CLAUDE.md`.
_Avoid_: agent guide, memory file

**Backstop**:
A check that runs whatever any agent or person did, such as CI on a pull request; it catches what guidance missed.

### How charter is used

**Core**:
What charter does in a plain folder with no git, agent or CI: validate notes against the contract, create notes, describe the rules and sweep for dependents.

**Layer**:
An opt-in addition to the core: the agent layer (agent files and the rulebook import, on when the contract declares `agents:`), the git layer (edit policies and history-based checks, inside a git repository) or the CI layer (the GitHub Action).
_Avoid_: plugin (a plugin is an external check), integration

### The contract's lifecycle

**Establish**:
Writing the first contract for a knowledge base: for an empty repository, for sparse existing documents, or for an existing knowledge base with its own conventions.
_Avoid_: init (that is only the command that writes a starter file)

**Survey**:
A factual report of what an existing set of Markdown files holds (folders, frontmatter fields and their observed values, filename shapes, headings), used to draft a contract.
_Avoid_: scan, inference (the survey reports; the human and agent infer)

**Migrate**:
Bringing existing files into line with a contract: adding frontmatter, renaming, moving or splitting files.
_Avoid_: fix, normalise

**Migration plan**:
A skill-owned record of what a migration will change, folder by folder, and how far it has got; it exists only until the contract is written.

**Draft contract**:
The contract a migration is working towards, validated against but not yet in force.
_Avoid_: proposed contract, temporary charter.yaml

**Way back**:
What restores the knowledge base to how it was before Establish or Migrate began: the starting branch under git, or a snapshot without it.
_Avoid_: backup (a snapshot is one kind of way back)

**Evolve**:
Changing an established contract: a new kind, field, value or path rule, and the follow-on work that brings notes into line.
_Avoid_: update the schema, extend

**Working within**:
Editing notes under a contract without changing it.

## Relationships

- A **knowledge base** has exactly one **contract**; the **rulebook** is generated from it.
- The **core** needs nothing but a folder of Markdown and a **contract**; every **layer** is opt-in, and charter never mentions agents unless the **contract** declares the agent **layer**.
- A **knowledge base** is self-contained in its folder by default: its **contract**, **rulebook**, templates and **agent files** sit in its root, so it can be moved or extracted whole. charter finds the nearest **contract** above where it runs, as git finds `.git`. A repository may hold several **knowledge bases**, each with its own **contract**.
- **Establish** interviews the human about the domain, not the schema: what things the **knowledge base** will hold, how they relate, roughly how many there are and how they change. It proposes the **kinds**, fields and links from those answers; the human never has to design fields or **vocabularies** from a blank page. Example kinds packaged with the skill only inform its proposals.
- The human approves a proposed **contract** in two steps: a plain-language summary of each **kind** and how they link, then the real **rulebook** rendered from the **draft contract** by `charter describe`. The YAML is never the review surface, but its path is named at every step and it is shown whenever asked.
- **Establish** drafts a **contract** from a **survey** and a conversation with the human; validating the draft lists what **Migrate** must do.
- When files must change, **Migrate** works against a **draft contract** and a **migration plan**; the **contract** itself is written last, so nothing is enforced mid-migration.
- No file is edited before a **way back** exists.
- **Evolve** drafts the changed **contract** and compares it with the current one; if **notes** must change, it runs as a **migration**, with the old **contract** in force until the new one replaces it.
- Protected **notes** (read-only, create-only, protected regions) are never changed autonomously. In a human-run **Evolve** they may change once the human and agent have explicitly agreed, which is what lets the agent add the `Charter-Allow` trailers.
- **Establish** produces the first **contract**; **Evolve** changes it; **Migrate** and **working within** change only **notes**.
- A **knowledge base**'s root folder holds an **agent file** that points agents at the **rulebook** and tells them how to work within it.
- **Working within** needs no skill: the **rulebook**, loaded through the **agent file** when an edit touches the **knowledge base**, governs every edit, including edits another skill makes. Where a skill's own opinion about a document conflicts with the **contract**, the **contract** wins.
- Adoption is deliberate: once charter and its skills are installed, the human runs **Establish**, then **Migrate** if files must change. Nothing starts them on its own.
- **Evolve** is always a human decision. An agent working within a knowledge base never changes the **contract** to make a note pass; it stops and tells the human, who may choose to **evolve** it.

## Example dialogue

> **Dev:** "The agent hit an unknown-field error writing a note. Should it add the field to the contract?"
> **Domain expert:** "No. That's **evolving** the contract, and only a human decides that. The agent fixes the note, or stops and asks."
> **Dev:** "And if the human agrees the field is needed?"
> **Domain expert:** "Then they start **Evolve**: the contract gains the field, the **rulebook** is regenerated, and any notes that need it are **migrated**."

## Flagged ambiguities

- Giving each **vocabulary** value a meaning in the **contract** was proposed and rejected. charter enforces the mechanical part of a rulebook: which values are allowed, not what they mean. What a value means belongs in a **note**. Kinds and fields keep their one-line `description` only to orient agents. A maintainer who wants a glossary of values writes it as an ordinary **note** and points to it from a field's `description`; charter needs to know nothing about it. A checkable pointer from a **vocabulary** to its glossary, with a check that every value is covered, is possible later if a knowledge base needs it.

- "Updating the contract" was used both for a human's deliberate change and for an agent loosening a rule to make a failing note pass. Resolved: the first is **Evolve**; the second is never allowed, as changing a test to match buggy code would not be.
