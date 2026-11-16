# Way back

Make it after the plan is agreed and before the first note edit. Only `git switch -c` and `charter snapshot` change anything, each with the human's yes.

## Under git

`git rev-parse --is-inside-work-tree` prints `true` inside a repository; otherwise use [Without git](#without-git).

1. Run `git status --porcelain --ignored -- <folder>`. Disregard this run's own plan, draft and snapshot zip. Any other line is uncommitted work (`??`, ` M`, `M `, ` D`, or `!!` ignored, which git cannot restore).
2. With lines left, refuse to start. Offer two routes: the human commits those files, or you take a snapshot. Commit nothing for them; check again after their commit.
3. Read START before any switch: `git branch --show-current`, and `git rev-parse HEAD`. When no branch prints (detached HEAD), START is the commit hash.
4. Offer a new branch; the human names it or declines. On a yes run `git switch -c <name>`; the plan and draft come along.

Done when the check is clean or a snapshot exists. Tick `Way back made:` with every value in backticks, as `` branch `NAME` from `START` at `COMMIT` ``, `` commit `COMMIT` on `START` `` (no new branch) or, for a snapshot, the shape under Without git. Filled in and ticked: ``- [x] Way back made: branch `evolve-fields` from `main` at `3f9c2ab` ``.

## Without git

Run `charter snapshot <folder>`. Tell the human where the zip went and the restore command, word for word; it runs from a folder outside the knowledge base.

When it is refused (exit 1, `snapshot/unsupported-entry`), relay the listed entries and tell the human to remove them or put the folder under git with a commit, then start Evolve again. Change no note until a way back exists.

Done when the zip exists. Tick the line with `` snapshot `PATH`, restore with `COMMAND` `` (both in backticks).

## The undo

Tell it in one line and run none of it:

- Snapshot: the `charter snapshot restore ...` command from the plan line.
- New branch: `git switch <START>` (a commit hash: `git switch --detach <hash>`).
- Current branch: return to the starting commit with git's own tools.
