"""Unit tests for Full Report CLI actions, menu wiring, prompts, and summary formatting."""

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from src.cli_menu import MenuItem, select_project_workflow_action
from src.project.environment import ProjectEnvironment
from src.project_workflow_actions import (
    FullReportAction,
    FullReportPostProcessingAction,
    generate_full_reports_action,
    get_project_workflow_actions,
    postprocess_full_reports_action,
)
from src.workflows.full_report import (
    FullReportBatchResult,
    FullReportInspection,
    FullReportStationExecutionResult,
    FullReportSubstationTelemetry,
    FullReportWorkflow,
)
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingInspection,
    FullReportPostProcessingResult,
    FullReportPostProcessingTelemetry,
    FullReportPostProcessingWorkflow,
    TestsheetPdfValidationResult,
)


@pytest.fixture
def mock_env() -> MagicMock:
    env = MagicMock(spec=ProjectEnvironment)
    env.base_path = Path("C:/fake/project")
    env.project_data = {"name": "TEST_PROJECT"}
    env.get_full_report_dir.return_value = Path("C:/fake/project/FULL REPORT")
    env.get_quick_report_dir.return_value = Path("C:/fake/project/QUICK REPORT")
    env.get_testsheet_dir.return_value = Path("C:/fake/project/TESTSHEET")
    return env


# ==============================================================================
# 1. FullReportAction Tests
# ==============================================================================

def test_full_report_action_cancel_date_selection(mock_env: MagicMock) -> None:
    action = FullReportAction()
    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=None):
        result = action.execute(mock_env)
        assert result is None


def test_full_report_action_dry_run_telemetry_and_cancel_confirmation(
    mock_env: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_workflow = MagicMock(spec=FullReportWorkflow)
    telem = FullReportSubstationTelemetry(
        substation_number=5,
        substation_name="TALAPIA",
        functional_location="FL-01",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        quick_report_path=Path("C:/fake/QR.docx"),
        is_quick_report_valid=True,
        preflight_result=None,
        target_output_path=Path("C:/fake/FR.docx"),
        stem="005. TALAPIA",
        defect_suffix="",
        cbm_defect_count=1,
        vi_defect_count=0,
    )
    inspection = FullReportInspection(targets=(telem,))
    mock_workflow.inspect.return_value = inspection

    action = FullReportAction(workflow=mock_workflow)

    date_dir = Path("C:/fake/project/TESTSHEET/RAUB/08. AUGUST/04-08-2026")
    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=date_dir), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", return_value=[telem]), \
         patch("src.project_workflow_actions.cli_selectors.confirm", return_value=False) as mock_confirm:

        result = action.execute(mock_env)
        assert result is None

        # Verify inspect was called
        mock_workflow.inspect.assert_called_once()
        # Verify confirm was prompted
        mock_confirm.assert_called_once()
        # Verify generate was NOT called due to cancellation
        mock_workflow.generate.assert_not_called()

        captured = capsys.readouterr().out
        assert "FULL REPORT PRE-FLIGHT TELEMETRY & DRY-RUN" in captured
        assert "TALAPIA" in captured
        assert "Generation cancelled" in captured


