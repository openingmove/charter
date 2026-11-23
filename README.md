<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/charter-logo-dark.svg">
    <img src="images/charter-logo-light.svg" alt="charter logo: a ship's wheel with an open rim" width="128" height="128">
  </picture>
</p>

# charter

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

## Documentation

The user manual is in [`docs/guide/`](docs/guide/README.md), and the same pages are on the [wiki](https://github.com/openingmove/charter/wiki). Start with [Getting started](docs/guide/Getting-started.md); the reference covers the [contract syntax](docs/guide/Contract-syntax.md), the [commands](docs/guide/Commands.md), [plugins](docs/guide/Plugins.md) and the [diagnostic codes](docs/guide/Diagnostic-codes.md).

## Install

charter supports every Python version that is not end-of-life (today 3.11 to 3.15). A version is dropped when it reaches end-of-life. charter installs with [uv](https://docs.astral.sh/uv/). It is not on PyPI yet, so install it from this repository, by git URL or from a local checkout:

```
uv tool install git+https://github.com/openingmove/charter@main
```

`main` holds the latest release. Check it with `charter --version`. To upgrade to the next release, run `uv tool upgrade charter`. Local checkouts and versions: see [Install](docs/guide/Install.md).

## Quick start

Run it in a scratch folder. First, a contract:

```
charter init novel
```

Replace the starter's contents with one kind (the starter explains every line it holds):

```yaml
charter: 1
root: .

kinds:
  character:
    description: "A person in the story."
    path: "Characters/{title}.md"
    fields:
      kind:   {type: string, required: true}
      title:  {type: string, required: true, matches_filename: true}
      status: {values: [alive, dead], default: alive}
```

Then, from inside `novel`, create a note and check it:

```
charter new character "Mara"
charter validate
```

```
No problems found (profile: commit).
```

[Getting started](docs/guide/Getting-started.md) carries the example on: a note that breaks the contract, `charter describe` and `charter sweep`.

## GitHub Action

The charter GitHub Action checks pull requests and pushes. Add it to a workflow:

```yaml
name: charter
on:
  pull_request:
  push:
    branches: [main]
jobs:
  charter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: openingmove/charter@v0.2.1
        with:
          ref: v0.2.1
```

Give `ref` the same tag as `uses`. `uses` picks the action's own files; `ref` picks the charter it installs, and without it that is `main`. Inputs and the commit range: see [GitHub Action](docs/guide/GitHub-Action.md).

## Skills

Three skills cover the life of a contract: Establish writes the first contract, Migrate brings existing files into line with it, and Evolve changes it. Each one is started by you with a slash command. See [Skills](docs/guide/Skills.md).

Pick one route for your agent. Each skill checks `charter --version` first and installs nothing on your system.

| Agent | Install |
|---|---|
| Claude Code | `claude plugin marketplace add openingmove/charter`, then `claude plugin install charter@charter` (in a session, the `/plugin` commands should do the same) |
| Codex | `codex plugin marketplace add openingmove/charter`, then `codex plugin add charter@charter` |
| GitHub Copilot | `copilot plugin marketplace add openingmove/charter`, then `copilot plugin install charter@charter` |
| Gemini CLI | `gemini skills install https://github.com/openingmove/charter.git --path skills` (Gemini CLI 0.70.0 cannot clone it: install from a local checkout, see [The skills](docs/guide/Install.md#the-skills)) |
| Any other agent | `npx skills@latest add openingmove/charter` (through [skills.sh](https://skills.sh)) |

Do not install the same skills by two routes for one agent, or you will get each skill twice. Updates, local checkouts and the hooks of the contract guard: see [The skills](docs/guide/Install.md#the-skills).

## Development

```
uv sync
uv run pytest
```

See [Development](docs/guide/Development.md).

## License

MIT. See [LICENSE](LICENSE).
