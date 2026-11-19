# Severity profiles

Every diagnostic has a base severity. A profile then adjusts it for the stage charter runs in, so work in progress warns while CI enforces. charter picks the profile automatically: `--file` uses `edit`, plain `charter validate` and `--staged` (with or without `--commit-msg`) use `commit`, and `--range` and any run with `CI=true` use `ci`. `--profile NAME` or the `CHARTER_PROFILE` environment variable forces one, including a custom name declared under `profiles:`. The output names the active profile.

The built-in `edit` and `commit` profiles downgrade `schema/unknown-field`, `schema/missing-frontmatter`, `structure` and `residue` to warnings; `ci` keeps base severities. That suits a branch + pull-request workflow where CI on the pull request is the gate. Declaring a profile replaces its built-in default:

```yaml
profiles:
  commit: {}                         # commits straight to main: enforce base severities
  review: {schema: warning, schema/type: error}   # keys: a diagnostic code or a check id; a code wins

checks:
  paths: {severity: warning}         # base severity of every diagnostic of the check
  schema: {enabled: false}           # turn a check off
```

Profile values are `error`, `warning`, `info` or `off`. A key must be a check id or a diagnostic code one of the checks reports. Built-in defaults only ever lower a severity; a declared profile sets exactly what it says. `--strict` turns the remaining warnings into errors, except those a `Charter-Allow` trailer accounts for (an allowed violation, `override/unused`). An unknown profile name, or a `--file` path that does not exist, is a usage error (exit `2`) reported as a diagnostic in the requested format.

Each diagnostic carries `path`, `line`, `severity`, `code`, `message` and `hint`. Paths are relative to the directory holding `charter.yaml`.

Exit codes: `0` clean (warnings allowed unless `--strict`), `1` errors found, `2` contract or usage error, `3` a plugin failed to run (see [Plugins](Plugins.md)).

When stdout is closed early (`charter validate | head`) charter stops quietly with no traceback. It exits `141` (the status of a process killed by SIGPIPE, on every platform) if the pipe closed while it was still writing, and with its own exit code if only the final flush met the closed pipe. A closed stderr is not handled. The console script now points at `charter.cli:run`, so an existing install needs `uv tool install --reinstall` (or an upgrade that regenerates the script) to get this.
