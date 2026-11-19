# Diagnostic codes

## More diagnostic codes

The other pages of this manual explain most codes where they arise. These are the rest, so that every code charter can emit is named in this manual (a test keeps it so).

| Code | Meaning |
|---|---|
| `contract/not-found` | No contract at the `--config` path, or none above the working directory (exit `2`). |
| `contract/yaml` | The contract or lock is not valid UTF-8 text or not valid YAML. |
| `docs/stale` | The rulebook is missing or out of date and the contract has no `agents:` layer (see [The agent rulebook](Agent-rulebook.md)). |
| `usage/no-rulebook` | `charter docs` on a contract with neither `docs:` nor `agents:`; declare either one. |
| `usage/no-agent-layer` | `charter docs --link-agents` on a contract without `agents:`. |
| `index/unreadable`, `index/invalid-frontmatter` | A Markdown file that cannot be read, or whose frontmatter is not a YAML mapping between two `---` lines. |
| `schema/missing-kind`, `schema/unknown-kind` | A note names no kind, or one the contract does not declare. |
| `schema/required`, `schema/not-allowed` | A required field is missing, or a field is present where `allowed_when` forbids it. |
| `schema/item-type`, `schema/pattern` | A list item has the wrong type, or a value does not match the field's `pattern`. |
| `links/ambiguous`, `links/missing-anchor`, `links/wrong-kind` | A link matches several notes, points at a heading the target lacks, or a `link` field targets a note of the wrong kind. |
| `paths/kind-not-allowed` | A note's kind is not allowed by the path policy covering it. |
| `new/exists`, `new/ignored-path`, `new/name-too-long` | `charter new` would overwrite a file, place the note where a `paths:` policy ignores it, or needs a file name or path the file system rejects as too long. |
| `new/missing-field`, `new/no-free-value`, `new/no-path`, `new/unplaceable` | `charter new` lacks a required value, has no free `ids` value in the range, the kind has no `path`, or the `path` cannot be rendered from the values given. |
| `usage/unknown-kind`, `usage/unknown-variant`, `usage/no-title-field` | `charter new` names a kind or variant that is not declared, or gives a title to a kind without a `title` field. |
| `usage/invalid-set`, `usage/repeated-set`, `usage/conflicting-set` | A `--set` that is not `FIELD=VALUE`, is repeated for a single value, or conflicts with the title or `auto` value. |
| `usage/unknown-note`, `usage/ambiguous-note`, `usage/not-a-note` | `charter sweep` names no note, several, or a file that is not a note. |
| `usage/file-not-found`, `usage/file-unreadable` | A `--file` or `--commit-msg` path that does not exist, or a commit message file that cannot be read. |
| `usage/commit-msg-without-staged`, `usage/commit-msg-installed-without-staged`, `usage/contract-not-staged`, `usage/not-a-git-repository` | `--commit-msg` or `--commit-msg-installed` without `--staged`, `--staged` with a contract git does not hold, or `--staged`/`--range` outside a git working tree. |
| `usage/conflicting-options`, `usage/unknown-profile`, `usage/mixed-contracts` | Options that cannot be combined, a profile that is neither built in nor declared, or `--file` paths under different contracts. |
| `usage/snapshot-arguments` | `charter snapshot` words that fit neither `snapshot FOLDER` nor `snapshot restore ZIP`. |
| `usage/no-recorded-folder` | `snapshot restore` of a zip charter did not write needs `--to`. |
| `snapshot/restore-failed`, `snapshot/target-in-the-way` | The restore could not complete (the target was left as it was), or the target exists and is not a folder. |
| `usage/unknown-plugin`, `usage/invalid-source`, `usage/not-updatable` | A plugin command names a plugin that does not exist, a source that is not a git URL followed by `@` and a ref, a `--dev` path that is not a directory, a ref that is not a branch, tag or commit name, or a plugin that was not installed from git. |
| `plugin/exists`, `plugin/invalid-manifest`, `plugin/fetch-failed`, `plugin/write-failed` | `charter plugin add` finds the plugin's name taken, its manifest invalid, cannot fetch it from git, or cannot write it. |
| `plugin/source-mismatch` | `charter plugin add`, `update` or `remove` finds a plugin that `charter.lock` lists but whose `checks.<id>.source` is not `.charter/plugins/<id>`, so charter runs it from elsewhere. Nothing is changed; edit `source` back, or delete the lock entry by hand. |
| `files/leftover` | A temporary folder could not be fully deleted: the `.staging-*` folder of `charter plugin add`, `update` or `remove`, the folder `charter plugin add --from` and `update` clone a plugin into, the temporary copy `--staged` runs make of plugin files, or the staging and set-aside folders of `charter snapshot restore`. A warning on stderr naming the path to delete; the command's output and exit code are unchanged. A restore that fails names the leftover in its refusal's hint instead. charter clears read-only files and retries a few times first. |
