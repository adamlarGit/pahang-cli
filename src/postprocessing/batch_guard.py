"""Batch-level race safety for Full Report post-processing (ticket #147).

A run lock per date folder, a sweep of temp files left by dead runs, and an idle-sleep inhibitor. Nothing here
touches Word: `~$*` owner files are never deleted because they can mean the operator has the document open.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

LOCK_NAME = ".postprocess.lock"
STALE_TEMP_PATTERNS = (".tmp_conv_*", ".tmp_native_*", ".tmp_restore_*", ".tmp_mrg_*")

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


_GRACE_SECONDS = 5.0  # an unreadable or empty lock younger than this is a writer mid-publication
_START_TOLERANCE = 2.0  # clock slack when comparing a lock's timestamp with its PID's creation time


def _kernel32():
    """kernel32 with pointer-sized HANDLE signatures, so 64-bit handles are not truncated."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.GetProcessTimes.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


def _win32_probe(pid: int) -> tuple[bool, float | None]:
    """(alive, creation time as epoch seconds) for a PID on Windows."""
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5, None  # ERROR_ACCESS_DENIED: it exists
    try:
        code = wintypes.DWORD()
        if k32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
            return False, None
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        started = None
        if k32.GetProcessTimes(handle, *(ctypes.byref(t) for t in (created, exited, kernel, user))):
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            started = ticks / 1e7 - 11644473600  # FILETIME (1601) -> Unix epoch
        return True, started
    finally:
        k32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """True when a process with this PID is running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _win32_probe(pid)[0]
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_start_time(pid: int) -> float | None:
    return _win32_probe(pid)[1] if sys.platform == "win32" else None


class FolderLock:
    """Exclusive lock file holding PID and start time. Use `FolderLock.acquire`.

    The lock is published atomically (content written to a temp file, then hard-linked into place) so a reader
    never sees a PID-less lock. A stale lock is taken over by renaming it aside first; only the process whose
    rename succeeds may continue.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def acquire(cls, folder: Path) -> FolderLock | None:
        """Take the lock, taking over one left by a dead PID. None when a live process holds it."""
        path = folder / LOCK_NAME
        for _ in range(5):
            if cls._publish(path):
                return cls(path)
            judged = cls._read(path)
            if judged is None:
                continue  # vanished between our attempt and our read: retry
            if cls._is_live(path, judged):
                return None
            if not cls._take_over(path, judged):
                continue
        return None

    @staticmethod
    def _publish(path: Path) -> bool:
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}), encoding="utf-8")
        try:
            os.link(tmp, path)  # atomic and fails if the lock exists
            return True
        except FileExistsError:
            return False
        except OSError:  # filesystem without hard links: exclusive create (readers apply the grace period)
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(tmp.read_text(encoding="utf-8"))
            return True
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            return ""

    @staticmethod
    def _is_live(path: Path, raw: str) -> bool:
        try:
            data = json.loads(raw)
            pid = int(data["pid"])
            started = float(data["started"])
        except (ValueError, KeyError, TypeError):
            try:
                young = time.time() - path.stat().st_mtime < _GRACE_SECONDS
            except OSError:
                young = False
            return young  # a writer may still be mid-publication; an old unreadable lock is abandoned
        if not pid_alive(pid):
            return False
        proc_started = _process_start_time(pid)
        if proc_started is not None and started < proc_started - _START_TOLERANCE:
            return False  # the PID is alive but was reused by a newer process
        return True

    @classmethod
    def _take_over(cls, path: Path, judged: str) -> bool:
        """Rename the stale lock aside; True only if our rename won and what we moved is still the stale one."""
        if cls._read(path) != judged:
            return False  # someone replaced it since we judged it
        aside = path.with_name(f"{path.name}.stale.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        try:
            os.rename(path, aside)
        except OSError:
            return False  # another taker won
        try:
            moved = aside.read_text(encoding="utf-8")
        except OSError:
            moved = ""
        if moved != judged:  # we grabbed a fresh lock created in the meantime: put it back
            with contextlib.suppress(OSError):
                os.link(aside, path)
            with contextlib.suppress(OSError):
                aside.unlink()
            return False
        logger.warning("Took over stale post-processing lock %s", path)
        with contextlib.suppress(OSError):
            aside.unlink()
        return True

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink()


def sweep_stale_temps(folder: Path) -> list[Path]:
    """Delete temp files left in `folder` by dead runs. Call only while holding the folder lock."""
    removed: list[Path] = []
    for pattern in STALE_TEMP_PATTERNS:
        for stale in folder.glob(pattern):
            if stale.name.startswith("~$") or not stale.is_file():
                continue
            try:
                stale.unlink()
                removed.append(stale)
            except OSError as exc:
                logger.warning("Could not remove stale temp %s: %s", stale, exc)
    return removed


@contextlib.contextmanager
def keep_awake() -> Iterator[None]:
    """Prevent idle sleep for the duration of the batch (cannot stop a forced sleep or lid close)."""
    if sys.platform != "win32":
        yield
        return
    import ctypes

    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        set_state(_ES_CONTINUOUS)
