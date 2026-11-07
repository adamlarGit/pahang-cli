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

Every line is one JSON object with a ``type`` and a ``time``. The types are ``run_start``,
``environment`` (app, git, Python, Word and Excel versions), ``request``, ``request_update``,
``input`` (path, size, modified), ``step_start``, ``step_finish``, ``log``, ``progress``,
``console``, ``warning`` and ``error`` (each with ``traceback`` when there was an exception),
``cancelled``, ``result``,
``output`` and ``run_finish``. Its ``status`` is ``completed``, ``completed_with_errors``
(some items failed), ``failed`` (the whole job failed) or ``cancelled`` (the operator cancelled
by way of ``OperationCancelled``; a cancel that just returns is recorded as ``completed``).

A ``request_update`` has ``workflow``, naming an earlier ``request`` with that ``workflow`` value,
and ``changes``, the fields that differ from it. To rebuild the final request, apply each
``changes`` over the ``request`` in order. A new key whose value is ``None`` is left out, because
it reads the same as a missing key. A key left out of a later request stays in the rebuilt one.

Records live in ``<project base path>/logs/``. Runs with no real project folder use
``%LOCALAPPDATA%\\pahang-cli\\logs\\``. Setting the environment variable
``PAHANG_CLI_RUN_RECORD_DIR`` sends every record to that folder instead, with no fallback.
The test suite relies on this, and it works the same way in production.

Nothing here may stop a workflow: a problem saving a Run Record is swallowed, and the
Run carries on recording nothing. ``current_run()`` always returns a usable Run, which
records nothing when no Run is open, so callers never check for one.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import logging
import math
import os
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

# When set, every Run Record goes to this folder and no other location is tried.
# The test suite sets it so that no test can write into a real project folder.
RECORD_DIR_OVERRIDE_VARIABLE = "PAHANG_CLI_RUN_RECORD_DIR"

_UTILITY_PROJECT_KEY = "utility"
_UNKNOWN = "unknown"
_GIT_TIMEOUT_SECONDS = 5
_PROGRESS_LINE = re.compile(r"\s*\[(PROGRESS|\d+/\d+)\]")
_OWN_LOGGER = "src"
_MODULE_LEVEL_LOGGING_CODE = {
    function.__code__
    for function in (logging.debug, logging.info, logging.warning, logging.error, logging.critical, logging.log)
}
_MAX_DESCRIBE_DEPTH = 12
_RESULT_OUTPUT_FIELDS = (
    "output_path",
    "output_pdf_path",
    "output_directory",
    "output_folder",
    "cleaned_pdf_path",
    "generated_paths",
    "deliverables",
    "final_deliverables",
    "created_directories",
    "ingested_files",
    "files_moved",
)

_current: "Run | None" = None


