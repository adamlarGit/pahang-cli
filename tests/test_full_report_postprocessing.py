"""Unit tests for FullReportPostProcessingWorkflow (Ticket #36 / T6.3).

Decisions and Architectural Policies Enforced:
- D42: Decoupled two-stage architecture: FullReportPostProcessingWorkflow converts finalized Full Report .docx
  to .pdf and merges with testsheet PDF.
- D43: Testsheet PDF reuse: strictly reuses pre-existing testsheet PDF from processed_testsheet/pdf/<stem>.pdf.
  Fails fast with clear diagnostic if testsheet PDF is missing.
- D45: Virtual printer configuration (configure_uniform_printer) and A4 fixed format export.
- SubstationIsolatedBatchResiliencePolicy: individual substation failures are captured in result.errors
  without halting the entire batch.
- Seam: Swappable DocumentConverter (ComDocumentConverter vs FakeDocumentConverter).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PyPDF2 import PdfReader, PdfWriter

from src.postprocessing.converters import FakeDocumentConverter
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingInspection,
    FullReportPostProcessingResult,
    FullReportPostProcessingTelemetry,
    FullReportPostProcessingWorkflow,
    TestsheetPdfNotFoundError,
    TestsheetPdfValidationResult,
    resolve_processed_testsheet_pdf_path,
    validate_processed_testsheet_pdf,
)


def _make_mock_env(tmp_path: Path) -> ProjectEnvironment:
    """Construct a minimal ProjectEnvironment rooted in tmp_path."""
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    (root / "TESTSHEET").mkdir(parents=True, exist_ok=True)
    (root / "QUICK REPORT").mkdir(parents=True, exist_ok=True)
    (root / "FULL REPORT").mkdir(parents=True, exist_ok=True)

    storage = LocalWorkspaceStorage(root)
    metadata = ProjectMetadata(
        key="TEST_PROJ",
        name="Test Project",
        state="PAHANG",
        po_number="PO123456",
        year="2026",
        cycle="1",
        voltage_type="11kV",
        technologies=("IR", "US", "TEV"),
        base_path=str(root),
    )
    return ProjectEnvironment(metadata=metadata, storage=storage)


def _create_mock_pdf(path: Path, page_count: int = 1) -> Path:
    """Create a minimal valid PDF file with PyPDF2."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _create_mock_docx(path: Path, content: bytes = b"mock docx content") -> Path:
    """Create a minimal mock .docx file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ==============================================================================
# 1. Pre-Flight Testsheet PDF Validation (D43)
# ==============================================================================

class TestTestsheetPdfValidation:
    """Tests for validate_processed_testsheet_pdf per D43."""

    def test_validate_missing_pdf_returns_invalid_result(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "processed_testsheet" / "pdf" / "005. TALAPIA (IR+VI).pdf"
        result = validate_processed_testsheet_pdf(
            missing_path, stem="005. TALAPIA (IR+VI)", raise_on_error=False
        )

        assert not result.is_valid
        assert not result.exists
        assert "processed_testsheet/pdf/" in result.error_message
        assert "Quick Report post-processing" in result.error_message

    def test_validate_missing_pdf_raises_when_raise_on_error(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "processed_testsheet" / "pdf" / "005. TALAPIA (IR+VI).pdf"

        with pytest.raises(TestsheetPdfNotFoundError) as exc_info:
            validate_processed_testsheet_pdf(
                missing_path, stem="005. TALAPIA (IR+VI)", raise_on_error=True
            )

        assert "Pre-existing testsheet PDF missing" in str(exc_info.value)
        assert "005. TALAPIA (IR+VI)" in str(exc_info.value)

    def test_validate_zero_byte_pdf_fails(self, tmp_path: Path) -> None:
        empty_pdf = tmp_path / "processed_testsheet" / "pdf" / "005. TALAPIA (IR+VI).pdf"
        empty_pdf.parent.mkdir(parents=True, exist_ok=True)
        empty_pdf.write_bytes(b"")

        result = validate_processed_testsheet_pdf(
            empty_pdf, stem="005. TALAPIA (IR+VI)", raise_on_error=False
        )

        assert not result.is_valid
        assert result.exists
        assert "0 bytes" in result.error_message

    def test_validate_valid_pdf_succeeds(self, tmp_path: Path) -> None:
        valid_pdf = tmp_path / "processed_testsheet" / "pdf" / "005. TALAPIA (IR+VI).pdf"
        _create_mock_pdf(valid_pdf, page_count=2)

        result = validate_processed_testsheet_pdf(
            valid_pdf, stem="005. TALAPIA (IR+VI)", raise_on_error=True
        )

        assert result.is_valid
        assert result.exists
        assert result.size_bytes > 0
        assert result.error_message is None


# ==============================================================================
# 2. Testsheet PDF Resolution Tests
# ==============================================================================

class TestTestsheetPdfResolution:
    """Tests for resolve_processed_testsheet_pdf_path."""

    def test_resolve_exact_match(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        station = "RAUB"
        month = "08. AUGUST"
        date_str = "04-08-2026"
        stem = "005. TALAPIA (IR+VI)"

        docx_path = env.get_full_report_dir() / station / month / date_str / f"{stem}.docx"
        _create_mock_docx(docx_path)

        ts_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / f"{stem}.pdf"
        _create_mock_pdf(ts_pdf)

        resolved = resolve_processed_testsheet_pdf_path(docx_path, env)
        assert resolved is not None
        assert resolved.resolve() == ts_pdf.resolve()

    def test_resolve_numerical_prefix_match(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        station = "KUANTAN"
        month = "08. AUGUST"
        date_str = "28-08-2026"

        docx_path = env.get_full_report_dir() / station / month / date_str / "179. CENDERAWASIH NO.1 (IR+VI).docx"
        _create_mock_docx(docx_path)

        # Testsheet PDF named with raw prefix e.g. "179. CENDERAWASIH NO.1.pdf"
        ts_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / "179. CENDERAWASIH NO.1.pdf"
        _create_mock_pdf(ts_pdf)

        resolved = resolve_processed_testsheet_pdf_path(docx_path, env)
        assert resolved is not None
        assert resolved.resolve() == ts_pdf.resolve()

    def test_resolve_missing_returns_none(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)

        resolved = resolve_processed_testsheet_pdf_path(docx_path, env)
        assert resolved is None


# ==============================================================================
# 3. Dry-Run Inspection Tests
# ==============================================================================

class TestFullReportPostProcessingInspection:
    """Tests for FullReportPostProcessingWorkflow.inspect()."""

    def test_inspect_ready_and_unready_targets(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        station = "RAUB"
        month = "08. AUGUST"
        date_str = "04-08-2026"

        # Station 1: Ready (has testsheet PDF)
        s1_docx = env.get_full_report_dir() / station / month / date_str / "005. TALAPIA (IR+VI).docx"
        _create_mock_docx(s1_docx)
        s1_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / "005. TALAPIA (IR+VI).pdf"
        _create_mock_pdf(s1_pdf)

        # Station 2: Unready (missing testsheet PDF)
        s2_docx = env.get_full_report_dir() / station / month / date_str / "006. CHEROH (IR).docx"
        _create_mock_docx(s2_docx)

        converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=converter)

        inspection = workflow.inspect(date_str, env)

        assert len(inspection.targets) == 2
        assert inspection.total_count == 2
        assert inspection.ready_count == 1
        assert len(inspection.unready_targets) == 1

        ready = inspection.ready_targets[0]
        assert ready.stem == "005. TALAPIA (IR+VI)"
        assert ready.substation_number == 5
        assert ready.is_ready
        assert ready.testsheet_pdf_path == s1_pdf.resolve()

        unready = inspection.unready_targets[0]
        assert unready.stem == "006. CHEROH (IR)"
        assert not unready.is_ready
        assert "processed_testsheet/pdf/" in unready.errors[0]

        # Ensure inspect() performed ZERO converter calls
        assert len(converter.convert_docx_calls) == 0
        assert len(converter.merge_pdfs_calls) == 0

    def test_inspect_station_filtering(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        d_raub = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        d_ktn = env.get_full_report_dir() / "KUANTAN" / "08. AUGUST" / "04-08-2026" / "179. CENDERAWASIH.docx"
        _create_mock_docx(d_raub)
        _create_mock_docx(d_ktn)

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        inspection = workflow.inspect("04-08-2026", env, station="RAUB")

        assert len(inspection.targets) == 1
        assert inspection.targets[0].station == "RAUB"


# ==============================================================================
# 4. Execution & Swappable Converter Seam Tests
# ==============================================================================

class TestFullReportPostProcessingExecution:
    """Tests for FullReportPostProcessingWorkflow.process() with FakeDocumentConverter."""

    def test_process_single_success(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        station = "RAUB"
        month = "08. AUGUST"
        date_str = "04-08-2026"
        stem = "005. TALAPIA (IR+VI)"

        docx_path = env.get_full_report_dir() / station / month / date_str / f"{stem}.docx"
        _create_mock_docx(docx_path)

        ts_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / f"{stem}.pdf"
        _create_mock_pdf(ts_pdf, page_count=2)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process(docx_path, env)

        assert result.is_success
        assert result.succeeded_count == 1
        assert result.failed_count == 0
        assert len(result.deliverables) == 1

        deliverable = result.deliverables[0]
        assert deliverable.name == f"{stem}.pdf"
        assert deliverable.parent == docx_path.parent
        assert deliverable.exists()

        # Check FakeDocumentConverter call tracking
        assert len(fake_converter.convert_docx_calls) == 1
        assert fake_converter.convert_docx_calls[0][0] == docx_path.resolve()
        assert len(fake_converter.merge_pdfs_calls) == 1

    def test_process_merges_full_report_and_testsheet_pdf(self, tmp_path: Path) -> None:
        """Verify the deliverable PDF combines pages from both inputs."""
        env = _make_mock_env(tmp_path)
        station = "RAUB"
        month = "08. AUGUST"
        date_str = "04-08-2026"
        stem = "005. TALAPIA (IR+VI)"

        docx_path = env.get_full_report_dir() / station / month / date_str / f"{stem}.docx"
        _create_mock_docx(docx_path)

        ts_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / f"{stem}.pdf"
        _create_mock_pdf(ts_pdf, page_count=2)  # 2 testsheet pages

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process(docx_path, env)
        assert result.is_success

        deliverable = result.deliverables[0]
        reader = PdfReader(str(deliverable))
        # FakeDocumentConverter generates 1 page for docx, and 2 pages from ts_pdf -> 3 total pages
        assert len(reader.pages) == 3

    def test_process_missing_testsheet_fails_fast_on_fail_fast(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        with pytest.raises(TestsheetPdfNotFoundError) as exc_info:
            workflow.process(docx_path, env, fail_fast=True)

        assert "Pre-existing testsheet PDF missing" in str(exc_info.value)
        assert "005. TALAPIA" in str(exc_info.value)

    def test_batch_resilience_isolates_failures(self, tmp_path: Path) -> None:
        """SubstationIsolatedBatchResiliencePolicy: unready station fails, healthy station succeeds."""
        env = _make_mock_env(tmp_path)
        station = "RAUB"
        month = "08. AUGUST"
        date_str = "04-08-2026"

        # Station 1: healthy
        s1_docx = env.get_full_report_dir() / station / month / date_str / "001. STATION ONE.docx"
        _create_mock_docx(s1_docx)
        s1_pdf = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf" / "001. STATION ONE.pdf"
        _create_mock_pdf(s1_pdf, page_count=1)

        # Station 2: missing testsheet PDF
        s2_docx = env.get_full_report_dir() / station / month / date_str / "002. STATION TWO.docx"
        _create_mock_docx(s2_docx)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process("04-08-2026", env, fail_fast=False)

        assert result.total_reports == 2
        assert result.succeeded_count == 1
        assert result.failed_count == 1
        assert len(result.deliverables) == 1
        assert result.deliverables[0].name == "001. STATION ONE.pdf"
        assert len(result.errors) == 1
        assert "Pre-existing testsheet PDF missing" in result.errors[0]

    def test_progress_sink_invoked(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)
        ts_pdf = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "processed_testsheet" / "pdf" / "005. TALAPIA.pdf"
        _create_mock_pdf(ts_pdf)

        progress_messages: list[str] = []
        sink = progress_messages.append

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        workflow.process(docx_path, env, progress_sink=sink)

        assert len(progress_messages) > 0
        assert any("005. TALAPIA" in m for m in progress_messages)

    def test_process_with_custom_output_dir(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)
        ts_pdf = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "processed_testsheet" / "pdf" / "005. TALAPIA.pdf"
        _create_mock_pdf(ts_pdf)

        custom_out = tmp_path / "custom_output"
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        result = workflow.process(docx_path, env, output_dir=custom_out)

        assert result.is_success
        assert result.deliverables[0].parent == custom_out
        assert result.deliverables[0].name == "005. TALAPIA.pdf"
        assert result.deliverables[0].exists()

    def test_process_single_direct_call(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)
        ts_pdf = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "processed_testsheet" / "pdf" / "005. TALAPIA.pdf"
        _create_mock_pdf(ts_pdf)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)
        output_pdf = workflow.process_single(docx_path, env)

        assert output_pdf.exists()
        assert output_pdf.name == "005. TALAPIA.pdf"
        assert len(fake_converter.convert_docx_calls) == 1
        assert len(fake_converter.merge_pdfs_calls) == 1

    def test_temp_file_cleanup_on_conversion_failure(self, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)
        ts_pdf = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "processed_testsheet" / "pdf" / "005. TALAPIA.pdf"
        _create_mock_pdf(ts_pdf)

        fake_converter = FakeDocumentConverter()

        def _exploding_convert(docx: Path, pdf: Path, **kwargs: object) -> Path:
            pdf.write_bytes(b"partial temp pdf")
            raise RuntimeError("Word COM export crashed")

        fake_converter.convert_docx_to_pdf = _exploding_convert  # type: ignore[method-assign]

        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)
        result = workflow.process(docx_path, env)

        assert result.failed_count == 1
        assert "Word COM export crashed" in result.errors[0]
        # Verify temporary conversion file was cleanly unlinked in finally block
        temp_pdf = docx_path.parent / f".tmp_conv_{docx_path.stem}.pdf"
        assert not temp_pdf.exists()

    @patch("src.workflows.full_report_postprocessing.configure_uniform_printer")
    def test_configure_uniform_printer_called(self, mock_printer: MagicMock, tmp_path: Path) -> None:
        env = _make_mock_env(tmp_path)
        docx_path = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "005. TALAPIA.docx"
        _create_mock_docx(docx_path)
        ts_pdf = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / "04-08-2026" / "processed_testsheet" / "pdf" / "005. TALAPIA.pdf"
        _create_mock_pdf(ts_pdf)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        mock_session = MagicMock()
        mock_word = MagicMock()
        mock_session.word_app = mock_word
        mock_session.__enter__.return_value = mock_session
        mock_session.__exit__.return_value = None

        workflow.process(docx_path, env, com_session=mock_session)
        mock_printer.assert_called_once_with(mock_word)
