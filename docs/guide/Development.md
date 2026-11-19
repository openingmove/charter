# Development

```
uv sync
uv run pytest
```

Tests drive the CLI in-process against small invented knowledge bases under `tests/fixtures/` and compare `--format json` output with each fixture's `expected.json`. After an intentional output change, regenerate with `uv run pytest --update-golden` and review the diff.
