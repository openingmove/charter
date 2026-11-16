"""Watching, from a test, a process that a command left behind on Windows."""

import ctypes
import os
import subprocess
import time

import pytest

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259

# A process charter left behind sleeps this long, so a test that fails leaves nothing running for long.
# tests/fixtures/plugins/misbehave/misbehave.py repeats this value as a literal, since a plugin cannot import it.
LEFTOVER_SECONDS = 30


def windows_only():
    if os.name != "nt":
        pytest.skip("this platform has no Windows Job Objects")


def alive(pid):
    """Whether the process `pid` is still running."""
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


def gone_within(pid, seconds=10.0):
    """Whether the process `pid` has ended, or ends within `seconds`."""
    deadline = time.monotonic() + seconds
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def end(pid):
    """Ends the process `pid` if it still runs, so a failing test leaves nothing behind."""
    if pid is not None and alive(pid):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False, timeout=10)
