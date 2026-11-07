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
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
from src.project_workflow_actions import (
    FullReportAction,
    FullReportPostProcessingAction,
    ProjectWorkflowAction,
    QuickReportAction,
)
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, current_run, open_run
from src.testsheet.models import SubstationPackage, SubstationTestsheetPackage
from src.utility_actions import UtilityAction, get_utility_actions
from src.workflows.consolidate_msms import ConsolidateMsmsExtractor
from src.workflows.full_report import FullReportInspection, FullReportWorkflow
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingInspection,
    FullReportPostProcessingWorkflow,
)
from src.workflows.models import (
    ConsolidateMsmsResult,
    PostProcessingMode,
    PostProcessingRequest,
    PostProcessingSummary,
    QuickReportInspection,
    QuickReportResult,
)
from src.workflows.postprocessing_pipeline import PostProcessingPipelineWorkflow
from src.workflows.quick_report import QuickReportWorkflow
from src.workflows.service import WorkflowService
from src.workflows.us_audio import UsAudioCandidate, UsAudioWorkflow
from src.workflows.us_tev_graphs import (
    BrowserPrerequisiteError,
    SubstationGraphResult,
    UsTevCandidate,
    UsTevGraphWorkflow,
)
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
    assert "[TIMER] Workflow 'Fake Workflow' completed in" in console
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


class _FakeRequest:
    """A request with nothing to serialise, for workflows whose request type doesn't matter."""

    progress_sink = None


class _FakeConverter:
    """Stands in for a converter: an object that JSON cannot express."""


def test_service_records_its_request_and_describes_what_cannot_be_serialised(locations, tmp_path) -> None:
    signature = tmp_path / "vendor_signature.png"
    signature.write_bytes(b"12345")
    request = PostProcessingRequest(
        mode=PostProcessingMode.BY_DATE,
        target_dates=("07.11.2026",),
        vendor_signature_path=signature,
        converter=_FakeConverter(),
        progress_sink=_FakeConverter(),
    )
    summary = PostProcessingSummary()

    def action(environment) -> PostProcessingSummary:
        with patch("src.workflows.postprocessing_pipeline.PostProcessingPipelineWorkflow") as workflow:
            workflow.return_value.execute.return_value = summary
            return WorkflowService().run_postprocessing_pipeline(environment, request)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    recorded = entries_of(entries, "request")[0]["request"]
    assert recorded["__type__"] == "PostProcessingRequest"
    assert recorded["mode"] == "BY_DATE"
    assert recorded["target_dates"] == ["07.11.2026"]
    assert recorded["vendor_signature_path"] == str(signature)
    assert recorded["converter"] == "<object test_run_records._FakeConverter>"
    inputs = {entry["path"]: entry for entry in entries_of(entries, "input")}
    assert inputs[str(signature)]["size"] == 5
    assert inputs[str(signature)]["modified"]
    assert entries[-1]["status"] == "completed"


@pytest.mark.parametrize(
    "call_service, patch_target",
    [
        (lambda s, e, r: s.run_populate_total_pe(e, r), "src.workflows.service.PopulateTotalPeWorkflow"),
        (lambda s, e, r: s.run_raw_material(e, r), "src.workflows.service.RawMaterialWorkflow"),
        (lambda s, e, r: s.run_propagate_wo(e, r), "src.workflows.propagate_wo.PropagateWoWorkflow"),
        (lambda s, e, r: s.run_consolidate_msms(e, r), "src.workflows.consolidate_msms.ConsolidateMsmsWorkflow"),
        (lambda s, e, r: s.run_enrich_msms(e, r), "src.workflows.enrich_msms.EnrichMsmsWorkflow"),
        (lambda s, e, r: s.run_ingest_msms_csv(e, r), "src.workflows.ingest_msms_csv.IngestMsmsCsvWorkflow"),
        (lambda s, e, r: s.run_populate_data_msms(e, r), "src.workflows.populate_data_msms.PopulateDataMsmsWorkflow"),
        (lambda s, e, r: s.run_update_qr02_cba(e, r), "src.workflows.update_qr02_cba.UpdateQr02CbaWorkflow"),
        (lambda s, e, r: s.run_whatsapp(e, r), "src.workflows.whatsapp.WhatsAppReportWorkflow"),
        (
            lambda s, e, r: s.run_generate_testsheet_folder(e, r),
            "src.workflows.generate_testsheet_folder.GenerateTestsheetFolderStructureWorkflow",
        ),
    ],
)
def test_every_service_workflow_records_its_request_centrally(locations, call_service, patch_target) -> None:
    (locations.project / "PYTHON").mkdir()
    (locations.project / "PYTHON" / "TOTAL PE.xlsx").write_bytes(b"123")

    def action(environment) -> None:
        with patch(patch_target):
            call_service(WorkflowService(), environment, _FakeRequest())

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries_of(entries, "request")[0]["request"] == "<object test_run_records._FakeRequest>"
    inputs = {entry["path"]: entry for entry in entries_of(entries, "input")}
    assert inputs[str(locations.project / "PYTHON" / "TOTAL PE.xlsx")]["size"] == 3


