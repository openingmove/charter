import os
import subprocess
import sys

import pytest

CONTRACT = (
    "charter: 1\nroot: notes\nkinds:\n  entry:\n    fields:\n"
    "      title: {type: string, required: true}\n      n: {type: int}\n"
)
NOTE = "---\nkind: entry\ntitle: A\nn: 値\n---\n"
NOTE_PATH = "notes/日本語.md"


@pytest.fixture
def non_ascii_kb(make_kb):
    return make_kb({"charter.yaml": CONTRACT, NOTE_PATH: NOTE})


def _run_charter(cwd, *argv, encoding):
    # Windows without UTF-8 mode pipes stdout through the ANSI code page; forcing one here reproduces
    # that on any platform. The real check is the Windows CI job.
    return _run_charter_with(cwd, *argv, settings={"PYTHONIOENCODING": encoding})


@pytest.mark.parametrize("output_format", ["text", "agent"])
def test_non_ascii_output_is_written_as_utf8_whatever_the_locale(non_ascii_kb, output_format):
    result = _run_charter(non_ascii_kb, "validate", "--format", output_format, encoding="cp1252")

    assert result.returncode == 1
    assert b"UnicodeEncodeError" not in result.stderr
    output = result.stdout.decode("utf-8")
    assert NOTE_PATH in output
    assert "値" in output


def test_non_ascii_on_stderr_is_utf8_too(tmp_path):
    # argparse echoes a bad option value on stderr, the one place the CLI writes user-supplied text there.
    result = _run_charter(tmp_path, "validate", "--format", "日本語", encoding="cp1252")

    assert result.returncode == 2
    assert b"UnicodeEncodeError" not in result.stderr
    assert "日本語" in result.stderr.decode("utf-8")


def test_ascii_output_is_byte_identical_on_every_platform(make_kb):
    kb = make_kb({"charter.yaml": CONTRACT, "notes/a.md": "---\nkind: entry\ntitle: A\nn: many\n---\n"})

    result = _run_charter(kb, "validate", "--format", "agent", encoding="cp1252")

    assert result.stdout == (
        b"notes/a.md:4: error schema/type: Field `n` must be an integer, got text `many`.\n(profile: commit)\n"
    )


# The ways a process can start: no UTF-8 setting, UTF-8 mode, and a UTF-8 stream encoding. Under the last two
# the streams are already UTF-8, so a fix that only touches the encoding would leave Windows newlines in place.
STREAM_SETTINGS = {
    "no-utf8-setting": {},
    "utf8-mode": {"PYTHONUTF8": "1"},
    "utf8-io-encoding": {"PYTHONIOENCODING": "utf-8"},
}


def _run_charter_with(cwd, *argv, settings):
    # Starts from the environment without any UTF-8 setting, then applies `settings`.
    # CI and CHARTER_PROFILE would pick the `ci` profile (the in-process `charter` fixture clears them too).
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONUTF8", "PYTHONIOENCODING", "CI", "CHARTER_PROFILE")
    }
    env.update(settings)
    return subprocess.run(
        [sys.executable, "-m", "charter", *argv], cwd=cwd, env=env, capture_output=True, check=False
    )


@pytest.mark.parametrize("settings", STREAM_SETTINGS.values(), ids=STREAM_SETTINGS.keys())
@pytest.mark.parametrize("output_format", ["text", "json", "agent"])
def test_stdout_ends_lines_with_lf_on_every_platform(make_kb, output_format, settings):
    kb = make_kb({
        "charter.yaml": CONTRACT,
        "notes/a.md": "---\nkind: entry\ntitle: A\nn: many\n---\n",
        "notes/b.md": "---\nkind: entry\ntitle: B\nn: lots\n---\n",
    })

    result = _run_charter_with(kb, "validate", "--format", output_format, settings=settings)

    assert result.returncode == 1
    assert result.stdout.count(b"\n") >= 2
    assert b"\r\n" not in result.stdout
    assert b"\r\n" not in result.stderr


@pytest.mark.parametrize("settings", STREAM_SETTINGS.values(), ids=STREAM_SETTINGS.keys())
def test_stderr_ends_lines_with_lf_on_every_platform(tmp_path, settings):
    # argparse writes a usage line and an error line on stderr.
    result = _run_charter_with(tmp_path, "validate", "--format", "nope", settings=settings)

    assert result.returncode == 2
    assert result.stderr.count(b"\n") >= 2
    assert b"\r\n" not in result.stderr
