# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Records the request it receives, relative to its working directory, and reports nothing."""

import json
import sys
from pathlib import Path

request = sys.stdin.buffer.read()
Path("request.json").write_bytes(request)
sys.stdout.write(json.dumps({"protocol": "charter-plugin/1", "diagnostics": []}))
