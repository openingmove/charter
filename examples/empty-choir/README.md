# Harbourside Community Choir

We are a volunteer choir of about thirty singers. We want one knowledge base that holds what we currently keep in scattered chat threads and a shared spreadsheet.

The idea:

- The repertoire is the heart of it. We sing around forty pieces a year, and each piece has a composer, a voicing (SATB, SSA and so on), a difficulty, and a state: learning, performance-ready or retired.
- Singers belong to a section (soprano, alto, tenor, bass). A few of them are section leaders. We would like to know who can cover which part.
- Every Thursday we hold a rehearsal and about four times a year we give a concert. Each rehearsal works on a handful of pieces, and each concert has a programme drawn from the repertoire.
- Nothing is written down yet. We are starting from this paragraph.

## About this example

This is the "day one" example: a repository holding only an idea, with no notes and no `charter.yaml`.

Walkthrough of the Establish skill: the survey (`charter survey . --format json`) reports one Markdown file and no frontmatter, so this is an empty start and the README above counts as the first interview answer. The skill reads it back to you and asks only what it leaves open, in your words and one question at a time: which things are written once and never change, which go through stages, and how a concert's programme relates to the repertoire (the README already gives the kinds and the counts). It never asks about fields or YAML; it proposes those itself (for instance a composer and a difficulty for each piece) and asks you to confirm. It writes the draft with the README ignored, asks per kind whether its notes share a fixed outline (a rehearsal's agenda, say) and writes `Templates/<Kind>.md` for each yes for you to read and edit, then shows a plain summary and `charter describe --config <draft>`, and installs with `charter init --from <draft> --agents` once you say yes. The walkthrough succeeds when the installed `charter.yaml` covers pieces, singers, rehearsals and concerts, and `charter validate --all` and `charter docs --check` both pass.
