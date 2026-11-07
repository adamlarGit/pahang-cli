"""Run Record behaviour, tested by running fake actions through the action-running layer.

No test here starts Word or Excel, and none touches a real project folder or the
real %LOCALAPPDATA%: every location used is under pytest's tmp_path.
"""

from __future__ import annotations

import gc
import io
import json
import logging
import os
import subprocess
import sys
import time
import uuid
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import openpyxl
import pythoncom
import pytest
import questionary
import win32com.client
import win32com.client.dynamic
from prompt_toolkit.application import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output

from src import __version__
from src.cli_session import CliSession
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.quick_report.compiler import FakeDocumentCompiler
from src.quick_report.transformer import QuickReportTransformer
from src.project_settings_actions import handle_switch_project, handle_view_project_info
from src.project_workflow_actions import (
    ConsolidateMsmsAction,
    EnrichMsmsAction,
    FullReportAction,
    FullReportPostProcessingAction,
    GenerateTestsheetFolderAction,
    IngestMsmsCsvAction,
    PopulateDataMsmsAction,
    PopulateTotalPeAction,
    ProjectWorkflowAction,
    PropagateWoAction,
    QuickReportAction,
    RawMaterialAction,
    UpdateQr02CbaAction,
    WhatsAppReportAction,
)
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, current_run, open_run
from src.testsheet.models import SubstationPackage, SubstationTestsheetPackage
from src.utility_actions import UtilityAction, get_utility_actions
from src.workflows.combine_pdfs_with_separator import CombinePdfsWithSeparatorSummary
from src.workflows.consolidate_msms import ConsolidateMsmsExtractor, ConsolidateMsmsWorkflow
from src.workflows.enrich_msms import EnrichMsmsWorkflow
from src.workflows.full_report import (
    FullReportInspection,
    FullReportWorkflow,
    _SubstationExecutionContext,
)
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingInspection,
    FullReportPostProcessingResult,
    FullReportPostProcessingWorkflow,
    PostProcessingTargetGroup,
)
from src.workflows.generate_testsheet_folder import GenerateTestsheetFolderStructureWorkflow
from src.workflows.ingest_msms_csv import IngestMsmsCsvWorkflow
from src.workflows.models import (
    ConsolidateMsmsRequest,
    ConsolidateMsmsResult,
    EnrichMsmsRequest,
    EnrichMsmsResult,
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
    IngestMsmsCsvRequest,
    IngestMsmsCsvResult,
    PopulateDataMsmsRequest,
    PopulateDataMsmsResult,
    PopulateMode,
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
    PostProcessingMode,
    PostProcessingFailure,
    PostProcessingRequest,
    PostProcessingSummary,
    PropagateWoRequest,
    PropagateWoResult,
    QuickReportInspection,
    QuickReportResult,
    RawMaterialRequest,
    RawMaterialResult,
    UpdateQr02CbaRequest,
    UpdateQr02CbaResult,
    WhatsAppReportRequest,
    WhatsAppReportResult,
)
from src.workflows.pdf_extract import PdfExtractSummary
from src.workflows.populate_data_msms import PopulateDataMsmsWorkflow
from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.workflows.postprocessing_pipeline import PostProcessingPipelineWorkflow
from src.workflows.propagate_wo import PropagateWoWorkflow
from src.workflows.quick_report import QuickReportWorkflow
from src.workflows.raw_material import RawMaterialWorkflow
from src.workflows.service import WorkflowService
from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow
from src.workflows.us_audio import UsAudioCandidate, UsAudioWorkflow
from src.workflows.us_tev_graphs import (
    BrowserPrerequisiteError,
    SubstationGraphResult,
    UsTevCandidate,
    UsTevGraphWorkflow,
)
from src.workflows.whatsapp import WhatsAppReportWorkflow
from src.workflow_cli import (
    _run_action,
    _run_project_workflow_menu,
    _run_recorded_action,
    _run_utility_actions_menu,
    _select_project,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_real_office(monkeypatch: pytest.MonkeyPatch):
    """Fail any test in this file that tries to start real Word or Excel.

    The action layer catches Exception, so raising alone could pass unnoticed. Attempts are
    logged and fail the test at teardown. This stays even with a suite-wide guard, because
    no test here may ever start Office, whatever markers it has.
    """
    attempts: list[str] = []

    def blocked(name: str):
        def fail(*args, **kwargs):
            attempts.append(f"{name}{args!r}")
            raise AssertionError(f"Real Word or Excel must not start in these tests: {name}{args!r}")

        return fail

    monkeypatch.setattr(win32com.client, "Dispatch", blocked("Dispatch"))
    monkeypatch.setattr(win32com.client, "DispatchEx", blocked("DispatchEx"))
    monkeypatch.setattr(win32com.client.gencache, "EnsureDispatch", blocked("EnsureDispatch"))
    monkeypatch.setattr(win32com.client.dynamic, "Dispatch", blocked("dynamic.Dispatch"))
    monkeypatch.setattr(pythoncom, "CoCreateInstance", blocked("CoCreateInstance"))
    monkeypatch.setattr(pythoncom, "CoCreateInstanceEx", blocked("CoCreateInstanceEx"))
    yield attempts
    if attempts:
        pytest.fail(f"A test tried to start real Word or Excel: {attempts}", pytrace=False)


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


def test_protection_reaches_a_child_process(tmp_path) -> None:
    """A child process's Run lands in the suite's redirect folder, and nowhere else."""
    project = tmp_path / "project"
    project.mkdir()
    local_app_data = tmp_path / "local_app_data"
    label = f"child-{uuid.uuid4().hex}"
    script = (
        "import sys\n"
        "from types import SimpleNamespace\n"
        "from src.run_records import open_run\n"
        "environment = SimpleNamespace(project_key='child_project', base_path=sys.argv[2])\n"
        "with open_run(sys.argv[1], environment) as run:\n"
        "    run.call(lambda: None)\n"
        "print(run.path)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, label, str(project)],
        cwd=REPO_ROOT,
        env={**os.environ, "LOCALAPPDATA": str(local_app_data)},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    record = Path(completed.stdout.strip())
    assert record.parent == Path(os.environ[RECORD_DIR_OVERRIDE_VARIABLE])
    assert label in record.name
    assert json.loads(record.read_text(encoding="utf-8").splitlines()[0])["project_key"] == "child_project"
    assert not (project / "logs").exists()
    assert not local_app_data.exists()


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


def _progress_sink(message: str) -> None:
    pass


_SERVICE_WORKFLOW_CASES = {
    "populate_total_pe": (
        lambda s, e, r: s.run_populate_total_pe(e, r),
        "src.workflows.service.PopulateTotalPeWorkflow",
        PopulateTotalPeRequest(mode=PopulateMode.AUTO, target_folder_names=("07-11-2026",), progress_sink=_progress_sink),
    ),
    "raw_material": (
        lambda s, e, r: s.run_raw_material(e, r),
        "src.workflows.service.RawMaterialWorkflow",
        RawMaterialRequest(output_path=Path("RAW"), target_dir=Path("TS"), progress_sink=_progress_sink),
    ),
    "propagate_wo": (
        lambda s, e, r: s.run_propagate_wo(e, r),
        "src.workflows.propagate_wo.PropagateWoWorkflow",
        PropagateWoRequest(target_date="07-11-2026", overwrite=True, progress_sink=_progress_sink),
    ),
    "consolidate_msms": (
        lambda s, e, r: s.run_consolidate_msms(e, r),
        "src.workflows.consolidate_msms.ConsolidateMsmsWorkflow",
        ConsolidateMsmsRequest(progress_sink=_progress_sink),
    ),
    "enrich_msms": (
        lambda s, e, r: s.run_enrich_msms(e, r),
        "src.workflows.enrich_msms.EnrichMsmsWorkflow",
        EnrichMsmsRequest(progress_sink=_progress_sink),
    ),
    "ingest_msms_csv": (
        lambda s, e, r: s.run_ingest_msms_csv(e, r),
        "src.workflows.ingest_msms_csv.IngestMsmsCsvWorkflow",
        IngestMsmsCsvRequest(progress_sink=_progress_sink),
    ),
    "populate_data_msms": (
        lambda s, e, r: s.run_populate_data_msms(e, r),
        "src.workflows.populate_data_msms.PopulateDataMsmsWorkflow",
        PopulateDataMsmsRequest(mode=PopulateMode.ALL, overwrite=True, progress_sink=_progress_sink),
    ),
    "update_qr02_cba": (
        lambda s, e, r: s.run_update_qr02_cba(e, r),
        "src.workflows.update_qr02_cba.UpdateQr02CbaWorkflow",
        UpdateQr02CbaRequest(mode=PopulateMode.AUTO, progress_sink=_progress_sink),
    ),
    "whatsapp": (
        lambda s, e, r: s.run_whatsapp(e, r),
        "src.workflows.whatsapp.WhatsAppReportWorkflow",
        WhatsAppReportRequest(target_date=date(2026, 11, 7), report_dir=Path("QR"), progress_sink=_progress_sink),
    ),
    "generate_testsheet_folder": (
        lambda s, e, r: s.run_generate_testsheet_folder(e, r),
        "src.workflows.generate_testsheet_folder.GenerateTestsheetFolderStructureWorkflow",
        GenerateTestsheetFolderRequest(station="KUANTAN", month="NOV", target_dates=("07-11-2026",), progress_sink=_progress_sink),
    ),
}


@pytest.mark.parametrize("case", list(_SERVICE_WORKFLOW_CASES))
def test_every_service_workflow_records_its_request_centrally(locations, case) -> None:
    call_service, patch_target, request = _SERVICE_WORKFLOW_CASES[case]
    (locations.project / "PYTHON").mkdir()
    (locations.project / "PYTHON" / "TOTAL PE.xlsx").write_bytes(b"123")

    def action(environment) -> None:
        with patch(patch_target):
            call_service(WorkflowService(), environment, request)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    recorded = entries_of(entries, "request")[0]["request"]
    assert recorded["__type__"] == type(request).__name__
    assert recorded["progress_sink"] == "<function test_run_records._progress_sink>"
    inputs = {entry["path"]: entry for entry in entries_of(entries, "input")}
    assert inputs[str(locations.project / "PYTHON" / "TOTAL PE.xlsx")]["size"] == 3
    assert entries[-1]["status"] == "completed"


def test_real_request_field_values_are_kept_readable(locations) -> None:
    _, _, request = _SERVICE_WORKFLOW_CASES["whatsapp"]

    run_project_action(lambda environment: current_run().record_request(request), locations.environment)

    recorded = entries_of(read_entries(locations.project_logs), "request")[0]["request"]
    assert recorded["target_date"] == "2026-11-07"
    assert recorded["report_dir"] == "QR"


def test_service_with_no_request_records_the_default_it_uses(locations) -> None:
    def action(environment) -> None:
        with patch("src.workflows.propagate_wo.PropagateWoWorkflow"):
            WorkflowService().run_propagate_wo(environment)

    run_project_action(action, locations.environment)

    recorded = entries_of(read_entries(locations.project_logs), "request")[0]["request"]
    assert recorded["__type__"] == "PropagateWoRequest"
    assert recorded["overwrite"] is False


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
    "result",
    [
        QuickReportResult(reports_generated=2, errors=("PE 3 failed",)),
        QuickReportResult(reports_generated=0, errors=("PE 3 failed",)),
        ConsolidateMsmsResult(files_processed=0, errors=("bad xls",)),
    ],
)
def test_errors_in_a_result_alone_never_mean_the_whole_job_failed(locations, result) -> None:
    """Only the workflow knows that. The module doesn't guess from count fields."""
    run_project_action(lambda environment: result, locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == "completed_with_errors"


def test_mark_failed_is_not_downgraded_and_writes_no_entry_of_its_own(locations) -> None:
    def action(environment) -> QuickReportResult:
        current_run().mark_failed()
        return QuickReportResult(reports_generated=1, errors=("PE 3 failed",))

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert [entry["message"] for entry in entries_of(entries, "error")] == ["PE 3 failed"]


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

    assert_problem_recorded(locations.fallback_logs, "failed", "locked", capsys)


def test_desktop_ini_with_some_removed_has_errors(locations, utility_env, tmp_path, capsys) -> None:
    folder = tmp_path / "scan"
    (folder / "locked").mkdir(parents=True)
    (folder / "free").mkdir()
    (folder / "locked" / "desktop.ini").write_text("x", encoding="utf-8")
    (folder / "free" / "desktop.ini").write_text("x", encoding="utf-8")

    def chmod(path, mode):
        if Path(path).parent.name == "locked":
            raise PermissionError("locked")

    with (
        patch("src.cli_selectors.prompt_directory_path", return_value=folder),
        patch("src.remove_desktop_ini_workflow.subprocess.run", return_value=SimpleNamespace(returncode=1)),
        patch("src.remove_desktop_ini_workflow.os.chmod", chmod),
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
    requests = entries_of(entries, "request")
    assert [request["request"] for request in requests] == [
        {"workflow": "Quick Report", "target": ["07-11-2026"]}
    ]
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

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert [entry["request"] for entry in entries_of(entries, "request")] == [
        {"workflow": "Full Report", "target": ["FL1"]}
    ]
    captured = capsys.readouterr().out
    assert "No substations discovered to process." in captured
    assert str(next(locations.project_logs.glob("*.jsonl"))) in captured


def test_full_report_with_nothing_found_and_no_errors_is_not_a_failure(locations, capsys) -> None:
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportInspection(targets=(), warnings=(), errors=())
    action = FullReportAction("Generate Full Reports", workflow=workflow)

    with patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]):
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    assert entries_of(entries, "warning")
    assert entries_of(entries, "request")
    captured = capsys.readouterr().out
    assert "No substations discovered to process." in captured
    assert "Run Record:" not in captured


def test_postprocessing_with_nothing_found_and_no_errors_is_not_a_failure(locations, capsys) -> None:
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportPostProcessingInspection(targets=(), warnings=(), errors=())
    workflow.locate_full_reports_for_fls.return_value = ([], [])
    action = FullReportPostProcessingAction("Post-Process Full Reports", workflow=workflow)

    with patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]):
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    assert not entries_of(entries, "error")
    assert [entry["request"] for entry in entries_of(entries, "request")] == [
        {"workflow": "Full Report Post-Processing", "target": ["FL1"]}
    ]
    captured = capsys.readouterr().out
    assert "No Full Report documents discovered for post-processing." in captured
    assert "Run Record:" not in captured


