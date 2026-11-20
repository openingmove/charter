# Install

charter has two parts: the command line tool, and the skills that drive it. They install separately and release together from one version.

## The command line tool

charter needs Python 3.11 or later and installs with [uv](https://docs.astral.sh/uv/). It is not on PyPI yet, so install it from this repository, by git URL or from a local checkout:

```
uv tool install git+https://github.com/openingmove/charter@main
```

`main` holds the latest release, and uv remembers the branch, so an upgrade moves to the next release. To pin one release, name its tag instead, such as `@v0.2.1` (the tags are on the Releases page).

For a local checkout, give its path instead: `uv tool install /path/to/charter`, or `uv tool install C:\src\charter` on Windows.

Check it with `charter --version`. To upgrade:

```
uv tool upgrade charter
```

## The skills

The skills are described under [Skills](Skills.md). They install nothing on your system: the command line tool stays your decision, and each skill checks `charter --version` first and tells you what to run if it is missing or too old.

Pick one route for your agent. The repository is its own plugin marketplace (the plugin is named `charter`, in a marketplace named `charter`), and its skills sit in the `skills/` folder in the open Agent Skills format. The routes below name the repository's address, `openingmove/charter` on GitHub. While the repository is private, point a tool at a local checkout instead, as its own documentation allows. Claude Code, for example, reads a path as a local marketplace only when it starts with `./` or is absolute (a bare `name/name` means a GitHub repository).

**Claude Code**

```
/plugin marketplace add openingmove/charter
/plugin install charter@charter
```

This gives `/charter:establish`, `/charter:migrate` and `/charter:evolve`, and the hooks of [the contract guard](Contract-guard.md), which act only on a contract that opts in. Claude Code updates the plugin when the version changes.

**Codex** reads the same marketplace. Add it, then install `charter` from the plugin browser in a Codex session (`/plugins`):

```
codex plugin marketplace add openingmove/charter
```

**GitHub Copilot** (CLI and VS Code):

```
copilot plugin marketplace add openingmove/charter
copilot plugin install charter@charter
```

Copilot's marketplace list may also need the repository added to its settings.

Each tool changes its commands over time. If one of these is refused, see the tool's own documentation for adding a plugin marketplace.

**Gemini CLI** installs from the skills folder. Updating is manual: run the command again. A local checkout path or git URL works as Gemini's own documentation allows.

```
gemini skills install https://github.com/openingmove/charter.git --path skills
```

**Any other agent** installs through [skills.sh](https://skills.sh), which copies the skills into your project; update by hand. skills.sh's own documentation says which sources it accepts, such as a local checkout:

```
npx skills@latest add openingmove/charter
```

Do not install the same skills by two routes for one agent, or you will get each skill twice.

## Versions

The skills and the command line tool release together from one version. `plugin.json`'s `version` must equal `version` in `pyproject.toml` and `__version__` in `src/charter/__init__.py`, which `charter --version` prints (`tests/test_plugin_packaging.py` fails otherwise). Bump all three in one commit and tag that commit. After updating the skills, run `uv tool upgrade charter` so the two match. The plugin's hooks run `charter-hook`, a second command the tool installs beside `charter`. A command line tool too old to have it does not stop you: Claude Code reports a hook error and goes on, and the [contract guard](Contract-guard.md) stays off until you upgrade.

