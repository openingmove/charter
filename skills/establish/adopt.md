# Adopting an existing contract

Adopt mode is for a folder that already holds a hand-written `charter.yaml` whose notes do not all fit it. The contract stays exactly as the human wrote it; Establish surveys the notes against it and writes the plan that brings them into line, and `/charter:migrate` carries the plan out. Changing the contract itself is `/charter:evolve`'s job, not this mode's.

Enter it from step 2, only after the human said yes to the offer. The offer is made when `charter validate --strict` shows an `error` or `warning`, not on the plain exit code, which stays 0 for warnings. The numbered steps of SKILL.md still apply, with these differences:

- **Step 2**: record that the run adopts. The folder, the survey and the done-condition are unchanged.
- **Step 3**: survey as usual, then read the contract's own rules (`charter describe --config <folder>/charter.yaml`) beside the survey.
- **Step 4**: no interview about the domain: the contract already answers it. Ask only what the survey cannot show, such as what a note without frontmatter is.
- **Step 5**: the judgement calls come from `charter validate --config <folder>/charter.yaml --all --strict --format json`. For each finding, ask the human and record a note fix: `add frontmatter`, `set`, a changed or removed field, a retitle or a file rename (the table in [migration-plan.md](migration-plan.md)). The contract is not up for change, so a rule the notes keep breaking is put to the human as "the notes change to match" and nothing else. If they want the rule changed, stop and send them to `/charter:evolve`.
- **Steps 6 and 9**: skip. There are no new kinds, and the contract's templates are already in place.
- **Step 7**: the confirmation lists `charter.draft.yaml` and `charter.migration-plan.md`, and nothing else.
- **Step 8**: the draft is a copy of `<folder>/charter.yaml`, text for text, written with your file tools. Change nothing in it.
- **Step 10**: show `charter describe --config <draft>` and ask for a yes to the contract as it stands. There is nothing to revise.
- **Step 11**: skip. The notes did not fit, which is why the run adopts. Go to step 13.
- **Step 12**: skip. The contract is installed already.
- **Step 13**: write the plan as usual, with these rules:
  - Add the bullet `- Contract: adopted` to `Draft contract`.
  - Mark only folders `migrate in place` or `leave as it is`, never `migrate`, and write no `Section map`: an adopted run fixes the notes where they stand. A folder is `leave as it is` only when the contract already governs it cleanly (a path rule ignores it or allows its files, or `charter validate --config <folder>/charter.yaml --all` reports nothing for it). Otherwise its notes are `Note fixes`.
  - Write the `Dates` section as usual when the contract has a cutoff, copied from it: Migrate dates the undated notes. The cutoff itself stays the contract's.
  - Tick `Left folders have path policies`. Leave `Contract installed with ...` unticked: Migrate's install step checks that `charter.yaml` equals the draft, ticks the line and installs nothing.
  - Add the plan-ignore line to the draft, as the step says. It is the only line that makes the draft differ from `charter.yaml`.

Migrate then runs unchanged, except that its install step has nothing to install (see Migrate step 7).

Committing: the contract is already in the parent commit's tree, so any edit to a note under a `read-only` or `create-only` path breaks that policy in every commit, whatever the order. The only route is a `Charter-Allow` trailer in the commit message, which is the human's call; Migrate never adds one.