def test_postprocessing_discovery_errors_are_a_failed_run_with_the_request(locations, capsys) -> None:
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportPostProcessingInspection(targets=(), warnings=(), errors=("scan broke",))
    workflow.locate_full_reports_for_fls.return_value = ([], [])
    action = FullReportPostProcessingAction("Post-Process Full Reports", workflow=workflow)

    with patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]):
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert entries_of(entries, "request")[0]["request"]["target"] == ["FL1"]
    assert str(next(locations.project_logs.glob("*.jsonl"))) in capsys.readouterr().out


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
    errors = entries_of(entries, "error")
    assert len(errors) == 1, errors
    assert "signature stamp broke" in errors[0]["traceback"]
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


class _FakeConverterClass:
    """Replaces ComDocumentConverter, so the real conversion loops run with no COM."""

    def convert_docx_to_pdf(self, source, target, **kwargs) -> None:
        pass

    def convert_testsheet_to_pdf(self, source, target, **kwargs) -> None:
        pass

    def merge_pdfs(self, first, second, target) -> None:
        pass


def _file(path: Path, content: bytes = b"content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _answers(*answers: str):
    return patch("builtins.input", side_effect=list(answers))


def _stub_stages(workflow, **stages):
    for name in ("preflight_guard", "extractor", "filter_stage", "transformer", "loader", "auditor"):
        setattr(workflow, name, stages.get(name, MagicMock()))
    return workflow


def _package(path: Path) -> SubstationTestsheetPackage:
    return SubstationTestsheetPackage(
        testsheet_path=path,
        unsorted_raw_data_dir=path.parent,
        station="KUANTAN",
        month="NOV",
        date_str="07-11-2026",
        substation_number=1,
    )


def _case_rename(locations, tmp_path):
    source = _file(tmp_path / "in" / "1 name.txt")
    target = _file(tmp_path / "out" / "1 old.txt")
    with _answers(str(source.parent), str(target.parent)):
        run_registered_utility("Rename files (match names from input dir)")
    return {"input_directory": str(source.parent)}, [source, target], [target.parent.resolve()]


def _case_extract(locations, tmp_path):
    pdf = _file(tmp_path / "scan.pdf")
    summary = PdfExtractSummary(pdf_path=pdf, total_pages=1, extracted_sections=1, cleaned_pdf_path=pdf)
    with _answers(str(pdf)), patch("src.workflows.pdf_extract.extract_pdf_sections_and_clean", return_value=summary):
        run_registered_utility("Extract PE pages from PDF (black-page detection)")
    return {"pdf_path": str(pdf)}, [pdf], [pdf]


def _case_combine(locations, tmp_path):
    first = _file(tmp_path / "primary" / "1.pdf")
    second = _file(tmp_path / "secondary" / "1.pdf")
    with (
        _answers(str(first.parent), str(second.parent)),
        patch("src.workflows.combine_pdfs.ComDocumentConverter", _FakeConverterClass),
    ):
        run_registered_utility("Combine PDFs from primary and secondary folders")
    return {"primary_folder": str(first.parent)}, [first, second], [first.resolve()]


def _case_combine_with_separator(locations, tmp_path):
    separator = _file(tmp_path / "separator.pdf")
    pdf = _file(tmp_path / "folder" / "1.pdf")
    combined = tmp_path / "folder" / "combined_pdf" / "combined.pdf"
    summary = CombinePdfsWithSeparatorSummary(pdf.parent, separator, combined, 1)
    with (
        patch.object(ProjectEnvironment, "get_template", return_value=separator),
        patch("src.cli_selectors.select_testsheet_subfolder", return_value=pdf.parent),
        patch("src.workflows.combine_pdfs_with_separator.combine_pdfs_with_separator", return_value=summary),
    ):
        run_registered_utility("Combine PDFs with separator sheet")
    return {"target_folder": str(pdf.parent)}, [pdf, separator], [combined]


def _case_docx_to_pdf(locations, tmp_path):
    docx = _file(tmp_path / "folder" / "1.docx")
    with (
        _answers(str(docx.parent)),
        patch("src.workflows.docx_to_pdf.ComDocumentConverter", _FakeConverterClass),
        # Without this, the fake passes the loop's isinstance check and it starts real Word.
        patch("src.workflows.docx_to_pdf.win32com", None),
    ):
        run_registered_utility("Convert DOCX to PDF (batch)")
    return {"input_directory": str(docx.parent)}, [docx], [docx.resolve().with_suffix(".pdf")]


def _case_testsheet_to_pdf(locations, tmp_path):
    sheet = _file(tmp_path / "folder" / "1.xlsx")
    with (
        _answers(str(sheet.parent)),
        patch("src.workflows.testsheet_to_pdf.ComDocumentConverter", _FakeConverterClass),
        # Without this, the fake passes the loop's isinstance check and it starts real Excel.
        patch("src.workflows.testsheet_to_pdf.win32com", None),
    ):
        run_registered_utility("Convert Testsheet to PDF (batch)")
    return {"folder_path": str(sheet.parent)}, [sheet], [sheet.resolve().with_suffix(".pdf")]


def _case_rename_flir(locations, tmp_path):
    raw = _file(tmp_path / "raw" / "a.jpg")
    out = tmp_path / "out"
    with _answers(str(raw.parent), str(out), "5"):
        run_registered_utility("Rename FLIR raw files numbering")
    return {"input_folder": str(raw.parent), "starting_number": "5"}, [raw], [out.resolve()]


def _case_diagonal(locations, tmp_path):
    workbook = tmp_path / "folder" / "1.xlsx"
    workbook.parent.mkdir()
    openpyxl.Workbook().save(workbook)
    with _answers(str(workbook.parent)):
        run_registered_utility("Apply diagonal borders to blank cells")
    output = workbook.parent.resolve() / "processed_testsheet" / "1.xlsx"
    return {"target_path": str(workbook.parent)}, [workbook], [output]


def _case_replace_signatures(locations, tmp_path):
    workbook = _file(tmp_path / "1.xlsx")
    signature = _file(tmp_path / "sign.png")
    prompts = (
        _answers(str(workbook)),
        patch("src.cli_selectors.select_one", return_value="placeholder"),
        patch("src.workflows.replace_signatures._select_signature_path", return_value=(signature, "person")),
        patch("src.workflows.replace_signatures.replace_pce_images"),
    )
    with prompts[0], prompts[1], prompts[2], prompts[3]:
        run_registered_utility("Replace signature images in testsheets")
    output = workbook.resolve().parent / "processed_testsheet" / "1.xlsx"
    return {"mode": "placeholder", "target": str(workbook.resolve())}, [workbook.resolve(), signature], [output]


def _case_us_tev_graphs(locations, tmp_path):
    candidate = _tev_candidate(tmp_path, "PE1")
    testsheet = _file(candidate.package.testsheet_path)
    prompts = _tev_prompts([candidate])
    result = SubstationGraphResult(generated=[tmp_path / "graph.png"])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "run_substation", return_value=result),
    ):
        run_registered_utility("Generate US+TEV survey graphs")
    return {"mode": "option_b", "dates": ["07-11-2026"]}, [candidate.survey_dir, testsheet], [candidate.output_dir]