def test_request_that_cannot_be_described_does_not_stop_the_action(locations) -> None:
    class Hostile:
        def __getattribute__(self, name):
            raise RuntimeError("no attribute access at all")

        def __repr__(self):
            raise RuntimeError("no repr either")

    @dataclass
    class WithBrokenField:
        fine: str
        hostile: object

        @property
        def broken(self):
            raise RuntimeError("broken property")

    circular: list[object] = []
    circular.append(circular)
    requests = [Hostile(), WithBrokenField("kept", Hostile()), circular, {"nan": float("nan"), Hostile(): 1}]
    calls: list[str] = []

    def action(environment) -> None:
        for request in requests:
            current_run().record_request(request)
        calls.append("ran")

    run_project_action(action, locations.environment)

    assert calls == ["ran"]
    entries = read_entries(locations.project_logs)
    recorded = [entry["request"] for entry in entries_of(entries, "request")]
    assert len(recorded) == 4
    assert recorded[1]["fine"] == "kept"
    assert entries[-1]["status"] == "completed"


def test_result_that_cannot_be_described_does_not_stop_the_action(locations, capsys) -> None:
    class Hostile:
        def __getattribute__(self, name):
            raise RuntimeError("no attribute access at all")

    run_project_action(lambda environment: Hostile(), locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == "completed"
    assert "Action failed" not in capsys.readouterr().out


def test_outputs_warnings_and_errors_come_from_the_result(locations, tmp_path, capsys) -> None:
    report = tmp_path / "report.docx"
    result = QuickReportResult(
        reports_generated=1,
        generated_paths=(report,),
        warnings=("photo missing",),
        errors=("PE 3 failed",),
    )

    run_project_action(lambda environment: result, locations.environment)

    entries = read_entries(locations.project_logs)
    assert [entry["path"] for entry in entries_of(entries, "output")] == [str(report)]
    assert [entry["message"] for entry in entries_of(entries, "warning")] == ["photo missing"]
    assert [entry["message"] for entry in entries_of(entries, "error")] == ["PE 3 failed"]
    assert entries_of(entries, "result")[0]["result"]["reports_generated"] == 1
    assert entries[-1]["status"] == "completed_with_errors"
    assert str(next(locations.project_logs.glob("*.jsonl"))) in capsys.readouterr().out


def test_clean_result_finishes_as_completed(locations, tmp_path, capsys) -> None:
    result = QuickReportResult(reports_generated=1, generated_paths=(tmp_path / "report.docx",))

    run_project_action(lambda environment: result, locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == "completed"
    assert "Run Record:" not in capsys.readouterr().out


def test_steps_are_timed_and_a_failed_step_is_marked(locations) -> None:
    def action(environment) -> None:
        with current_run().step("Substation A"):
            pass
        try:
            with current_run().step("Substation B"):
                raise ValueError("bad testsheet")
        except ValueError:
            pass

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert [entry["name"] for entry in entries_of(entries, "step_start")] == ["Substation A", "Substation B"]
    finished = entries_of(entries, "step_finish")
    assert [(entry["name"], entry["status"]) for entry in finished] == [
        ("Substation A", "completed"),
        ("Substation B", "failed"),
    ]
    assert finished[0]["duration_seconds"] >= 0
    assert "bad testsheet" in finished[1]["error"]
    assert entries[-1]["status"] == "completed"


def test_inputs_are_recorded_without_copying_and_missing_ones_are_marked(locations, tmp_path) -> None:
    present = tmp_path / "testsheet.xlsx"
    present.write_bytes(b"1234567")
    missing = tmp_path / "gone.xlsx"
    logs_before = set(tmp_path.rglob("*"))

    def action(environment) -> None:
        current_run().record_inputs([present, str(missing), None, object()])

    run_project_action(action, locations.environment)

    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert inputs[str(present)]["size"] == 7
    assert inputs[str(missing)]["size"] is None
    assert not inputs[str(missing)]["exists"]
    assert logs_before >= {p for p in tmp_path.rglob("*") if locations.project_logs not in [p, *p.parents]}


def test_recording_with_no_open_run_does_nothing_and_never_raises(tmp_path) -> None:
    run = current_run()
    run.record_request({"a": 1})
    run.record_inputs([tmp_path])
    run.record_outputs([tmp_path])
    run.record_warning("nobody is listening")
    run.record_error("nobody is listening", ValueError("x"))
    with run.step("nothing"):
        pass
    assert run.path is None
    assert list(tmp_path.iterdir()) == []


def test_a_run_inside_a_run_keeps_one_record(locations) -> None:
    def action(environment) -> None:
        with open_run("Inner") as inner:
            inner.call(lambda: print("from inside"))

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "run_start")) == 1
    assert entries_of(entries, "console")[0]["text"] == "from inside"


