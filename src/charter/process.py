"""Running a command as an argv list, without a shell, with bounded time and output."""

import contextlib
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from charter import winjob

_CHUNK = 65536
# How long to keep reading after the command has exited or been stopped: a process it started may hold its
# output open long after, and charter must not wait for that.
_DRAIN_SECONDS = 1.0
# Polling interval while waiting for the command, so output past the limit stops it early.
_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class Finished:
    # None when charter stopped the command.
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    # Whether stdout or stderr went past the limit; what was read up to it is kept.
    overflowed: bool


def run_bounded(
    argv: Sequence[str],
    cwd: Path,
    stdin: bytes,
    *,
    timeout: float,
    limit: int,
    env: Mapping[str, str] | None = None,
) -> Finished:
    """Runs `argv` in `cwd` with `stdin`, and `env` in place of charter's own environment if given, stopping it
    and everything it started after `timeout` seconds or once stdout or stderr passes `limit` bytes. A process
    the command left running when it exited is ended too. Raises OSError when the command cannot start."""
    with _job() as job:
        process = _start(argv, cwd, env, job.creationflags)
        try:
            adopted = job.adopt(process)
        except BaseException:
            # The command may still be suspended and outside the job, where closing the job cannot reach it. Once
            # Popen has returned, no path leaves it suspended; for the window inside Popen, see `_start`.
            discard(process)
            raise
        if not adopted:
            # The job could not take the command, which ran no code; start it again on its own.
            process = _start(argv, cwd, env, 0)
        overflow = threading.Event()
        stdout, stderr = bytearray(), bytearray()
        readers = [
            threading.Thread(target=_read, args=(process.stdout, stdout, limit, overflow), daemon=True),
            threading.Thread(target=_read, args=(process.stderr, stderr, limit, overflow), daemon=True),
        ]
        # Written from a thread so a command that writes before reading cannot deadlock against charter.
        writer = threading.Thread(target=_write, args=(process.stdin, stdin), daemon=True)
        for thread in (writer, *readers):
            thread.start()

        deadline = time.monotonic() + timeout
        while process.poll() is None and not overflow.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            overflow.wait(min(remaining, _POLL_SECONDS))
        stopped = process.poll() is None
        # Decided from the last poll: a command that exits just as the deadline passes has finished, not timed out.
        timed_out = stopped and not overflow.is_set()
        if stopped:
            _stop(process, job)
            process.wait()
        elif os.name != "nt":
            # The command is gone, but its process group may not be: end what it left running.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
        # On Windows, ends every process the command left running. On both platforms, ending those processes also
        # ends the drain early when one holds the command's output open.
        job.close()
        drained_by = time.monotonic() + _DRAIN_SECONDS
        for reader in readers:
            reader.join(max(0.0, drained_by - time.monotonic()))
    return Finished(
        None if stopped else process.returncode, bytes(stdout), bytes(stderr), timed_out, overflow.is_set()
    )


def _start(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None, creationflags: int) -> subprocess.Popen:
    # Accepted window: an interrupt inside Popen after the process is created makes Popen raise without ending
    # it, so a command started suspended stays suspended, outside the job. The window lies inside the standard
    # library and lasts microseconds, and Popen returns no object, so charter cannot reach that process.
    return subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # Its own process group, so stopping it reaches the processes it started too.
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )


def discard(process: subprocess.Popen) -> None:
    """Ends `process`, waits for it, and closes its pipes."""
    try:
        process.kill()
        process.wait()
    finally:
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe:
                pipe.close()


def _read(pipe: BinaryIO, sink: bytearray, limit: int, overflow: threading.Event) -> None:
    # Closing the pipe on overflow makes a command still writing to it fail instead of blocking.
    with pipe:
        while chunk := pipe.read1(_CHUNK):
            if len(sink) + len(chunk) > limit:
                overflow.set()
                return
            sink += chunk


def _write(pipe: BinaryIO, data: bytes) -> None:
    # A command may exit, or close stdin, without reading all of it.
    try:
        with pipe:
            pipe.write(data)
    except OSError:
        pass


def _stop(process: subprocess.Popen, job: "_NoJob | winjob.Job") -> None:
    if os.name == "nt":
        if job.stop():
            return
        # taskkill /T ends the whole tree; process.kill() alone would leave the processes it started running.
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _job() -> "_NoJob | winjob.Job":
    """On Windows, a Job Object that ends every process the command starts once charter is done with it."""
    if os.name != "nt":
        return _NoJob()
    from charter import winjob

    return winjob.Job()


class _NoJob:
    """Stands in for a Windows Job Object where there is none."""

    creationflags = 0

    def __enter__(self) -> "_NoJob":
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def adopt(self, process: subprocess.Popen) -> bool:
        return True

    def stop(self) -> bool:
        return False

    def close(self) -> None:
        pass
