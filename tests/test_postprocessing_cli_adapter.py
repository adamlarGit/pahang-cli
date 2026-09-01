"""Unit tests for the 1-Click Substation Post-Processing CLI Presentation Adapter and Summary Formatter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import (
    PostProcessingPipelineAction,
    _print_postprocessing_summary,
)
from src.testsheet.models import SubstationPackage
from src.workflows.models import (
    PostProcessingFailure,
    PostProcessingMode,
    PostProcessingRequest,
    PostProcessingSummary,
)


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    """Provide an isolated ProjectEnvironment backed by a temporary directory."""
    meta = ProjectMetadata(
        key="test_pahang",
        name="Test Pahang Project",
        base_path=str(tmp_path),
        state="pahang",
        po_number="PO-998877",
        voltage_type="11kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


def _make_dummy_package(name: str = "PE TEST", date_folder: str = "10-08-2026") -> SubstationPackage:
    return SubstationPackage(
        station_name=name,
        fl_erms="FL-001",
        date_folder=date_folder,
        testsheet_xlsx=Path(f"C:/mock/TESTSHEET/{date_folder}/01. {name}.xlsx"),
        quick_report_docx=Path(f"C:/mock/QUICK REPORT/{date_folder}/01. {name}.docx"),
        substation_number=1,
    )


def test_postprocessing_action_by_date_with_signatures_and_whatsapp(mock_env: ProjectEnvironment) -> None:
    """Test full BY_DATE flow with signatures and WhatsApp enabled."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    date_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026")
    vendor_sign = Path("C:/data/OTHERS/SIGN/ALI")
    tnb_sign = Path("C:/data/OTHERS/SIGN/BAKAR")

    summary_mock = PostProcessingSummary(
        processed_packages=(_make_dummy_package(),),
        final_deliverables=(Path("C:/data/QUICK REPORT/10-08-2026/01. PE TEST.pdf"),),
        duration_seconds=5.2,
    )

    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=date_path) as mock_date_select,
        patch("src.cli_selectors.confirm", side_effect=[True, True]) as mock_confirm,
        patch("src.workflows.replace_signatures._select_signature_path", side_effect=[
            (vendor_sign, "ALI"),
            (tnb_sign, "BAKAR"),
        ]) as mock_sign_select,
        patch("src.workflows.service.WorkflowService.run_postprocessing_pipeline", return_value=summary_mock) as mock_run,
        patch("src.project_workflow_actions._print_postprocessing_summary") as mock_print_summary,
    ):
        result = action.execute(mock_env)

        assert result == summary_mock
        mock_date_select.assert_called_once_with(environment=mock_env)
        assert mock_confirm.call_count == 2
        assert mock_sign_select.call_count == 2
        mock_run.assert_called_once()
        mock_print_summary.assert_called_once_with(summary_mock)

        call_req: PostProcessingRequest = mock_run.call_args[0][1]
        assert call_req.mode == PostProcessingMode.BY_DATE
        assert call_req.target_dates == ("10-08-2026",)
        assert call_req.target_fls == ()
        assert call_req.apply_signatures is True
        assert call_req.vendor_signature_path == vendor_sign
        assert call_req.tnb_signature_path == tnb_sign
        assert call_req.generate_whatsapp is True
        assert call_req.progress_sink is not None