def test_quick_report_records_request_and_inputs_directly(locations, tmp_path) -> None:
    testsheet = tmp_path / "testsheet.xlsx"
    testsheet.write_bytes(b"12")
    plan = SimpleNamespace(package=SimpleNamespace(testsheet_path=testsheet))
    inspection = QuickReportInspection(targets=(), missing_templates=(), warnings=(), errors=())

    def stop_after_planning(message: str) -> None:
        if message.startswith("Found"):
            raise _StopWorkflow(message)

    def action(environment) -> None:
        with patch.object(QuickReportWorkflow, "_plan", return_value=(inspection, [plan])):
            QuickReportWorkflow().generate(["FL1"], environment, station="KUANTAN", progress_sink=stop_after_planning)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    request = entries_of(entries, "request")[0]["request"]
    assert request == {"workflow": "Quick Report", "target": ["FL1"], "station": "KUANTAN", "condition_template": None}
    assert entries_of(entries, "input")[0]["path"] == str(testsheet)


def test_full_report_records_request_and_inputs_directly(locations, tmp_path) -> None:
    testsheet = tmp_path / "testsheet.xlsx"
    testsheet.write_bytes(b"12")
    package = SimpleNamespace(testsheet_path=testsheet)

    def stop_after_discovery(message: str) -> None:
        if message.startswith("Found"):
            raise _StopWorkflow(message)

    def action(environment) -> None:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(FullReportWorkflow, "_discover_packages", return_value=([package], [], [])),
        ):
            FullReportWorkflow().generate(["FL1"], environment, progress_sink=stop_after_discovery)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    request = entries_of(entries, "request")[0]["request"]
    assert request["workflow"] == "Full Report"
    assert request["target"] == ["FL1"]
    assert entries_of(entries, "input")[0]["path"] == str(testsheet)


def test_full_report_postprocessing_records_request_and_inputs_directly(locations, tmp_path) -> None:
    docx = tmp_path / "full_report.docx"
    docx.write_bytes(b"123")

    def action(environment) -> None:
        with (
            patch.object(FullReportPostProcessingWorkflow, "_discover_docx_files", return_value=([docx], [], [])),
            patch.object(FullReportPostProcessingWorkflow, "_group_multipart_targets", side_effect=_StopWorkflow),
        ):
            FullReportPostProcessingWorkflow().process("07.11.2026", environment)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    request = entries_of(entries, "request")[0]["request"]
    assert request["workflow"] == "Full Report Post-Processing"
    assert request["target"] == "07.11.2026"
    assert entries_of(entries, "input")[0]["path"] == str(docx)


class _StopWorkflow(Exception):
    """Ends a real workflow straight after the part under test, before it reaches Word."""


def _record_com_attempts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import pythoncom
    import win32com.client

    attempts: list[str] = []

    def attempt(name: str):
        def fail(*args, **kwargs):
            attempts.append(name)
            raise AssertionError(f"{name} must not be called while capturing versions")

        return fail

    monkeypatch.setattr(win32com.client, "Dispatch", attempt("Dispatch"))
    monkeypatch.setattr(win32com.client, "DispatchEx", attempt("DispatchEx"))
    monkeypatch.setattr(win32com.client.gencache, "EnsureDispatch", attempt("EnsureDispatch"))
    monkeypatch.setattr(pythoncom, "CoCreateInstance", attempt("CoCreateInstance"))
    return attempts


def test_capturing_versions_attempts_no_com_dispatch(locations, monkeypatch) -> None:
    attempts = _record_com_attempts(monkeypatch)

    run_project_action(lambda environment: None, locations.environment)

    assert attempts == []
    assert entries_of(read_entries(locations.project_logs), "environment")


