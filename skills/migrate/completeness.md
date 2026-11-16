# Completeness pass

Before deleting a source, prove that none of its text was lost. charter has no command for it: you do it with your own file and search tools and `charter` commands, and no script.

The paragraph rule is the plan format's, under `Section map`: blank-line separated, one fenced code block is one paragraph, a heading line is one paragraph, frontmatter is excluded.

1. Read the source and number its paragraphs from 1.
2. Take the notes the map lists as targets for this source. For each paragraph, find the same text in one of them. The match is exact once runs of whitespace (spaces, tabs, line breaks) collapse to one space. Search each target for the whole paragraph with your search tool in fixed-string mode; when the source wraps its lines, search one distinctive line of the paragraph and read around the hit to confirm the rest. A heading paragraph is present when the target note its part names has a heading line or a `title` with the same words, whatever the number of `#`; a different note's title does not count.
3. List every paragraph with no match: its number, its first words and the part of the map it belongs to.
4. Settle each listed paragraph with the human: add it verbatim to the target its part names, or record that the human confirmed it intentionally dropped, as a line under the `Progress` line: `Dropped from SRC: paragraph N, "first words"`.
5. Run steps 2 and 3 again on the changed notes.

Done when the list is empty: every paragraph is found in a target or confirmed dropped. Tell the human the count (`N paragraphs, all found` or `N found, M confirmed dropped`) before you delete anything.
