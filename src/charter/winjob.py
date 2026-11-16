"""A Windows Job Object that holds a command and every process it starts, and ends them all when charter closes it.

Windows only. Every step that fails leaves the command running without a job, as if this module did not exist."""

import ctypes
import subprocess
from ctypes import wintypes

from charter.process import discard

_CREATE_SUSPENDED = 0x00000004
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_THREAD_SUSPEND_RESUME = 0x0002
_TH32CS_SNAPTHREAD = 0x00000004
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_RESUME_FAILED = 0xFFFFFFFF
# The exit code of every process charter ends through the job.
_STOPPED_EXIT_CODE = 1


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, restype, argtypes in (
        ("CreateJobObjectW", wintypes.HANDLE, [ctypes.c_void_p, wintypes.LPCWSTR]),
        ("SetInformationJobObject", wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]),
        ("AssignProcessToJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
        ("TerminateJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.UINT]),
        ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("OpenThread", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
        ("ResumeThread", wintypes.DWORD, [wintypes.HANDLE]),
        ("CreateToolhelp32Snapshot", wintypes.HANDLE, [wintypes.DWORD, wintypes.DWORD]),
        ("Thread32First", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)]),
        ("Thread32Next", wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry)]),
        ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
    ):
        function = getattr(kernel32, name)
        function.restype, function.argtypes = restype, argtypes
    return kernel32


def _fail():
    raise ctypes.WinError(ctypes.get_last_error())


def _create(kernel32):
    """Returns a new job that ends every process in it when its last handle closes. Raises OSError."""
    # An interrupt between CreateJobObjectW returning and `job` being set would leak one empty job handle. That
    # window lies inside the interpreter, and the handle is unreachable from charter there, so it is accepted.
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        _fail()
    # From here on, any exception, an interrupt included, closes the handle before it propagates.
    try:
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            _fail()
    except BaseException:
        kernel32.CloseHandle(job)
        raise
    return job


def _assign(kernel32, job, pid):
    """Puts the process `pid` in `job`. Raises OSError."""
    process = kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not process:
        _fail()
    try:
        if not kernel32.AssignProcessToJobObject(job, process):
            _fail()
    finally:
        kernel32.CloseHandle(process)


def _threads(kernel32, pid):
    """Returns the ids of every thread of the process `pid`. Raises OSError."""
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
        _fail()
    ids = []
    try:
        entry = _ThreadEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32OwnerProcessID == pid:
                ids.append(entry.th32ThreadID)
            entry.dwSize = ctypes.sizeof(entry)
            found = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return ids


def _resume_thread(kernel32, thread_id):
    """Resumes the thread `thread_id`. Raises OSError."""
    thread = kernel32.OpenThread(_THREAD_SUSPEND_RESUME, False, thread_id)
    if not thread:
        _fail()
    try:
        if kernel32.ResumeThread(thread) == _RESUME_FAILED:
            _fail()
    finally:
        kernel32.CloseHandle(thread)


def _resume(kernel32, pid):
    """Resumes every thread of the process `pid`, which started suspended. Raises OSError only when no thread
    was resumed, so the process has run no code."""
    thread_ids = _threads(kernel32, pid)
    if not thread_ids:
        raise OSError(f"found no thread of process {pid} to resume")
    _resume_thread(kernel32, thread_ids[0])
    for thread_id in thread_ids[1:]:
        # Once one thread runs, the command has started: ending it and starting it again would run it twice, and
        # ending it for good would make it fail, which the quiet fall-back forbids. So it keeps running, in the
        # job if the assignment worked. A process started suspended has one thread, so a later thread is one the
        # running command started itself, which is not suspended; failing to resume it costs nothing.
        try:
            _resume_thread(kernel32, thread_id)
        except OSError:
            pass


class Job:
    """Use as a context manager around one command: start it with `creationflags`, then `adopt` it, and start it
    again without `creationflags` when `adopt` returns False. Closing the job, explicitly or on leaving the
    context, ends every process still in it."""

    def __init__(self) -> None:
        self._kernel32 = None
        self._handle = None
        try:
            self._kernel32 = _kernel32()
            self._handle = _create(self._kernel32)
            # Started suspended, the command cannot start a process before it is in the job.
            self.creationflags = _CREATE_SUSPENDED if self._handle else 0
        except (OSError, AttributeError):
            self.close()
            self.creationflags = 0
        except BaseException:
            # No caller holds this job yet, so nothing else could close its handle.
            self.close()
            raise

    def __enter__(self) -> "Job":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def adopt(self, process: subprocess.Popen) -> bool:
        """Puts `process`, started with `creationflags`, in the job and lets it run. Without a job, or when the
        assignment fails, the process runs on its own. Returns False, after ending the process and closing the
        job, when the process cannot be resumed: it has run no code, so the caller starts the command again
        without `creationflags`. Any other error also ends the process, then propagates; no path through this
        method leaves a process suspended. A process that `Popen` itself leaves behind when interrupted is out of
        reach: see `charter.process._start`."""
        if not self._handle:
            return True
        try:
            try:
                _assign(self._kernel32, self._handle, process.pid)
            except OSError:
                self.close()
            _resume(self._kernel32, process.pid)
        # A process left suspended would hang until its timeout, or for ever; end it instead.
        except OSError:
            discard(process)
            self.close()
            return False
        except BaseException:
            discard(process)
            self.close()
            raise
        return True

    def stop(self) -> bool:
        """Ends every process in the job. Returns False when there is no job to end."""
        if not self._handle:
            return False
        return bool(self._kernel32.TerminateJobObject(self._handle, _STOPPED_EXIT_CODE))

    def close(self) -> None:
        """Closes the job, which ends every process still in it."""
        if self._handle:
            handle, self._handle = self._handle, None
            self._kernel32.CloseHandle(handle)