def test_capturing_versions_does_not_even_load_com_in_a_fresh_process(tmp_path) -> None:
    script = (
        "import sys\n"
        "from src.run_records import open_run\n"
        "with open_run('Fresh') as run:\n"
        "    run.call(lambda: None)\n"
        "assert 'win32com' not in sys.modules, 'win32com was imported'\n"
        "assert 'pythoncom' not in sys.modules, 'pythoncom was imported'\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, RECORD_DIR_OVERRIDE_VARIABLE: str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    assert read_entries(tmp_path)[-1]["type"] == "run_finish"


def test_capture_setup_failure_does_not_stop_the_action(locations, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("logging is broken")

    monkeypatch.setattr(logging.Logger, "setLevel", broken)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    assert read_entries(locations.project_logs)[-1]["type"] == "run_finish"


def test_input_prompt_still_reads_its_answer_during_a_run(locations, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("KUANTAN\n"))
    answers: list[str] = []

    _run_recorded_action("Fake", lambda: answers.append(input("Functional Locations: ")), locations.environment)

    assert answers == ["KUANTAN"]
    assert "Functional Locations: " in capsys.readouterr().out


def test_text_the_record_file_cannot_encode_does_not_end_the_record(locations) -> None:
    run_project_action(lambda environment: current_run().record_warning("bad \udc80 text"), locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries_of(entries, "warning")
    assert entries[-1]["type"] == "run_finish"


def run_registered_utility(label: str) -> None:
    """Choose a real utility action from the registry, then leave the menu."""
    action = next(item for item in get_utility_actions() if item.label == label)
    with patch("src.cli_menu.select_utility_action", side_effect=[action, None]):
        _run_utility_actions_menu([action])


@pytest.fixture
def utility_env(locations):
    """A project environment for utility actions. Records still use the fallback folder."""
    with patch("src.project.environment.load_project_environment", return_value=locations.environment):
        yield locations.environment


def assert_problem_recorded(folder: Path, status: str, marker: str, capsys) -> list[dict]:
    """The Run's status, a traceback naming the failure, and the path on the console."""
    entries = read_entries(folder)
    assert entries[-1]["type"] == "run_finish"
    assert entries[-1]["status"] == status
    tracebacks = [entry["traceback"] for entry in entries_of(entries, "error") if "traceback" in entry]
    assert any(marker in text for text in tracebacks), f"no traceback with {marker!r} in {tracebacks}"
    record_path = next(folder.glob("*.jsonl"))
    assert f"Run Record: {record_path}" in capsys.readouterr().out
    return entries


def test_record_error_finishes_as_completed_with_errors_and_shows_the_path(locations, capsys) -> None:
    def action(environment) -> None:
        try:
            raise ValueError("substation 3 is bad")
        except ValueError as exc:
            current_run().record_error("Substation 3 failed", exc)

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "completed_with_errors", "substation 3 is bad", capsys)


def test_record_failure_is_not_downgraded_by_what_the_action_returns(locations, capsys) -> None:
    def action(environment) -> QuickReportResult:
        try:
            raise ValueError("whole job broke")
        except ValueError as exc:
            current_run().record_failure("It all failed", exc)
        return QuickReportResult(reports_generated=1, errors=("one more",))

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "failed", "whole job broke", capsys)


def test_error_also_returned_in_the_result_is_recorded_once(locations) -> None:
    def action(environment) -> QuickReportResult:
        try:
            raise ValueError("detail")
        except ValueError as exc:
            current_run().record_error("Failed to process PE 3: detail", exc)
        return QuickReportResult(reports_generated=1, errors=("Failed to process PE 3: detail",))

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert len(errors) == 1
    assert "traceback" in errors[0]


@pytest.mark.parametrize(
    "result, status",
    [
        (QuickReportResult(reports_generated=2, errors=("PE 3 failed",)), "completed_with_errors"),
        (QuickReportResult(reports_generated=0, errors=("PE 3 failed",)), "failed"),
        (ConsolidateMsmsResult(files_processed=0, errors=("bad xls",)), "failed"),
        (ConsolidateMsmsResult(files_processed=2, errors=("bad xls",)), "completed_with_errors"),
    ],
)
def test_batch_status_says_whether_anything_succeeded(locations, result, status) -> None:
    run_project_action(lambda environment: result, locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == status


def test_combine_pdfs_hard_stop_is_a_failed_run(locations, monkeypatch, capsys) -> None:
    answers = iter([str(locations.project / "no_primary"), str(locations.project / "no_secondary")])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    run_registered_utility("Combine PDFs from primary and secondary folders")

    captured = capsys.readouterr()
    assert "HARD STOP: Primary folder not found" in captured.out
    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "failed"
    assert "Primary folder not found" in entries_of(entries, "error")[0]["traceback"]
    assert str(next(locations.fallback_logs.glob("*.jsonl"))) in captured.out


def test_combine_with_separator_missing_template_is_a_failed_run(locations, utility_env, capsys) -> None:
    with patch.object(ProjectEnvironment, "get_template", side_effect=RuntimeError("no separator template")):
        run_registered_utility("Combine PDFs with separator sheet")

    assert_problem_recorded(locations.fallback_logs, "failed", "no separator template", capsys)


def test_combine_with_separator_hard_stop_is_a_failed_run(locations, utility_env, tmp_path, capsys) -> None:
    separator = tmp_path / "separator.pdf"
    separator.write_bytes(b"pdf")
    empty_folder = tmp_path / "no_pdfs"
    empty_folder.mkdir()

    with (
        patch.object(ProjectEnvironment, "get_template", return_value=separator),
        patch("src.cli_selectors.select_testsheet_subfolder", return_value=empty_folder),
    ):
        run_registered_utility("Combine PDFs with separator sheet")

    assert_problem_recorded(locations.fallback_logs, "failed", "No PDF files found", capsys)


def test_whatsapp_utility_failure_is_a_failed_run(locations, utility_env, capsys) -> None:
    with patch.object(ProjectEnvironment, "get_whatsapp_report_resources", side_effect=RuntimeError("no total pe")):
        run_registered_utility("Generate WhatsApp report (from Quick Reports)")

    assert_problem_recorded(locations.fallback_logs, "failed", "no total pe", capsys)


def test_propagate_wo_utility_failure_is_a_failed_run(locations, utility_env, capsys) -> None:
    with patch.object(WorkflowService, "run_propagate_wo", side_effect=RuntimeError("workbook locked")):
        run_registered_utility("Propagate Work Orders (DATA MSMS -> TOTAL PE)")

    assert_problem_recorded(locations.fallback_logs, "failed", "workbook locked", capsys)


def test_rename_files_hard_stop_is_a_failed_run(locations, monkeypatch, capsys) -> None:
    """Today this also hits a pre-existing NameError on logging. The record holds both causes."""
    answers = iter([str(locations.project / "no_input"), str(locations.project / "no_output")])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    run_registered_utility("Rename files (match names from input dir)")

    assert_problem_recorded(locations.fallback_logs, "failed", "Input directory not found", capsys)


def _tev_candidate(tmp_path: Path, name: str) -> UsTevCandidate:
    survey = tmp_path / name
    survey.mkdir()
    package = SimpleNamespace(substation_name=name, date_str="", testsheet_path=tmp_path / f"{name}.xlsx")
    return UsTevCandidate(package=package, raw_data_dir=survey, survey_dir=survey, output_dir=survey / "graphs")


def _tev_prompts(candidates: list[UsTevCandidate]):
    module = "src.workflows.us_tev_graphs"
    return (
        patch(f"{module}.select_one", return_value="enter_dates"),
        patch(f"{module}.prompt_target_inspection_dates_with_ranges", return_value=["07-11-2026"]),
        patch(f"{module}.discover_us_tev_candidate_substations", return_value=candidates),
        patch(f"{module}.select_us_tev_substations_interactive", return_value=candidates),
        patch.object(ProjectEnvironment, "get_prpd_config", return_value=SimpleNamespace(mode="option_b")),
    )


def test_us_tev_missing_browser_is_a_failed_run(locations, utility_env, tmp_path, capsys) -> None:
    prompts = _tev_prompts([_tev_candidate(tmp_path, "PE1")])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "check_browser_prerequisite", side_effect=BrowserPrerequisiteError("no chrome")),
    ):
        run_registered_utility("Generate US+TEV survey graphs")

    assert_problem_recorded(locations.fallback_logs, "failed", "no chrome", capsys)