class OperationCancelled(ValueError):
    """The operator cancelled a prompt. Reaches the action layer, but isn't a failure."""


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
        self._error_messages: set[str] = set()
        self._errors_with_traceback: set[str] = set()
        self._warning_messages: set[str] = set()
        self._requests: dict[str, dict[str, Any]] = {}
        self._inputs_seen: set[str] = set()
        self._outputs_seen: set[str] = set()

    def call(self, action: Callable[[], Any]) -> Any:
        """Run the action, record its outcome, and re-raise its failure unchanged."""
        try:
            with self.step("Execute action"):
                result = action()
        except OperationCancelled as exc:
            self._status = "cancelled"
            self._write("cancelled", message=_text_of(exc))
            raise
        except Exception as exc:
            self.record_failure(exc, exc)
            raise
        self._record_result(result)
        return result

    def record_request(self, request: Any) -> None:
        """Record what was asked for. Unserialisable parts are recorded by a description.

        For a dataclass request, any path field other than an output path is also recorded as
        an input. A dict request's paths aren't, so its caller records them with record_inputs().

        An action can record what the operator selected, and its workflow can record the
        full request later. A dict request with the same ``workflow`` as an earlier one adds
        only what changed, as a ``request_update``, or nothing if nothing did.
        """
        if self._file is None:
            return
        described = _describe_safely(request)
        workflow = described.get("workflow") if isinstance(described, dict) else None
        earlier = self._requests.get(workflow) if isinstance(workflow, str) else None
        if earlier is None:
            self._write("request", request=described)
            if isinstance(workflow, str):
                self._requests[workflow] = dict(described)
        else:
            changes = {key: value for key, value in described.items() if earlier.get(key) != value}
            if changes:
                self._write("request_update", workflow=workflow, changes=changes)
                earlier.update(changes)
        self.record_inputs(_input_paths_in(request))

    def record_inputs(self, paths: Iterable[Any]) -> None:
        """Record each input file's path, size and modified time, with no copy and no hash."""
        if self._file is None:
            return
        try:
            for path in paths:
                self._record_input(path)
        except Exception:
            pass

    def record_input_folder(self, folder: Any, suffixes: Iterable[str] = (), *, recursive: bool = False) -> None:
        """Record a folder's input files, optionally including nested survey files.

        ``suffixes`` limits which files count. A folder with nothing to list, or a path that
        isn't a folder, is recorded as itself.
        """
        if self._file is None:
            return
        try:
            wanted = {suffix.lower() for suffix in suffixes}
            root = Path(folder).expanduser()
            children = root.rglob("*") if recursive else root.iterdir()
            files = sorted(
                child
                for child in children
                if child.is_file()
                and not child.name.startswith("~$")
                and (not wanted or child.suffix.lower() in wanted)
            )
        except Exception:
            files = []
        self.record_inputs(files or [folder])

    def record_outputs(self, paths: Iterable[Any]) -> None:
        """Record what the action produced. A path already recorded adds nothing."""
        if self._file is None:
            return
        try:
            for path in paths:
                if path is not None and str(path) not in self._outputs_seen:
                    self._outputs_seen.add(str(path))
                    self._write("output", path=str(path))
        except Exception:
            pass

    def record_warning(self, message: Any, exc: BaseException | None = None) -> None:
        """Record a warning, which doesn't change the status. A repeat adds nothing."""
        text = _text_of(message)
        if text in self._warning_messages:
            return
        self._warning_messages.add(text)
        fields = {} if exc is None else {"traceback": _traceback_of(exc)}
        self._write("warning", message=text, **fields)

    def record_error(self, message: Any, exc: BaseException | None = None) -> None:
        """Record that one item failed while the action carried on.

        The Run finishes as ``completed_with_errors`` and the console shows the record's path.
        """
        self._mark_problem("completed_with_errors")
        self._write_error(message, exc)

    def record_failure(self, message: Any, exc: BaseException | None = None) -> None:
        """Record that the action's whole job failed, even though it returns normally.

        The Run finishes as ``failed`` and the console shows the record's path.
        """
        self._mark_problem("failed")
        self._write_error(message, exc)

    def mark_failed(self) -> None:
        """Say that the errors already recorded add up to the whole job failing."""
        self._mark_problem("failed")

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        """Record one named, timed stage. A failure inside it passes straight through."""
        started = time.perf_counter()
        self._write("step_start", name=name)
        try:
            yield
        except BaseException as exc:
            self._write(
                "step_finish",
                name=name,
                status="failed",
                error=_text_of(exc),
                duration_seconds=round(time.perf_counter() - started, 3),
            )
            raise
        self._write(
            "step_finish",
            name=name,
            status="completed",
            duration_seconds=round(time.perf_counter() - started, 3),
        )

    def __enter__(self) -> "Run":
        global _current
        if self._file is not None and _current is None:
            _current = self
            _ignoring_failure(self._start_captures)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        global _current
        if _current is self:
            _current = None
            for capture in self._captures:
                _ignoring_failure(capture.stop)
        # Anything escaping here is an interruption such as Ctrl+C, so the record is
        # left with no finish entry, which is what marks it as interrupted.
        if exc_type is None:
            self._write(
                "run_finish",
                status=self._status,
                duration_seconds=round(time.perf_counter() - self._started, 3),
            )
        self._close()

    def _start_captures(self) -> None:
        self._captures = [_LoggerCapture(self), _ConsoleCapture(self)]
        for capture in self._captures:
            _ignoring_failure(capture.start)

    def _mark_problem(self, status: str) -> None:
        if self._file is None and self.path is None:
            return
        self.failed = True
        if self._status != "failed":
            self._status = status

    def _write_error(self, message: Any, exc: BaseException | None) -> None:
        """Write one error. A repeat adds nothing, unless it brings the first traceback."""
        text = _text_of(message)
        if exc is None:
            if text not in self._error_messages:
                self._error_messages.add(text)
                self._write("error", message=text)
        elif text not in self._errors_with_traceback:
            self._error_messages.add(text)
            self._errors_with_traceback.add(text)
            self._write("error", message=text, exception_type=type(exc).__name__, traceback=_traceback_of(exc))

    def _record_result(self, result: Any) -> None:
        """Take outputs, warnings and errors from what the action returned, if it says."""
        if self._file is None or result is None:
            return
        try:
            self._write("result", result=_describe_safely(result))
            for field in _RESULT_OUTPUT_FIELDS:
                self.record_outputs(_as_list(getattr(result, field, None)))
            for warning in _as_list(getattr(result, "warnings", None)):
                self.record_warning(warning)
            # The workflow says when its whole job failed, through mark_failed() or record_failure().
            errors = _as_list(getattr(result, "errors", None))
            for error in errors:
                self.record_error(error)
            failed_count = getattr(result, "failed_count", 0)
            # Whoever filled failed_packages has recorded those failures, with tracebacks.
            if (
                errors
                or _as_list(getattr(result, "failed_packages", None))
                or (isinstance(failed_count, int) and failed_count > 0)
            ):
                self._mark_problem("completed_with_errors")
        except Exception:
            pass

    def _record_input(self, path: Any) -> None:
        if not isinstance(path, (str, os.PathLike)) or str(path) in self._inputs_seen:
            return
        self._inputs_seen.add(str(path))
        try:
            stat = os.stat(path)
        except OSError:
            self._write("input", path=str(path), exists=False, size=None, modified=None)
            return
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        self._write("input", path=str(path), exists=True, size=stat.st_size, modified=modified)

    def _write(self, entry_type: str, **fields: Any) -> None:
        with self._lock:
            if self._file is None:
                return
            try:
                entry = {"type": entry_type, "time": datetime.now(timezone.utc).isoformat(), **fields}
                line = json.dumps(entry, ensure_ascii=False) + "\n"
            except Exception:
                return
            try:
                self._file.write(line)
                self._file.flush()
            except Exception:
                # Stop here rather than risk a half-written line in the middle of the file.
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
    """Sends this program's logger output into the Run Record, leaving the console as it was.

    Levels are lowered only for what is captured: the ``src`` logger, and calls made directly
    on the root logger such as ``logging.info()``. The root level never changes, so other
    libraries' loggers behave as they did, whatever handlers they have.

    The entry point configures no logging, so a plain root handler would silence logging's
    last-resort output and stop ``logging.warning()`` from configuring itself. So for the
    length of a Run this is the root logger's only handler, and it hands each record on to
    the root's real handlers only if it would have reached them before the Run. A handler
    added to the root during a Run joins them. Only a handler attached to a ``src`` logger
    during a Run would see lowered levels; nothing in this program attaches one.
    """

    def __init__(self, run: Run) -> None:
        super().__init__()
        self._run = run
        self._console_handlers: list[logging.Handler] = []
        self._src_level = logging.NOTSET

    def start(self) -> None:
        root = logging.getLogger()
        src = logging.getLogger(_OWN_LOGGER)
        self._src_level = src.level
        self._console_handlers = list(root.handlers)
        root.handlers[:] = [self]
        src.setLevel(logging.DEBUG)
        # Shadows the method on this one object. Other loggers look up the root's level
        # themselves, so this lets through direct root calls and nothing else.
        root.isEnabledFor = lambda level: root.manager.disable < level

    def stop(self) -> None:
        # During a Run, logging.basicConfig() and removeHandler() on a root handler that was
        # there before the Run don't take effect, because this handler has replaced them on
        # the root. Nothing in src does either.
        root = logging.getLogger()
        vars(root).pop("isEnabledFor", None)
        added_during_run = [h for h in root.handlers if h is not self and h not in self._console_handlers]
        root.handlers[:] = [*self._console_handlers, *added_during_run]
        logging.getLogger(_OWN_LOGGER).setLevel(self._src_level)
        self.close()

    def emit(self, record: logging.LogRecord) -> None:
        self._gate_handlers_added_during_run()
        self._record(record)
        if not self._console_handlers and _called_through_logging_module():
            _ignoring_failure(self._configure_like_module_level_logging)
        if self._was_enabled_before_run(record):
            self._hand_on(record)

    def _gate_handlers_added_during_run(self) -> None:
        root = logging.getLogger()
        added = [h for h in root.handlers if h is not self]
        if added:
            self._console_handlers.extend(h for h in added if h not in self._console_handlers)
            root.handlers[:] = [self]

    def _record(self, record: logging.LogRecord) -> None:
        try:
            fields = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
            if record.exc_info:
                fields["traceback"] = "".join(traceback.format_exception(*record.exc_info))
            self._run._write("log", **fields)
        except Exception:
            pass

    def _was_enabled_before_run(self, record: logging.LogRecord) -> bool:
        logger: logging.Logger | None = logging.getLogger(record.name)
        while logger is not None:
            level = self._src_level if logger.name == _OWN_LOGGER else logger.level
            if level:
                return record.levelno >= level
            logger = logger.parent
        return True

    def _configure_like_module_level_logging(self) -> None:
        """logging.info() and friends call basicConfig() when the root has no handlers."""
        root = logging.getLogger()
        root.handlers[:] = []
        try:
            logging.basicConfig()
            self._console_handlers = list(root.handlers)
        finally:
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