def _case_us_audio(locations, tmp_path):
    survey = tmp_path / "survey"
    survey.mkdir()
    pdf = _file(tmp_path / "report.pdf")
    sounds = tmp_path / "sounds"
    candidate = UsAudioCandidate(raw_data_dir=survey, survey_dir=survey, sounds_output_dir=sounds, full_report_pdf=pdf)
    module = "src.workflows.us_audio"
    prompts = (
        patch(f"{module}.select_one", side_effect=["both", "enter_dates"]),
        patch(f"{module}.prompt_target_inspection_dates_with_ranges", return_value=["07-11-2026"]),
        patch(f"{module}.discover_us_audio_candidate_substations", return_value=[candidate]),
        patch(f"{module}.select_us_audio_substations_interactive", return_value=[candidate]),
        patch(f"{module}.export_substation_16bit_wavs", return_value=[]),
        patch(f"{module}.embed_survey_ultrasound_into_pdf", return_value=1),
    )
    with prompts[0], prompts[1], prompts[2], prompts[3], prompts[4], prompts[5]:
        run_registered_utility("Generate US 16-bit audio & embed sounds into PDFs")
    return {"mode": "both", "dates": ["07-11-2026"]}, [survey, pdf], [sounds, pdf]


def _case_remove_desktop_ini(locations, tmp_path):
    folder = tmp_path / "scan"
    folder.mkdir()
    with (
        patch("src.cli_selectors.prompt_directory_path", return_value=folder),
        patch("src.remove_desktop_ini_workflow.remove_desktop_ini_files", return_value=0),
    ):
        run_registered_utility("Remove desktop.ini files (recursive)")
    return {"target_path": str(folder)}, [folder], []


_UTILITY_RECORDING_CASES = {
    "rename": _case_rename,
    "extract_pe": _case_extract,
    "combine": _case_combine,
    "combine_with_separator": _case_combine_with_separator,
    "docx_to_pdf": _case_docx_to_pdf,
    "testsheet_to_pdf": _case_testsheet_to_pdf,
    "rename_flir": _case_rename_flir,
    "diagonal": _case_diagonal,
    "replace_signatures": _case_replace_signatures,
    "us_tev_graphs": _case_us_tev_graphs,
    "us_audio": _case_us_audio,
    "remove_desktop_ini": _case_remove_desktop_ini,
}


def _assert_recorded(entries: list[dict], request_fields: dict, inputs: list[Path], outputs: list[Path]) -> None:
    requests = [entry["request"] for entry in entries_of(entries, "request")]
    assert requests, "no request entry"
    assert requests[0] is not None
    for field, value in request_fields.items():
        assert requests[0][field] == value, field
    recorded_inputs = {entry["path"]: entry for entry in entries_of(entries, "input")}
    for path in inputs:
        assert str(path) in recorded_inputs, f"{path} not in {list(recorded_inputs)}"
        assert recorded_inputs[str(path)]["exists"] is True
        assert recorded_inputs[str(path)]["modified"]
    recorded_outputs = {entry["path"] for entry in entries_of(entries, "output")}
    for path in outputs:
        assert str(path) in recorded_outputs, f"{path} not in {recorded_outputs}"


@pytest.mark.parametrize("case", list(_UTILITY_RECORDING_CASES))
def test_utility_action_records_request_inputs_and_outputs(locations, utility_env, tmp_path, case, capsys) -> None:
    request_fields, inputs, outputs = _UTILITY_RECORDING_CASES[case](locations, tmp_path)

    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "completed", capsys.readouterr().out
    _assert_recorded(entries, request_fields, inputs, outputs)


def _case_populate_total_pe(locations):
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    total_pe = _file(locations.project / "PYTHON" / "TOTAL PE.xlsx")
    package = _package(testsheet)
    stages = _stub_stages(PopulateTotalPeWorkflow())
    stages.extractor.discover_packages.return_value = [package]
    stages.extractor.hydrate_packages_metadata.return_value = [package]
    stages.extractor.get_existing_auto_keys.return_value = set()
    stages.filter_stage.filter_packages.return_value = [package]
    stages.loader.upsert_packages.return_value = (1, 0)
    stages.auditor.audit.return_value = PopulateTotalPeResult(new_rows_added=1)
    action = PopulateTotalPeAction("Populate TOTAL PE")
    with (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="auto"),
        patch("src.workflows.service.PopulateTotalPeWorkflow", return_value=stages),
    ):
        _run_project_action_object(action, locations)
    return "PopulateTotalPeRequest", [testsheet, total_pe], [total_pe]


def _case_raw_material(locations):
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    stages = _stub_stages(RawMaterialWorkflow())
    stages.extractor.discover_packages.return_value = [_package(testsheet)]
    stages.auditor.audit.return_value = (None, RawMaterialResult(substations_count=1))
    action = RawMaterialAction("Raw Material")
    with (
        patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=testsheet.parent),
        patch("src.workflows.service.RawMaterialWorkflow", return_value=stages),
        patch.object(stages, "_process_package", return_value=(0, 0, 0)),
    ):
        _run_project_action_object(action, locations)
    return "RawMaterialRequest", [testsheet], [locations.project / "RAW MATERIAL"]


def _case_update_qr02(locations):
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    package = _package(testsheet)
    workflow = UpdateQr02CbaWorkflow()
    loader = workflow.loader
    stages = _stub_stages(workflow, loader=loader)
    stages.extractor.extract_packages.return_value = [package]
    stages.extractor.extract_records.return_value = ({}, [])
    stages.filter_stage.filter.return_value = [package]
    stages.transformer.transform.return_value = SimpleNamespace(
        station_plans=[SimpleNamespace(station="KUANTAN", records=[], packages=[package])]
    )
    stages.auditor.audit.return_value = UpdateQr02CbaResult(records_updated=1)
    action = UpdateQr02CbaAction("Update QR02")
    workbook = locations.environment.storage.get_engr_cba_path("KUANTAN", "2026", voltage_type="11kV")
    with (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="auto"),
        patch("src.workflows.update_qr02_cba.UpdateQr02CbaWorkflow", return_value=stages),
        patch.object(loader, "_create_repository"),
    ):
        _run_project_action_object(action, locations)
    return "UpdateQr02CbaRequest", [testsheet], [workbook]


def _case_consolidate(locations):
    xls = _file(locations.project / "PYTHON" / "MSMS" / "a.xls")
    data_msms = locations.project / "PYTHON" / "DATA MSMS.xlsx"
    stages = _stub_stages(ConsolidateMsmsWorkflow())
    stages.extractor.read_xls_file.return_value = ([], None)
    stages.filter_stage.filter_rows.return_value = ([], 0)
    stages.auditor.audit.return_value = ConsolidateMsmsResult(files_processed=1)
    action = ConsolidateMsmsAction("Consolidate")
    with patch("src.workflows.consolidate_msms.ConsolidateMsmsWorkflow", return_value=stages):
        _run_project_action_object(action, locations)
    return "ConsolidateMsmsRequest", [xls], [data_msms]


def _case_ingest(locations):
    csv = _file(locations.project / "PYTHON" / "MSMS" / "RAW DATA" / "a.csv")
    ingested = locations.project / "PYTHON" / "MSMS" / "TO BE FILLED" / "a.csv"
    stages = _stub_stages(IngestMsmsCsvWorkflow())
    stages.extractor.extract_files.return_value = [csv]
    stages.filter_stage.filter_files.return_value = ([csv], [])
    stages.auditor.audit.return_value = IngestMsmsCsvResult(files_ingested=1, ingested_files=(ingested,))
    action = IngestMsmsCsvAction("Ingest")
    with patch("src.workflows.ingest_msms_csv.IngestMsmsCsvWorkflow", return_value=stages):
        _run_project_action_object(action, locations)
    return "IngestMsmsCsvRequest", [csv], [ingested]


def _case_enrich(locations):
    data_msms = _file(locations.project / "PYTHON" / "DATA MSMS.xlsx")
    total_pe = _file(locations.project / "PYTHON" / "TOTAL PE.xlsx")
    stages = _stub_stages(EnrichMsmsWorkflow())
    stages.filter_stage.filter_rows.return_value = ([], 0, 0, [], 0)
    stages.auditor.audit.return_value = EnrichMsmsResult()
    action = EnrichMsmsAction("Enrich")
    with patch("src.workflows.enrich_msms.EnrichMsmsWorkflow", return_value=stages):
        _run_project_action_object(action, locations)
    return "EnrichMsmsRequest", [data_msms, total_pe], [data_msms]


def _case_propagate(locations):
    data_msms = _file(locations.project / "PYTHON" / "DATA MSMS.xlsx")
    total_pe = _file(locations.project / "PYTHON" / "TOTAL PE.xlsx")
    stages = _stub_stages(PropagateWoWorkflow())
    stages.auditor.audit.return_value = PropagateWoResult()
    action = PropagateWoAction("Propagate")
    with patch("src.workflows.propagate_wo.PropagateWoWorkflow", return_value=stages):
        _run_project_action_object(action, locations)
    return "PropagateWoRequest", [data_msms, total_pe], [total_pe]


def _case_populate_data_msms(locations):
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    csv = _file(locations.project / "PYTHON" / "MSMS" / "TO BE FILLED" / "a.csv")
    stages = _stub_stages(PopulateDataMsmsWorkflow())
    stages.extractor.extract.return_value = SimpleNamespace(packages=[_package(testsheet)], csv_files=[csv])
    stages.filter_stage.filter_csv_files.return_value = [csv]
    stages.auditor.audit.return_value = PopulateDataMsmsResult(csv_files_processed=1)
    action = PopulateDataMsmsAction("Populate Data MSMS")
    with (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="auto"),
        patch("src.workflows.populate_data_msms.PopulateDataMsmsWorkflow", return_value=stages),
    ):
        _run_project_action_object(action, locations)
    return "PopulateDataMsmsRequest", [testsheet, csv], [csv]


