# charter user manual

Schemas, validation and scaffolding for Markdown knowledge bases.

`charter` reads a `charter.yaml` contract that declares the kinds of notes a knowledge base contains: their frontmatter fields, allowed values, where they live, how they are named, how they link to each other and what their body looks like. It then:

- **validates** the knowledge base against that contract (whole tree, staged files, or a single file),
- **scaffolds** new notes from per-kind templates (`charter new decision "Title"`),
- **describes** the rules to people and AI agents (`charter describe`, generated `CHARTER.md`),
- **sweeps** for notes affected by a change (`charter sweep <note>`),
- **runs plugins** for domain-specific checks, written in any language.

Editor-agnostic: plain Markdown with YAML frontmatter, Markdown links and/or `[[wikilinks]]`.

> **Beta.** charter is under active development. The command line, the contract format (`charter: 1`) and the skills may still change before 1.0; read the release notes before you upgrade, and pin a release tag in CI.
>
> Status: version 0.2.1, installed from this repository (not on PyPI). Delivered: the command line (`init`, `new`, `validate`, `describe`, `sweep`, `docs`, `survey`, `snapshot`, `plugin`), the optional agent, git and CI layers, and the Establish, Migrate and Evolve skills.

## Pages

Start here:

- [Getting started](Getting-started.md): the core commands with a worked example, and the optional agent, git and CI layers.
- [Install](Install.md): the command line tool, the skills, and how their versions match.
- [Skills](Skills.md): Establish, Migrate and Evolve.

Reference:

- [Contract syntax](Contract-syntax.md): kinds, fields, path policies, path patterns, variants, unique fields, links, tags, templates and the structure cutoff.
- [Edit policies and history checks](Edit-policies.md): `read-only` and `create-only`, the `Charter-Allow` trailer, `updated-date` and `protected-region`.
- [Commands](Commands.md): `init`, `validate`, `new`, `describe`, `survey`, `snapshot` and `sweep`.
- [Git hooks](Git-hooks.md): checking each commit with pre-commit or plain git hooks.
- [GitHub Action](GitHub-Action.md): checking pull requests and pushes in CI.
- [The agent rulebook](Agent-rulebook.md): `charter docs`, the generated `CHARTER.md` and the `agents-include` check.
- [The contract guard](Contract-guard.md): stopping a Claude Code session from editing `charter.yaml` on its own.
- [Severity profiles](Severity-profiles.md): profiles, diagnostic fields and exit codes.
- [Plugins](Plugins.md): the plugin protocol, installing plugins from git, and managing them.
- [Diagnostic codes](Diagnostic-codes.md): the codes no other page explains.
- [Development](Development.md): running the test suite.
