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
import logging
import os
import platform
import re
import subprocess
import sys
import threading
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
_PROGRESS_LINE = re.compile(r"\s*\[(PROGRESS|\d+/\d+)\]")
_OWN_LOGGER_NAMES = ("root", "config", "__main__")

_current: "Run | None" = None


class Run:
    """One open Run Record. Every method is safe to call and never raises."""

    def __init__(self, record_file: Any = None, path: Path | None = None) -> None:
        self._file = record_file
        self._started = time.perf_counter()
        self.path = path
        self.failed = False
        self._status = "completed"
        self._lock = threading.RLock()
        self._captures: list[Any] = []

    def call(self, action: Callable[[], Any]) -> Any:
        """Run the action, record its outcome, and re-raise its failure unchanged."""
        try:
            return action()
        except Exception as exc:
            self._record_failure(exc)
            raise

    def __enter__(self) -> "Run":
        global _current
        if self._file is not None and _current is None:
            _current = self
            self._captures = [_LoggerCapture(self), _ConsoleCapture(self)]
            for capture in self._captures:
                capture.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        global _current
        if _current is self:
            _current = None
            for capture in self._captures:
                capture.stop()
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
        with self._lock:
            if self._file is None:
                return
            try:
                entry = {"type": entry_type, "time": datetime.now(timezone.utc).isoformat(), **fields}
                self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self._file.flush()
            except Exception:
                self._close()

    def _close(self) -> None:
        with self._lock:
            record_file, self._file = self._file, None
        if record_file is not None:
            try:
                record_file.close()
            except Exception:
                pass


class _LoggerCapture(logging.Handler):
    """Sends logger output into the Run Record, leaving what reaches the console as it was.

    Capturing INFO and DEBUG means lowering the root logger's level, and the CLI's entry
    point configures no logging, so a root handler would also silence logging's
    last-resort output and stop logging.warning() from configuring itself. So for the
    length of a Run this is the root logger's only handler, and it hands each record on
    exactly as logging would have done before the Run.
    """

    def __init__(self, run: Run) -> None:
        super().__init__()
        self._run = run
        self._console_handlers: list[logging.Handler] = []
        self._root_level = logging.WARNING

    def start(self) -> None:
        root = logging.getLogger()
        self._root_level = root.level
        self._console_handlers = list(root.handlers)
        root.handlers[:] = [self]
        root.setLevel(logging.DEBUG)

    def stop(self) -> None:
        root = logging.getLogger()
        added_during_run = [h for h in root.handlers if h is not self and h not in self._console_handlers]
        root.handlers[:] = [*self._console_handlers, *added_during_run]
        root.setLevel(self._root_level)
        self.close()

    def emit(self, record: logging.LogRecord) -> None:
        was_enabled = self._was_enabled_before_run(record)
        if was_enabled or record.name in _OWN_LOGGER_NAMES or record.name.startswith("src."):
            self._record(record)
        if record.name == "root" and not self._console_handlers:
            self._configure_like_module_level_logging()
        if was_enabled:
            self._hand_on(record)

    def _record(self, record: logging.LogRecord) -> None:
        try:
            fields = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
            if record.exc_info:
                fields["traceback"] = "".join(traceback.format_exception(*record.exc_info))
            self._run._write("log", **fields)
        except Exception:
            pass

    def _was_enabled_before_run(self, record: logging.LogRecord) -> bool:
        logger: logging.Logger = logging.getLogger(record.name)
        while not logger.level and logger.parent is not None:
            logger = logger.parent
        level = self._root_level if logger.parent is None else logger.level
        return record.levelno >= level

    def _configure_like_module_level_logging(self) -> None:
        """logging.info() and friends call basicConfig() when the root has no handlers."""
        root = logging.getLogger()
        root.handlers[:] = []
        logging.basicConfig()
        self._console_handlers = list(root.handlers)
        root.handlers[:] = [self]

    def _hand_on(self, record: logging.LogRecord) -> None:
        if self._console_handlers:
            for handler in self._console_handlers:
                if record.levelno >= handler.level:
                    handler.handle(record)
        elif not self._reached_a_library_handler(record):
            last_resort = logging.lastResort
            if last_resort is not None and record.levelno >= last_resort.level:
                last_resort.handle(record)

    @staticmethod
    def _reached_a_library_handler(record: logging.LogRecord) -> bool:
        logger: logging.Logger | None = logging.getLogger(record.name)
        while logger is not None and logger.parent is not None:
            if logger.handlers:
                return True
            logger = logger.parent if logger.propagate else None
        return False


class _ConsoleCapture:
    """Copies lines printed to the console into the Run Record.

    ``sys.stdout`` is replaced for the Run by a thin stand-in. Writes go to the real
    stream first and its errors reach the caller, and everything else (``fileno``,
    ``isatty``, ``encoding``) is the real stream's own, so ``input()`` still takes its
    console path. Nothing is recorded while a prompt_toolkit prompt is running, so
    prompt drawing can never enter the record. In the CLI, prompts don't write through
    here at all, because prompt_toolkit binds its output to the real console the first
    time it is used, which is the top-level menu, before any Run opens.
    """

    def __init__(self, run: Run) -> None:
        self._run = run
        self._real = sys.stdout
        self._partial_line = ""

    def start(self) -> None:
        if self._real is not None:
            sys.stdout = self

    def stop(self) -> None:
        if sys.stdout is self:
            sys.stdout = self._real
        with self._run._lock:
            partial_line, self._partial_line = self._partial_line, ""
        self._record_line(partial_line)
        # Anything still holding this object keeps reaching the console, unrecorded.
        self._run = Run()

    def write(self, text: str) -> int:
        written = self._real.write(text)
        self._capture(text)
        return written

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self._real.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def _capture(self, text: str) -> None:
        try:
            if _prompt_is_running():
                return
            with self._run._lock:
                *lines, self._partial_line = (self._partial_line + text).split("\n")
            for line in lines:
                self._record_line(line)
        except Exception:
            pass

    def _record_line(self, line: str) -> None:
        text = line.rstrip()
        if text:
            self._run._write("progress" if _PROGRESS_LINE.match(text) else "console", text=text)


def _prompt_is_running() -> bool:
    prompt_toolkit_current = sys.modules.get("prompt_toolkit.application.current")
    return prompt_toolkit_current is not None and prompt_toolkit_current.get_app_or_none() is not None


def current_run() -> Run:
    """Return the open Run, or a Run that records nothing when none is open."""
    return _current if _current is not None else _NO_RUN


def open_run(label: str, environment: Any = None) -> Run:
    """Open a Run Record for one execution. Never raises.

    Inside an open Run this returns a Run that records nothing, so one execution always
    has one Run Record.
    """
    if _current is not None:
        return Run()
    project_key, base_path = _project_of(environment) if environment is not None else _active_project()
    return _start_run(label, project_key, base_path)


def save_failure(label: str, exc: BaseException) -> Path | None:
    """Save a failure from before any project is selected, in the per-user folder."""
    with _start_run(label, None, None) as run:
        run._record_failure(exc)
    return run.path


def _start_run(label: str, project_key: str | None, base_path: str | None) -> Run:
    try:
        record_file, path = _create_record_file(label, base_path)
        run = Run(record_file, path)
        run._write("run_start", label=label, project_key=project_key, base_path=base_path)
        run._write("environment", **_capture_versions())
        return run
    except Exception:
        return Run()


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


_NO_RUN = Run()
