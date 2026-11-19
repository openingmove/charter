# The contract guard

An optional step. Offer the guard once per run: in step 12 after the install, or in step 13 before the hand-off. On a no, change nothing and go on.

## What to tell the human

Say it in these terms:

- The rulebook tells agents never to change the contract to make a note pass, but that rule is advice. The guard enforces it in Claude Code: a session can write `charter.yaml` only after you have typed `/charter:evolve`, `/charter:establish` or `/charter:migrate` in that session. An agent cannot start those skills, and a yes in the conversation does not lift the guard.
- It is one line in the contract, `guard: true` under `agents:`, and it acts only where the charter plugin is enabled in Claude Code.
- Its limits:
  - Once you have typed one of those commands, the session may write the contract for the rest of that session, also after the skill has finished. A new session starts guarded again.
  - It covers `charter.yaml` only: not the templates, the rulebook or the Evolve draft.
  - It reads shell commands best effort, so an unusual way of writing the file can go unseen.
  - It stops a cooperative agent going around Evolve, not a hostile one: an agent that writes a marker itself gets past it.
  - It works in Claude Code only. Other agents get no guard and rely on the rulebook's rule.

Then ask whether to switch it on.

## Before offering

Run `charter-hook --help`. If it fails, the command line tool is too old for the guard: say so, name `uv tool upgrade charter`, and offer nothing.

Look at the contract: in step 12 the installed `<folder>/charter.yaml`, in step 13 the draft. When it has no `agents:` section (the human declined the agent files), the guard has no rulebook to announce it: say that the guard comes with the agent layer, and offer nothing. Never add an `agents:` section for the guard, because that switches the whole agent layer on.

## On a yes

In step 12, the contract is installed:

1. Add `guard: true` to the `agents:` mapping of `<folder>/charter.yaml`, so that `agents: {file: AGENTS.md}` becomes `agents: {file: AGENTS.md, guard: true}`. Change nothing else. This session started with `/charter:establish`, so the guard lets it write the contract.
2. Run `charter docs --config <folder>/charter.yaml` to regenerate the rulebook, which now says the guard is on.
3. Run `charter validate --config <folder>/charter.yaml --all` and `charter docs --config <folder>/charter.yaml --check`. Both must exit 0.

In step 13, nothing is installed yet: add `guard: true` to the `agents:` mapping of the draft, as in step 12. Change nothing else. Migrate installs the contract with the agent layer, so the guard comes on with the install.

Done when the human has said no, or the key is in place and the checks pass. `charter.yaml` and the rulebook were already in the file list of step 7, so the commit of step 7 carries the change.