def test_postprocessing_action_by_fl_with_discovered_packages_and_no_signatures(mock_env: ProjectEnvironment) -> None:
    """Test BY_FL flow using discovered packages, skipping signatures and suppressing WhatsApp prompt."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    pkg1 = _make_dummy_package("PE ALFA", "10-08-2026")
    pkg2 = _make_dummy_package("PE BETA", "10-08-2026")

    summary_mock = PostProcessingSummary(
        processed_packages=(pkg1, pkg2),
        final_deliverables=(Path("01. PE ALFA.pdf"), Path("02. PE BETA.pdf")),
        duration_seconds=3.1,
    )

    with (
        patch("src.cli_selectors.select_one", return_value="by_fl"),
        patch("src.workflows.postprocessing_pipeline.discover_substation_packages", return_value=[pkg1, pkg2]),
        patch("src.cli_selectors.select_multiple", return_value=["FL-001", "FL-002"]) as mock_multi,
        patch("src.cli_selectors.confirm", return_value=False) as mock_confirm,
        patch("src.workflows.replace_signatures._select_signature_path") as mock_sign_select,
        patch("src.workflows.service.WorkflowService.run_postprocessing_pipeline", return_value=summary_mock) as mock_run,
        patch("src.project_workflow_actions._print_postprocessing_summary") as mock_print_summary,
    ):
        result = action.execute(mock_env)

        assert result == summary_mock
        mock_multi.assert_called_once()
        # Only 1 confirm call (for signatures), WhatsApp confirm prompt must NOT be called in by_fl mode
        assert mock_confirm.call_count == 1
        mock_sign_select.assert_not_called()
        mock_run.assert_called_once()
        mock_print_summary.assert_called_once_with(summary_mock)

        call_req: PostProcessingRequest = mock_run.call_args[0][1]
        assert call_req.mode == PostProcessingMode.BY_FL
        assert call_req.target_dates == ()
        assert call_req.target_fls == ("FL-001", "FL-002")
        assert call_req.apply_signatures is False
        assert call_req.vendor_signature_path is None
        assert call_req.tnb_signature_path is None
        assert call_req.generate_whatsapp is False


def test_postprocessing_action_by_fl_manual_input_fallback(mock_env: ProjectEnvironment) -> None:
    """Test BY_FL flow falling back to manual prompt when no packages are discovered."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")

    summary_mock = PostProcessingSummary(duration_seconds=1.0)

    with (
        patch("src.cli_selectors.select_one", return_value="by_fl"),
        patch("src.workflows.postprocessing_pipeline.discover_substation_packages", return_value=[]),
        patch("builtins.input", return_value="PE 101, PE 102"),
        patch("src.cli_selectors.confirm", return_value=False),
        patch("src.workflows.service.WorkflowService.run_postprocessing_pipeline", return_value=summary_mock) as mock_run,
    ):
        result = action.execute(mock_env)
        assert result == summary_mock

        call_req: PostProcessingRequest = mock_run.call_args[0][1]
        assert call_req.mode == PostProcessingMode.BY_FL
        assert call_req.target_fls == ("PE 101", "PE 102")
        assert call_req.generate_whatsapp is False


def test_postprocessing_action_cancel_at_scope_selection(mock_env: ProjectEnvironment) -> None:
    """Cancellation at initial scope selection returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    with patch("src.cli_selectors.select_one", return_value="__cancel__"):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_date_selection(mock_env: ProjectEnvironment) -> None:
    """Cancellation at date folder selection returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=None),
    ):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_substation_multiselect(mock_env: ProjectEnvironment) -> None:
    """Cancellation at substation multi-select returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    pkg = _make_dummy_package()
    with (
        patch("src.cli_selectors.select_one", return_value="by_fl"),
        patch("src.workflows.postprocessing_pipeline.discover_substation_packages", return_value=[pkg]),
        patch("src.cli_selectors.select_multiple", return_value=None),
    ):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_signature_confirm(mock_env: ProjectEnvironment) -> None:
    """Cancellation at signature confirm prompt returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    date_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026")
    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=date_path),
        patch("src.cli_selectors.confirm", return_value=None),
    ):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_vendor_signature_path(mock_env: ProjectEnvironment) -> None:
    """Cancellation during vendor signature selection returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    date_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026")
    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=date_path),
        patch("src.cli_selectors.confirm", return_value=True),
        patch("src.workflows.replace_signatures._select_signature_path", return_value=(None, "__cancel__")),
    ):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_tnb_signature_path(mock_env: ProjectEnvironment) -> None:
    """Cancellation during TNB signature selection returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    date_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026")
    vendor_sign = Path("C:/data/OTHERS/SIGN/ALI")
    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=date_path),
        patch("src.cli_selectors.confirm", return_value=True),
        patch("src.workflows.replace_signatures._select_signature_path", side_effect=[
            (vendor_sign, "ALI"),
            (None, "__cancel__"),
        ]),
    ):
        res = action.execute(mock_env)
        assert res is None