def test_us_tev_batch_with_one_failed_substation_has_errors_and_a_traceback(
    locations, utility_env, tmp_path, capsys
) -> None:
    def graphs_or_failure(self, survey_root, output_dir=None):
        if Path(survey_root).name == "PE2":
            raise RuntimeError("survey unreadable")
        return SubstationGraphResult(generated=[tmp_path / "graph.png"])

    prompts = _tev_prompts([_tev_candidate(tmp_path, "PE1"), _tev_candidate(tmp_path, "PE2")])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "run_substation", graphs_or_failure),
    ):
        run_registered_utility("Generate US+TEV survey graphs")

    assert_problem_recorded(locations.fallback_logs, "completed_with_errors", "survey unreadable", capsys)


def test_us_audio_failed_substation_has_a_traceback(locations, capsys) -> None:
    candidate = UsAudioCandidate(raw_data_dir=locations.project)

    def action(environment) -> object:
        with patch.object(UsAudioWorkflow, "run_substation", side_effect=RuntimeError("wav export broke")):
            return UsAudioWorkflow().run_batch([candidate])

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "failed", "wav export broke", capsys)


def _signature_prompts(answer: str):
    return (
        patch("builtins.input", return_value=answer),
        patch("src.cli_selectors.select_one", return_value="placeholder"),
        patch("src.workflows.replace_signatures._select_signature_path", return_value=(None, "__none__")),
    )


