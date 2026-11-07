"""Run Record behaviour, tested by running fake actions through the action-running layer.

No test here starts Word or Excel, and none touches a real project folder or the
real %LOCALAPPDATA%: every location used is under pytest's tmp_path.
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import questionary
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output

from src import __version__
from src.cli_session import CliSession
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import ProjectWorkflowAction
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE
from src.utility_actions import UtilityAction
from src.workflow_cli import (
    _run_action,
    _run_project_workflow_menu,
    _run_recorded_action,
    _run_utility_actions_menu,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def make_environment(base_path: Path, key: str = "fake_project") -> ProjectEnvironment:
    metadata = ProjectMetadata(
        key=key,
        name="Fake Project",
        base_path=str(base_path),
        state="pahang",
        po_number="PO1",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
    )
    return ProjectEnvironment(metadata=metadata, storage=LocalWorkspaceStorage(base_path))


def run_project_action(behaviour, environment: ProjectEnvironment) -> None:
    """Choose one fake project workflow from the menu, then leave the menu."""
    action = ProjectWorkflowAction("Fake Workflow", runner_factory=lambda: behaviour)
    session = CliSession(
        persistence_file=Path(environment.base_path) / ".active_project.json",
        active_project=environment,
    )
    with patch("src.cli_menu.select_project_workflow_action", side_effect=[action, None]):
        _run_project_workflow_menu(session, [action])


def run_utility_action(behaviour) -> None:
    """Choose one fake utility action from the menu, then leave the menu."""
    action = UtilityAction("Fake Utility", lambda: behaviour)
    with patch("src.cli_menu.select_utility_action", side_effect=[action, None]):
        _run_utility_actions_menu([action])


def read_entries(folder: Path) -> list[dict]:
    """Read the single Run Record in a folder as a list of JSON entries."""
    records = list(folder.glob("*.jsonl"))
    assert len(records) == 1, f"expected one Run Record in {folder}, found {records}"
    return [json.loads(line) for line in records[0].read_text(encoding="utf-8").splitlines()]


def entries_of(entries: list[dict], entry_type: str) -> list[dict]:
    return [entry for entry in entries if entry["type"] == entry_type]


@pytest.fixture
def locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Production location rules, with the project and per-user folders under tmp_path."""
    project = tmp_path / "project"
    project.mkdir()
    local_app_data = tmp_path / "local_app_data"
    monkeypatch.delenv(RECORD_DIR_OVERRIDE_VARIABLE)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(
        project=project,
        project_logs=project / "logs",
        fallback_logs=local_app_data / "pahang-cli" / "logs",
        environment=make_environment(project),
    )


def test_project_workflow_saves_one_run_record_in_project_logs(locations) -> None:
    run_project_action(lambda environment: None, locations.environment)

    entries = read_entries(locations.project_logs)

    assert entries[0]["type"] == "run_start"
    assert entries[0]["label"] == "Fake Workflow"
    assert entries[0]["project_key"] == "fake_project"
    assert entries[-1]["type"] == "run_finish"
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["duration_seconds"] >= 0


def test_record_holds_app_git_python_word_and_excel_versions(locations) -> None:
    run_project_action(lambda environment: None, locations.environment)

    environment_entry = entries_of(read_entries(locations.project_logs), "environment")[0]

    assert environment_entry["app_version"] == __version__
    for field in ("git_sha", "python", "word", "excel"):
        assert isinstance(environment_entry[field], str) and environment_entry[field]


def test_failed_run_records_full_traceback_and_console_shows_path(locations, capsys) -> None:
    def inner_failure() -> None:
        raise RuntimeError("template is broken")

    def failing(environment) -> None:
        inner_failure()

    run_project_action(failing, locations.environment)

    entries = read_entries(locations.project_logs)
    error = entries_of(entries, "error")[0]
    assert "template is broken" in error["message"]
    assert "inner_failure" in error["traceback"]
    assert "Traceback (most recent call last)" in error["traceback"]
    assert entries[-1] == {**entries[-1], "type": "run_finish", "status": "failed"}

    console = capsys.readouterr().out
    assert "Action failed: template is broken" in console
    record_path = next(locations.project_logs.glob("*.jsonl"))
    assert str(record_path) in console