def test_full_report_action_multi_station_selection_and_summary(
    mock_env: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_workflow = MagicMock(spec=FullReportWorkflow)

    telem1 = FullReportSubstationTelemetry(
        substation_number=5,
        substation_name="TALAPIA",
        functional_location="FL-01",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        quick_report_path=Path("C:/fake/QR1.docx"),
        is_quick_report_valid=True,
        preflight_result=None,
        target_output_path=Path("C:/fake/FR1.docx"),
        stem="005. TALAPIA",
        defect_suffix="",
        cbm_defect_count=1,
        vi_defect_count=0,
    )
    telem2 = FullReportSubstationTelemetry(
        substation_number=10,
        substation_name="BAD_STATION",
        functional_location="FL-02",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        quick_report_path=None,
        is_quick_report_valid=False,
        preflight_result=None,
        target_output_path=Path("C:/fake/FR2.docx"),
        stem="010. BAD_STATION",
        defect_suffix="",
        cbm_defect_count=0,
        vi_defect_count=0,
        errors=("Pre-flight validation failed: Quick Report missing",),
    )
    inspection = FullReportInspection(targets=(telem1, telem2))
    mock_workflow.inspect.return_value = inspection

    out_path = Path("C:/fake/project/FULL REPORT/RAUB/08. AUGUST/04-08-2026/005. TALAPIA.docx")
    batch_result = FullReportBatchResult(
        total_stations=1,
        succeeded_count=1,
        failed_count=0,
        station_results=(
            FullReportStationExecutionResult(
                station="TALAPIA",
                substation_number=5,
                output_path=out_path,
                is_success=True,
            ),
        ),
        generated_paths=(out_path,),
    )
    mock_workflow.generate.return_value = batch_result

    action = FullReportAction(workflow=mock_workflow)
    date_dir = Path("C:/fake/project/TESTSHEET/RAUB/08. AUGUST/04-08-2026")

    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=date_dir), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive") as mock_interactive, \
         patch("src.project_workflow_actions.cli_selectors.confirm", return_value=True):

        # Operator selects only telem1
        mock_interactive.return_value = [telem1]

        result = action.execute(mock_env)
        assert result == batch_result

        # Verify multi-station interactive selector was called
        mock_interactive.assert_called_once()
        items = mock_interactive.call_args[0][0]
        assert len(items) == 2

        # Verify generate was invoked with the selected station
        mock_workflow.generate.assert_called_once_with(
            date_dir,
            mock_env,
            station=["TALAPIA"],
            progress_sink=ANY,
        )

        captured = capsys.readouterr().out
        assert "FULL REPORT BATCH EXECUTION SUMMARY" in captured
        assert "Total Processed : 1" in captured
        assert "Succeeded       : 1" in captured
        assert "Failed          : 0" in captured
        assert str(out_path) in captured


# ==============================================================================
# 2. FullReportPostProcessingAction Tests
# ==============================================================================

def test_full_report_postprocessing_action_cancel_date_selection(mock_env: MagicMock) -> None:
    action = FullReportPostProcessingAction()
    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=None):
        result = action.execute(mock_env)
        assert result is None


def test_full_report_postprocessing_action_dry_run_telemetry_and_cancel_confirmation(
    mock_env: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_workflow = MagicMock(spec=FullReportPostProcessingWorkflow)
    docx_p = Path("C:/fake/project/FULL REPORT/RAUB/08. AUGUST/04-08-2026/005. TALAPIA.docx")
    ts_pdf = Path("C:/fake/project/processed_testsheet/pdf/005. TALAPIA.pdf")
    telem = FullReportPostProcessingTelemetry(
        docx_path=docx_p,
        testsheet_pdf_path=ts_pdf,
        target_pdf_path=docx_p.with_suffix(".pdf"),
        stem="005. TALAPIA",
        substation_name="TALAPIA",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        substation_number=5,
        is_testsheet_pdf_valid=True,
        validation_result=TestsheetPdfValidationResult(path=ts_pdf, is_valid=True, size_bytes=2048),
    )
    inspection = FullReportPostProcessingInspection(targets=(telem,))
    mock_workflow.inspect.return_value = inspection

    action = FullReportPostProcessingAction(workflow=mock_workflow)
    date_dir = Path("C:/fake/project/FULL REPORT/RAUB/08. AUGUST/04-08-2026")

    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=date_dir), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", return_value=[telem]), \
         patch("src.project_workflow_actions.cli_selectors.confirm", return_value=False) as mock_confirm:

        result = action.execute(mock_env)
        assert result is None

        mock_workflow.inspect.assert_called_once()
        mock_confirm.assert_called_once()
        mock_workflow.process.assert_not_called()

        captured = capsys.readouterr().out
        assert "FULL REPORT POST-PROCESSING PRE-FLIGHT TELEMETRY" in captured
        assert "005. TALAPIA.docx" in captured
        assert "Post-processing cancelled" in captured


