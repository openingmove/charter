# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Reports each heading of a targeted note that contains one of the configured words."""

import json
import sys

request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
words = request["params"]["words"]
targets = set(request["targets"])
diagnostics = [
    {
        "path": note["path"],
        "line": heading["line"],
        "severity": "error",
        "code": "banned-words/found",
        "message": f"Heading `{heading['text']}` contains `{word}`.",
        "hint": "Reword the heading.",
    }
    for note in request["index"]["notes"]
    if note["path"] in targets
    for heading in note["headings"]
    for word in words
    if word in heading["text"].lower()
]
sys.stdout.write(json.dumps({"protocol": "charter-plugin/1", "diagnostics": diagnostics}))