def test_successful_run_does_not_show_the_record_path(locations, capsys) -> None:
    run_project_action(lambda environment: None, locations.environment)

    record_path = next(locations.project_logs.glob("*.jsonl"))
    assert str(record_path) not in capsys.readouterr().out


def test_settings_style_action_is_not_recorded(locations) -> None:
    from src.workflow_cli import _run_settings_menu

    session = CliSession(persistence_file=locations.project / ".active_project.json")
    with (
        patch("src.cli_menu.select_settings_action", side_effect=["configure_cameras", None]),
        patch("src.settings_actions.run_configure_camera_patterns"),
    ):
        _run_settings_menu(session)

    assert not locations.project_logs.exists()
    assert not locations.fallback_logs.exists()


def test_interrupted_run_leaves_readable_record_with_no_finish_entry(locations) -> None:
    def interrupted(environment) -> None:
        print("working on substation 1")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_project_action(interrupted, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[0]["type"] == "run_start"
    assert not entries_of(entries, "run_finish")


def test_hard_crash_keeps_every_line_written_so_far(tmp_path: Path) -> None:
    """A process that dies without any cleanup, as when a hung Word run gets killed."""
    script = (
        "import os\n"
        "from src.run_records import open_run\n"
        "run = open_run('Crashing Workflow')\n"
        "run.__enter__()\n"
        "run.call(lambda: os._exit(3))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, RECORD_DIR_OVERRIDE_VARIABLE: str(tmp_path)},
        capture_output=True,
        timeout=60,
    )

    assert completed.returncode == 3
    entries = read_entries(tmp_path)
    assert entries[0]["type"] == "run_start"
    assert entries_of(entries, "environment")
    assert not entries_of(entries, "run_finish")


def test_each_entry_reaches_disk_while_the_run_is_going(locations) -> None:
    seen: list[str] = []

    def peek_at_own_record(environment) -> None:
        seen.append(next(locations.project_logs.glob("*.jsonl")).read_text(encoding="utf-8"))

    run_project_action(peek_at_own_record, locations.environment)

    assert '"run_start"' in seen[0]
    assert '"environment"' in seen[0]


def test_utility_action_with_no_active_project_uses_fallback(locations) -> None:
    run_utility_action(lambda: None)

    entries = read_entries(locations.fallback_logs)
    assert entries[0]["label"] == "Fake Utility"
    assert entries[0]["project_key"] is None
    assert not locations.project_logs.exists()


def test_transient_utility_environment_does_not_create_logs_in_typed_folder(locations, tmp_path) -> None:
    from src.project.environment import get_or_create_utility_environment

    typed_folder = tmp_path / "typed_by_operator"
    typed_folder.mkdir()

    run_utility_action(lambda: get_or_create_utility_environment(typed_folder))

    assert not (typed_folder / "logs").exists()
    assert read_entries(locations.fallback_logs)[-1]["type"] == "run_finish"


def test_environment_with_the_utility_key_uses_fallback(locations, tmp_path) -> None:
    typed_folder = tmp_path / "typed_by_operator"
    typed_folder.mkdir()

    run_project_action(lambda environment: None, make_environment(typed_folder, key="utility"))

    assert not (typed_folder / "logs").exists()
    assert read_entries(locations.fallback_logs)[0]["project_key"] == "utility"


def _make_project_active(cwd: Path, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Register a project in a temporary catalog and mark it active, as the CLI does."""
    catalog = cwd / "catalog.json"
    catalog.write_text(
        json.dumps({"projects": {"active_one": {"name": "Active", "base_path": str(project)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("config._CONFIG_FILE", catalog)
    (cwd / ".active_project.json").write_text(json.dumps({"active_project": "active_one"}), encoding="utf-8")
    monkeypatch.chdir(cwd)


def test_utility_action_with_active_project_uses_that_project(locations, tmp_path, monkeypatch) -> None:
    _make_project_active(tmp_path, locations.project, monkeypatch)

    run_utility_action(lambda: None)

    assert read_entries(locations.project_logs)[0]["project_key"] == "active_one"
    assert not locations.fallback_logs.exists()


def test_failure_while_selecting_a_project_is_saved_in_fallback(locations, capsys) -> None:
    session = CliSession(persistence_file=locations.project / ".active_project.json")

    with (
        patch("src.workflow_cli.select_active_project_wizard", side_effect=RuntimeError("catalog unreadable")),
        pytest.raises(RuntimeError, match="catalog unreadable"),
    ):
        _run_project_workflow_menu(session, [])

    entries = read_entries(locations.fallback_logs)
    assert "catalog unreadable" in entries_of(entries, "error")[0]["traceback"]
    assert entries[-1]["status"] == "failed"
    assert str(next(locations.fallback_logs.glob("*.jsonl"))) in capsys.readouterr().out


def test_selecting_a_project_normally_saves_nothing(locations) -> None:
    session = CliSession(persistence_file=locations.project / ".active_project.json")

    with patch("src.workflow_cli.select_active_project_wizard", return_value=None):
        _run_project_workflow_menu(session, [])

    assert not locations.fallback_logs.exists()


def test_missing_project_folder_is_not_recreated(locations, tmp_path) -> None:
    gone = tmp_path / "gone"
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), make_environment(gone))

    assert calls == ["ran"]
    assert not gone.exists()
    assert read_entries(locations.fallback_logs)


def test_blocked_project_logs_falls_back_to_per_user_folder(locations) -> None:
    locations.project_logs.write_text("a file where the folder should be", encoding="utf-8")

    run_project_action(lambda environment: None, locations.environment)

    assert read_entries(locations.fallback_logs)[-1]["type"] == "run_finish"


def _block_every_location(locations, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    locations.project_logs.write_text("a file where the folder should be", encoding="utf-8")
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))


def test_unwritable_log_locations_do_not_stop_the_action(locations, tmp_path, monkeypatch, capsys) -> None:
    _block_every_location(locations, monkeypatch, tmp_path)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    assert "Run Record" not in capsys.readouterr().out


def test_failed_action_with_unwritable_log_locations_still_reports_its_failure(
    locations, tmp_path, monkeypatch, capsys
) -> None:
    _block_every_location(locations, monkeypatch, tmp_path)

    def failing(environment) -> None:
        raise RuntimeError("real problem")

    run_project_action(failing, locations.environment)

    console = capsys.readouterr().out
    assert "Action failed: real problem" in console
    assert "Run Record:" not in console


class _FileThatFailsAfter:
    """A record file that stops accepting writes, as on a full disk or a lost drive."""

    def __init__(self, real_file, good_writes: int) -> None:
        self._real_file = real_file
        self._good_writes = good_writes

    def write(self, text: str) -> int:
        if self._good_writes <= 0:
            raise OSError(28, "No space left on device")
        self._good_writes -= 1
        return self._real_file.write(text)

    def flush(self) -> None:
        self._real_file.flush()

    def close(self) -> None:
        self._real_file.close()


def test_write_failure_mid_run_does_not_stop_the_action(locations, monkeypatch) -> None:
    real_open = open

    def open_failing_later(*args, **kwargs):
        return _FileThatFailsAfter(real_open(*args, **kwargs), good_writes=2)

    monkeypatch.setattr("src.run_records.open", open_failing_later, raising=False)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    entries = read_entries(locations.project_logs)
    assert [entry["type"] for entry in entries] == ["run_start", "environment"]


def test_failure_while_capturing_versions_does_not_stop_the_action(locations, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise OSError("not available")

    monkeypatch.setattr("subprocess.run", broken)
    monkeypatch.setattr("platform.python_version", broken)
    monkeypatch.setattr("winreg.OpenKey", broken)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    versions = entries_of(read_entries(locations.project_logs), "environment")[0]
    for field in ("git_sha", "python", "word", "excel"):
        assert versions[field] == "unknown"


def test_tests_cannot_write_run_records_into_a_real_project_folder(tmp_path) -> None:
    """The suite-wide default with nothing lifted: no fixture here arranges it."""
    project = tmp_path / "looks_like_a_real_project"
    project.mkdir()
    before = set(Path(os.environ[RECORD_DIR_OVERRIDE_VARIABLE]).glob("*.jsonl"))

    run_project_action(lambda environment: None, make_environment(project))

    assert not (project / "logs").exists()
    assert len(set(Path(os.environ[RECORD_DIR_OVERRIDE_VARIABLE]).glob("*.jsonl")) - before) == 1


def test_tests_reading_the_active_project_cannot_write_into_it(tmp_path, monkeypatch) -> None:
    project = tmp_path / "active_project_folder"
    project.mkdir()
    _make_project_active(tmp_path, project, monkeypatch)
    local_app_data = tmp_path / "local_app_data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    run_utility_action(lambda: None)

    assert not (project / "logs").exists()
    assert not local_app_data.exists()


def test_protection_reaches_a_child_process() -> None:
    """Subprocesses and xdist workers inherit the redirect from the environment."""
    probe = "import os; from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE as v; print(os.environ[v])"
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert completed.stdout.strip() == os.environ[RECORD_DIR_OVERRIDE_VARIABLE]


def test_unwritable_override_never_falls_through_to_a_real_location(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    monkeypatch.setenv(RECORD_DIR_OVERRIDE_VARIABLE, str(blocker))
    local_app_data = tmp_path / "local_app_data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), make_environment(project))

    assert calls == ["ran"]
    assert not (project / "logs").exists()
    assert not local_app_data.exists()


def _noisy_action() -> None:
    """Writes to the console and the loggers in every way the CLI does."""
    print("plain print")
    print("[PROGRESS] Found 2 packages")
    print("[1/2] Generating report", flush=True)
    print("no newline at the end ", end="")
    print("of this line")
    logging.getLogger("src.fake").info("src info is hidden on the console")
    logging.getLogger("src.fake").warning("src warning one")
    logging.debug("direct debug is hidden on the console")
    logging.info("direct info is hidden on the console")
    logging.getLogger("src.fake").warning("src warning two")
    logging.warning("direct warning")
    logging.getLogger("src.fake").warning("src warning three")
    logging.getLogger("thirdparty.lib").debug("third party debug is hidden on the console")
    logging.getLogger("thirdparty.lib").warning("third party warning")
    print("last print, with no newline", end="")


def _failing_noisy_action() -> None:
    _noisy_action()
    raise RuntimeError("noisy failure")


def _console_handler_like_main_py() -> list[logging.Handler]:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("MAIN - %(levelname)s - %(message)s"))
    return [handler]


@pytest.fixture(params=["installed_entry_point", "main_py"])
def console_setup(request, monkeypatch):
    """start_cli.bat runs the pahang-cli entry point, which configures no logging at all."""
    monkeypatch.setattr(logging.root, "handlers", [])
    level_before = logging.root.level
    logging.root.setLevel(logging.WARNING)

    def reset() -> None:
        logging.root.handlers[:] = [] if request.param == "installed_entry_point" else _console_handler_like_main_py()

    yield reset
    logging.root.setLevel(level_before)


@pytest.mark.parametrize("behaviour", [_noisy_action, _failing_noisy_action])
def test_console_output_is_identical_with_and_without_a_run(locations, console_setup, capsys, behaviour) -> None:
    console_setup()
    _run_action("Fake", behaviour)
    without_run = capsys.readouterr()

    console_setup()
    _run_recorded_action("Fake", behaviour, locations.environment)
    with_run = capsys.readouterr()

    record_line = [line for line in with_run.out.splitlines() if line.startswith("Run Record: ")]
    assert with_run.err == without_run.err
    assert with_run.out.replace(f"{record_line[0]}\n" if record_line else "", "") == without_run.out
    assert "hidden" not in with_run.err + with_run.out
    assert "src warning one" in with_run.err
    assert "third party warning" in with_run.err


def test_entry_point_console_keeps_its_exact_log_formats(locations, monkeypatch, capsys) -> None:
    monkeypatch.setattr(logging.root, "handlers", [])

    _run_recorded_action("Fake", _noisy_action, locations.environment)

    assert capsys.readouterr().err.splitlines() == [
        "src warning one",
        # logging.debug() above configured the root logger, as it does without a Run.
        "WARNING:src.fake:src warning two",
        "WARNING:root:direct warning",
        "WARNING:src.fake:src warning three",
        "WARNING:thirdparty.lib:third party warning",
    ]


def test_library_logger_with_null_handler_stays_silent(locations, monkeypatch, capsys) -> None:
    monkeypatch.setattr(logging.root, "handlers", [])
    library = logging.getLogger("quiet_library")
    library.addHandler(logging.NullHandler())

    try:
        _run_recorded_action("Fake", lambda: library.warning("kept quiet"), locations.environment)
    finally:
        library.handlers.clear()

    assert capsys.readouterr().err == ""


def test_logger_and_progress_output_flow_into_the_record(locations, console_setup) -> None:
    console_setup()

    _run_recorded_action("Fake", _noisy_action, locations.environment)

    entries = read_entries(locations.project_logs)
    logged = {(entry["level"], entry["message"]) for entry in entries_of(entries, "log")}
    assert ("INFO", "src info is hidden on the console") in logged
    assert ("DEBUG", "direct debug is hidden on the console") in logged
    assert ("INFO", "direct info is hidden on the console") in logged
    assert ("WARNING", "src warning one") in logged
    assert ("WARNING", "third party warning") in logged
    assert not any("third party debug" in message for _, message in logged)

    assert [entry["text"] for entry in entries_of(entries, "progress")] == [
        "[PROGRESS] Found 2 packages",
        "[1/2] Generating report",
    ]
    console_lines = [entry["text"] for entry in entries_of(entries, "console")]
    assert "plain print" in console_lines
    assert "no newline at the end of this line" in console_lines
    assert "last print, with no newline" in console_lines
    assert entries[-1]["type"] == "run_finish"


def test_logged_exception_keeps_its_traceback(locations) -> None:
    def action(environment) -> None:
        try:
            raise ValueError("inner detail")
        except ValueError:
            logging.getLogger("src.fake").exception("swallowed")

    run_project_action(action, locations.environment)

    logged = next(e for e in entries_of(read_entries(locations.project_logs), "log") if e["message"] == "swallowed")
    assert "inner detail" in logged["traceback"]


class _Stop(BaseException):
    """Stands in for an interruption such as Ctrl+C."""


@pytest.mark.parametrize("ending", [None, RuntimeError("failed"), _Stop()])
def test_console_and_logging_are_restored_after_a_run(locations, console_setup, ending) -> None:
    console_setup()
    stdout_before = sys.stdout
    handlers_before = list(logging.root.handlers)
    level_before = logging.root.level
    seen: dict[str, object] = {}

    def action() -> None:
        seen["stdout"] = sys.stdout
        if ending is not None:
            raise ending

    if isinstance(ending, _Stop):
        with pytest.raises(_Stop):
            _run_recorded_action("Fake", action, locations.environment)
    else:
        _run_recorded_action("Fake", action, locations.environment)

    assert seen["stdout"] is not stdout_before, "the Run should have been capturing"
    assert sys.stdout is stdout_before
    assert logging.root.handlers[: len(handlers_before)] == handlers_before
    assert not [h for h in logging.root.handlers if type(h).__module__ == "src.run_records"]
    assert logging.root.level == level_before
    assert logging.getLogger("src.fake").getEffectiveLevel() == level_before


def test_nothing_is_changed_when_no_record_can_be_opened(locations, tmp_path, monkeypatch) -> None:
    _block_every_location(locations, monkeypatch, tmp_path)
    seen: dict[str, object] = {}

    def action() -> None:
        seen["stdout"] = sys.stdout
        seen["level"] = logging.root.level

    stdout_before, level_before = sys.stdout, logging.root.level
    _run_recorded_action("Fake", action, locations.environment)

    assert seen == {"stdout": stdout_before, "level": level_before}


def test_console_keeps_working_after_a_mid_run_write_failure(locations, monkeypatch, capsys) -> None:
    real_open = open

    def open_failing_later(*args, **kwargs):
        return _FileThatFailsAfter(real_open(*args, **kwargs), good_writes=2)

    monkeypatch.setattr("src.run_records.open", open_failing_later, raising=False)

    def action(environment) -> None:
        print("first line after the disk filled up")
        logging.getLogger("src.fake").warning("logged after the disk filled up")
        print("second line after the disk filled up")

    run_project_action(action, locations.environment)

    captured = capsys.readouterr()
    assert "first line after the disk filled up" in captured.out
    assert "second line after the disk filled up" in captured.out


def test_handler_added_during_a_run_stays_after_it(locations) -> None:
    extra = logging.NullHandler()

    def action(environment) -> None:
        logging.root.addHandler(extra)

    try:
        run_project_action(action, locations.environment)
        assert extra in logging.root.handlers
    finally:
        logging.root.removeHandler(extra)


def test_console_stream_looks_the_same_to_code_that_inspects_it(locations, capsys) -> None:
    seen: list[object] = []

    def action() -> None:
        stream = sys.stdout
        seen.extend([stream.encoding, stream.isatty(), stream.errors])

    _run_recorded_action("Fake", action, locations.environment)

    assert seen == [sys.stdout.encoding, sys.stdout.isatty(), sys.stdout.errors]


def test_console_write_error_reaches_the_caller_unchanged(locations, monkeypatch) -> None:
    """Workflow code may rely on seeing UnicodeEncodeError from print on a narrow console."""

    class AsciiOnly(io.StringIO):
        def write(self, text: str) -> int:
            return super().write(text.encode("ascii").decode("ascii"))

    monkeypatch.setattr(sys, "stdout", AsciiOnly())
    caught: list[type] = []

    def action() -> None:
        try:
            print("⚡")
        except UnicodeEncodeError as exc:
            caught.append(type(exc))

    _run_recorded_action("Fake", action, locations.environment)

    assert caught == [UnicodeEncodeError]


def test_prompt_runs_normally_and_its_drawing_is_not_recorded(locations, capsys) -> None:
    """Runs a real questionary prompt with its output on the captured stream.

    This is the worst case, where prompt_toolkit writes through the capture. In the CLI
    the top-level menu binds prompt_toolkit to the real console before any Run opens.
    Only a hand check in a real console can confirm how that console behaves.
    """
    answers: list[str] = []

    def action() -> None:
        print("before the prompt")
        output = Vt100_Output(sys.stdout, lambda: Size(rows=24, columns=80), term="xterm")
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=output):
            pipe.send_text("j\r")
            answers.append(questionary.select("Pick a thing", choices=["first", "second"]).ask())
        print("after the prompt")

    _run_recorded_action("Fake", action, locations.environment)

    assert answers == ["second"]
    assert "Pick a thing" in capsys.readouterr().out
    entries = read_entries(locations.project_logs)
    console_lines = [entry["text"] for entry in entries_of(entries, "console")]
    assert console_lines == ["before the prompt", "after the prompt"]
    assert "Pick a thing" not in json.dumps(entries)