def _case_whatsapp(locations):
    docx = _file(locations.project / "QUICK" / "1.docx")
    report = locations.project / "WHATSAPP" / "report.docx"
    stages = _stub_stages(WhatsAppReportWorkflow())
    stages.extractor.extract.return_value = SimpleNamespace(substation_docx_files=[docx], resources=None)
    stages.auditor.audit.return_value = WhatsAppReportResult(substations_count=1, output_path=report)
    action = WhatsAppReportAction("WhatsApp")
    resources = SimpleNamespace(quick_report_dir=docx.parent)
    with (
        patch.object(ProjectEnvironment, "get_whatsapp_report_resources", return_value=resources),
        patch("src.project_workflow_actions._select_whatsapp_report_batch", return_value=docx.parent),
        patch("src.workflows.whatsapp.WhatsAppReportWorkflow", return_value=stages),
    ):
        _run_project_action_object(action, locations)
    return "WhatsAppReportRequest", [docx], [report]


_PROJECT_RECORDING_CASES = {
    "populate_total_pe": _case_populate_total_pe,
    "raw_material": _case_raw_material,
    "update_qr02": _case_update_qr02,
    "consolidate": _case_consolidate,
    "ingest": _case_ingest,
    "enrich": _case_enrich,
    "propagate": _case_propagate,
    "populate_data_msms": _case_populate_data_msms,
    "whatsapp": _case_whatsapp,
}


@pytest.mark.parametrize("case", list(_PROJECT_RECORDING_CASES))
def test_project_workflow_records_real_request_inputs_and_outputs(locations, case, capsys) -> None:
    request_type, inputs, outputs = _PROJECT_RECORDING_CASES[case](locations)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed", capsys.readouterr().out
    _assert_recorded(entries, {"__type__": request_type}, inputs, outputs)


def test_pipeline_records_each_target_package_as_inputs(locations, tmp_path) -> None:
    testsheet = _file(tmp_path / "TS" / "1. PE.xlsx")
    report = _file(tmp_path / "QR" / "1. PE.docx")
    package = SubstationPackage(testsheet_xlsx=testsheet, quick_report_docx=report, station_name="PE ONE")
    request = PostProcessingRequest(mode=PostProcessingMode.BY_FL, target_packages=(package,), converter=_FakeConverter())

    def action(environment) -> object:
        module = "src.workflows.postprocessing_pipeline"
        with (
            patch(f"{module}.validate_postprocessing_preflight", side_effect=_StopWorkflow("stop here")),
        ):
            return WorkflowService().run_postprocessing_pipeline(environment, request)

    run_project_action(action, locations.environment)

    inputs = {entry["path"] for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert {str(testsheet), str(report)} <= inputs


def test_recording_does_not_add_prompts_or_change_answers(locations, utility_env, tmp_path) -> None:
    """The entry functions must ask exactly what they asked before."""
    raw = _file(tmp_path / "raw" / "a.jpg")
    prompts: list[str] = []
    answers = iter([str(raw.parent), str(tmp_path / "out"), ""])

    def recording_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    with patch("builtins.input", recording_input):
        run_registered_utility("Rename FLIR raw files numbering")

    assert prompts == [
        "Enter the input folder path: ",
        "Enter the output folder path: ",
        "Enter the starting number [1]: ",
    ]
    assert (tmp_path / "out" / "FLIR0001.jpg").exists()


def test_input_folder_with_nothing_to_list_is_recorded_as_itself(locations, tmp_path) -> None:
    missing = tmp_path / "gone"
    single_file = _file(tmp_path / "one.xlsx")
    empty = tmp_path / "empty"
    empty.mkdir()

    def action(environment) -> None:
        run = current_run()
        run.record_input_folder(missing)
        run.record_input_folder(single_file)
        run.record_input_folder(empty)

    run_project_action(action, locations.environment)

    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert inputs[str(missing)]["exists"] is False
    assert inputs[str(single_file)]["size"] == len(b"content")
    assert inputs[str(empty)]["exists"] is True


def test_same_input_and_output_are_recorded_once(locations, tmp_path) -> None:
    path = _file(tmp_path / "TOTAL PE.xlsx")

    def action(environment) -> None:
        current_run().record_inputs([path, path])
        current_run().record_outputs([path, path, None])

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "input")) == 1
    assert [entry["path"] for entry in entries_of(entries, "output")] == [str(path)]


@pytest.mark.parametrize("field", ["cleaned_pdf_path", "output_directory", "output_folder", "output_pdf_path"])
def test_result_output_fields_are_recorded(locations, tmp_path, field) -> None:
    run_project_action(lambda environment: SimpleNamespace(**{field: tmp_path / "made"}), locations.environment)

    outputs = entries_of(read_entries(locations.project_logs), "output")
    assert [entry["path"] for entry in outputs] == [str(tmp_path / "made")]


def test_output_path_that_cannot_be_worked_out_does_not_stop_update_qr02(locations) -> None:
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    package = _package(testsheet)
    workflow = UpdateQr02CbaWorkflow()
    loader = workflow.loader
    stages = _stub_stages(workflow, loader=loader)
    stages.extractor.extract_packages.return_value = [package]
    stages.extractor.extract_records.return_value = ({}, [])
    stages.filter_stage.filter.return_value = [package]
    stages.transformer.transform.return_value = SimpleNamespace(
        station_plans=[SimpleNamespace(station="NOT A STATION", records=[], packages=[package])]
    )
    stages.auditor.audit.return_value = UpdateQr02CbaResult(records_updated=1)

    def action(environment) -> object:
        with patch.object(loader, "_create_repository"):
            return stages.execute(environment, UpdateQr02CbaRequest())

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    assert not entries_of(entries, "output")


def test_blocked_office_start_is_logged_even_when_the_action_layer_swallows_it(
    locations, _no_real_office, capsys
) -> None:
    """The guard's own proof. The call is blocked, and it's logged for teardown to fail on."""
    # A class name that doesn't exist, so even a broken guard couldn't start Word.
    run_project_action(lambda environment: win32com.client.DispatchEx("Pahang.DoesNotExist"), locations.environment)

    assert "Action failed" in capsys.readouterr().out
    assert _no_real_office == ["DispatchEx('Pahang.DoesNotExist',)"]
    _no_real_office.clear()  # This test expected the attempt. Teardown would fail on it.


@pytest.mark.parametrize(
    "start",
    [
        "win32com.client.Dispatch('Pahang.DoesNotExist')",
        "win32com.client.DispatchEx('Pahang.DoesNotExist')",
        "win32com.client.gencache.EnsureDispatch('Pahang.DoesNotExist')",
        "win32com.client.dynamic.Dispatch('Pahang.DoesNotExist')",
        "pythoncom.CoCreateInstance('Pahang.DoesNotExist')",
        "pythoncom.CoCreateInstanceEx('Pahang.DoesNotExist')",
    ],
)
def test_every_office_start_route_is_blocked(_no_real_office, start) -> None:
    with pytest.raises(AssertionError, match="must not start"):
        eval(start)  # noqa: S307 - fixed strings above

    assert len(_no_real_office) == 1
    _no_real_office.clear()


def test_swallowed_office_start_fails_the_test_at_teardown(tmp_path) -> None:
    """Runs a small test file in its own pytest, through the action layer, and expects it to fail."""
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        "import win32com.client\n"
        "from src.workflow_cli import _run_action\n"
        "from tests.test_run_records import _no_real_office\n"
        "\n"
        "def test_swallowed():\n"
        "    # A class name that doesn't exist, so even a broken guard couldn't start Word.\n"
        "    _run_action('Fake', lambda: win32com.client.DispatchEx('Pahang.DoesNotExist'))\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(sample), "-q", "--no-header", "-p", "no:cacheprovider", "--rootdir", str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode != 0, completed.stdout
    assert "A test tried to start real Word or Excel" in completed.stdout
    assert "1 passed" in completed.stdout
    assert "1 error" in completed.stdout


def test_quick_report_unknown_fl_says_failed_so_the_run_is_failed(locations, capsys) -> None:
    """The workflow's error text also appears in the inspection's warnings, as it does for real."""
    message = "No testsheet packages found for target: ['FL1']"
    inspection = QuickReportInspection(targets=(), missing_templates=(), warnings=(message,), errors=())
    action = QuickReportAction("Generate Quick Report")

    with (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="manual"),
        patch("builtins.input", return_value="FL1"),
        patch.object(QuickReportWorkflow, "_plan", return_value=(inspection, [])),
    ):
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert [entry["message"] for entry in entries_of(entries, "error")] == [message]
    console = capsys.readouterr().out
    assert f"[FAILED] {message}" in console
    assert f"Run Record: {next(locations.project_logs.glob('*.jsonl'))}" in console


def test_full_report_generate_finding_nothing_is_a_failed_run(locations, capsys) -> None:
    message = "No testsheet packages found for target: ['FL1']"

    def action(environment) -> object:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(FullReportWorkflow, "_discover_packages", return_value=([], [message], [])),
        ):
            return FullReportWorkflow().generate(["FL1"], environment)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert [entry["message"] for entry in entries_of(entries, "error")] == [message]
    assert f"Run Record: {next(locations.project_logs.glob('*.jsonl'))}" in capsys.readouterr().out


def test_error_and_warning_with_the_same_text_both_count(locations) -> None:
    result = QuickReportResult(reports_generated=1, warnings=("same text",), errors=("same text",))

    run_project_action(lambda environment: result, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed_with_errors"
    assert [entry["message"] for entry in entries_of(entries, "error")] == ["same text"]


def test_request_recorded_again_with_the_same_values_adds_nothing(locations) -> None:
    def action(environment) -> None:
        current_run().record_request({"workflow": "Quick Report", "target": ["FL1"]})
        current_run().record_request({"workflow": "Quick Report", "target": ["FL1"], "station": None})

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "request")) == 1
    assert not entries_of(entries, "request_update")


def test_later_details_of_a_request_are_recorded_as_an_update(locations) -> None:
    def action(environment) -> None:
        current_run().record_request({"workflow": "Full Report", "target": ["FL1"]})
        current_run().record_request({"workflow": "Full Report", "target": ["FL1"], "station": ["PE ONE"]})
        current_run().record_request({"workflow": "Full Report", "target": ["FL1"], "station": ["PE ONE"]})

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "request")) == 1
    updates = entries_of(entries, "request_update")
    assert [(update["workflow"], update["changes"]) for update in updates] == [("Full Report", {"station": ["PE ONE"]})]


def test_selected_target_then_generate_gives_one_request_and_one_update(locations) -> None:
    """The whole Quick Report action: selection recorded first, then the chosen stations."""
    target_item = SimpleNamespace(station="KUANTAN")
    other_item = SimpleNamespace(station="TEMERLOH")
    inspection = QuickReportInspection(targets=(target_item, other_item), missing_templates=(), warnings=(), errors=())
    empty = QuickReportInspection(targets=(), missing_templates=(), warnings=(), errors=())
    action = QuickReportAction("Generate Quick Report")
    prompts = _quick_report_prompts()
    with (
        prompts[0], prompts[1],
        patch("src.project_workflow_actions.cli_selectors.select_multiple", return_value=["KUANTAN"]),
        patch.object(QuickReportWorkflow, "inspect", return_value=inspection),
        patch.object(QuickReportWorkflow, "_plan", return_value=(empty, [])),
    ):
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "request")) == 1
    assert entries_of(entries, "request_update")[0]["changes"] == {"station": ["KUANTAN"]}


