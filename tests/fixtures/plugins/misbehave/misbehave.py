# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Breaks the plugin protocol in the way the `behaviour` parameter names."""

import json
import subprocess
import sys
import time

behaviour = json.loads(sys.stdin.buffer.read().decode("utf-8"))["params"]["behaviour"]


def respond(diagnostics, protocol="charter-plugin/1"):
    sys.stdout.write(json.dumps({"protocol": protocol, "diagnostics": diagnostics}))


def diagnostic(**changes):
    return {"path": "a.md", "line": 1, "severity": "error", "code": "misbehave/found", "message": "Found.", **changes}


if behaviour == "crash":
    sys.stderr.write("misbehave: could not read the traversal table\n")
    sys.exit(4)
elif behaviour == "noisy-crash":
    sys.stderr.write("noise " * 5000 + "\nthe real cause\n")
    sys.exit(1)
elif behaviour == "hang":
    time.sleep(60)
elif behaviour == "not-json":
    sys.stdout.write("All good!\n")
elif behaviour == "wrong-protocol":
    respond([], protocol="charter-plugin/2")
elif behaviour == "malformed-diagnostic":
    respond([diagnostic(severity="fatal")])
elif behaviour == "foreign-code":
    respond([diagnostic(code="schema/type")])
elif behaviour == "escaping-path":
    respond([diagnostic(path="../charter.yaml")])
elif behaviour == "backslash-path":
    respond([diagnostic(path="sub\\a.md")])
elif behaviour == "drive-path":
    respond([diagnostic(path="C:/a.md")])
elif behaviour == "flood":
    sys.stdout.write("x" * (17 * 1024 * 1024))
elif behaviour == "orphan":
    # A process in its own session, out of reach of a process-group kill, that keeps stdout and stderr open.
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    time.sleep(60)
elif behaviour.startswith("leave-child"):
    # A process that outlives the plugin unless charter ends it; its pid goes to `child.pid` for the test.
    # The 30 matches LEFTOVER_SECONDS in tests/process_support.py; a plugin cannot import it, so keep them equal.
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    with open("child.pid", "w", encoding="utf-8") as pid_file:
        pid_file.write(str(child.pid))
    if behaviour == "leave-child-and-hang":
        time.sleep(60)
    elif behaviour == "leave-child-and-flood":
        sys.stdout.write("x" * (17 * 1024 * 1024))
    else:
        respond([])
elif behaviour == "bom":
    response = {"protocol": "charter-plugin/1", "diagnostics": [diagnostic()]}
    sys.stdout.buffer.write(b"\xef\xbb\xbf" + json.dumps(response).encode("utf-8"))
