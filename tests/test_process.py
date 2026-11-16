import sys
import time

import pytest
from process_support import LEFTOVER_SECONDS, end, gone_within, windows_only

from charter.process import Finished, run_bounded

# Starts a process that outlives it, prints that process's pid, and exits 0.
LEAVES_A_PROCESS = (
    "import subprocess, sys\n"
    f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep({LEFTOVER_SECONDS})'])\n"
    "print(child.pid, flush=True)\n"
)


def test_a_process_the_command_left_running_ends_when_the_command_finishes(tmp_path):
    windows_only()
    pid = None
    try:
        finished = run_bounded(
            [sys.executable, "-c", LEAVES_A_PROCESS], tmp_path, b"", timeout=20, limit=65536
        )
        pid = int(finished.stdout.split()[0])

        assert (finished.returncode, finished.timed_out, finished.overflowed) == (0, False, False)
        assert gone_within(pid)
    finally:
        end(pid)


def _refuse_resume(monkeypatch, error):
    """Makes resuming a command started suspended raise `error`. Returns the pids it was asked to resume."""
    from charter import winjob

    pids = []

    def refuse(kernel32, pid):
        pids.append(pid)
        raise error

    monkeypatch.setattr(winjob, "_resume", refuse)
    return pids


def test_a_command_runs_unchanged_when_it_cannot_be_resumed_in_a_job(tmp_path, monkeypatch, capsys):
    windows_only()
    pids = _refuse_resume(monkeypatch, OSError("the resume is refused"))

    finished = run_bounded(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"],
        tmp_path,
        b"hello",
        timeout=20,
        limit=65536,
    )

    assert finished == Finished(0, b"HELLO", b"", False, False)
    assert capsys.readouterr().err == ""
    assert len(pids) == 1
    assert gone_within(pids[0])


def test_no_suspended_command_is_left_when_resuming_it_is_interrupted(tmp_path, monkeypatch):
    windows_only()
    pids = _refuse_resume(monkeypatch, KeyboardInterrupt())
    try:
        with pytest.raises(KeyboardInterrupt):
            run_bounded([sys.executable, "-c", "pass"], tmp_path, b"", timeout=20, limit=65536)

        assert len(pids) == 1
        assert gone_within(pids[0])
    finally:
        end(pids[0] if pids else None)


def test_a_command_runs_once_when_resuming_it_fails_after_one_thread_resumed(tmp_path, monkeypatch, capsys):
    windows_only()
    from charter import winjob

    runs = tmp_path / "runs.txt"
    real_threads, real_resume_thread = winjob._threads, winjob._resume_thread
    calls = []

    def two_threads(kernel32, pid):
        thread_ids = real_threads(kernel32, pid)
        return [*thread_ids, thread_ids[0]]

    def resume_once(kernel32, thread_id):
        calls.append(thread_id)
        if len(calls) > 1:
            # Fail only once the command has run, so starting it again would show.
            deadline = time.monotonic() + 10
            while not runs.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            raise OSError("the second thread cannot be resumed")
        real_resume_thread(kernel32, thread_id)

    monkeypatch.setattr(winjob, "_threads", two_threads)
    monkeypatch.setattr(winjob, "_resume_thread", resume_once)

    finished = run_bounded(
        [
            sys.executable,
            "-c",
            f"import sys; open({str(runs)!r}, 'a').write('run\\n'); sys.stdout.write(sys.stdin.read().upper())",
        ],
        tmp_path,
        b"hello",
        timeout=20,
        limit=65536,
    )

    assert finished == Finished(0, b"HELLO", b"", False, False)
    assert runs.read_text() == "run\n"
    assert capsys.readouterr().err == ""


def test_no_suspended_command_is_left_when_an_interrupt_comes_before_the_job_takes_it(tmp_path, monkeypatch):
    windows_only()
    from charter import winjob

    pids = []

    def interrupted(self, process):
        # The interrupt arrives after the command started suspended, before the job could take it.
        pids.append(process.pid)
        raise KeyboardInterrupt

    monkeypatch.setattr(winjob.Job, "adopt", interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):
            run_bounded([sys.executable, "-c", "pass"], tmp_path, b"", timeout=20, limit=65536)

        assert len(pids) == 1
        assert gone_within(pids[0])
    finally:
        end(pids[0] if pids else None)
