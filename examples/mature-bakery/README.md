# Mature example: a small bakery notebook

A neighbourhood bakery's notebook of 23 notes in six kinds (recipe, ingredient, supplier, equipment, bake, decision), linked with wikilinks and a few Markdown links, a hand-written rulebook (`Kitchen Rules.md`) and an `AGENTS.md`. There is no `charter.yaml`.

It has deliberate drift:

- A mistyped recipe status (`tesetd`).
- Properties the rulebook does not allow: `oven_temp_f` on two recipes and `rating` on one bake. The rulebook lists a recipe's six properties, so these are drift, not an emerging field.
- A recipe whose title differs from its file name (`recipes/Rye Loaf.md` is titled "Rye Bread"). The survey pairs each title with an example file, so the agent running the walkthrough compares the two; with more than 20 distinct titles the list is cut off, and it reads the `title:` line of the remaining files.
- Decision notes whose text must stay fixed above an "Amendments (append-only)" heading.

## Walkthrough

- **Establish** (on a copy of this folder): the draft ignores this README, which describes the example and is not a note. It should derive the contract from the notes and `Kitchen Rules.md`, and put each drift case to you as a question instead of fixing it silently (the typo, the extra properties, the title) and ask whether the new rulebook replaces `Kitchen Rules.md`. The draft has the `protected-region` check on for decisions. It also asks per kind whether the notes share an outline, offering the headings the survey found (a recipe's `Method` and `Notes`, with `Notes` optional because one recipe lacks it), and writes the agreed `Templates/<Kind>.md` files for you to read and edit before you approve the draft. A fix on record means the files do not fit the draft yet, so Establish writes a migration plan and tells you to run `/charter:migrate` to apply the fixes; only if you decide every case by changing the contract does it install with `charter init --from <draft> --agents` and end with an approved `charter.yaml`.
- **Evolve**: once a contract exists, split the status `draft` into `idea` and `trial`. `draft` is used on three recipes and also on one decision (`decisions/Test new recipes on Mondays.md`), and that decision is protected. The agent should propose a change shape that leaves the protected note alone (for example, keeping `draft` valid for decisions only, or giving decisions their own value) or else ask for explicit agreement before touching it. It must not edit the decision's text above the Amendments heading until you agree. Success: `charter validate --all` is clean, the three recipes carry their new values, and the decision changed only if you agreed to it.