def test_replace_signatures_on_one_file_failing_is_a_failed_run(locations, utility_env, tmp_path, capsys) -> None:
    workbook = tmp_path / "PE1.xlsx"
    workbook.write_bytes(b"x")
    prompts = _signature_prompts(str(workbook))
    with (
        prompts[0], prompts[1], prompts[2],
        patch("src.workflows.replace_signatures.replace_pce_images", side_effect=RuntimeError("bad workbook")),
    ):
        run_registered_utility("Replace signature images in testsheets")

    assert_problem_recorded(locations.fallback_logs, "failed", "bad workbook", capsys)


@pytest.mark.parametrize("good_files, status", [(1, "completed_with_errors"), (0, "failed")])
def test_replace_signatures_batch_status(locations, utility_env, tmp_path, capsys, good_files, status) -> None:
    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "bad.xlsx").write_bytes(b"x")
    if good_files:
        (folder / "good.xlsx").write_bytes(b"x")

    def replace(path, *args, **kwargs):
        if Path(path).name == "bad.xlsx":
            raise RuntimeError("bad workbook")

    prompts = _signature_prompts(str(folder))
    with prompts[0], prompts[1], prompts[2], patch("src.workflows.replace_signatures.replace_pce_images", replace):
        run_registered_utility("Replace signature images in testsheets")

    assert_problem_recorded(locations.fallback_logs, status, "bad workbook", capsys)


def test_desktop_ini_that_cannot_be_removed_is_recorded(locations, utility_env, tmp_path, capsys) -> None:
    folder = tmp_path / "scan"
    folder.mkdir()
    (folder / "desktop.ini").write_text("x", encoding="utf-8")

    with (
        patch("src.cli_selectors.prompt_directory_path", return_value=folder),
        patch("src.remove_desktop_ini_workflow.subprocess.run", return_value=SimpleNamespace(returncode=1)),
        patch("src.remove_desktop_ini_workflow.os.chmod", side_effect=PermissionError("locked")),
    ):
        run_registered_utility("Remove desktop.ini files (recursive)")

    assert_problem_recorded(locations.fallback_logs, "completed_with_errors", "locked", capsys)


def _quick_report_prompts():
    return (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="browse_dates"),
        patch(
            "src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive",
            return_value=("07-11-2026",),
        ),
    )


@pytest.mark.parametrize(
    "inspection, printed",
    [
        (QuickReportInspection((), ("Sticker template missing",), (), ()), "Cannot generate Quick Report"),
        (QuickReportInspection((), (), (), ("Package discovery failed: boom",)), "Inspection found 1 error(s)"),
    ],
)
def test_quick_report_that_cannot_start_is_a_failed_run(locations, capsys, inspection, printed) -> None:
    action = QuickReportAction("Generate Quick Report")
    session = CliSession(persistence_file=locations.project / ".active", active_project=locations.environment)
    prompts = _quick_report_prompts()
    with (
        prompts[0], prompts[1],
        patch("src.cli_menu.select_project_workflow_action", side_effect=[action, None]),
        patch.object(QuickReportWorkflow, "inspect", return_value=inspection),
    ):
        _run_project_workflow_menu(session, [action])

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    captured = capsys.readouterr().out
    assert printed in captured
    assert str(next(locations.project_logs.glob("*.jsonl"))) in captured


def _run_project_action_object(action, locations) -> None:
    session = CliSession(persistence_file=locations.project / ".active", active_project=locations.environment)
    with patch("src.cli_menu.select_project_workflow_action", side_effect=[action, None]):
        _run_project_workflow_menu(session, [action])


def test_full_report_with_nothing_to_process_is_a_failed_run(locations, capsys) -> None:
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportInspection(targets=(), warnings=(), errors=("discovery broke",))
    action = FullReportAction("Generate Full Reports", workflow=workflow)

    with patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]):
        _run_project_action_object(action, locations)

    assert read_entries(locations.project_logs)[-1]["status"] == "failed"
    captured = capsys.readouterr().out
    assert "No substations discovered to process." in captured
    assert str(next(locations.project_logs.glob("*.jsonl"))) in captured


