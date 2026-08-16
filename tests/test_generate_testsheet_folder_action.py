"""Unit tests for Generate TESTSHEET Folder Structure action and WorkflowService seam."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import (
    PROJECT_WORKFLOW_ACTIONS,
    GenerateTestsheetFolderAction,
    get_project_workflow_actions,
)
from src.workflows.models import (
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
)
from src.workflows.service import WorkflowService


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    meta = ProjectMetadata(
        key="pahang_2026",
        name="Pahang 2026 Test",
        po_number="PO42289580",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    storage.get_template = MagicMock(return_value=tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


def test_workflow_service_run_generate_testsheet_folder(mock_env: ProjectEnvironment) -> None:
    service = WorkflowService()
    progress_messages: list[str] = []

    def dummy_progress(msg: str) -> None:
        progress_messages.append(msg)

    request = GenerateTestsheetFolderRequest(
        station="GAMBANG",
        month="01. JANUARY",
        target_dates=("10-08-2026", "11-08-2026"),
        progress_sink=dummy_progress,
    )

    expected_result = GenerateTestsheetFolderResult(
        station="GAMBANG",
        month="01. JANUARY",
        created_directories=(Path("/tmp/a"),),
        existing_directories=(),
        total_dates_processed=2,
    )

    with patch(
        "src.workflows.generate_testsheet_folder.GenerateTestsheetFolderStructureWorkflow.execute",
        return_value=expected_result,
    ) as mock_exec:
        result = service.run_generate_testsheet_folder(mock_env, request)

        assert result == expected_result
        mock_exec.assert_called_once_with(mock_env, request)
        assert any("Generating folder structure for GAMBANG / 01. JANUARY..." in m for m in progress_messages)


def test_generate_testsheet_folder_action_success(
    mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]
) -> None:
    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")

    expected_result = GenerateTestsheetFolderResult(
        station="GAMBANG",
        month="01. JANUARY",
        created_directories=(Path("/tmp/d1"), Path("/tmp/d2")),
        existing_directories=(),
        total_dates_processed=2,
        warnings=("Warning about date format normalization",),
    )

    with patch(
        "src.cli_selectors.select_or_create_testsheet_station",
        return_value="GAMBANG",
    ) as mock_station, patch(
        "src.cli_selectors.select_or_create_testsheet_month",
        return_value="01. JANUARY",
    ) as mock_month, patch(
        "src.cli_selectors.prompt_target_inspection_dates",
        return_value=("10-08-2026", "11-08-2026"),
    ) as mock_dates, patch(
        "src.workflows.service.WorkflowService.run_generate_testsheet_folder",
        return_value=expected_result,
    ) as mock_run:
        result = action.execute(mock_env)

        assert result == expected_result
        mock_station.assert_called_once_with(mock_env)
        mock_month.assert_called_once_with(mock_env, "GAMBANG")
        mock_dates.assert_called_once()
        mock_run.assert_called_once()

        req: GenerateTestsheetFolderRequest = mock_run.call_args[0][1]
        assert req.station == "GAMBANG"
        assert req.month == "01. JANUARY"
        assert req.target_dates == ("10-08-2026", "11-08-2026")
        assert req.progress_sink is not None

        captured = capsys.readouterr().out
        assert "Successfully generated folder structure for GAMBANG / 01. JANUARY (2 dates)." in captured
        assert "[WARNING] Warning about date format normalization" in captured


def test_generate_testsheet_folder_action_singular_date(
    mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]
) -> None:
    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")

    expected_result = GenerateTestsheetFolderResult(
        station="PEKAN",
        month="02. FEBRUARY",
        created_directories=(Path("/tmp/d1"),),
        existing_directories=(),
        total_dates_processed=1,
    )

    with patch(
        "src.cli_selectors.select_or_create_testsheet_station",
        return_value="PEKAN",
    ), patch(
        "src.cli_selectors.select_or_create_testsheet_month",
        return_value="02. FEBRUARY",
    ), patch(
        "src.cli_selectors.prompt_target_inspection_dates",
        return_value=("15-02-2026",),
    ), patch(
        "src.workflows.service.WorkflowService.run_generate_testsheet_folder",
        return_value=expected_result,
    ):
        result = action.execute(mock_env)
        assert result == expected_result

        captured = capsys.readouterr().out
        assert "Successfully generated folder structure for PEKAN / 02. FEBRUARY (1 date)." in captured


def test_generate_testsheet_folder_action_cancel_station(mock_env: ProjectEnvironment) -> None:
    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")

    with patch(
        "src.cli_selectors.select_or_create_testsheet_station",
        return_value=None,
    ), patch(
        "src.cli_selectors.select_or_create_testsheet_month"
    ) as mock_month, patch(
        "src.cli_selectors.prompt_target_inspection_dates"
    ) as mock_dates, patch(
        "src.workflows.service.WorkflowService.run_generate_testsheet_folder"
    ) as mock_run:
        result = action.execute(mock_env)

        assert result is None
        mock_month.assert_not_called()
        mock_dates.assert_not_called()
        mock_run.assert_not_called()


def test_generate_testsheet_folder_action_cancel_month(mock_env: ProjectEnvironment) -> None:
    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")

    with patch(
        "src.cli_selectors.select_or_create_testsheet_station",
        return_value="GAMBANG",
    ), patch(
        "src.cli_selectors.select_or_create_testsheet_month",
        return_value=None,
    ), patch(
        "src.cli_selectors.prompt_target_inspection_dates"
    ) as mock_dates, patch(
        "src.workflows.service.WorkflowService.run_generate_testsheet_folder"
    ) as mock_run:
        result = action.execute(mock_env)

        assert result is None
        mock_dates.assert_not_called()
        mock_run.assert_not_called()


def test_generate_testsheet_folder_action_cancel_dates(mock_env: ProjectEnvironment) -> None:
    action = GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")

    with patch(
        "src.cli_selectors.select_or_create_testsheet_station",
        return_value="GAMBANG",
    ), patch(
        "src.cli_selectors.select_or_create_testsheet_month",
        return_value="01. JANUARY",
    ), patch(
        "src.cli_selectors.prompt_target_inspection_dates",
        return_value=None,
    ), patch(
        "src.workflows.service.WorkflowService.run_generate_testsheet_folder"
    ) as mock_run:
        result = action.execute(mock_env)

        assert result is None
        mock_run.assert_not_called()


def test_project_workflow_actions_first_item() -> None:
    actions = get_project_workflow_actions()
    assert actions == PROJECT_WORKFLOW_ACTIONS
    assert len(actions) >= 1
    first_action = actions[0]
    assert isinstance(first_action, GenerateTestsheetFolderAction)
    assert first_action.label == "Generate TESTSHEET Folder Structure"
