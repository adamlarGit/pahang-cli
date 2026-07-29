"""Unit tests for project workflow actions and utility actions in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import openpyxl
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import PopulateTotalPeAction, QuickReportAction, RawMaterialAction
from src.workflows.models import PopulateTotalPeResult, QuickReportMode, QuickReportResult, RawMaterialResult


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
    return ProjectEnvironment(metadata=meta, storage=storage)


def test_populate_total_pe_action(mock_env: ProjectEnvironment) -> None:
    action = PopulateTotalPeAction("Populate TOTAL PE")

    with patch("src.cli_selectors.select_one", return_value="auto"):
        with patch("src.workflows.service.WorkflowService.run_populate_total_pe") as mock_run:
            mock_run.return_value = PopulateTotalPeResult(new_rows_added=5)
            res = action.execute(mock_env)
            assert res.new_rows_added == 5
            mock_run.assert_called_once()


def test_raw_material_action(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    action = RawMaterialAction("Automate Raw Material")
    testsheet_dir = mock_env.get_testsheet_dir()
    testsheet_dir.mkdir(parents=True, exist_ok=True)

    with patch("src.cli_selectors.select_pahang_date_folder", return_value=testsheet_dir):
        with patch("src.workflows.service.WorkflowService.run_raw_material") as mock_run:
            mock_run.return_value = RawMaterialResult(substations_count=2)
            res = action.execute(mock_env)
            assert res.substations_count == 2
            mock_run.assert_called_once()


def test_quick_report_action_folder_selection(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    action = QuickReportAction("Generate Quick Report")
    target_folder = tmp_path / "TESTSHEET" / "KUANTAN" / "2026-01 (Jan)" / "01-01-2026"

    with patch("src.cli_selectors.select_one", return_value="folder"):
        with patch("src.cli_selectors.select_pahang_date_folder", return_value=target_folder) as mock_select:
            with patch("src.workflows.service.WorkflowService.run_quick_report") as mock_run:
                mock_run.return_value = QuickReportResult(reports_generated=1)
                res = action.execute(mock_env)
                assert res.reports_generated == 1
                mock_select.assert_called_once_with(environment=mock_env)
                mock_run.assert_called_once()
                req = mock_run.call_args[0][1]
                assert req.mode == QuickReportMode.FOLDER
                assert req.target_folders == (str(target_folder),)


def test_quick_report_action_folder_selection_cancel(mock_env: ProjectEnvironment) -> None:
    action = QuickReportAction("Generate Quick Report")

    with patch("src.cli_selectors.select_one", return_value="folder"):
        with patch("src.cli_selectors.select_pahang_date_folder", return_value=None):
            res = action.execute(mock_env)
            assert res is None