def test_full_report_postprocessing_action_multi_document_and_summary(
    mock_env: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock_workflow = MagicMock(spec=FullReportPostProcessingWorkflow)

    doc1 = Path("C:/fake/005. TALAPIA.docx")
    doc2 = Path("C:/fake/010. BAD.docx")
    ts1 = Path("C:/fake/ts1.pdf")

    telem1 = FullReportPostProcessingTelemetry(
        docx_path=doc1,
        testsheet_pdf_path=ts1,
        target_pdf_path=doc1.with_suffix(".pdf"),
        stem="005. TALAPIA",
        substation_name="TALAPIA",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        substation_number=5,
        is_testsheet_pdf_valid=True,
        validation_result=TestsheetPdfValidationResult(path=ts1, is_valid=True, size_bytes=5000),
    )
    telem2 = FullReportPostProcessingTelemetry(
        docx_path=doc2,
        testsheet_pdf_path=None,
        target_pdf_path=doc2.with_suffix(".pdf"),
        stem="010. BAD",
        substation_name="BAD",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        substation_number=10,
        is_testsheet_pdf_valid=False,
        validation_result=TestsheetPdfValidationResult(path=None, is_valid=False),
        errors=("Testsheet PDF missing",),
    )
    inspection = FullReportPostProcessingInspection(targets=(telem1, telem2))
    mock_workflow.inspect.return_value = inspection

    merged_pdf = Path("C:/fake/005. TALAPIA.pdf")
    post_res = FullReportPostProcessingResult(
        total_reports=1,
        succeeded_count=1,
        failed_count=0,
        deliverables=(merged_pdf,),
        telemetries=(telem1,),
        duration_seconds=1.23,
    )
    mock_workflow.process.return_value = post_res

    action = FullReportPostProcessingAction(workflow=mock_workflow)
    date_dir = Path("C:/fake/project/FULL REPORT/RAUB/08. AUGUST/04-08-2026")

    with patch("src.project_workflow_actions.cli_selectors.select_pahang_date_folder", return_value=date_dir), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive") as mock_interactive, \
         patch("src.project_workflow_actions.cli_selectors.confirm", return_value=True):

        mock_interactive.return_value = [telem1]

        result = action.execute(mock_env)
        assert result == post_res

        mock_interactive.assert_called_once()
        mock_workflow.process.assert_called_once()
        call_args = mock_workflow.process.call_args[0]
        assert call_args[0] == [doc1]

        captured = capsys.readouterr().out
        assert "FULL REPORT POST-PROCESSING SUMMARY" in captured
        assert "Total Processed : 1" in captured
        assert "Succeeded       : 1" in captured
        assert "Failed          : 0" in captured
        assert str(merged_pdf) in captured


# ==============================================================================
# 3. CLI Menu Integration & Registry Tests
# ==============================================================================

def test_cli_menu_wiring_and_registry() -> None:
    actions = get_project_workflow_actions()

    assert len(actions) == 14
    # The last two actions are the Full Report actions per D44
    assert isinstance(actions[-2], FullReportAction)
    assert actions[-2].label == "Generate Full Reports"

    assert isinstance(actions[-1], FullReportPostProcessingAction)
    assert actions[-1].label == "Post-Process Full Reports (PDF + Testsheet Merge)"


def test_cli_menu_selection_renders_full_report_items() -> None:
    actions = get_project_workflow_actions()

    with patch("src.cli_menu.cli_selectors.select_one") as mock_select:
        mock_select.return_value = actions[-2]

        selected = select_project_workflow_action(actions, active_project_name="TEST_PROJECT")
        assert selected == actions[-2]

        title, options = mock_select.call_args[0]
        assert "PROJECT WORKFLOW" in title
        labels = [opt.title for opt in options]
        assert any("Generate Full Reports" in l for l in labels)
        assert any("Post-Process Full Reports" in l for l in labels)
