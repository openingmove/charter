# Way back

The way back restores the folder to how it was before the first edit. Make it before any note changes. Only two commands here change anything, both with the human's yes: `git switch -c` and `charter snapshot`. Every other command reads.

## Under git

Run `git rev-parse --is-inside-work-tree` from the folder. It prints `true` inside a repository. Anything else: use [Without git](#without-git).

1. Check for uncommitted work:

   ```
   git status --porcelain --ignored --untracked-files=all -- <folder>
   ```

   `--untracked-files=all` lists each new file, not just a new folder such as `?? Templates/`, so a file in the templates folder that Establish did not write cannot hide. Disregard lines for the files Establish wrote: the plan, the draft and the template files the plan's `Templates` bullet lists, and a snapshot zip from this run (it sits beside the folder, so inside a repository it shows as untracked). Every other line is uncommitted work: `??` untracked, ` M` or `M ` changed, ` D` deleted, and `!!` ignored (git cannot bring an ignored file back).

2. When lines remain, refuse to start. Show them and offer two routes: the human commits those files themselves, or you take a snapshot ([Without git](#without-git), which is then the way back whatever the tree holds). Commit nothing for them. After a commit, run the check again.

3. Read the starting point first: `git branch --show-current` (empty on a detached HEAD) and `git rev-parse HEAD`. Keep both values: once a branch is created, `git branch --show-current` names the new branch, not the one you started on. When no branch prints (detached HEAD), START is the commit hash from `git rev-parse HEAD`.

4. When the check shows nothing else, read the plan's `- Git:` bullet. It is the human's answer from Establish, so do not ask the branch question again:
   - `new branch` or `new branch pushed`: Establish already made that branch and switched to it, so the current branch is the one to stay on. Create no second branch and ask for no name. Fill in the line as `` branch `NAME` from `START` at `COMMIT` ``, with NAME the current branch and START and COMMIT the values the bullet gives after `from` and `at`: the branch and commit Establish started from. A bullet without them (an older plan) gives `` commit `COMMIT` on `START` `` instead, with START the current branch.
   - `uncommitted` or `commit to current branch`: the work stays on the current branch; offer no branch.
   - `no repository`: the plan was written outside a repository but this folder is in one now, so the answer is out of date: ask as for a plan with no bullet.
   - No `Git` bullet (a plan from an older run): offer a new branch for the migration and let the human name it or decline. On a yes, run `git switch -c <name>`: the untracked plan and draft come along. On a no, the work stays on the current branch.

   In every case Migrate commits nothing and pushes nothing: the recorded answer covers what Establish did with its own files, and Migrate's own work stays uncommitted for the human. With `new branch pushed`, tell the human at the end that the branch is theirs to push.

Done when the folder is clean apart from Establish's files, or a snapshot exists. Fill in `Way back made:` with every value in backticks, as `` branch `NAME` from `START` at `COMMIT` `` (START is the value read in step 3, before the switch), `` commit `COMMIT` on `START` `` (no new branch) or, for a snapshot, the shape under [Without git](#without-git), and tick it. Filled in and ticked: ``- [x] Way back made: branch `migrate-notes` from `main` at `3f9c2ab` ``.

## Without git

A snapshot copies the whole folder, attachments included, into a zip. For a folder of thousands of files or of large attachments, say so before running it and recommend the git route instead (the human commits first), since the zip can be large and slow; take the snapshot only when the human still wants it.

Run `charter snapshot <folder>`. It writes a zip beside the folder, never inside it, and prints where it went and an exact restore command. Tell the human both, word for word, and add that the restore command runs from a folder outside the knowledge base (charter refuses to replace the folder it runs in).

When the snapshot is refused (exit 1, `snapshot/unsupported-entry`), the output lists the symbolic links, special files and unrestorable names that block it. Relay the list, and tell the human to remove or replace those entries, or to put the folder under git with a commit, and to start Migrate again. Go no further: without a way back no file changes.

Done when the zip exists. Fill in the plan line as `` snapshot `PATH`, restore with `COMMAND` `` (both in backticks) and tick it.

## Resuming after an undo

An undo takes the folder back, but the plan is not always taken back with it. A snapshot restore restores the plan too, as it was when the snapshot was made, so its ticks are right. Switching back to the starting branch leaves the plan and the draft (untracked files) where they are, still ticked for work that is now gone; a human's own reset does the same.

When the human says the migration was undone, or a ticked line's work is missing (a `Created` target absent, a fix not in the note), do this before anything else:

1. Untick every line after `Section map agreed`, and empty the `Way back made` detail and untick it, so step 3 makes a new way back. Keep `Agreed: yes` and the `Dates` bullets unless the human says the agreement is off.
2. Files an earlier run left behind (untracked notes from `Created` lines) are not deleted. The `Created` step meets them as `new/exists` and settles them with the human, as moving.md says.
3. Tell the human what you unticked, then continue at step 3.

## The undo

Tell the human the undo in one line, and run nothing of it:

- Snapshot: the exact `charter snapshot restore ...` command from the plan line, run from a folder outside the knowledge base.
- Git, on a new branch (Migrate's own, or Establish's, per the plan's `Git` bullet): `git switch <starting branch>`, which leaves the migration on its own branch. When START is a commit hash, `git switch --detach <hash>` returns to that commit.
- A plan with a `Source` bullet only adds files under the knowledge-base folder and touches nothing in the source, so add to any of the above: the notes the `Created` lines list are the ones to remove to get back to the empty folder.
- Git, on the current branch (also a branch Establish made, when its plan bullet has no starting point): the starting commit, the state before Migrate's own edits, which the human restores with git's own tools.
