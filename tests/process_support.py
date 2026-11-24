"""Watching, from a test, a process that a command left behind."""

import contextlib
import ctypes
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259

# A process charter left behind sleeps this long, so a test that fails leaves nothing running for long.
# tests/fixtures/plugins/misbehave/misbehave.py repeats this value as a literal, since a plugin cannot import it;
# a test in tests/test_plugins.py fails when the two differ.
LEFTOVER_SECONDS = 30

# How long `gone_within` waits by default for a process to end.
GONE_WITHIN_SECONDS = 10.0


def windows_only():
    if os.name != "nt":
        pytest.skip("this platform has no Windows Job Objects")


def alive(pid):
    """Whether the process `pid` is still running."""
    if os.name != "nt":
        return _alive_posix(pid)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def _alive_posix(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # An ended process nobody has reaped yet still answers the signal, so read its state: Z means zombie.
    return _state_posix(pid) != "Z"


def _state_posix(pid):
    """The state letter of the process `pid`, or None when it cannot be read."""
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        # Linux. The command name in brackets may hold spaces or `)`, so the state follows the last `)`.
        try:
            return stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            return None
    # macOS and other systems without /proc.
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()[:1] or None


def gone_within(pid, seconds=GONE_WITHIN_SECONDS):
    """Whether the process `pid` has ended, or ends within `seconds`."""
    deadline = time.monotonic() + seconds
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def end(pid):
    """Ends the process `pid` if it still runs, so a failing test leaves nothing behind."""
    if pid is None or not alive(pid):
        return
    if os.name != "nt":
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        return
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False, timeout=10)