def _quick_report_workflow_with_loads(load_results: list[object]) -> QuickReportWorkflow:
    """Word can't start here: the compiler has no session and the composer is a stub."""
    workflow = QuickReportWorkflow()
    workflow._compiler = MagicMock(spec=[])
    workflow._composer = MagicMock()
    workflow._composer.load.side_effect = load_results
    return workflow


def _run_quick_report_plans(locations, load_results: list[object]) -> None:
    plans = [
        SimpleNamespace(package=SimpleNamespace(testsheet_path=locations.project / f"{index}.xlsx", date_str=""))
        for index in range(len(load_results))
    ]
    inspection = QuickReportInspection(targets=(), missing_templates=(), warnings=(), errors=())
    workflow = _quick_report_workflow_with_loads(load_results)

    def action(environment) -> object:
        with (
            patch.object(QuickReportWorkflow, "_plan", return_value=(inspection, plans)),
            patch.object(QuickReportWorkflow, "_resolve_substation_display_name", return_value="PE"),
        ):
            return workflow.generate(["FL1"], environment)

    run_project_action(action, locations.environment)


def test_quick_report_with_every_substation_failed_is_failed(locations) -> None:
    _run_quick_report_plans(locations, [RuntimeError("one"), RuntimeError("two")])

    assert read_entries(locations.project_logs)[-1]["status"] == "failed"


def test_quick_report_with_some_substations_failed_has_errors(locations, tmp_path) -> None:
    report = _file(tmp_path / "report.docx")

    _run_quick_report_plans(locations, [report, RuntimeError("two")])

    assert read_entries(locations.project_logs)[-1]["status"] == "completed_with_errors"


def _run_full_report_batch(locations, outcomes: list[bool]) -> None:
    """Word can't start here: fake compiler, a stub session, and the substation step is stubbed."""
    packages = [_package(locations.project / f"{index}.xlsx") for index in range(len(outcomes))]
    workflow = FullReportWorkflow(compiler=FakeDocumentCompiler())

    def execute(pkg_idx, pkg, word_app, ctx) -> None:
        ok = outcomes[pkg_idx]
        ctx.ordered_results[pkg_idx] = SimpleNamespace(is_success=ok, deliverable_paths=())
        if not ok:
            ctx.errors.append(f"Failed {pkg_idx}")

    def action(environment) -> object:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(FullReportWorkflow, "_discover_packages", return_value=(packages, [], [])),
            patch.object(FullReportWorkflow, "_execute_substation", side_effect=execute),
        ):
            return workflow.generate(["FL1"], environment, com_session=MagicMock())

    run_project_action(action, locations.environment)


@pytest.mark.parametrize("outcomes, status", [([False, False], "failed"), ([True, False], "completed_with_errors")])
def test_full_report_batch_status(locations, outcomes, status) -> None:
    _run_full_report_batch(locations, outcomes)

    assert read_entries(locations.project_logs)[-1]["status"] == status


@pytest.mark.parametrize("succeeded, status", [(0, "failed"), (1, "completed_with_errors")])
def test_postprocessing_batch_status(locations, succeeded, status) -> None:
    target = SimpleNamespace(
        is_ready=True,
        is_multipart=False,
        validation_result=None,
        errors=(),
        stem="PE",
        date_str="",
        docx_path=locations.project / "PE.docx",
        part_docx_paths=(),
    )
    workflow = MagicMock()
    workflow.inspect.return_value = FullReportPostProcessingInspection(targets=(target,), warnings=(), errors=())
    workflow.locate_full_reports_for_fls.return_value = ([target.docx_path], [])
    workflow.process.return_value = FullReportPostProcessingResult(
        total_reports=1 + succeeded, succeeded_count=succeeded, failed_count=1, errors=("PE failed",)
    )
    action = FullReportPostProcessingAction("Post-Process Full Reports", workflow=workflow)

    with (
        patch("src.project_workflow_actions._prompt_full_report_selection", return_value=["FL1"]),
        patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", return_value=[target]),
        patch("src.project_workflow_actions.cli_selectors.confirm", return_value=True),
    ):
        _run_project_action_object(action, locations)

    assert read_entries(locations.project_logs)[-1]["status"] == status


def test_pipeline_result_with_some_failed_records_no_repr_of_the_failure(locations, tmp_path) -> None:
    package = SubstationPackage(testsheet_xlsx=tmp_path / "1.xlsx", quick_report_docx=tmp_path / "1.docx")
    summary = PostProcessingSummary(
        processed_packages=(package,),
        failed_packages=(PostProcessingFailure(package=package, error="broke"),),
    )

    run_project_action(lambda environment: summary, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed_with_errors"
    assert not [e for e in entries_of(entries, "error") if "PostProcessingFailure" in e["message"]]


def test_us_tev_with_one_no_data_skip_and_one_failure_has_errors(locations, utility_env, tmp_path) -> None:
    def graphs_or_failure(self, survey_root, output_dir=None):
        if Path(survey_root).name == "PE2":
            raise RuntimeError("survey unreadable")
        return SubstationGraphResult(skipped_no_data=["no data here"])

    prompts = _tev_prompts([_tev_candidate(tmp_path, "PE1"), _tev_candidate(tmp_path, "PE2")])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "run_substation", graphs_or_failure),
    ):
        run_registered_utility("Generate US+TEV survey graphs")

    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "completed_with_errors"
    assert not entries_of(entries, "output")


def test_us_tev_with_every_substation_failed_is_failed(locations, utility_env, tmp_path) -> None:
    prompts = _tev_prompts([_tev_candidate(tmp_path, "PE1"), _tev_candidate(tmp_path, "PE2")])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "run_substation", side_effect=RuntimeError("survey unreadable")),
    ):
        run_registered_utility("Generate US+TEV survey graphs")

    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "failed"
    assert not entries_of(entries, "output")


def test_us_tev_lists_output_folders_only_for_substations_that_produced_graphs(
    locations, utility_env, tmp_path
) -> None:
    def graphs_or_failure(self, survey_root, output_dir=None):
        if Path(survey_root).name == "PE2":
            raise RuntimeError("survey unreadable")
        return SubstationGraphResult(generated=[tmp_path / "graph.png"])

    first, second = _tev_candidate(tmp_path, "PE1"), _tev_candidate(tmp_path, "PE2")
    prompts = _tev_prompts([first, second])
    with (
        prompts[0], prompts[1], prompts[2], prompts[3], prompts[4],
        patch.object(UsTevGraphWorkflow, "run_substation", graphs_or_failure),
    ):
        run_registered_utility("Generate US+TEV survey graphs")

    outputs = [entry["path"] for entry in entries_of(read_entries(locations.fallback_logs), "output")]
    assert outputs == [str(first.output_dir.resolve())]