def _called_through_logging_module() -> bool:
    """Tell logging.warning(), which configures an empty root, from root.warning(), which doesn't."""
    frame = sys._getframe(1)
    while frame is not None and frame.f_globals.get("__name__") in (__name__, "logging"):
        if frame.f_code in _MODULE_LEVEL_LOGGING_CODE:
            return True
        frame = frame.f_back
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
        run.record_failure(exc, exc)
    return run.path


def _start_run(label: str, project_key: str | None, base_path: str | None) -> Run:
    run = Run()
    try:
        record_file, path = _create_record_file(label, base_path)
        run = Run(record_file, path)
        run._write("run_start", label=label, project_key=project_key, base_path=base_path)
        run._write("environment", **_capture_versions())
        return run
    except Exception:
        run._close()
        return Run()


def _ignoring_failure(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        pass


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value] if isinstance(value, os.PathLike) else []


def _traceback_of(exc: BaseException) -> str:
    try:
        return "".join(traceback.format_exception(exc))
    except Exception:
        return _label_of(exc)


def _text_of(value: Any) -> str:
    try:
        return value if isinstance(value, str) else str(value)
    except Exception:
        return _label_of(value)


def _input_paths_in(request: Any) -> list[Any]:
    try:
        if not dataclasses.is_dataclass(request):
            return []
        values = [
            getattr(request, field.name)
            for field in dataclasses.fields(request)
            if "output" not in field.name
        ]
        return [path for value in values for path in _as_list(value) if isinstance(path, os.PathLike)]
    except Exception:
        return []


