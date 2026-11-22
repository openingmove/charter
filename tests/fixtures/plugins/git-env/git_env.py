# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Records the GIT_* variables in its environment in git-env.json, in its working directory, and reports nothing."""

import json
import os
import sys
from pathlib import Path

sys.stdin.buffer.read()
seen = {name: value for name, value in os.environ.items() if name.startswith("GIT_")}
Path("git-env.json").write_text(json.dumps(seen), encoding="utf-8")
sys.stdout.write(json.dumps({"protocol": "charter-plugin/1", "diagnostics": []}))
