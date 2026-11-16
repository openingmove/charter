# Dates for a structure cutoff

A kind with a `structure_cutoff` treats a note dated before it as a legacy note, exempt from the template's headings; the README's "Structure cutoff" subsection is the full rule. A note with no date is judged, so this file gives each undated note of such a kind a date that keeps it legacy. The cutoff itself stays exactly as the draft has it.

## Which notes need a date

Read each kind's `structure_cutoff` from the draft. For each such kind, take every note of the kind that the plan keeps or creates, and leave out a note that already holds a valid date in the cutoff's `field`. A date is an unquoted `YYYY-MM-DD` in the frontmatter. A value that is text or a timestamp (`2025-12-31T23:00:00`) is not a date: put that note to the human as a judgement call and write it as a `Note fixes` line.

A note that Migrate creates from a source takes the date of the source file it comes from. Several notes from one source share its date. With a `Source` bullet in the plan, that file lies in the source folder: give the history command and the modified-day command its path from the knowledge-base folder, the `Source` value joined to the file's path.

## Commands

Two commands below need a tool. Quote the note path in both, because names hold spaces (`"Rye Loaf.md"`): double quotes work in POSIX shells, `cmd` and PowerShell alike.

- `git` needs version 2.25 or newer (`%as`). On an older git, or outside a repository, skip it and use the modified day or the human's date.
- The modified-day command needs a Python interpreter. Use the first of `python3`, `python` and `py -3` that exists (try `python3 --version`, then the others), and write it where the commands below say `python3`.
- When no interpreter is available, do not guess: ask the human for one date for each folder that holds undated notes, and use source 1 below for every note there.

## Where each date comes from

In this order, per note:

1. **A date the human gives for a folder.** Ask once per folder that holds undated notes of such a kind: "Do you want to give one date for everything in this folder?" A given date applies to every undated note in that folder.
2. **The first-commit author date**, when the knowledge-base folder is under git (2.25 or newer) and the file has history. Run from the folder:

    ```
    git log --follow --diff-filter=A --format=%as -- "FILE"
    ```

    The last line printed is the day the file was first added (author date). No output means the file was never committed: use the modified time. A bulk import, a repository move or a squash gives many files one first-commit day: when the dates found for several notes of a folder are all the same day, say so to the human and ask whether to give one date for that folder instead.
3. **The file's modified time**, as the local calendar day (the same day `charter` uses for `today`), not the UTC day:

    ```
    python3 -c "import datetime,os,sys; print(datetime.date.fromtimestamp(os.stat(sys.argv[1]).st_mtime))" "FILE"
    ```

## Clamp to the day before the cutoff

Every date, whichever way it was found and whichever the human gave, is clamped by plain date arithmetic: take the cutoff date minus one day, and use the earlier of that day and the note's date. A date on or after the cutoff therefore becomes the day before it. A note edited on the migration day, which is the cutoff day, would otherwise be judged. For a cutoff of `2026-10-24`, `2026-10-24` and `2026-12-01` become `2026-10-23`, and `2024-05-09` stays.

Mark a clamped value in the plan (`clamped from DATE`) and tell the human how many were clamped. Never write a date on or after the cutoff.

## Show before writing

Write every proposed date into the plan's `Dates` section ([../establish/migration-plan.md](../establish/migration-plan.md) gives the lines) and walk the human through them before any note is written or edited. The human may change a proposed date; a changed date is clamped again. Writing a date means setting the kind's field to it: `--set FIELD=DATE` on `charter new` for a created note, an edit of the frontmatter for a note kept in place.

## Resume

The draft's cutoff is read again on every resume. When a date in the plan is on or after it, the human changed the draft by hand: compute the lines again from the cutoff the draft now holds before going on.
