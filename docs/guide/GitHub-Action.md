# GitHub Action

A composite action runs charter on pull requests and pushes: it sets up [uv](https://docs.astral.sh/uv/), installs charter at a ref, then runs `charter validate --all` and `charter validate --range` (both with `--profile ci`) and `charter docs --check`. All three run even if one fails, and the worst exit code decides the result. Make the job the required check on pull requests. For a contract with no rulebook (no `docs:` or `agents:` section) it skips the `docs --check` step.

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
      - uses: openingmove/charter@v0.2.0
        with:
          ref: v0.2.0
```

Give `ref` the same tag as `uses`. `uses` picks the action's own files; `ref` picks the charter it installs, and without it that is `main`.

`fetch-depth: 0` is required: `--range` compares each commit with its parent, and in a shallow clone it stops with `usage/shallow-history` rather than pass. The range comes from the event: for a pull request `<base sha>..<head sha>`; for a push `<before>..<after>`; for a push that creates a branch (an all-zero `before`) `origin/<default branch>..<after>`. A push that deletes a branch, or an event with no commits such as `workflow_dispatch`, skips the range and says so.

Inputs, all optional: `ref` (the branch, tag or commit of charter to install, default `main`), `source` (the repository to install charter from) and `config` (the path to `charter.yaml` when it is not at the top of the repository). One use of the action checks one contract: a repository with several knowledge bases adds the action once per contract, each with its own `config`.