def test_us_audio_with_some_substations_failed_has_errors(locations) -> None:
    candidates = [UsAudioCandidate(raw_data_dir=locations.project), UsAudioCandidate(raw_data_dir=locations.project)]

    def action(environment) -> object:
        with patch.object(UsAudioWorkflow, "run_substation", side_effect=[(0, 0), RuntimeError("wav export broke")]):
            return UsAudioWorkflow().run_batch(candidates)

    run_project_action(action, locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == "completed_with_errors"


def _testsheet_stages(result: GenerateTestsheetFolderResult) -> object:
    stages = _stub_stages(GenerateTestsheetFolderStructureWorkflow())
    stages.filter_stage.filter_dates.return_value = (("07-11-2026",), ())
    stages.loader.load.return_value = ((), ())
    stages.auditor.audit.return_value = result
    return stages


@pytest.mark.parametrize(
    "created, status",
    [((), "failed"), ((Path("made"),), "completed_with_errors")],
)
def test_testsheet_folder_status(locations, created, status) -> None:
    result = GenerateTestsheetFolderResult(
        station="KUANTAN", month="NOV", created_directories=created, total_dates_processed=1, errors=("missing dir",)
    )
    request = GenerateTestsheetFolderRequest(station="KUANTAN", month="NOV", target_dates=("07-11-2026",))
    stages = _testsheet_stages(result)

    run_project_action(lambda environment: stages.execute(environment, request), locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == status


def _run_raw_material_with_reads(locations, read_results: list[object], copied=(0, 0, 0)) -> None:
    """Testsheet reads are real calls on a stubbed reader. Raw material doesn't use Word or Excel."""
    packages = [_package(_file(locations.project / "TESTSHEET" / f"{i}.xlsx")) for i in range(len(read_results))]
    stages = RawMaterialWorkflow()
    extractor = stages.extractor
    extractor.extractor = MagicMock()
    extractor.extractor.extract_testsheet_data.side_effect = read_results
    stages = _stub_stages(stages, extractor=extractor)
    stages.auditor.audit.return_value = (None, RawMaterialResult(substations_count=len(packages)))
    request = RawMaterialRequest(output_path=locations.project / "RAW MATERIAL")

    def process(environment, request, package, warnings, camera_config=None):
        extractor._load_testsheet_data(package, warnings)
        return copied

    def action(environment) -> object:
        with (
            patch.object(extractor, "discover_packages", return_value=packages),
            patch.object(extractor, "load_pe_alignment_data", return_value=set()),
            patch.object(stages, "_process_package", side_effect=process),
        ):
            return stages.execute(environment, request)

    run_project_action(action, locations.environment)


def test_raw_material_with_every_testsheet_unreadable_is_failed(locations, capsys) -> None:
    _run_raw_material_with_reads(locations, [RuntimeError("bad sheet one"), RuntimeError("bad sheet two")])

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert entries_of(entries, "error")
    assert "bad sheet one" in entries_of(entries, "warning")[0]["traceback"]
    assert f"Run Record: {next(locations.project_logs.glob('*.jsonl'))}" in capsys.readouterr().out


def test_raw_material_with_every_testsheet_unreadable_but_photos_copied_has_errors(locations, capsys) -> None:
    _run_raw_material_with_reads(locations, [RuntimeError("bad sheet one")], copied=(4, 0, 0))

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed_with_errors"
    assert "1 testsheet(s)" in entries_of(entries, "error")[0]["message"]
    assert "bad sheet one" in entries_of(entries, "warning")[0]["traceback"]
    assert f"Run Record: {next(locations.project_logs.glob('*.jsonl'))}" in capsys.readouterr().out


def test_raw_material_status_does_not_depend_on_warning_text(locations) -> None:
    """A warning that merely reads like an unreadable testsheet isn't one."""
    testsheet = _file(locations.project / "TESTSHEET" / "1.xlsx")
    stages = _stub_stages(RawMaterialWorkflow())
    stages.extractor = RawMaterialWorkflow().extractor
    request = RawMaterialRequest(output_path=locations.project / "RAW MATERIAL")
    stages.auditor.audit.return_value = (None, RawMaterialResult(substations_count=1))

    def process(environment, request, package, warnings, camera_config=None):
        warnings.append("Failed to extract testsheet data from a photo caption")
        return 0, 0, 0

    def action(environment) -> object:
        with (
            patch.object(stages.extractor, "discover_packages", return_value=[_package(testsheet)]),
            patch.object(stages.extractor, "load_pe_alignment_data", return_value=set()),
            patch.object(stages, "_process_package", side_effect=process),
        ):
            return stages.execute(environment, request)

    run_project_action(action, locations.environment)

    assert read_entries(locations.project_logs)[-1]["status"] == "completed"


def test_raw_material_with_some_testsheets_unreadable_keeps_them_as_warnings(locations, capsys) -> None:
    _run_raw_material_with_reads(locations, [RuntimeError("bad sheet one"), MagicMock()])

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    assert not entries_of(entries, "error")
    assert "bad sheet one" in entries_of(entries, "warning")[0]["traceback"]
    assert "Run Record:" not in capsys.readouterr().out


def _consolidate_stages(result):
    stages = _stub_stages(ConsolidateMsmsWorkflow())
    stages.filter_stage.filter_rows.return_value = ([], 0)
    stages.auditor.audit.return_value = result
    return stages


@pytest.mark.parametrize(
    "build, request_object, nothing, something",
    [
        (
            _consolidate_stages,
            ConsolidateMsmsRequest(),
            ConsolidateMsmsResult(files_processed=0, errors=("bad",)),
            ConsolidateMsmsResult(files_processed=1, errors=("bad",)),
        ),
    ],
    ids=["consolidate"],
)
@pytest.mark.parametrize("outcome", ["nothing", "something"])
def test_msms_workflow_status_says_whether_anything_succeeded(
    locations, build, request_object, nothing, something, outcome
) -> None:
    stages = build(nothing if outcome == "nothing" else something)

    run_project_action(lambda environment: stages.execute(environment, request_object), locations.environment)

    expected = "failed" if outcome == "nothing" else "completed_with_errors"
    assert read_entries(locations.project_logs)[-1]["status"] == expected


def _run_update_qr02_with_reads(locations, read_results: list[object]) -> None:
    """Testsheet reads are real calls on a stubbed reader, and the loader that uses Excel is a stub."""
    packages = [_package(locations.project / f"{i}.xlsx") for i in range(len(read_results))]
    workflow = UpdateQr02CbaWorkflow()
    extractor = workflow.extractor
    extractor.data_extractor = MagicMock()
    extractor.data_extractor.extract_testsheet_data.side_effect = read_results
    stages = _stub_stages(workflow, extractor=extractor)
    stages.filter_stage.filter.return_value = packages
    stages.auditor.audit.return_value = UpdateQr02CbaResult(records_updated=0)
    action = UpdateQr02CbaAction("Update QR02")

    with (
        patch("src.project_workflow_actions.cli_selectors.select_one", return_value="auto"),
        patch("src.workflows.update_qr02_cba.UpdateQr02CbaWorkflow", return_value=stages),
        patch.object(extractor, "extract_packages", return_value=packages),
    ):
        _run_project_action_object(action, locations)


def test_update_qr02_with_every_testsheet_unreadable_is_failed(locations, capsys) -> None:
    _run_update_qr02_with_reads(locations, [RuntimeError("bad sheet one"), RuntimeError("bad sheet two")])

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "failed"
    assert entries_of(entries, "error")
    assert "bad sheet one" in entries_of(entries, "warning")[0]["traceback"]
    console = capsys.readouterr().out
    assert "Records updated: 0" in console
    assert f"Run Record: {next(locations.project_logs.glob('*.jsonl'))}" in console


def test_update_qr02_with_some_testsheets_unreadable_keeps_them_as_warnings(locations, capsys) -> None:
    _run_update_qr02_with_reads(locations, [RuntimeError("bad sheet one"), MagicMock()])

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    assert not entries_of(entries, "error")
    assert "bad sheet one" in entries_of(entries, "warning")[0]["traceback"]
    assert "Run Record:" not in capsys.readouterr().out


def test_warning_returned_in_the_result_after_being_recorded_appears_once(locations) -> None:
    def action(environment) -> QuickReportResult:
        current_run().record_warning("photo missing", ValueError("detail"))
        return QuickReportResult(reports_generated=1, warnings=("photo missing",))

    run_project_action(action, locations.environment)

    warnings = entries_of(read_entries(locations.project_logs), "warning")
    assert len(warnings) == 1
    assert "detail" in warnings[0]["traceback"]


def _catalog_with_a_broken_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A registered project whose base path is a file, so its folders can't be created."""
    blocker = tmp_path / "base_path_is_a_file"
    blocker.write_text("x", encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"projects": {"broken": {"name": "Broken", "base_path": str(blocker)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("config._CONFIG_FILE", catalog)


def _prompts_choosing_the_broken_project():
    return (
        patch("src.project.management.prompt_for_project_key", side_effect=["broken", None]),
        patch("src.project.management.first_run_setup", return_value=True),
    )


def _assert_activation_failure_saved(locations, session, capsys) -> None:
    entries = read_entries(locations.fallback_logs)
    assert entries[-1]["status"] == "failed"
    assert entries_of(entries, "error")[0]["traceback"]
    assert entries[0]["project_key"] is None
    console = capsys.readouterr().out
    assert "Project activation failed:" in console
    assert f"Run Record: {next(locations.fallback_logs.glob('*.jsonl'))}" in console
    assert session.active_project is None


def test_project_activation_failure_is_saved_in_the_fallback_folder(locations, tmp_path, monkeypatch, capsys) -> None:
    _catalog_with_a_broken_project(tmp_path, monkeypatch)
    session = CliSession(persistence_file=tmp_path / ".active_project.json")
    prompts = _prompts_choosing_the_broken_project()

    with prompts[0], prompts[1]:
        assert _select_project(session) is None

    _assert_activation_failure_saved(locations, session, capsys)


@pytest.mark.parametrize("handler", [handle_switch_project, handle_view_project_info])
def test_project_settings_activation_failures_are_not_recorded(locations, tmp_path, monkeypatch, capsys, handler) -> None:
    _catalog_with_a_broken_project(tmp_path, monkeypatch)
    session = CliSession(persistence_file=tmp_path / ".active_project.json")
    prompts = _prompts_choosing_the_broken_project()

    with prompts[0], prompts[1]:
        handler(session)

    assert not locations.fallback_logs.exists()
    assert not locations.project_logs.exists()
    assert "Project activation failed:" in capsys.readouterr().out
    assert session.active_project is None


def test_activating_a_project_normally_saves_nothing(locations, tmp_path, capsys) -> None:
    session = CliSession(persistence_file=tmp_path / ".active_project.json")

    with (
        patch("src.project.management.prompt_for_project_key", return_value="good"),
        patch("src.project.management.first_run_setup", return_value=True),
        patch("src.project.management.create_project_environment", return_value=locations.environment),
    ):
        assert _select_project(session) is locations.environment

    assert not locations.fallback_logs.exists()
    assert "Run Record:" not in capsys.readouterr().out


def test_one_bad_substation_gives_one_error_when_inspect_and_generate_both_plan(locations) -> None:
    package = SimpleNamespace(data=object(), substation_name="PE ONE", testsheet_path=locations.project / "a.xlsx")
    workflow = QuickReportWorkflow()

    def action(environment) -> object:
        with (
            patch.object(workflow, "_extractor") as extractor,
            patch.object(QuickReportWorkflow, "_resolve_substation_display_name", return_value="PE ONE"),
            patch.object(QuickReportWorkflow, "_resolve_target", return_value=(["07-11-2026"], [])),
            patch.object(QuickReportWorkflow, "_validate_templates", return_value=()),
        ):
            extractor.extract.return_value = [package]
            extractor.extract_defects.side_effect = RuntimeError("defect sheet broke")
            workflow.inspect(Path("07-11-2026"), environment)
            return workflow.generate(Path("07-11-2026"), environment)

    with patch.object(QuickReportWorkflow, "_target_path_exists", return_value=True):
        run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    errors = entries_of(entries, "error")
    assert len(errors) == 1, errors
    assert "defect sheet broke" in errors[0]["traceback"]
    assert entries[-1]["status"] == "failed"


def test_two_substations_failing_with_identical_text_both_keep_an_entry(locations) -> None:
    """Different substations can share a display name, so their messages can be identical."""
    _run_quick_report_plans(locations, [RuntimeError("same failure"), RuntimeError("same failure")])

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert len(errors) == 2, errors
    assert errors[0]["message"] == errors[1]["message"]
    assert all("same failure" in error["traceback"] for error in errors)


def test_pipeline_with_two_identical_failures_keeps_both_with_tracebacks(locations, tmp_path) -> None:
    (tmp_path / "TS").mkdir()
    packages = tuple(
        SubstationPackage(
            testsheet_xlsx=tmp_path / "TS" / f"{index}. PE.xlsx",
            quick_report_docx=tmp_path / "QR" / f"{index}. PE.docx",
            station_name="SAME NAME",
        )
        for index in (1, 2)
    )
    request = PostProcessingRequest(
        mode=PostProcessingMode.BY_FL,
        target_packages=packages,
        apply_signatures=True,
        vendor_signature_path=tmp_path / "sign.png",
        converter=_FakeConverter(),
    )

    def action(environment) -> object:
        module = "src.workflows.postprocessing_pipeline"
        with (
            patch(f"{module}.validate_postprocessing_preflight"),
            patch(f"{module}.discover_substation_packages", return_value=list(packages)),
            patch(f"{module}.replace_pce_images", side_effect=[RuntimeError("stamp broke"), RuntimeError("stamp broke")]),
        ):
            return PostProcessingPipelineWorkflow().execute(environment, request)

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert len(errors) == 2, errors
    assert all("stamp broke" in error["traceback"] for error in errors)


def test_identical_errors_only_in_the_result_both_keep_an_entry(locations) -> None:
    result = QuickReportResult(reports_generated=1, errors=("same text", "same text"))

    run_project_action(lambda environment: result, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert [error["message"] for error in errors] == ["same text", "same text"]


def test_result_repeating_one_of_two_recorded_errors_adds_only_the_extra(locations) -> None:
    def action(environment) -> QuickReportResult:
        current_run().record_error("same text", ValueError("one"))
        return QuickReportResult(reports_generated=1, errors=("same text", "same text"))

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert [("traceback" in error) for error in errors] == [True, False]


def test_same_exception_object_recorded_twice_gives_one_entry(locations) -> None:
    def action(environment) -> None:
        failure = ValueError("detail")
        current_run().record_error("first site", failure)
        raise failure

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert [error["message"] for error in errors] == ["first site"]
    assert read_entries(locations.project_logs)[-1]["status"] == "failed"


def test_full_report_inspect_then_generate_discovery_failure_gives_one_entry(locations) -> None:
    workflow = FullReportWorkflow()

    def action(environment) -> object:
        with (
            patch.object(FullReportWorkflow, "_validate_target_existence"),
            patch.object(workflow, "_extractor") as extractor,
        ):
            extractor.extract.side_effect = RuntimeError("testsheet scan broke")
            workflow.inspect(["FL1"], environment)
            return workflow.generate(["FL1"], environment)

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert len(errors) == 1, errors


def test_time_spent_waiting_on_a_prompt_is_in_no_step(locations) -> None:
    """A fake prompt sleeps, then a real action calls the service, whose workflow is stubbed."""
    wait_seconds = 0.5

    def slow_prompt(*args, **kwargs) -> str:
        time.sleep(wait_seconds)
        return "KUANTAN"

    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")
    result = GenerateTestsheetFolderResult(station="KUANTAN", month="NOV")
    module = "src.project_workflow_actions.cli_selectors"
    with (
        patch(f"{module}.select_or_create_testsheet_station", side_effect=slow_prompt),
        patch(f"{module}.select_or_create_testsheet_month", return_value="NOV"),
        patch(f"{module}.prompt_target_inspection_dates", return_value=("07-11-2026",)),
        patch("src.workflows.generate_testsheet_folder.GenerateTestsheetFolderStructureWorkflow") as workflow,
    ):
        workflow.return_value.execute.return_value = result
        _run_project_action_object(action, locations)

    entries = read_entries(locations.project_logs)
    finished = entries_of(entries, "step_finish")
    assert [entry["name"] for entry in finished] == ["Workflow: generate_testsheet_folder"]
    assert finished[0]["duration_seconds"] < wait_seconds
    assert entries[-1]["duration_seconds"] >= wait_seconds


def test_action_with_no_steps_of_its_own_records_none(locations) -> None:
    run_project_action(lambda environment: time.sleep(0.01), locations.environment)

    assert not entries_of(read_entries(locations.project_logs), "step_start")


def test_service_workflow_failure_marks_its_step_failed(locations) -> None:
    def action(environment) -> None:
        with patch("src.workflows.propagate_wo.PropagateWoWorkflow") as workflow:
            workflow.return_value.execute.side_effect = RuntimeError("workbook locked")
            WorkflowService().run_propagate_wo(environment)

    run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    finished = entries_of(entries, "step_finish")
    assert [(entry["name"], entry["status"]) for entry in finished] == [("Workflow: propagate_wo", "failed")]
    assert entries[-1]["status"] == "failed"


def test_nested_survey_files_have_individual_metadata(locations, tmp_path) -> None:
    survey = tmp_path / "survey"
    metadata = _file(survey / "survey_metadata.js")
    reading = _file(survey / "SWG1" / "reading" / "eventData.js")
    _file(survey / "~$locked.js")
    run_project_action(
        lambda environment: current_run().record_input_folder(survey, recursive=True),
        locations.environment,
    )
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert set(inputs) == {str(metadata), str(reading)}
    assert inputs[str(reading)]["size"] == 7
    assert inputs[str(reading)]["modified"]


def test_full_report_records_quick_report_before_validation(locations, tmp_path) -> None:
    testsheet = _file(tmp_path / "1. PE.xlsx")
    report = _file(tmp_path / "1. PE.docx")
    package = _package(testsheet)
    workflow = FullReportWorkflow()

    def action(environment):
        with (
            patch.object(workflow, "_validate_target_existence"),
            patch.object(workflow, "_discover_packages", return_value=([package], [], [])),
            patch.object(workflow, "_resolve_quick_report_path", return_value=report),
            patch("src.workflows.full_report.validate_finalized_quick_report", side_effect=ValueError("invalid report")),
        ):
            workflow.generate(["FL1"], environment, com_session=MagicMock())

    run_project_action(action, locations.environment)
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert inputs[str(report)]["size"] == 7
    assert inputs[str(report)]["modified"]


def test_raw_material_records_selected_photos_and_archives(locations, tmp_path) -> None:
    testsheet = _file(tmp_path / "1. PE.xlsx")
    ir = _file(tmp_path / "IR" / "FLIR0001.jpg")
    dg = _file(tmp_path / "DG" / "IMG0001.jpg")
    archive = _file(tmp_path / "US" / "1.zip")
    package = _package(testsheet)
    workflow = _stub_stages(RawMaterialWorkflow())
    workflow.extractor.discover_packages.return_value = [package]
    workflow.extractor.extract_package_data.return_value = SimpleNamespace(
        testsheet_data=None, ir_photos=[ir], dg_photos=[dg], us_tev_archives=[archive], substation_folder_name="001"
    )
    workflow.filter_stage.filter_ir_photos.return_value = [(ir, 1)]
    workflow.filter_stage.filter_dg_photos.return_value = [(dg, 1)]
    workflow.filter_stage.filter_us_tev_archives.return_value = [archive]
    workflow.loader.execute_plan.return_value = (1, 1, 1)
    workflow.auditor.audit.return_value = (None, RawMaterialResult(substations_count=1))
    request = RawMaterialRequest(output_path=tmp_path / "out")
    run_project_action(lambda environment: workflow.execute(environment, request), locations.environment)
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert {str(ir), str(dg), str(archive)} <= inputs.keys()
    assert all(inputs[str(path)]["size"] == 7 for path in (ir, dg, archive))


def test_postprocessing_records_testsheet_pdf_before_validation(locations, tmp_path) -> None:
    docx = _file(tmp_path / "KUANTAN" / "11. NOVEMBER" / "07-11-2026" / "1. PE.docx")
    pdf = _file(tmp_path / "processed_testsheet" / "pdf" / "1. PE.pdf")
    workflow = FullReportPostProcessingWorkflow()

    def action(environment):
        with (
            patch.object(workflow, "_discover_docx_files", return_value=([docx], [], [])),
            patch("src.workflows.full_report_postprocessing.resolve_processed_testsheet_pdf_path", return_value=pdf),
            patch("src.workflows.full_report_postprocessing.validate_processed_testsheet_pdf", side_effect=_StopWorkflow),
        ):
            workflow.process(str(docx), environment)

    run_project_action(action, locations.environment)
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert inputs[str(pdf)]["size"] == 7
    assert inputs[str(pdf)]["modified"]


def test_shared_project_resources_have_input_metadata(locations, tmp_path) -> None:
    template = _file(tmp_path / "templates" / "whatsapp.docx")
    master = _file(tmp_path / "ENGR" / "QR03 CBA.xlsx")
    photo = _file(tmp_path / "RAW DATA" / "IR" / "FLIR0001.jpg")
    environment = locations.environment

    def action(env):
        with (
            patch.object(env.storage, "get_template", return_value=template),
            patch.object(env.storage, "get_engr_folder", return_value=master.parent),
            patch.object(env.storage, "get_substation_raw_data_dir", return_value=photo.parent.parent),
        ):
            assert env.get_template("whatsapp_template") == template
            assert env.get_engr_folder() == master.parent
            assert env.get_substation_raw_data_dir("KUANTAN", "11. NOVEMBER", "07-11-2026", 1) == photo.parent.parent

    run_project_action(action, environment)
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert {str(template), str(master), str(photo)} <= inputs.keys()
    assert all(inputs[str(path)]["size"] == 7 for path in (template, master, photo))


def test_quick_report_records_explicit_condition_template(locations, tmp_path) -> None:
    template = _file(tmp_path / "condition.docx")
    workflow = QuickReportWorkflow()

    def action(environment):
        with (
            patch.object(workflow, "_validate_templates", return_value=()),
            patch.object(workflow._extractor, "extract", return_value=[]),
        ):
            workflow.generate(["FL1"], environment, condition_template=template)

    run_project_action(action, locations.environment)
    inputs = {entry["path"]: entry for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert inputs[str(template)]["size"] == 7
    assert inputs[str(template)]["modified"]


def _environment_with_engr_folder(locations, count: int) -> Path:
    folder = locations.project / "ENGR"
    folder.mkdir()
    for index in range(count):
        (folder / f"book{index}.xlsx").write_bytes(b"x")
    return folder


def test_same_folder_is_walked_and_recorded_once_in_a_run(locations) -> None:
    folder = _environment_with_engr_folder(locations, 3)

    def action(environment) -> None:
        for _ in range(5):
            environment.get_engr_folder()

    with (
        patch.object(LocalWorkspaceStorage, "get_engr_folder", return_value=folder),
        patch("src.run_records.os.walk", wraps=os.walk) as walk,
    ):
        run_project_action(action, locations.environment)

    assert walk.call_count == 1
    inputs = entries_of(read_entries(locations.project_logs), "input")
    assert sorted(entry["path"] for entry in inputs) == sorted(str(p) for p in folder.iterdir())


def test_getters_do_not_walk_when_no_run_is_open(locations) -> None:
    folder = _environment_with_engr_folder(locations, 3)

    with (
        patch.object(LocalWorkspaceStorage, "get_engr_folder", return_value=folder),
        patch("src.run_records.os.walk", wraps=os.walk) as walk,
    ):
        assert locations.environment.get_engr_folder() == folder

    assert walk.call_count == 0


def test_huge_folder_is_capped_with_a_note_of_what_was_left_out(locations, monkeypatch) -> None:
    folder = _environment_with_engr_folder(locations, 5)
    monkeypatch.setattr("src.run_records._MAX_INPUTS_PER_FOLDER", 3)

    run_project_action(lambda environment: current_run().record_input_folder(folder), locations.environment)

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "input")) == 3
    note = entries_of(entries, "input_truncated")[0]
    assert (note["folder"], note["recorded"], note["left_out"]) == (str(folder), 3, 2)


def test_recursive_folder_is_capped_too(locations, monkeypatch) -> None:
    for index in range(4):
        _file(locations.project / "survey" / f"m{index}" / "data.dat")
    monkeypatch.setattr("src.run_records._MAX_INPUTS_PER_FOLDER", 3)

    run_project_action(
        lambda environment: current_run().record_input_folder(locations.project / "survey", recursive=True),
        locations.environment,
    )

    entries = read_entries(locations.project_logs)
    assert len(entries_of(entries, "input")) == 3
    assert entries_of(entries, "input_truncated")[0]["left_out"] == 1


def test_folder_at_the_limit_has_no_truncation_note(locations, monkeypatch) -> None:
    folder = _environment_with_engr_folder(locations, 3)
    monkeypatch.setattr("src.run_records._MAX_INPUTS_PER_FOLDER", 3)

    run_project_action(lambda environment: current_run().record_input_folder(folder), locations.environment)

    assert not entries_of(read_entries(locations.project_logs), "input_truncated")


def test_folder_walk_failure_does_not_stop_the_action(locations) -> None:
    folder = _environment_with_engr_folder(locations, 1)
    calls: list[str] = []

    def action(environment) -> None:
        current_run().record_input_folder(folder)
        calls.append("ran")

    with patch("src.run_records.os.walk", side_effect=OSError("network gone")):
        run_project_action(action, locations.environment)

    assert calls == ["ran"]
    assert entries_of(read_entries(locations.project_logs), "input")[0]["path"] == str(folder)


def test_recording_a_folder_never_opens_its_files(locations) -> None:
    folder = _environment_with_engr_folder(locations, 3)
    opened: list[str] = []
    real_open = open

    def watching_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def action(environment) -> None:
        with patch("builtins.open", watching_open):
            current_run().record_input_folder(folder)

    run_project_action(action, locations.environment)

    assert not [path for path in opened if str(folder) in path]
    assert len(entries_of(read_entries(locations.project_logs), "input")) == 3


def _raw_data_folder(locations) -> tuple[Path, Path]:
    measurement = _file(locations.project / "RAW MATERIAL" / "PE1" / "US" / "survey" / "reading.dat")
    return locations.project / "RAW MATERIAL" / "PE1", measurement


@pytest.mark.parametrize("has_raw_data", [True, False])
def test_quick_report_plan_records_raw_data_files(locations, has_raw_data) -> None:
    raw_dir, measurement = _raw_data_folder(locations)
    package = SimpleNamespace(data=MagicMock(), station="KUANTAN", month="NOV", date_str="07-11-2026", substation_number=1)

    def action(environment) -> None:
        # Nothing after the raw-data lookup matters here, so stop straight after it.
        with patch("src.quick_report.transformer.ContractScope.from_source", side_effect=_StopWorkflow("stop")):
            QuickReportTransformer().transform(package, [], [], environment)

    with patch.object(
        LocalWorkspaceStorage, "get_substation_raw_data_dir", return_value=raw_dir if has_raw_data else None
    ):
        run_project_action(action, locations.environment)

    paths = {entry["path"] for entry in entries_of(read_entries(locations.project_logs), "input")}
    assert (str(measurement) in paths) is has_raw_data


@pytest.mark.parametrize("has_raw_data", [True, False])
def test_full_report_postprocessing_sound_hook_records_raw_data_files(locations, tmp_path, has_raw_data) -> None:
    raw_dir, measurement = _raw_data_folder(locations)
    docx = _file(tmp_path / "FULL" / "KUANTAN" / "NOV" / "07-11-2026" / "1. PE.docx")
    out_pdf = _file(docx.with_suffix(".pdf"))
    group = PostProcessingTargetGroup(stem="1. PE", docx_paths=(docx,))
    # A stub converter, so this can't reach Word.
    workflow = FullReportPostProcessingWorkflow(converter=MagicMock())

    def action(environment) -> None:
        workflow._compile_deliverable(group, tmp_path / "ts.pdf", out_pdf, environment=environment)

    with patch.object(
        LocalWorkspaceStorage, "get_substation_raw_data_dir", return_value=raw_dir if has_raw_data else None
    ):
        run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    paths = {entry["path"] for entry in entries_of(entries, "input")}
    assert (str(measurement) in paths) is has_raw_data


@pytest.mark.parametrize("has_raw_data", [True, False])
def test_pipeline_sound_hook_records_raw_data_files(locations, tmp_path, has_raw_data) -> None:
    raw_dir, measurement = _raw_data_folder(locations)
    package = SubstationPackage(
        testsheet_xlsx=_file(tmp_path / "TS" / "1. PE.xlsx"),
        quick_report_docx=_file(tmp_path / "QR" / "1. PE.docx"),
        station_name="PE ONE",
    )
    # A stub converter, and the workbook steps are patched, so this can't reach Word or Excel.
    request = PostProcessingRequest(mode=PostProcessingMode.BY_FL, target_packages=(package,), converter=MagicMock())
    module = "src.workflows.postprocessing_pipeline"

    def action(environment) -> object:
        with (
            patch(f"{module}.validate_postprocessing_preflight"),
            patch(f"{module}.discover_substation_packages", return_value=[package]),
            patch(f"{module}.replace_pce_images"),
            patch(f"{module}.process_workbook"),
        ):
            return PostProcessingPipelineWorkflow().execute(environment, request)

    with patch.object(
        LocalWorkspaceStorage, "get_substation_raw_data_dir", return_value=raw_dir if has_raw_data else None
    ):
        run_project_action(action, locations.environment)

    entries = read_entries(locations.project_logs)
    assert entries[-1]["status"] == "completed"
    paths = {entry["path"] for entry in entries_of(entries, "input")}
    assert (str(measurement) in paths) is has_raw_data


class _FakeWord:
    """A plain object standing in for Word. Weakly referenced, to see whether it stays alive."""

    Documents = None


def _run_failing_station(locations, tmp_path) -> tuple[weakref.ref, Path]:
    """Runs the real _execute_substation, with a plan step that fails holding an open file.

    Word can't start: the compiler and slicer are fakes, and Word itself is a plain object.
    """
    package = _package(_file(tmp_path / "TS" / "1. PE.xlsx"))
    temp_root = tmp_path / "temp_root"
    workflow = FullReportWorkflow(compiler=FakeDocumentCompiler())

    def fail_with_open_file(*args, station_temp_dir, **kwargs):
        handle = open(station_temp_dir / "held_open.tmp", "w", encoding="utf-8")  # noqa: F841, SIM115
        raise RuntimeError("station failed")

    context = _SubstationExecutionContext(
        environment=locations.environment,
        output_dir=None,
        base_temp_root=temp_root,
        keep_temp=False,
        progress_sink=None,
        total_packages=1,
        ordered_results=[None],
        generated_paths=[],
        errors=[],
    )
    word = _FakeWord()
    word_ref = weakref.ref(word)
    with (
        patch.object(FullReportWorkflow, "_resolve_quick_report_path", return_value=tmp_path / "1. PE.docx"),
        patch("src.workflows.full_report.validate_finalized_quick_report", return_value=SimpleNamespace(is_valid=True)),
        patch.object(FullReportWorkflow, "_build_station_plan", side_effect=fail_with_open_file),
        patch("src.quick_report.compiler.clear_windows_clipboard"),
    ):
        workflow._execute_substation(pkg_idx=0, pkg=package, word_app=word, ctx=context)
    assert context.errors
    return word_ref, temp_root


@contextmanager
def _no_log_handlers():
    """pytest's own log handlers keep each record's traceback. The CLI's handlers don't."""
    saved = list(logging.root.handlers)
    logging.root.handlers[:] = []
    try:
        yield
    finally:
        logging.root.handlers[:] = saved


def test_failed_station_frees_word_and_its_temp_folder_with_a_run(locations, tmp_path) -> None:
    def action(environment) -> None:
        results.append(_run_failing_station(locations, tmp_path))
        gc.collect()
        results.append(results[0][0]())
        results.append(list(results[0][1].iterdir()))

    results: list = []
    with _no_log_handlers():
        run_project_action(action, locations.environment)

    assert results[1] is None, "Word is still alive after the station ended"
    assert results[2] == [], "the station's temp folder was left behind"
    errors = entries_of(read_entries(locations.project_logs), "error")
    assert "station failed" in errors[0]["traceback"]


def test_failed_station_frees_word_and_its_temp_folder_with_no_run(locations, tmp_path) -> None:
    with _no_log_handlers():
        word_ref, temp_root = _run_failing_station(locations, tmp_path)
        gc.collect()

    assert word_ref() is None, "Word is still alive after the station ended"
    assert list(temp_root.iterdir()) == [], "the station's temp folder was left behind"


class _WeaklyHeldError(Exception):
    pass


def test_recording_an_exception_keeps_no_reference_to_it(locations) -> None:
    refs: list = []

    def action(environment) -> None:
        for record in (current_run().record_error, current_run().record_failure, current_run().record_warning):
            failure = _WeaklyHeldError("detail")
            refs.append(weakref.ref(failure))
            record("recorded", failure)
            del failure
        gc.collect()
        alive_during_the_run.extend(ref() for ref in refs)

    alive_during_the_run: list = []
    run_project_action(action, locations.environment)

    assert alive_during_the_run == [None, None, None]


def test_recording_with_no_open_run_keeps_no_reference_to_the_exception() -> None:
    failure = _WeaklyHeldError("detail")
    ref = weakref.ref(failure)
    current_run().record_error("recorded", failure)
    del failure
    gc.collect()

    assert ref() is None


def test_recording_with_no_open_run_stores_nothing(tmp_path) -> None:
    run = current_run()
    before = (len(run._errors_written), len(run._warning_messages))
    run.record_error(f"unique {uuid.uuid4().hex}", ValueError("x"))
    run.record_warning(f"unique {uuid.uuid4().hex}", ValueError("x"))

    assert (len(run._errors_written), len(run._warning_messages)) == before


class _UnmarkableError(Exception):
    def __setattr__(self, name, value):
        raise AttributeError("no attributes on this one")


def test_exception_that_cannot_be_marked_is_recorded_each_time_rather_than_dropped(locations) -> None:
    def action(environment) -> None:
        failure = _UnmarkableError("detail")
        current_run().record_error("first", failure)
        current_run().record_error("second", failure)

    run_project_action(action, locations.environment)

    errors = entries_of(read_entries(locations.project_logs), "error")
    assert [error["message"] for error in errors] == ["first", "second"]


def test_exception_marked_by_an_earlier_run_is_recorded_again_by_a_later_one(locations) -> None:
    failure = ValueError("carried over")

    with open_run("First", locations.environment) as first:
        first.record_error("from first", failure)
    with open_run("Second", locations.environment) as second:
        second.record_error("from second", failure)

    records = sorted(locations.project_logs.glob("*.jsonl"), key=lambda path: path.stat().st_mtime_ns)
    assert len(records) == 2
    messages = [
        json.loads(line)["message"]
        for record in records
        for line in record.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "error"
    ]
    assert sorted(messages) == ["from first", "from second"]
