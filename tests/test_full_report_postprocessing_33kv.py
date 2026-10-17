"""Integration and unit tests for 33kV Full Report post-processing pipeline (Ticket #102).

Validates:
1. Multi-part target grouping (_group_multipart_targets):
   - Substation stem grouping (e.g. '06. SSU FLEXSYS CHEMICAL 33kV (VI)').
   - Ascending numerical sorting of part chunks (Part 01, Part 02, ...).
   - Standalone single-file fallback preservation (Decision Q85).
   - Substation names with internal parentheses (e.g. SSU KIIP (SSU CAMEL POWER)).
2. Phased testsheet PDF resolution (_find_pdf_in_dirs):
   - 2-digit zero-padded prefix matching (e.g. f"{prefix_num:02d}.") resolving
     testsheet '06. SSU FLEXSYS CHEMICAL 33kV.pdf' for stem '06. SSU FLEXSYS CHEMICAL 33kV (VI)' (Decision Q80).
   - Exact match resolution when signed testsheet PDF matches stem.
3. Pre-flight D43 fail-fast validation (Decision Q81):
   - Missing testsheet PDF flags target as unready in inspect().
   - Missing testsheet PDF raises TestsheetPdfNotFoundError in process(fail_fast=True) and process_single().
   - Zero-byte testsheet PDF fails validation.
4. Multi-part PDF conversion, sequential stitching, and testsheet append (Decisions Q82, Q83, Q84):
   - Sequential conversion to temporary PDFs inside shared BatchComSession.
   - Strict numerical concatenation via converter.merge_pdfs_batch().
   - Testsheet PDF appended as final section to <STEM>.pdf deliverable.
   - Automatic cleanup of intermediate .tmp_conv_* PDFs in finally block while preserving original .docx chunks (ADR 0005).
5. SubstationIsolatedBatchResiliencePolicy across multi-substation and multi-station batches.
"""

from __future__ import annotations

import logging
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
    PostProcessingTargetGroup,
    TestsheetPdfNotFoundError,
    _find_pdf_in_dirs,
    resolve_processed_testsheet_pdf_path,
    validate_processed_testsheet_pdf,
)