def test_postprocessing_with_nothing_to_process_is_a_failed_run(locations, capsys) -> None:
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportPostProcessingInspection(targets=(), warnings=(), errors=())
    action = FullReportPostProcessingAction("Post-Process Full Reports", workflow=workflow)

    with patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]):
        workflow.locate_full_reports_for_fls.return_value = ([], [])
        _run_project_action_object(action, locations)

    assert read_entries(locations.project_logs)[-1]["status"] == "failed"
    captured = capsys.readouterr().out
    assert "No Full Report documents discovered for post-processing." in captured
    assert str(next(locations.project_logs.glob("*.jsonl"))) in captured


def test_pipeline_failed_substation_keeps_traceback_off_the_console(locations, tmp_path, capfd) -> None:
    package = SubstationPackage(
        testsheet_xlsx=tmp_path / "TS" / "1. PE.xlsx",
        quick_report_docx=tmp_path / "QR" / "1. PE.docx",
        station_name="PE ONE",
    )
    (tmp_path / "TS").mkdir()
    request = PostProcessingRequest(
        mode=PostProcessingMode.BY_FL,
        target_packages=(package,),
        apply_signatures=True,
        vendor_signature_path=tmp_path / "sign.png",
        converter=_FakeConverter(),
    )

    def action(environment) -> object:
        module = "src.workflows.postprocessing_pipeline"
        with (
            patch(f"{module}.validate_postprocessing_preflight"),
            patch(f"{module}.discover_substation_packages", return_value=[package]),
            patch(f"{module}.replace_pce_images", side_effect=RuntimeError("signature stamp broke")),
        ):
            return PostProcessingPipelineWorkflow().execute(environment, request)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    tracebacks = [e["traceback"] for e in entries_of(entries, "error") if "traceback" in e]
    assert any("signature stamp broke" in text for text in tracebacks)
    captured = capfd.readouterr()
    assert "Traceback" not in captured.out + captured.err


def test_full_report_discovery_failure_has_a_traceback(locations, capsys) -> None:
    workflow = FullReportWorkflow()

    def action(environment) -> object:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(workflow, "_extractor") as extractor,
        ):
            extractor.extract.side_effect = RuntimeError("testsheet scan broke")
            return workflow.generate(["FL1"], environment)

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "failed", "testsheet scan broke", capsys)


def test_full_report_inspection_failure_has_a_traceback(locations, capsys) -> None:
    package = SubstationTestsheetPackage(
        testsheet_path=locations.project / "a.xlsx",
        unsorted_raw_data_dir=locations.project,
        station="KUANTAN",
        month="NOV",
        date_str="07-11-2026",
        substation_number=1,
    )
    workflow = FullReportWorkflow()

    def action(environment) -> object:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(FullReportWorkflow, "_discover_packages", return_value=([package], [], [])),
            patch.object(FullReportWorkflow, "_inspect_single_package", side_effect=RuntimeError("inspection broke")),
        ):
            return workflow.inspect(["FL1"], environment)

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "completed_with_errors", "inspection broke", capsys)


def test_quick_report_discovery_failure_has_a_traceback(locations, capsys) -> None:
    workflow = QuickReportWorkflow()

    def action(environment) -> object:
        with patch.object(workflow, "_extractor") as extractor:
            extractor.extract.side_effect = RuntimeError("testsheet scan broke")
            return workflow.inspect(["FL1"], environment)

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "completed_with_errors", "testsheet scan broke", capsys)


def test_quick_report_failed_substation_has_a_traceback(locations, capsys) -> None:
    package = SimpleNamespace(data=object(), substation_name="PE ONE", testsheet_path=locations.project / "a.xlsx")
    workflow = QuickReportWorkflow()

    def action(environment) -> object:
        with (
            patch.object(workflow, "_extractor") as extractor,
            patch.object(QuickReportWorkflow, "_resolve_substation_display_name", return_value="PE ONE"),
        ):
            extractor.extract.return_value = [package]
            extractor.extract_defects.side_effect = RuntimeError("defect sheet broke")
            return workflow.inspect(Path("07-11-2026"), environment)

    with patch.object(QuickReportWorkflow, "_resolve_target", return_value=(["07-11-2026"], [])):
        run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "completed_with_errors", "defect sheet broke", capsys)


