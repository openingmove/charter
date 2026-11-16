# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Reports each heading of a targeted note that says TODO."""

import json
import sys

request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
targets = set(request["targets"])
diagnostics = [
    {
        "path": note["path"],
        "line": heading["line"],
        "severity": "error",
        "code": "todo-free/todo",
        "message": f"Heading `{heading['text']}` says TODO.",
    }
    for note in request["index"]["notes"]
    if note["path"] in targets
    for heading in note["headings"]
    if "TODO" in heading["text"]
]
sys.stdout.write(json.dumps({"protocol": "charter-plugin/1", "diagnostics": diagnostics}))
