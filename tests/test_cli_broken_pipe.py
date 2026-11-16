"""A closed stdout (`charter ... | head`) ends quietly, with no traceback, for every command that writes output."""

import os
import subprocess
import sys

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n      title: {type: string, required: true}\n"
# Far more than any pipe buffer holds, so the command is still writing when the reader leaves.
NOTE_COUNT = 1500


def _run_and_close_early(cwd, argv):
    process = subprocess.Popen(
        [sys.executable, "-m", "charter", *argv], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    process.stdout.read(16)
    process.stdout.close()
    stderr = process.stderr.read()
    process.stderr.close()
    return process.wait(timeout=60), stderr.decode()


def test_closed_pipe_while_writing_exits_quietly(make_kb):
    files = {"charter.yaml": CONTRACT}
    files.update({f"notes/n{number:04}.md": "---\nkind: entry\n---\n" for number in range(NOTE_COUNT)})
    kb = make_kb(files)

    code, stderr = _run_and_close_early(kb, ["validate", "--format", "json"])

    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
    assert stderr == ""
    assert code == 141


def test_closed_pipe_at_the_final_flush_keeps_the_commands_own_exit_status(make_kb):
    # The read end is closed before the child starts, and its small output stays buffered until the flush at
    # exit, so only that flush meets the closed pipe.
    kb = make_kb({"charter.yaml": CONTRACT, "notes/a.md": "---\nkind: entry\n---\n"})
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "charter", "validate"], cwd=kb, stdout=write_end, stderr=subprocess.PIPE
        )
    finally:
        os.close(write_end)
    stderr = process.stderr.read().decode()
    process.stderr.close()

    assert process.wait(timeout=60) == 1
    assert stderr == ""
