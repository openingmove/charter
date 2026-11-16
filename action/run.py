"""Runs charter's CI checks for a GitHub Actions event; the entry point of the composite action in action.yml."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# The code `charter docs` reports for a contract with nothing to generate. Repeated from charter.docs because
# this script runs outside charter's environment; a test keeps the two equal.
NO_RULEBOOK = "usage/no-rulebook"


def is_null_sha(sha):
    return set(sha) == {"0"}


def commit_range(event_name, event):
    """None when the event has no commits to judge; KeyError or TypeError when its payload lacks what it needs."""
    if event_name == "pull_request":
        pull_request = event["pull_request"]
        return f"{pull_request['base']['sha']}..{pull_request['head']['sha']}"
    if event_name == "push":
        before, after = event["before"], event["after"]
        if is_null_sha(after):
            return None
        if is_null_sha(before):
            # A new branch has no previous tip; what it adds is what the default branch lacks.
            before = f"origin/{event['repository']['default_branch']}"
        return f"{before}..{after}"
    return None


def main():
    # The echoed charter output is UTF-8 and the inherited-stdout steps write UTF-8 into the same log.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    config = ["--config", path] if (path := os.environ.get("CHARTER_CONFIG")) else []
    charter = shutil.which("charter")
    if charter is None:
        print("::error::charter was not found on PATH", file=sys.stderr)
        return 2
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    try:
        revisions = commit_range(event_name, event)
    except (KeyError, TypeError):
        print(f"::error::the `{event_name}` event payload lacks the commits to check", file=sys.stderr)
        return 2
    profile = ["--profile", "ci"]
    commands = [["validate", "--all", *profile], ["docs", "--check"]]
    if revisions is None:
        print(f"::notice::charter has no commit range to check for a `{event_name}` event; skipping --range.")
    else:
        commands.insert(1, ["validate", f"--range={revisions}", *profile])
    # A reviewer fixing a failing check wants every finding at once, not one per push.
    worst = 0
    for command in commands:
        print(f"::group::charter {' '.join(command)}", flush=True)
        if command[0] != "docs":
            # Inherited stdout, so a long validation streams into the Actions log as it runs.
            finished = subprocess.run([charter, *command, *config], check=False)
        else:
            # charter writes UTF-8 whatever the locale, so decode as UTF-8 rather than the Windows code page.
            finished = subprocess.run(
                [charter, *command, *config], check=False, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
            )
            if NO_RULEBOOK in finished.stdout:
                # The contract declares no rulebook, so there is none to be current.
                print("the contract declares no rulebook; skipping the rulebook check.")
                print("::endgroup::", flush=True)
                continue
            print(finished.stdout, end="", flush=True)
        print("::endgroup::", flush=True)
        worst = max(worst, finished.returncode)
    return worst


if __name__ == "__main__":
    sys.exit(main())
