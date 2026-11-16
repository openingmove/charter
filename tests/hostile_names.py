"""File names that tools mishandle, and the helpers to put them where a test needs them.

Every character is built with chr() so that no invisible or non-ASCII character sits in this source file.
"""

import os
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

import pytest
from conftest import run_git

CATALOGUE = [
    ("lf", f"a{chr(0x0A)}b"),
    ("cr", f"a{chr(0x0D)}b"),
    ("vt", f"a{chr(0x0B)}b"),
    ("ff", f"a{chr(0x0C)}b"),
    ("u2028", f"a{chr(0x2028)}b"),
    ("u0085", f"a{chr(0x85)}b"),
    ("tab", f"a{chr(0x09)}b"),
    ("backslash", "a\\b"),
    ("colon", "a:b"),
    ("quote", 'a"b'),
    ("leading-dash", "-a"),
    ("trailing-dot", "a."),
    ("trailing-space", "a "),
    ("con", "CON"),
    ("nul", "NUL"),
    ("aux", "AUX"),
    ("nfc", f"caf{chr(0xE9)}"),
    ("nfd", f"cafe{chr(0x301)}"),
    ("long", "n" * 300),
]
NAMES = [pytest.param(name, id=label) for label, name in CATALOGUE]

_probed = {}


def can_create(name, tmp_path):
    """Whether the file system under `tmp_path` really holds a file called `name` (str or bytes), probed once."""
    key = (name, tmp_path.stat().st_dev)
    if key not in _probed:
        _probed[key] = _probe(name, tmp_path)
    return _probed[key]


def _probe(name, tmp_path):
    folder = Path(tempfile.mkdtemp(dir=tmp_path))
    raw = os.fsencode(name)
    try:
        with open(os.fsencode(folder) + os.sep.encode() + raw, "wb"):
            pass
        # A volume may create the file yet keep another spelling (Windows drops a trailing dot or space).
        return os.listdir(os.fsencode(folder)) == [raw]
    except (OSError, ValueError):
        return False
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def zip_with_raw_name(path, name_bytes):
    """A one-entry zip whose headers carry `name_bytes` exactly, which zipfile cannot write for a name that is
    not valid UTF-8 or that it would rewrite."""
    data = b"x\n"
    crc = zlib.crc32(data)
    head = struct.pack("<HHHHHIIIHH", 20, 0, 0, 0, 0x21, crc, len(data), len(data), len(name_bytes), 0)
    local = b"PK\x03\x04" + head + name_bytes + data
    # Central entry: version made by, the same fields as the local header, then comment, disk, attributes, offset.
    central = b"PK\x01\x02" + struct.pack("<H", 20) + head + struct.pack("<HHHII", 0, 0, 0, 0, 0) + name_bytes
    end = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 1, 1, len(central), len(local), 0)
    path.write_bytes(local + central + end)
    return path


def git_tree_with_paths(repo, paths, content=b"", *, refused_ok=False):
    """Stage a file with `content` at each of `paths` (str or bytes) straight into the index, with no working
    copy: a name that is not valid UTF-8, or holds a newline, cannot be created on every file system.

    Git for Windows leaves out, and still exits 0 for, a name Windows cannot hold (a control character, `CON`,
    `AUX`). The test skips then, unless `refused_ok`; the paths git left out are returned either way."""
    content = content if isinstance(content, bytes) else content.encode()
    blob = run_git(repo, "hash-object", "-w", "--stdin", input=content).decode()
    entries = b"".join(b"100644 " + blob.encode() + b"\t" + os.fsencode(path) + b"\0" for path in paths)
    run_git(repo, "update-index", "--add", "-z", "--index-info", input=entries)
    held = set(run_git(repo, "ls-files", "-z", input=b"").split(b"\0"))
    refused = [path for path in paths if os.fsencode(path) not in held]
    if refused and not refused_ok:
        pytest.skip(f"git on this system refuses the name {refused[0]!r}")
    return refused


_git_probed = {}


def git_can_hold(name, tmp_path):
    """Whether git on this system puts a file called `name` in the index, probed once per name."""
    if name not in _git_probed:
        repo = Path(tempfile.mkdtemp(dir=tmp_path))
        try:
            run_git(repo, "init", "-q")
            _git_probed[name] = not git_tree_with_paths(repo, [name], refused_ok=True)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
    return _git_probed[name]