def _describe_safely(value: Any) -> Any:
    try:
        return _describe(value, 0, set())
    except Exception:
        return "<could not be described>"


def _describe(value: Any, depth: int, enclosing: set[int]) -> Any:
    """Turn a value into something JSON can hold, describing whatever it can't."""
    if isinstance(value, enum.Enum):
        return value.name
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, os.PathLike):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if depth >= _MAX_DESCRIBE_DEPTH or id(value) in enclosing:
        return _label_of(value)

    inner = enclosing | {id(value)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        described = {"__type__": type(value).__name__}
        for field in dataclasses.fields(value):
            described[field.name] = _describe_field(value, field.name, depth, inner)
        return described
    if isinstance(value, Mapping):
        return {_text_of(key): _describe(item, depth + 1, inner) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_describe(item, depth + 1, inner) for item in value]
    return _label_of(value)


def _describe_field(owner: Any, name: str, depth: int, enclosing: set[int]) -> Any:
    try:
        return _describe(getattr(owner, name), depth + 1, enclosing)
    except Exception:
        return "<could not be described>"


def _label_of(value: Any) -> str:
    """Describe an object by what it is. Never calls its repr, which can do anything."""
    kind = "function" if callable(value) and hasattr(value, "__qualname__") else "object"
    target = value if kind == "function" else type(value)
    return f"<{kind} {target.__module__}.{target.__qualname__}>"


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
    A utility action's record deliberately goes in the active project's logs/ folder.
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
