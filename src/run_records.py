"""Run Records: the saved account of one workflow execution.

Interface::

    with open_run("Generate Full Reports", environment) as run:
        run.call(action)                     # records outcome, re-raises its failure
        if run.failed and run.path: ...      # the file an operator can send

    current_run().record_request(request)    # from anywhere, without new parameters
    current_run().record_inputs(paths)
    with current_run().step("Export PDF"): ...

A Run Record is one JSON Lines file, flushed line by line, so a Word hang or a crash
still leaves everything up to that point. A record with no ``run_finish`` entry was
interrupted, crashed or hung.

Nothing here may stop a workflow: a problem saving a Run Record is swallowed, and the
Run carries on recording nothing. ``current_run()`` always returns a usable Run, which
records nothing when no Run is open, so callers never check for one.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# When set, every Run Record goes to this folder and no other location is tried.
# The test suite sets it so that no test can write into a real project folder.
RECORD_DIR_OVERRIDE_VARIABLE = "PAHANG_CLI_RUN_RECORD_DIR"

_UTILITY_PROJECT_KEY = "utility"
_UNKNOWN = "unknown"
_GIT_TIMEOUT_SECONDS = 5


class Run:
    """One open Run Record. Every method is safe to call and never raises."""

    def __init__(self, record_file: Any = None, path: Path | None = None) -> None:
        self._file = record_file
        self._started = time.perf_counter()
        self.path = path
        self.failed = False
        self._status = "completed"

    def call(self, action: Callable[[], Any]) -> Any:
        """Run the action, record its outcome, and re-raise its failure unchanged."""
        try:
            return action()
        except Exception as exc:
            self._record_failure(exc)
            raise

    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Anything escaping here is an interruption such as Ctrl+C, so the record is
        # left with no finish entry, which is what marks it as interrupted.
        if exc_type is None:
            self._write(
                "run_finish",
                status=self._status,
                duration_seconds=round(time.perf_counter() - self._started, 3),
            )
        self._close()

    def _record_failure(self, exc: BaseException) -> None:
        self.failed = True
        self._status = "failed"
        self._write(
            "error",
            message=str(exc),
            exception_type=type(exc).__name__,
            traceback="".join(traceback.format_exception(exc)),
        )

    def _write(self, entry_type: str, **fields: Any) -> None:
        if self._file is None:
            return
        try:
            entry = {"type": entry_type, "time": datetime.now(timezone.utc).isoformat(), **fields}
            self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._file.flush()
        except Exception:
            self._close()

    def _close(self) -> None:
        record_file, self._file = self._file, None
        if record_file is not None:
            try:
                record_file.close()
            except Exception:
                pass


def open_run(label: str, environment: Any = None) -> Run:
    """Open a Run Record for one execution. Never raises."""
    project_key, base_path = _project_of(environment) if environment is not None else _active_project()
    return _start_run(label, project_key, base_path)


def save_failure(label: str, exc: BaseException) -> Path | None:
    """Save a failure from before any project is selected, in the per-user folder."""
    with _start_run(label, None, None) as run:
        run._record_failure(exc)
    return run.path


def _start_run(label: str, project_key: str | None, base_path: str | None) -> Run:
    record_file, path = _create_record_file(label, base_path)
    run = Run(record_file, path)
    run._write("run_start", label=label, project_key=project_key, base_path=base_path)
    run._write("environment", **_capture_versions())
    return run


def _project_of(environment: Any) -> tuple[str | None, str | None]:
    """Return the project key, and the project folder when there is a real one."""
    try:
        key = environment.project_key
        base_path = Path(environment.base_path)
        if key == _UTILITY_PROJECT_KEY or not base_path.is_dir():
            return key, None
        return key, str(base_path)
    except Exception:
        return None, None


def _active_project() -> tuple[str | None, str | None]:
    """Find the project a utility action will use, without changing anything on disk.

    Utility actions build their environment after a Run opens. Building one here would
    create project subfolders, so this only reads the saved project and its catalog.
    """
    try:
        from src.cli_session import load_last_project_key
        from src.project.repository import JsonFileProjectRepository

        key = load_last_project_key()
        if key is None:
            return None, None
        base_path = Path(JsonFileProjectRepository().get(key).base_path)
        return key, str(base_path) if base_path.is_dir() else None
    except Exception:
        return None, None


def _create_record_file(label: str, base_path: str | None) -> tuple[Any, Path | None]:
    for folder, parents in _candidate_folders(base_path):
        try:
            folder.mkdir(parents=parents, exist_ok=True)
            path = folder / _record_name(label)
            return open(path, "x", encoding="utf-8", errors="backslashreplace"), path
        except Exception:
            continue
    return None, None


def _candidate_folders(base_path: str | None) -> list[tuple[Path, bool]]:
    override = os.environ.get(RECORD_DIR_OVERRIDE_VARIABLE)
    if override:
        return [(Path(override), True)]
    candidates: list[tuple[Path, bool]] = []
    if base_path is not None:
        # parents=False: a project folder that has gone away must not be recreated.
        candidates.append((Path(base_path) / "logs", False))
    candidates.append((_per_user_folder(), True))
    return candidates


def _per_user_folder() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return root / "pahang-cli" / "logs"


def _record_name(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-")[:40].lower() or "run"
    return f"{stamp}-{slug}-{uuid.uuid4().hex[:6]}.jsonl"


def _capture_versions() -> dict[str, str]:
    """Read versions without starting Word or Excel. Anything unreadable is unknown."""
    from src import __version__

    return {
        "app_version": __version__,
        "git_sha": _read_or_unknown(_git_sha),
        "python": _read_or_unknown(platform.python_version),
        "word": _read_or_unknown(lambda: _office_version("WINWORD.EXE")),
        "excel": _read_or_unknown(lambda: _office_version("EXCEL.EXE")),
    }


def _read_or_unknown(read: Callable[[], str]) -> str:
    try:
        return read() or _UNKNOWN
    except Exception:
        return _UNKNOWN


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parent.parent,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )
    return completed.stdout.strip()


def _office_version(executable: str) -> str:
    """Read an Office program's file version from disk, by way of the registry."""
    import win32api
    import winreg

    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
        program_path = winreg.QueryValue(key, None)
    info = win32api.GetFileVersionInfo(program_path, "\\")
    high, low = info["FileVersionMS"], info["FileVersionLS"]
    return f"{high >> 16}.{high & 0xFFFF}.{low >> 16}.{low & 0xFFFF}"
