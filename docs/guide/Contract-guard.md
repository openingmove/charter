# The contract guard

The rulebook tells agents never to change the contract to make a note pass, but a rule in prose is advice. The contract guard enforces it in Claude Code: with the guard on, a Claude Code session can write `charter.yaml` only after the human has typed `/charter:evolve`, `/charter:establish` or `/charter:migrate` in that session. An agent cannot start those skills, so a yes in the conversation is not enough. The guard is off unless the contract opts in, inside the agent layer:

```yaml
agents: {file: AGENTS.md, guard: true}
```

It needs the charter plugin enabled in Claude Code (see [The skills](Install.md#the-skills)) and a command line tool that has the `charter-hook` command (check with `charter-hook --help`). Nothing is written to `.claude/settings.json`: the plugin's hooks (`hooks/hooks.json`) are active wherever the plugin is enabled, and act only on a contract with `guard: true`. When the guard is on, the rulebook says so in a "Contract guard" section, and `charter describe --format json` reports `"guard": true`. Establish offers to switch it on.

How it works:

- When the human types one of the three commands, a `UserPromptExpansion` hook runs `charter-hook skill-started`, which records a marker for that session in a per-user state folder (`$XDG_STATE_HOME/charter` or `~/.local/state/charter` on Linux, `~/Library/Application Support/charter` on macOS, `%LOCALAPPDATA%\charter` on Windows), never in the repository. Each marker is the file `sessions/<sha256 of the session id>.json` in that folder.
- Before an `Edit`, `Write`, `MultiEdit` or `Bash` call whose input names a `charter.yaml`, a `PreToolUse` hook runs `charter-hook pre-tool-use`. It denies the call when the contract it writes has `guard: true` and the session has no marker, with a reason that tells the human to type `/charter:evolve`. Otherwise it answers nothing, and Claude Code's own permissions decide as usual.
- Claude Code filters the calls with each hook's `if` rule and matcher, so no process starts for a prompt or a tool call that does not name `charter.yaml`.

The guard judges the contract on disk before the call, so the edit that removes `guard: true` is itself refused. A contract that is missing or does not parse as YAML has no opt-in the guard can see, and the guard leaves it alone.

Limits:

- The marker lasts for the rest of the session: after Evolve finishes, the same session can still write `charter.yaml`. A new session starts without one.
- It covers a file named `charter.yaml` only. Templates, the rulebook, the Evolve draft and a contract under another name are not guarded.
- It reads a `Bash` command best effort: redirects, `tee`, in-place `sed` or `perl`, `mv`, `cp`, `rm`, `truncate`, `dd`, `git checkout`, `git restore`, `git rm`, `git mv`, and inline code (`python -c`, `sh -c`) that names `charter.yaml` count as writes; reading it, as `charter validate --config charter.yaml` does, does not. A script file that writes the contract goes unseen.
- It guards against a cooperative agent going around Evolve, not a hostile one: an agent that writes a marker itself, for example through `Bash`, gets past it.
- It works in Claude Code only. Other agents get no guard and rely on the rulebook's rule.
- A command line tool without `charter-hook` leaves the guard off: Claude Code reports a hook error on each guarded call and goes on.
