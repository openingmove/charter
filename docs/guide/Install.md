# Install

charter has two parts: the command line tool, and the skills that drive it. They install separately and release together from one version.

## The command line tool

charter supports every Python version that is not end-of-life (today 3.11 to 3.15). A version is dropped when it reaches end-of-life. charter installs with [uv](https://docs.astral.sh/uv/). It is not on PyPI yet, so install it from this repository, by git URL or from a local checkout:

```
uv tool install git+https://github.com/openingmove/charter@main
```

`main` holds the latest release, and uv remembers the branch, so an upgrade moves to the next release. To pin one release, name its tag instead, such as `@v0.3.0` (the tags are on the Releases page).

For a local checkout, give its path instead: `uv tool install /path/to/charter`, or `uv tool install C:\src\charter` on Windows.

Check it with `charter --version`. To upgrade:

```
uv tool upgrade charter
```

## The skills

The skills are described under [Skills](Skills.md). They install nothing on your system: the command line tool stays your decision, and each skill checks `charter --version` first and tells you what to run if it is missing or too old.

Pick one route for your agent. The repository is its own plugin marketplace (the plugin is named `charter`, in a marketplace named `charter`), and its skills sit in the `skills/` folder in the open Agent Skills format. The routes below name the repository's address, `openingmove/charter` on GitHub. For Claude Code, Gemini CLI and skills.sh, you can give the path of a local checkout instead. Claude Code reads a path as a local marketplace only when it starts with `./` or is absolute (a bare `name/name` means a GitHub repository).

**Claude Code**, from a shell:

```
claude plugin marketplace add openingmove/charter
claude plugin install charter@charter
```

The in-session commands `/plugin marketplace add openingmove/charter` and `/plugin install charter@charter` should do the same; see Claude Code's documentation if one is refused. This gives `/charter:establish`, `/charter:migrate` and `/charter:evolve`, and the hooks of [the contract guard](Contract-guard.md), which act only on a contract that opts in. Claude Code updates the plugin when the version changes.

**Codex** reads the same marketplace. Add it, then install `charter`. The plugin browser in a Codex session, `/plugins`, should also install it; see Codex's documentation if it does not:

```
codex plugin marketplace add openingmove/charter
codex plugin add charter@charter
```

**GitHub Copilot** (CLI and VS Code):

```
copilot plugin marketplace add openingmove/charter
copilot plugin install charter@charter
```

In VS Code, Copilot's marketplace list may also need the repository added to its settings.

**Gemini CLI** installs from the skills folder. Updating is manual: run the command again. A local checkout path works in place of the git URL. Gemini CLI 0.70.0 cannot clone a git URL (`Use of "GIT_CONFIG_SYSTEM" is not permitted`); with that version, install from a local checkout.

```
gemini skills install https://github.com/openingmove/charter.git --path skills
```

**Any other agent** installs through [skills.sh](https://skills.sh), which copies the skills into your project; update by hand. A local checkout path works in place of `openingmove/charter`:

```
npx skills@latest add openingmove/charter
```

Do not install the same skills by two routes for one agent, or you will get each skill twice.

## Versions

The skills and the command line tool release together from one version. `plugin.json`'s `version` must equal `version` in `pyproject.toml` and `__version__` in `src/charter/__init__.py`, which `charter --version` prints (`tests/test_plugin_packaging.py` fails otherwise). Bump all three in one commit and tag that commit. After updating the skills, run `uv tool upgrade charter` so the two match. The plugin's hooks run `charter-hook`, a second command the tool installs beside `charter`. A command line tool too old to have it does not stop you: Claude Code reports a hook error and goes on, and the [contract guard](Contract-guard.md) stays off until you upgrade.