def test_postprocessing_action_cancel_at_whatsapp_confirm(mock_env: ProjectEnvironment) -> None:
    """Cancellation at WhatsApp confirm prompt returns None."""
    action = PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)")
    date_path = Path("C:/data/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026")
    with (
        patch("src.cli_selectors.select_one", return_value="by_date"),
        patch("src.cli_selectors.select_pahang_date_folder", return_value=date_path),
        patch("src.cli_selectors.confirm", side_effect=[False, None]),  # Signatures=False, WhatsApp=None (cancelled)
    ):
        res = action.execute(mock_env)
        assert res is None


def test_print_postprocessing_summary_success(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify _print_postprocessing_summary formats structured CLI box on success."""
    pkg1 = _make_dummy_package("PE STATION 1")
    pkg2 = _make_dummy_package("PE STATION 2")

    summary = PostProcessingSummary(
        processed_packages=(pkg1, pkg2),
        final_deliverables=(
            Path("C:/data/QUICK REPORT/10-08-2026/01. PE STATION 1.pdf"),
            Path("C:/data/QUICK REPORT/10-08-2026/02. PE STATION 2.pdf"),
        ),
        failed_packages=(),
        warnings=(),
        duration_seconds=12.456,
    )

    _print_postprocessing_summary(summary)
    captured = capsys.readouterr().out

    assert "1-CLICK POST-PROCESSING PIPELINE SUMMARY" in captured
    assert "Total Queued    : 2" in captured
    assert "Succeeded       : 2" in captured
    assert "Failed          : 0" in captured
    assert "Warnings        : 0" in captured
    assert "Duration        : 12.46s" in captured
    assert "FINAL DELIVERABLES:" in captured
    assert "✓ 01. PE STATION 1.pdf" in captured
    assert "✓ 02. PE STATION 2.pdf" in captured


def test_print_postprocessing_summary_with_failures_and_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify _print_postprocessing_summary formats warnings and failed substations."""
    pkg_succeed = _make_dummy_package("PE GOOD")
    pkg_fail = _make_dummy_package("PE BROKEN")

    summary = PostProcessingSummary(
        processed_packages=(pkg_succeed,),
        final_deliverables=(Path("01. PE GOOD.pdf"),),
        failed_packages=(
            PostProcessingFailure(package=pkg_fail, error="COM Conversion Timeout Error"),
        ),
        warnings=("Testsheet renaming skipped: Unmatched files exist in folder",),
        duration_seconds=8.0,
    )

    _print_postprocessing_summary(summary)
    captured = capsys.readouterr().out

    assert "1-CLICK POST-PROCESSING PIPELINE SUMMARY" in captured
    assert "Total Queued    : 2" in captured
    assert "Succeeded       : 1" in captured
    assert "Failed          : 1" in captured
    assert "Warnings        : 1" in captured
    assert "Duration        : 8.00s" in captured
    assert "FINAL DELIVERABLES:" in captured
    assert "✓ 01. PE GOOD.pdf" in captured
    assert "WARNINGS:" in captured
    assert "- Testsheet renaming skipped: Unmatched files exist in folder" in captured
    assert "FAILED SUBSTATIONS:" in captured
    assert "[FAILED] PE BROKEN: COM Conversion Timeout Error" in captured


def test_print_postprocessing_summary_none_handled_gracefully(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify _print_postprocessing_summary handles None without crashing."""
    _print_postprocessing_summary(None)  # type: ignore[arg-type]
    captured = capsys.readouterr().out
    assert captured == ""