def _make_mock_33kv_env(tmp_path: Path) -> ProjectEnvironment:
    """Construct an isolated 33kV ProjectEnvironment rooted in tmp_path."""
    root = tmp_path / "workspace_33kv"
    root.mkdir(parents=True, exist_ok=True)
    (root / "TESTSHEET").mkdir(parents=True, exist_ok=True)
    (root / "QUICK REPORT").mkdir(parents=True, exist_ok=True)
    (root / "FULL REPORT").mkdir(parents=True, exist_ok=True)
    (root / "RAW MATERIAL").mkdir(parents=True, exist_ok=True)

    storage = LocalWorkspaceStorage(root)
    metadata = ProjectMetadata(
        key="TEST_33KV",
        name="Test 33kV Project",
        state="PAHANG",
        po_number="PO-42394550",
        year="2026",
        cycle="Cycle 4",
        voltage_type="33kV",
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


def _create_mock_docx(path: Path, content: bytes = b"mock 33kv docx content") -> Path:
    """Create a minimal mock .docx file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ==============================================================================
# 1. Multi-Part Target Grouping & Stem Extraction (Decision Q85)
# ==============================================================================

class TestMultipartTargetGrouping33kV:
    """Verify _group_multipart_targets with 33kV chunk names and standalone fallback."""

    def test_group_33kv_multipart_chunks_by_stem(self, tmp_path: Path) -> None:
        """Groups 33kV multi-part chunks by their common substation stem in ascending order."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        p4 = _create_mock_docx(folder / f"{stem} - Part 04 - TX and Condition.docx")
        p1 = _create_mock_docx(folder / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(folder / f"{stem} - Part 02 - Panel 01 (33kV - 3P5).docx")
        p3 = _create_mock_docx(folder / f"{stem} - Part 03 - Panel 02 (33kV - 3P6).docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        groups = workflow._group_multipart_targets([p4, p2, p1, p3])

        assert len(groups) == 1
        group = groups[0]
        assert group.stem == stem
        assert group.is_multipart is True
        assert group.docx_paths == (p1.resolve(), p2.resolve(), p3.resolve(), p4.resolve())
        assert group.primary_docx_path == p1.resolve()

    def test_group_preserves_standalone_single_file_fallback(self, tmp_path: Path) -> None:
        """Non-multipart 33kV reports remain single-item targets with is_multipart=False."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        standalone = _create_mock_docx(folder / "06. SSU FLEXSYS CHEMICAL 33kV (VI).docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        groups = workflow._group_multipart_targets([standalone])

        assert len(groups) == 1
        group = groups[0]
        assert group.stem == "06. SSU FLEXSYS CHEMICAL 33kV (VI)"
        assert group.is_multipart is False
        assert group.docx_paths == (standalone.resolve(),)
        assert group.primary_docx_path == standalone.resolve()

    def test_group_substation_with_internal_parentheses(self, tmp_path: Path) -> None:
        """Handles complex names with internal parentheses like '03. SSU KIIP (SSU CAMEL POWER) 33kV (US+VI)'."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        stem = "03. SSU KIIP (SSU CAMEL POWER) 33kV (US+VI)"

        p1 = _create_mock_docx(folder / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(folder / f"{stem} - Part 02 - Panel 1 (33kV - 3P1).docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        groups = workflow._group_multipart_targets([p2, p1])

        assert len(groups) == 1
        assert groups[0].stem == stem
        assert groups[0].is_multipart is True
        assert groups[0].docx_paths == (p1.resolve(), p2.resolve())

    def test_group_mixed_batch_multipart_and_standalone(self, tmp_path: Path) -> None:
        """Mixed batches group multi-part chunks while retaining standalone reports independently."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        stem1 = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"
        stem2 = "07. PMU GBID CABIN 33kV"

        p1 = _create_mock_docx(folder / f"{stem1} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(folder / f"{stem1} - Part 02 - Panel 1.docx")
        s2 = _create_mock_docx(folder / f"{stem2}.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        groups = workflow._group_multipart_targets([p2, s2, p1])

        assert len(groups) == 2
        assert groups[0].stem == stem1
        assert groups[0].is_multipart is True
        assert groups[0].docx_paths == (p1.resolve(), p2.resolve())

        assert groups[1].stem == stem2
        assert groups[1].is_multipart is False
        assert groups[1].docx_paths == (s2.resolve(),)

    def test_group_deduplicates_identical_chunk_paths(self, tmp_path: Path) -> None:
        """Duplicate input paths for the same chunk are deduplicated without double inclusion."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        p1 = _create_mock_docx(folder / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(folder / f"{stem} - Part 02 - Panel 1.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        # Pass p1 twice
        groups = workflow._group_multipart_targets([p1, p2, p1])

        assert len(groups) == 1
        assert groups[0].docx_paths == (p1.resolve(), p2.resolve())

    def test_group_suppresses_standalone_when_multipart_chunks_present(self, tmp_path: Path) -> None:
        """Standalone <STEM>.docx is suppressed when <STEM> - Part 01.docx exists for the same stem."""
        folder = tmp_path / "FULL REPORT" / "GEBENG" / "10. OCTOBER" / "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        standalone = _create_mock_docx(folder / f"{stem}.docx")
        p1 = _create_mock_docx(folder / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(folder / f"{stem} - Part 02 - Panel 01.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        # Standalone passed before multipart parts
        groups1 = workflow._group_multipart_targets([standalone, p1, p2])
        assert len(groups1) == 1
        assert groups1[0].stem == stem
        assert groups1[0].is_multipart is True
        assert groups1[0].docx_paths == (p1.resolve(), p2.resolve())
        assert standalone.resolve() not in groups1[0].docx_paths

        # Multipart parts passed before standalone
        groups2 = workflow._group_multipart_targets([p1, p2, standalone])
        assert len(groups2) == 1
        assert groups2[0].stem == stem
        assert groups2[0].is_multipart is True
        assert groups2[0].docx_paths == (p1.resolve(), p2.resolve())
        assert standalone.resolve() not in groups2[0].docx_paths

    def test_group_suppresses_standalone_end_to_end_in_process_and_inspect(self, tmp_path: Path) -> None:
        """Integration test verifying workflow.inspect() and workflow.process() suppress standalone .docx on disk."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        standalone = _create_mock_docx(fr_dir / f"{stem}.docx")
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        # Dry-run inspection
        inspection = workflow.inspect(date_str, env)
        assert len(inspection.targets) == 1
        telem = inspection.targets[0]
        assert telem.stem == stem
        assert telem.is_multipart is True
        assert telem.part_docx_paths == (p1.resolve(), p2.resolve())
        assert standalone.resolve() not in telem.part_docx_paths

        # Live post-processing execution
        result = workflow.process(date_str, env)
        assert result.is_success
        assert result.total_reports == 1
        assert result.succeeded_count == 1
        assert len(result.deliverables) == 1
        assert result.deliverables[0] == fr_dir / f"{stem}.pdf"
        assert len(fake_converter.convert_docx_calls) == 2
        assert len(fake_converter.merge_pdfs_batch_calls) == 1



# ==============================================================================
# 2. Testsheet PDF Prefix Matching (Decision Q80)
# ==============================================================================

class TestTestsheetPdfResolution33kV:
    """Verify _find_pdf_in_dirs and resolve_processed_testsheet_pdf_path for 33kV."""

    def test_find_pdf_phase2_2digit_zero_padded_prefix(self, tmp_path: Path) -> None:
        """Testsheet '06. SSU FLEXSYS CHEMICAL 33kV.pdf' resolves for stem '06. SSU FLEXSYS CHEMICAL 33kV (VI)'."""
        pdf_dir = tmp_path / "processed_testsheet" / "pdf"
        pdf_dir.mkdir(parents=True)
        # Testsheet without defect indicator
        ts_pdf = _create_mock_pdf(pdf_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        # Stem from Full Report has defect indicator (VI)
        matched = _find_pdf_in_dirs([pdf_dir], "06. SSU FLEXSYS CHEMICAL 33kV (VI)")

        assert matched is not None
        assert matched.resolve() == ts_pdf.resolve()

    def test_find_pdf_phase1_exact_match(self, tmp_path: Path) -> None:
        """When signed testsheet PDF exactly matches stem including defect suffix, exact match succeeds."""
        pdf_dir = tmp_path / "processed_testsheet" / "pdf"
        pdf_dir.mkdir(parents=True)
        ts_pdf = _create_mock_pdf(pdf_dir / "06. SSU FLEXSYS CHEMICAL 33kV (VI).pdf")

        matched = _find_pdf_in_dirs([pdf_dir], "06. SSU FLEXSYS CHEMICAL 33kV (VI)")

        assert matched is not None
        assert matched.resolve() == ts_pdf.resolve()

    def test_find_pdf_3digit_and_unpadded_compatibility(self, tmp_path: Path) -> None:
        """Prefix matching seamlessly supports 3-digit zero-padded and unpadded formats."""
        pdf_dir = tmp_path / "processed_testsheet" / "pdf"
        pdf_dir.mkdir(parents=True)
        ts1 = _create_mock_pdf(pdf_dir / "006. SSU OLD FORMAT.pdf")
        ts2 = _create_mock_pdf(pdf_dir / "7. PMU UNPADDED.pdf")

        matched1 = _find_pdf_in_dirs([pdf_dir], "06. SSU OLD FORMAT (VI)")
        assert matched1 == ts1.resolve()

        matched2 = _find_pdf_in_dirs([pdf_dir], "07. PMU UNPADDED (IR)")
        assert matched2 == ts2.resolve()

    def test_resolve_testsheet_pdf_path_from_multipart_chunk(self, tmp_path: Path) -> None:
        """resolve_processed_testsheet_pdf_path extracts stem from Part XX chunk and finds PDF."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        chunk_path = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")

        # Testsheet in processed_testsheet/pdf/
        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        ts_pdf = _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        resolved = resolve_processed_testsheet_pdf_path(chunk_path, env)
        assert resolved is not None
        assert resolved.resolve() == ts_pdf.resolve()

    def test_find_pdf_multiple_files_with_same_prefix_resolves_correct_substation(self, tmp_path: Path) -> None:
        """When multiple files share the same numerical prefix, the one matching the substation name is preferred."""
        pdf_dir = tmp_path / "processed_testsheet" / "pdf"
        pdf_dir.mkdir(parents=True)
        # SSU ALPHA comes first alphabetically, but stem is SSU FLEXSYS CHEMICAL
        ts_alpha = _create_mock_pdf(pdf_dir / "06. SSU ALPHA 33kV.pdf")
        ts_flexsys = _create_mock_pdf(pdf_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        matched = _find_pdf_in_dirs([pdf_dir], "06. SSU FLEXSYS CHEMICAL 33kV (VI)")
        assert matched is not None
        assert matched.resolve() == ts_flexsys.resolve()

    def test_find_pdf_non_dot_prefix_separators(self, tmp_path: Path) -> None:
        """Prefix matching supports underscore and space separated numerical prefixes."""
        pdf_dir = tmp_path / "processed_testsheet" / "pdf"
        pdf_dir.mkdir(parents=True)
        ts_underscore = _create_mock_pdf(pdf_dir / "06_SSU FLEXSYS CHEMICAL 33kV.pdf")

        matched = _find_pdf_in_dirs([pdf_dir], "06. SSU FLEXSYS CHEMICAL 33kV (VI)")
        assert matched is not None
        assert matched.resolve() == ts_underscore.resolve()


# ==============================================================================
# 3. Pre-Flight D43 Fail-Fast Validation (Decision Q81)
# ==============================================================================

class TestPreflightValidation33kV:
    """Verify D43 pre-flight validation behavior for 33kV Full Reports."""

    def test_inspect_marks_unready_when_testsheet_pdf_missing(self, tmp_path: Path) -> None:
        """inspect() identifies missing signed testsheet PDF and marks target unready."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        inspection = workflow.inspect(date_str, env)

        assert len(inspection.targets) == 1
        telem = inspection.targets[0]
        assert telem.stem == stem
        assert telem.is_ready is False
        assert telem.is_testsheet_pdf_valid is False
        assert "Pre-existing testsheet PDF missing" in telem.errors[0]
        assert len(inspection.ready_targets) == 0
        assert len(inspection.unready_targets) == 1

    def test_process_raises_testsheet_pdf_not_found_on_fail_fast(self, tmp_path: Path) -> None:
        """process(fail_fast=True) raises TestsheetPdfNotFoundError when testsheet PDF missing."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        with pytest.raises(TestsheetPdfNotFoundError) as exc_info:
            workflow.process(date_str, env, fail_fast=True)

        assert "Pre-existing testsheet PDF missing" in str(exc_info.value)
        assert stem in str(exc_info.value)

    def test_process_single_raises_on_missing_testsheet(self, tmp_path: Path) -> None:
        """process_single() strictly raises TestsheetPdfNotFoundError when testsheet PDF missing."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        with pytest.raises(TestsheetPdfNotFoundError):
            workflow.process_single(p1, env)

    def test_zero_byte_testsheet_pdf_rejected(self, tmp_path: Path) -> None:
        """0-byte testsheet PDF fails validation and is rejected."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        ts_dir.mkdir(parents=True)
        empty_ts = ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf"
        empty_ts.write_bytes(b"")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        inspection = workflow.inspect(date_str, env)

        assert len(inspection.targets) == 1
        telem = inspection.targets[0]
        assert telem.is_ready is False
        assert "0 bytes" in telem.errors[0]


# ==============================================================================
# 4. Multi-Part PDF Conversion, Stitching & Deliverable Concatenation (Q82-Q84)
# ==============================================================================

class TestMultipartPostProcessingExecution33kV:
    """End-to-end execution of 33kV multi-part PDF conversion, stitching, and testsheet merge."""

    def test_process_multipart_conversion_and_deliverable_concatenation(self, tmp_path: Path) -> None:
        """Sequential conversion, batch merge of parts, testsheet append, and cleanup."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01 (33kV - 3P5).docx")
        p3 = _create_mock_docx(fr_dir / f"{stem} - Part 03 - Panel 02 (33kV - 3P6).docx")
        p4 = _create_mock_docx(fr_dir / f"{stem} - Part 04 - TX and Condition.docx")

        # 33kV signed testsheet PDF (3 sheets / pages)
        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        ts_pdf = _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf", page_count=3)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process(date_str, env)

        assert result.is_success
        assert result.total_reports == 1
        assert result.succeeded_count == 1
        assert result.failed_count == 0
        assert len(result.deliverables) == 1

        # Deliverable saved to FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf (Decision Q83)
        expected_deliverable = fr_dir / f"{stem}.pdf"
        assert result.deliverables[0] == expected_deliverable
        assert expected_deliverable.exists()

        # 1. Converted each part to temporary PDF in sequence
        assert len(fake_converter.convert_docx_calls) == 4
        assert fake_converter.convert_docx_calls[0][0] == p1.resolve()
        assert fake_converter.convert_docx_calls[1][0] == p2.resolve()
        assert fake_converter.convert_docx_calls[2][0] == p3.resolve()
        assert fake_converter.convert_docx_calls[3][0] == p4.resolve()

        expected_temp_p1 = fr_dir / f".tmp_conv_{stem}_part_01.pdf"
        expected_temp_p2 = fr_dir / f".tmp_conv_{stem}_part_02.pdf"
        expected_temp_p3 = fr_dir / f".tmp_conv_{stem}_part_03.pdf"
        expected_temp_p4 = fr_dir / f".tmp_conv_{stem}_part_04.pdf"
        expected_master = fr_dir / f".tmp_conv_{stem}_master.pdf"

        # 2. Batch merged all 4 parts in numerical order into master PDF
        assert len(fake_converter.merge_pdfs_batch_calls) == 1
        parts_merged, master_out = fake_converter.merge_pdfs_batch_calls[0]
        assert tuple(parts_merged) == (
            expected_temp_p1,
            expected_temp_p2,
            expected_temp_p3,
            expected_temp_p4,
        )
        assert master_out == expected_master

        # 3. Master PDF merged with signed testsheet PDF -> final deliverable
        assert len(fake_converter.merge_pdfs_calls) == 1
        primary, secondary, final_out = fake_converter.merge_pdfs_calls[0]
        assert primary == expected_master
        assert secondary == ts_pdf.resolve()
        assert final_out == expected_deliverable

        # 4. Verified page count: 4 parts (1 page each) + 3 testsheet pages = 7 pages
        reader = PdfReader(str(expected_deliverable))
        assert len(reader.pages) == 7

        # 5. Temporary intermediate PDFs cleaned up in finally block (Decision Q82)
        assert not expected_temp_p1.exists()
        assert not expected_temp_p2.exists()
        assert not expected_temp_p3.exists()
        assert not expected_temp_p4.exists()
        assert not expected_master.exists()

        # 6. Original docx chunks strictly preserved permanently per ADR 0005
        assert p1.exists()
        assert p2.exists()
        assert p3.exists()
        assert p4.exists()

    def test_process_single_multipart_substation(self, tmp_path: Path) -> None:
        """process_single() on Part 01 chunk automatically discovers siblings, converts, and merges."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        ts_pdf = _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf", page_count=2)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        deliverable = workflow.process_single(p1, env)

        assert deliverable == fr_dir / f"{stem}.pdf"
        assert deliverable.exists()
        assert len(fake_converter.convert_docx_calls) == 2
        assert len(fake_converter.merge_pdfs_batch_calls) == 1
        assert len(fake_converter.merge_pdfs_calls) == 1
        assert p1.exists() and p2.exists()

    def test_process_single_establishes_batch_session(self, tmp_path: Path) -> None:
        """process_single() establishes batch COM session context to reuse Word instance across chunks."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        mock_session_cm = MagicMock()
        mock_active_session = MagicMock()
        mock_active_session.word_app = MagicMock()
        mock_session_cm.__enter__.return_value = mock_active_session
        workflow._establish_batch_session = MagicMock(return_value=mock_session_cm)

        workflow.process_single(p1, env)

        workflow._establish_batch_session.assert_called_once_with(None)
        mock_session_cm.__enter__.assert_called_once()
        mock_session_cm.__exit__.assert_called_once()

    def test_establish_batch_session_wraps_explicit_session_in_nullcontext(self) -> None:
        """Explicit session is wrapped in nullcontext so entering/exiting does not terminate outer COM session."""
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        mock_session = MagicMock()
        mock_session.__exit__ = MagicMock()

        session_cm = workflow._establish_batch_session(mock_session)
        with session_cm as active:
            assert active is mock_session

        mock_session.__exit__.assert_not_called()

    def test_process_with_explicit_com_session_does_not_terminate_outer_session(self, tmp_path: Path) -> None:
        """process() with explicit com_session does not invoke __exit__ on caller's active session."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        mock_session = MagicMock()
        mock_session.__exit__ = MagicMock()

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        result = workflow.process(date_str, env, com_session=mock_session)

        assert result.is_success
        mock_session.__exit__.assert_not_called()

    def test_process_single_with_explicit_session_does_not_terminate_outer_session(self, tmp_path: Path) -> None:
        """process_single() with session does not invoke __exit__ on caller's active session."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        mock_session = MagicMock()
        mock_session.__exit__ = MagicMock()

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        deliverable = workflow.process_single(p1, env, session=mock_session)

        assert deliverable.exists()
        mock_session.__exit__.assert_not_called()

    def test_cleanup_on_conversion_crash(self, tmp_path: Path) -> None:
        """If COM conversion crashes midway, temporary PDFs are cleaned up and original chunks remain."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        p2 = _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        fake_converter = FakeDocumentConverter()

        def _crashing_converter(docx: Path, pdf: Path, **kwargs: object) -> Path:
            pdf.write_bytes(b"temp")
            if "Part 02" in str(docx):
                raise RuntimeError("Simulated COM conversion crash on Part 02")
            return pdf

        fake_converter.convert_docx_to_pdf = _crashing_converter  # type: ignore[method-assign]

        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)
        result = workflow.process(date_str, env, fail_fast=False)

        assert result.failed_count == 1
        assert "Simulated COM conversion crash on Part 02" in result.errors[0]

        # Temporary files unlinked
        temp_p1 = fr_dir / f".tmp_conv_{stem}_part_01.pdf"
        temp_p2 = fr_dir / f".tmp_conv_{stem}_part_02.pdf"
        master_pdf = fr_dir / f".tmp_conv_{stem}_master.pdf"
        assert not temp_p1.exists()
        assert not temp_p2.exists()
        assert not master_pdf.exists()

        # Original chunks preserved
        assert p1.exists()
        assert p2.exists()


# ==============================================================================
# 5. Multi-Substation / Multi-Station Batch Resilience
# ==============================================================================

class TestMultiSubstationBatchResilience33kV:
    """Verify batch processing across multiple 33kV substations and stations."""

    def test_multi_station_batch_processes_both_stations(self, tmp_path: Path) -> None:
        """Processes 33kV Full Reports across multiple station folders for the same date."""
        env = _make_mock_33kv_env(tmp_path)
        month = "10. OCTOBER"
        date_str = "07-10-2026"

        # Station 1: GEBENG (multi-part)
        st1 = "GEBENG"
        stem1 = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"
        fr1 = env.get_full_report_dir() / st1 / month / date_str
        p1_1 = _create_mock_docx(fr1 / f"{stem1} - Part 01 - Summary.docx")
        p1_2 = _create_mock_docx(fr1 / f"{stem1} - Part 02 - Panel 01.docx")
        ts1_dir = env.get_testsheet_dir() / st1 / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts1_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf", page_count=2)

        # Station 2: KUANTAN (standalone fallback)
        st2 = "KUANTAN"
        stem2 = "07. PMU GBID CABIN 33kV"
        fr2 = env.get_full_report_dir() / st2 / month / date_str
        s2 = _create_mock_docx(fr2 / f"{stem2}.docx")
        ts2_dir = env.get_testsheet_dir() / st2 / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts2_dir / "07. PMU GBID CABIN 33kV.pdf", page_count=2)

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process(date_str, env)

        assert result.is_success
        assert result.total_reports == 2
        assert result.succeeded_count == 2
        assert result.failed_count == 0
        assert len(result.deliverables) == 2

        assert (fr1 / f"{stem1}.pdf") in result.deliverables
        assert (fr2 / f"{stem2}.pdf") in result.deliverables
        assert p1_1.exists() and p1_2.exists() and s2.exists()

    def test_partial_failure_isolation_in_batch(self, tmp_path: Path) -> None:
        """One substation missing testsheet does not halt processing of other valid substations."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        fr_dir = env.get_full_report_dir() / station / month / date_str

        # Substation 1: Valid with testsheet
        stem1 = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"
        _create_mock_docx(fr_dir / f"{stem1} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem1} - Part 02 - Panel 01.docx")
        ts1_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts1_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf", page_count=2)

        # Substation 2: Missing testsheet
        stem2 = "08. SSU PETROPIPE 33kV"
        _create_mock_docx(fr_dir / f"{stem2} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem2} - Part 02 - Panel 01.docx")

        fake_converter = FakeDocumentConverter()
        workflow = FullReportPostProcessingWorkflow(converter=fake_converter)

        result = workflow.process(date_str, env, fail_fast=False)

        assert result.total_reports == 2
        assert result.succeeded_count == 1
        assert result.failed_count == 1
        assert len(result.deliverables) == 1
        assert result.deliverables[0] == fr_dir / f"{stem1}.pdf"
        assert any("Pre-existing testsheet PDF missing" in err for err in result.errors)


# ==============================================================================
# 6. Target Document Discovery & Error Handling (Finding 3)
# ==============================================================================

class TestDiscoverDocxFiles33kV:
    """Verify discovery error handling and multipart expansion in _discover_docx_files."""

    def test_discover_missing_docx_file_path_appends_error(self, tmp_path: Path) -> None:
        """Nonexistent Path target ending with .docx returns empty list and specific error message."""
        env = _make_mock_33kv_env(tmp_path)
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        missing_p = tmp_path / "nonexistent_substation.docx"
        files, warnings, errors = workflow._discover_docx_files(missing_p, env)

        assert files == []
        assert any(f"Target file does not exist: {missing_p}" in e for e in errors)

    def test_discover_missing_docx_file_string_appends_error(self, tmp_path: Path) -> None:
        """Nonexistent string target ending with .docx returns empty list and specific error message."""
        env = _make_mock_33kv_env(tmp_path)
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        missing_s = str(tmp_path / "nonexistent_substation.docx")
        files, warnings, errors = workflow._discover_docx_files(missing_s, env)

        assert files == []
        assert any(f"Target file does not exist: {missing_s}" in e for e in errors)

    def test_discover_sequence_with_missing_docx_appends_error(self, tmp_path: Path) -> None:
        """Sequence target containing missing .docx records an error while discovering valid files."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        missing_p = tmp_path / "nonexistent_substation.docx"

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        files, warnings, errors = workflow._discover_docx_files([p1, missing_p], env)

        assert p1.resolve() in files
        assert any(f"Target file does not exist: {missing_p}" in e for e in errors)

    def test_discover_path_date_folder_matches_reports(self, tmp_path: Path) -> None:
        """Target passed as Path('07-10-2026') correctly resolves reports matching calendar date."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem}.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        files, warnings, errors = workflow._discover_docx_files(Path(date_str), env)

        assert len(files) == 1
        assert files[0] == p1.resolve()
        assert errors == []

    def test_discover_path_directory_applies_station_filter(self, tmp_path: Path) -> None:
        """Target passed as directory Path respects station filtering."""
        env = _make_mock_33kv_env(tmp_path)
        month = "10. OCTOBER"
        date_str = "07-10-2026"

        fr_g = env.get_full_report_dir() / "GEBENG" / month / date_str
        fr_k = env.get_full_report_dir() / "KUANTAN" / month / date_str
        p_g = _create_mock_docx(fr_g / "06. SSU FLEXSYS.docx")
        _create_mock_docx(fr_k / "07. PMU GBID.docx")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        # Inspect parent directory covering both stations
        parent_dir = env.get_full_report_dir()
        files_g, _, _ = workflow._discover_docx_files(parent_dir, env, station="GEBENG")
        assert len(files_g) == 1
        assert files_g[0] == p_g.resolve()



# ==============================================================================
# 7. Testsheet Data Resolution & Audio Embedding Hook (Findings 1 & 4)
# ==============================================================================

class TestTestsheetDataResolutionAndAudioHook33kV:
    """Verify testsheet data resolution traversal fallback and sound embedding hook for 33kV."""

    def test_resolve_testsheet_data_traversal_fallback_ascends_to_date_folder(self, tmp_path: Path) -> None:
        """Fallback traversal ascends past 'pdf' and 'processed_testsheet' to date folder to locate .xlsx."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        # Set up full report docx
        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        group = PostProcessingTargetGroup(stem=stem, docx_paths=(p1,), is_multipart=True)

        # Set up testsheet PDF at TESTSHEET/GEBENG/10. OCTOBER/07-10-2026/processed_testsheet/pdf/
        ts_pdf_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        ts_pdf = _create_mock_pdf(ts_pdf_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        # Place raw testsheet .xlsx at TESTSHEET/GEBENG/10. OCTOBER/07-10-2026/
        # (NOT in processed_testsheet, requiring the while loop to ascend 2 levels)
        raw_ts_dir = env.get_testsheet_dir() / station / month / date_str
        raw_ts_xlsx = raw_ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.xlsx"
        raw_ts_xlsx.write_bytes(b"mock xlsx content")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        mock_extracted = MagicMock()
        with patch("src.testsheet.extractor.TestsheetExtractor") as mock_extractor_cls:
            mock_extractor_instance = MagicMock()
            mock_extractor_instance.extract_testsheet_data.return_value = mock_extracted
            mock_extractor_cls.return_value = mock_extractor_instance

            # Ensure storage seam returns None so fallback #2 is exercised
            with patch.object(env.storage, "get_substation_testsheet_path", return_value=None):
                result = workflow._resolve_testsheet_data_for_group(group, env, testsheet_pdf_path=ts_pdf)

            assert result == mock_extracted
            # Verify TestsheetExtractor was instantiated with 33kV voltage_type from metadata
            mock_extractor_cls.assert_called_once_with(voltage_type="33kV")
            mock_extractor_instance.extract_testsheet_data.assert_called_once_with(raw_ts_xlsx)

    def test_audio_embedding_hook_invoked_when_us_tev_raw_data_present(self, tmp_path: Path) -> None:
        """When US+TEV raw material exists, sound embedding is invoked with resolved package."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")
        _create_mock_docx(fr_dir / f"{stem} - Part 02 - Panel 01.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        # Create raw survey dir with survey_summary.js marker
        raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / "006. SSU FLEXSYS" / "RAW DATA" / "US+TEV"
        raw_sub_dir.mkdir(parents=True, exist_ok=True)
        (raw_sub_dir / "survey_summary.js").write_text("// test", encoding="utf-8")
        (raw_sub_dir / "test.wav").write_bytes(b"RIFFmockwavdata")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        mock_ts_pkg = MagicMock()
        with patch.object(workflow, "_resolve_testsheet_data_for_group", return_value=mock_ts_pkg), \
             patch("src.workflows.full_report_postprocessing.embed_survey_ultrasound_into_pdf", return_value=2) as mock_embed:
            result = workflow.process(date_str, env)

        assert result.is_success
        assert len(result.deliverables) == 1
        mock_embed.assert_called_once()
        _, kwargs = mock_embed.call_args
        assert kwargs.get("package") == mock_ts_pkg

    def test_audio_embedding_resilience_on_failure(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Sound embedding exception is caught and logged as warning without failing post-processing."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem = "06. SSU FLEXSYS CHEMICAL 33kV (VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        _create_mock_docx(fr_dir / f"{stem} - Part 01 - Summary.docx")

        ts_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_dir / "06. SSU FLEXSYS CHEMICAL 33kV.pdf")

        raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / "006. SSU FLEXSYS" / "RAW DATA" / "US+TEV"
        raw_sub_dir.mkdir(parents=True, exist_ok=True)
        (raw_sub_dir / "survey_summary.js").write_text("// test", encoding="utf-8")
        (raw_sub_dir / "test.wav").write_bytes(b"RIFFmockwavdata")

        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        with patch("src.workflows.full_report_postprocessing.embed_survey_ultrasound_into_pdf", side_effect=RuntimeError("Corrupt audio stream")):
            with caplog.at_level(logging.WARNING):
                result = workflow.process(date_str, env)

        assert result.is_success
        assert len(result.deliverables) == 1
        assert "Sound embedding failed" in caplog.text

    def test_substation_stem_internal_parentheses_disambiguation(self, tmp_path: Path) -> None:
        """Stems with internal parentheses (e.g. '03. SSU KIIP (SSU CAMEL POWER) 33kV (US+VI)')
        correctly disambiguate matching testsheets and PDFs from identically-prefixed substations
        (e.g. '03. SSU KIIP 11kV')."""
        env = _make_mock_33kv_env(tmp_path)
        station = "GEBENG"
        month = "10. OCTOBER"
        date_str = "07-10-2026"
        stem_33kv = "03. SSU KIIP (SSU CAMEL POWER) 33kV (US+VI)"

        fr_dir = env.get_full_report_dir() / station / month / date_str
        p1 = _create_mock_docx(fr_dir / f"{stem_33kv} - Part 01 - Summary.docx")
        group = PostProcessingTargetGroup(stem=stem_33kv, docx_paths=(p1,), is_multipart=True)

        # Create two competing testsheet PDFs: 11kV sorts first alphabetically
        ts_pdf_dir = env.get_testsheet_dir() / station / month / date_str / "processed_testsheet" / "pdf"
        _create_mock_pdf(ts_pdf_dir / "03. SSU KIIP 11kV.pdf")
        ts_pdf_33kv = _create_mock_pdf(ts_pdf_dir / "03. SSU KIIP (SSU CAMEL POWER) 33kV.pdf")

        # Create two competing testsheet workbooks: 11kV sorts first alphabetically
        raw_ts_dir = env.get_testsheet_dir() / station / month / date_str
        (raw_ts_dir / "03. SSU KIIP 11kV.xlsx").write_bytes(b"mock 11kv xlsx")
        ts_xlsx_33kv = raw_ts_dir / "03. SSU KIIP (SSU CAMEL POWER) 33kV.xlsx"
        ts_xlsx_33kv.write_bytes(b"mock 33kv xlsx")

        # 1. Test PDF resolution via _find_pdf_in_dirs
        matched_pdf = _find_pdf_in_dirs([ts_pdf_dir], stem_33kv)
        assert matched_pdf is not None
        assert matched_pdf.resolve() == ts_pdf_33kv.resolve()

        # 2. Test testsheet data resolution via _resolve_testsheet_data_for_group
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())
        with patch("src.testsheet.extractor.TestsheetExtractor") as mock_extractor_cls:
            mock_extractor_instance = MagicMock()
            mock_extractor_cls.return_value = mock_extractor_instance
            with patch.object(env.storage, "get_substation_testsheet_path", return_value=None):
                workflow._resolve_testsheet_data_for_group(group, env, testsheet_pdf_path=ts_pdf_33kv)

            mock_extractor_instance.extract_testsheet_data.assert_called_once_with(ts_xlsx_33kv)

        # 3. Test inspect() telemetry preserves full substation name
        telemetry = workflow._inspect_single_report(group, env)
        assert telemetry.substation_name == "SSU KIIP (SSU CAMEL POWER) 33kV"

    def test_resolve_testsheet_data_traversal_root_termination(self, tmp_path: Path) -> None:
        """Directory traversal fallback terminates safely even if ts_dir reaches root path."""
        env = _make_mock_33kv_env(tmp_path)
        group = PostProcessingTargetGroup(
            stem="06. SSU FLEXSYS",
            docx_paths=(tmp_path / "dummy.docx",),
            is_multipart=False,
        )
        workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

        # Point testsheet_pdf_path to root-like path
        fake_pdf = Path(tmp_path.anchor) / "pdf" / "dummy.pdf"
        with patch.object(Path, "exists", return_value=True):
            # Should not hang or loop infinitely
            result = workflow._resolve_testsheet_data_for_group(group, env, testsheet_pdf_path=fake_pdf)
            assert result is None

