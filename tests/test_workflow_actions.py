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
    storage.get_template = MagicMock(return_value=tmp_path) # prevent FileNotFoundError
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


def test_print_quick_report_batch_summary(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify _print_quick_report_batch_summary formats CLI summary box."""
    from src.project_workflow_actions import _print_quick_report_batch_summary

    result = QuickReportResult(
        reports_generated=2,
        generated_paths=[Path("001. SUBSTATION A.docx"), Path("002. SUBSTATION B (IR).docx")],
        warnings=["Missing DG photo for SUBSTATION B"],
        errors=["003. SUBSTATION C: PCE VI sheet missing"],
    )

    _print_quick_report_batch_summary(result)
    captured = capsys.readouterr().out

    assert "QUICK REPORT BATCH EXECUTION SUMMARY" in captured
    assert "[FAILED] 003. SUBSTATION C: PCE VI sheet missing" in captured


def test_propagate_wo_action(mock_env: ProjectEnvironment) -> None:
    from src.project_workflow_actions import PropagateWoAction
    from src.workflows.models import PropagateWoResult

    action = PropagateWoAction("Propagate Work Orders")
    with patch("src.workflows.service.WorkflowService.run_propagate_wo") as mock_run:
        mock_run.return_value = PropagateWoResult(matched_count=3, already_populated_count=1, unmatched_count=0, updated_count=3)
        res = action.execute(mock_env)
        assert res.updated_count == 3
        mock_run.assert_called_once_with(mock_env)


def test_update_qr02_cba_action(mock_env: ProjectEnvironment) -> None:
    from src.project_workflow_actions import UpdateQr02CbaAction
    from src.workflows.models import UpdateQr02CbaResult

    action = UpdateQr02CbaAction("Update QR02 CBA")
    with patch("src.cli_selectors.select_one", return_value="auto"):
        with patch("src.workflows.service.WorkflowService.run_update_qr02_cba") as mock_run:
            mock_run.return_value = UpdateQr02CbaResult(records_updated=4)
            res = action.execute(mock_env)
            assert res.records_updated == 4
            mock_run.assert_called_once()


def test_consolidate_msms_action(mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]) -> None:
    from src.project_workflow_actions import ConsolidateMsmsAction
    from src.workflows.models import ConsolidateMsmsResult

    action = ConsolidateMsmsAction("Consolidate MSMS")
    with patch("src.workflows.service.WorkflowService.run_consolidate_msms") as mock_run:
        mock_run.return_value = ConsolidateMsmsResult(
            files_processed=3,
            rows_appended=10,
            duplicates_skipped=2,
        )
        res = action.execute(mock_env)
        assert res.files_processed == 3
        assert res.rows_appended == 10
        assert res.duplicates_skipped == 2
        mock_run.assert_called_once_with(mock_env)
        captured = capsys.readouterr().out
        assert "Files processed: 3, Rows appended: 10, Duplicates skipped: 2" in captured


def test_enrich_msms_action(mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]) -> None:
    from src.project_workflow_actions import EnrichMsmsAction
    from src.workflows.models import EnrichMsmsResult

    action = EnrichMsmsAction("Enrich MSMS")
    with patch("src.workflows.service.WorkflowService.run_enrich_msms") as mock_run:
        mock_run.return_value = EnrichMsmsResult(
            updated_cells_count=12,
            matched_count=5,
            unmatched_count=1,
        )
        res = action.execute(mock_env)
        assert res.updated_cells_count == 12
        assert res.matched_count == 5
        assert res.unmatched_count == 1
        mock_run.assert_called_once_with(mock_env)
        captured = capsys.readouterr().out
        assert "Cells updated: 12, Matched: 5, Unmatched: 1" in captured


def test_ingest_msms_csv_action(mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]) -> None:
    from src.project_workflow_actions import IngestMsmsCsvAction
    from src.workflows.models import IngestMsmsCsvResult

    action = IngestMsmsCsvAction("Ingest MSMS CSVs")
    with patch("src.workflows.service.WorkflowService.run_ingest_msms_csv") as mock_run:
        mock_run.return_value = IngestMsmsCsvResult(
            files_ingested=4,
            files_skipped_duplicate=1,
        )
        res = action.execute(mock_env)
        assert res.files_ingested == 4
        assert res.duplicates_skipped == 1
        mock_run.assert_called_once_with(mock_env)
        captured = capsys.readouterr().out
        assert "Files ingested: 4, Duplicates skipped: 1" in captured


def test_populate_data_msms_action_auto(mock_env: ProjectEnvironment, capsys: pytest.CaptureFixture[str]) -> None:
    from src.project_workflow_actions import PopulateDataMsmsAction
    from src.workflows.models import PopulateDataMsmsResult, PopulateMode

    action = PopulateDataMsmsAction("Populate Data MSMS")
    with patch("src.cli_selectors.select_one", return_value="auto"):
        with patch("src.workflows.service.WorkflowService.run_populate_data_msms") as mock_run:
            mock_run.return_value = PopulateDataMsmsResult(
                csv_files_processed=2,
                rows_populated=50,
                rows_skipped_already_filled=5,
            )
            res = action.execute(mock_env)
            assert res.csv_files_processed == 2
            assert res.rows_populated == 50
            assert res.rows_skipped_already_filled == 5
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            req = call_args[0][1]
            assert req.mode == PopulateMode.AUTO
            assert req.overwrite is False
            captured = capsys.readouterr().out
            assert "CSV files processed: 2, Rows populated: 50, Rows skipped: 5" in captured


def test_populate_data_msms_action_all_with_overwrite(mock_env: ProjectEnvironment) -> None:
    from src.project_workflow_actions import PopulateDataMsmsAction
    from src.workflows.models import PopulateDataMsmsResult, PopulateMode

    action = PopulateDataMsmsAction("Populate Data MSMS")
    with patch("src.cli_selectors.select_one", return_value="all"):
        with patch("src.cli_selectors.confirm", return_value=True):
            with patch("src.workflows.service.WorkflowService.run_populate_data_msms") as mock_run:
                mock_run.return_value = PopulateDataMsmsResult(csv_files_processed=3, rows_populated=100)
                res = action.execute(mock_env)
                assert res.rows_populated == 100
                call_args = mock_run.call_args
                req = call_args[0][1]
                assert req.mode == PopulateMode.ALL
                assert req.overwrite is True


def test_populate_data_msms_action_select_folder(mock_env: ProjectEnvironment) -> None:
    from src.project_workflow_actions import PopulateDataMsmsAction
    from src.workflows.models import PopulateDataMsmsResult, PopulateMode

    action = PopulateDataMsmsAction("Populate Data MSMS")
    selected_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/18-08-2026")
    with patch("src.cli_selectors.select_one", return_value="select"):
        with patch("src.cli_selectors.select_pahang_date_folder", return_value=selected_path):
            with patch("src.cli_selectors.confirm", return_value=False):
                with patch("src.workflows.service.WorkflowService.run_populate_data_msms") as mock_run:
                    mock_run.return_value = PopulateDataMsmsResult(csv_files_processed=1, rows_populated=20)
                    res = action.execute(mock_env)
                    assert res.rows_populated == 20
                    call_args = mock_run.call_args
                    req = call_args[0][1]
                    assert req.mode == PopulateMode.SPECIFIC_FOLDERS
                    assert req.target_folder_names == ("18-08-2026", str(selected_path))
                    assert req.overwrite is False


def test_populate_data_msms_action_cancel(mock_env: ProjectEnvironment) -> None:
    from src.project_workflow_actions import PopulateDataMsmsAction

    action = PopulateDataMsmsAction("Populate Data MSMS")
    with patch("src.cli_selectors.select_one", return_value="__cancel__"):
        res = action.execute(mock_env)
        assert res is None



def test_project_workflow_actions_registry() -> None:
    from src.project_workflow_actions import (
        PROJECT_WORKFLOW_ACTIONS,
        ConsolidateMsmsAction,
        EnrichMsmsAction,
        GenerateTestsheetFolderAction,
        IngestMsmsCsvAction,
        PopulateDataMsmsAction,
        PopulateTotalPeAction,
        PostProcessingPipelineAction,
        PropagateWoAction,
        QuickReportAction,
        RawMaterialAction,
        UpdateQr02CbaAction,
        WhatsAppReportAction,
        get_project_workflow_actions,
    )

    actions = get_project_workflow_actions()
    assert actions == PROJECT_WORKFLOW_ACTIONS
    assert len(actions) == 12

    expected_specs = [
        (GenerateTestsheetFolderAction, "Generate TESTSHEET Folder Structure"),
        (PopulateTotalPeAction, "Populate TOTAL PE (from testsheets)"),
        (RawMaterialAction, "Automate Raw Material Creation & Sorting (from Testsheets)"),
        (UpdateQr02CbaAction, "Update QR02 CBA (from testsheets)"),
        (QuickReportAction, "Generate Quick Report (Visual Report)"),
        (PostProcessingPipelineAction, "Run Full Substation Post-Processing Pipeline (1-Click)"),
        (WhatsAppReportAction, "Generate WhatsApp Report"),
        (ConsolidateMsmsAction, "Consolidate MSMS (PYTHON/MSMS/*.xls -> DATA MSMS)"),
        (EnrichMsmsAction, "Enrich MSMS (TOTAL PE -> DATA MSMS metadata)"),
        (PropagateWoAction, "Propagate Work Orders (DATA MSMS -> TOTAL PE)"),
        (IngestMsmsCsvAction, "Ingest MSMS CSVs (RAW DATA -> TO BE FILLED)"),
        (PopulateDataMsmsAction, "Populate Data MSMS (Testsheets -> TO BE FILLED CSVs)"),
    ]

    for idx, (expected_cls, expected_label) in enumerate(expected_specs):
        assert isinstance(actions[idx], expected_cls)
        assert actions[idx].label == expected_label




