# Git hooks

Enforce the contract at commit time with [pre-commit](https://pre-commit.com), or with plain git hooks written in Python (these need `python3` on `PATH`; see below). Both run `charter validate --staged --commit-msg-installed` before the commit and `charter validate --staged --commit-msg FILE` once the message exists, so a `Charter-Allow` trailer can authorise an edit-policy violation. Install charter so the `charter` command is on `PATH`.

Install both hooks together. The pre-commit hook passes `--commit-msg-installed`, so it no longer warns that edit policies and `protected-region` wait for the commit-msg hook; with only the pre-commit hook installed, those checks are not judged at all and nothing says so.

Hooks are opt-in and protect only the clone they are installed in: `core.hooksPath` and `pre-commit install` are local configuration that never travels with the repository. `charter init` and the skills never install them unasked. CI ([GitHub Action](GitHub-Action.md)) is the only check guaranteed to cover every contributor.

With pre-commit, add this to `.pre-commit-config.yaml` and run `pre-commit install --hook-type pre-commit --hook-type commit-msg`:

```yaml
repos:
  - repo: https://github.com/openingmove/charter
    rev: <release tag or commit>
    hooks:
      - id: charter
      - id: charter-commit-msg
```

Without pre-commit, copy this repository's `.githooks/` directory (`pre-commit` and `commit-msg`, two short Python scripts) into the repository holding `charter.yaml`, then point git at it:

```
git config core.hooksPath .githooks
```

The scripts start with `#!/usr/bin/env python3`. On Unix they must be executable (`chmod +x .githooks/*`, then commit them so the bit travels). Git runs hooks from the repository's top directory, so `charter.yaml` must sit there.

**On Windows**, Git for Windows runs the hooks through its own `sh`, which needs a `python3` command on `PATH`. The python.org installer provides `python` and `py`, but not `python3`. Check from Git Bash before you rely on the hooks:

```
python3 --version
```

If that prints a version, the hooks work. If it fails, or prints "Python was not found; run without arguments to install from the Microsoft Store", `python3` is missing or is only the Windows "app execution alias" placeholder, and every commit will fail at the hook. To fix it, do one of these:

- Install Python from the Microsoft Store, which provides `python3`.
- Copy `python.exe` to `python3.exe` in the same folder of your Python installation, and make sure that folder is on `PATH`.
- Use pre-commit instead (above), which finds Python itself.