def test_consolidate_unreadable_xls_has_a_traceback(locations, tmp_path, capsys) -> None:
    bad_file = tmp_path / "bad.xls"
    bad_file.write_bytes(b"not a table")

    def action(environment) -> None:
        with patch("src.workflows.consolidate_msms.pd.read_html", side_effect=RuntimeError("html parser broke")):
            ConsolidateMsmsExtractor().read_xls_file(bad_file)

    run_project_action(action, locations.environment)

    assert_problem_recorded(locations.project_logs, "completed_with_errors", "html parser broke", capsys)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_library_handler_sees_what_it_saw_before_the_run(locations) -> None:
    library = logging.getLogger("library_with_handler")
    handler = _ListHandler()
    library.addHandler(handler)

    def noisy() -> None:
        library.debug("library debug")
        library.info("library info")
        library.warning("library warning")

    try:
        _run_action("Fake", noisy)
        without_run = list(handler.messages)
        handler.messages.clear()
        _run_recorded_action("Fake", noisy, locations.environment)
    finally:
        library.removeHandler(handler)

    assert handler.messages == without_run == ["library warning"]


def test_handler_added_to_root_during_a_run_sees_only_what_it_would_have_seen(locations) -> None:
    handler = _ListHandler()

    def action() -> None:
        logging.root.addHandler(handler)
        logging.getLogger("src.fake").debug("src debug")
        logging.getLogger("src.fake").info("src info")
        logging.debug("direct debug")
        logging.getLogger("src.fake").warning("src warning")
        logging.warning("direct warning")

    try:
        _run_recorded_action("Fake", action, locations.environment)
        assert handler in logging.root.handlers
    finally:
        logging.root.removeHandler(handler)

    assert handler.messages == ["src warning", "direct warning"]


def test_root_level_is_not_changed_during_a_run(locations) -> None:
    seen: list[object] = []
    level_before = logging.root.level

    def action() -> None:
        seen.append(logging.root.level)
        seen.append(logging.getLogger("thirdparty.lib").isEnabledFor(logging.DEBUG))

    _run_recorded_action("Fake", action, locations.environment)

    assert seen == [level_before, level_before <= logging.DEBUG]
    assert "isEnabledFor" not in vars(logging.root)
    assert logging.getLogger("src").level == logging.NOTSET


def test_root_logger_method_on_unconfigured_root_prints_as_it_does_without_a_run(
    locations, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(logging.root, "handlers", [])

    def action() -> None:
        logging.getLogger().warning("rootmethod")
        logging.getLogger().debug("hidden")

    _run_action("Fake", action)
    without_run = capsys.readouterr().err
    assert logging.root.handlers == []

    _run_recorded_action("Fake", action, locations.environment)
    with_run = capsys.readouterr().err

    assert with_run == without_run == "rootmethod\n"
    assert logging.root.handlers == []
    logged = entries_of(read_entries(locations.project_logs), "log")
    assert [entry["message"] for entry in logged] == ["rootmethod", "hidden"]


class _BadStr(Exception):
    def __str__(self) -> str:
        raise RuntimeError("str() of this exception is broken")


def test_exception_with_a_broken_str_reaches_the_caller_unchanged(locations) -> None:
    def failing() -> None:
        raise _BadStr()

    with open_run("Fake", locations.environment) as run, pytest.raises(_BadStr):
        run.call(failing)

    entries = read_entries(locations.project_logs)
    assert entries_of(entries, "error")[0]["exception_type"] == "_BadStr"
    assert entries[-1]["status"] == "failed"


def test_failure_building_the_captures_does_not_stop_the_action(locations, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("handler cannot be built")

    monkeypatch.setattr(logging.Handler, "__init__", broken)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    assert read_entries(locations.project_logs)[-1]["type"] == "run_finish"


def test_record_file_is_closed_when_a_run_cannot_start(locations, monkeypatch) -> None:
    def broken():
        raise RuntimeError("cannot capture")

    monkeypatch.setattr("src.run_records._capture_versions", broken)
    calls: list[str] = []

    run_project_action(lambda environment: calls.append("ran"), locations.environment)

    assert calls == ["ran"]
    # Windows refuses to delete a file that is still open.
    next(locations.project_logs.glob("*.jsonl")).unlink()


def test_cancelling_the_transient_environment_prompt_is_not_a_failure(locations, capsys) -> None:
    with (
        patch("src.project.environment.load_project_environment", return_value=None),
        patch("src.cli_selectors.prompt_directory_path", return_value=None),
    ):
        run_registered_utility("Remove desktop.ini files (recursive)")

    console = capsys.readouterr().out
    assert "Action failed: Operation cancelled" in console
    assert "Run Record:" not in console
    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "cancelled"
    assert not entries_of(entries, "error")


def test_cancelled_prompt_still_raises_value_error_for_existing_callers() -> None:
    from src.project.environment import get_or_create_utility_environment

    with (
        patch("src.project.environment.load_project_environment", return_value=None),
        patch("src.cli_selectors.prompt_directory_path", return_value=None),
        pytest.raises(ValueError, match="Operation cancelled"),
    ):
        get_or_create_utility_environment()
