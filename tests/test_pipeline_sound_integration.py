"""Pipeline integration tests for automatic post-processing sound embedding.

Verifies post-merge sound embedding hooks in:
1. FullReportPostProcessingWorkflow._compile_deliverable
2. PostProcessingPipelineWorkflow.execute (Quick Report)

Adheres to:
- UsTevAudioResiliencePolicy (missing survey data logs and skips cleanly without error)
- IdempotentSoundEmbeddingPolicy (multiple passes do not duplicate annotations)
- Guarded execution blocks (sound embedding exceptions logged as warnings without halting pipeline)
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch
try:
    import pymupdf as fitz
except ImportError:
    import fitz
import pytest

from src.postprocessing.converters import FakeDocumentConverter
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.testsheet.models import SubstationPackage
from tests.test_us_audio_workflow import (
    _create_synthetic_report_pdf,
    _create_synthetic_survey,
    _create_synthetic_wav,
)
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingWorkflow,
    PostProcessingTargetGroup,
)
from src.workflows.models import PostProcessingRequest
from src.workflows.postprocessing_pipeline import PostProcessingPipelineWorkflow


class ReportWithSoundDocConverter(FakeDocumentConverter):
    """FakeDocumentConverter that generates synthetic report PDFs with Sound clip anchors."""

    def convert_docx_to_pdf(
        self,
        docx_path: Path,
        pdf_path: Path,
        word_app: object | None = None,
        session: object | None = None,
    ) -> Path:
        self.convert_docx_calls.append((docx_path, pdf_path))
        return _create_synthetic_report_pdf(pdf_path)


def _create_mock_xlsx(path: Path) -> Path:
    """Create a minimal valid openpyxl workbook."""
    import openpyxl
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.save(str(path))
    return path


def _setup_test_environment(tmp_path: Path) -> tuple[ProjectEnvironment, Path, Path, Path]:
    """Helper to initialize workspace structure with storage and environment."""
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    ts_dir = root / "TESTSHEET"
    qr_dir = root / "QUICK REPORT"
    fr_dir = root / "FULL REPORT"
    rm_dir = root / "RAW MATERIAL"
    for d in (ts_dir, qr_dir, fr_dir, rm_dir):
        d.mkdir(parents=True, exist_ok=True)

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
    env = ProjectEnvironment(metadata=metadata, storage=storage)
    return env, ts_dir, qr_dir, fr_dir


def test_full_report_delivery_embeds_sound_when_survey_supplied(tmp_path: Path):
    """Test Full Report delivery includes sound annotations when survey data is supplied."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    sub_num = 1
    stem = "001. PE JENGKA 1"

    # Setup Full Report docx and testsheet PDF
    doc_dir = fr_dir / station / month / date_str
    doc_dir.mkdir(parents=True, exist_ok=True)
    docx_path = doc_dir / f"{stem}.docx"
    docx_path.write_bytes(b"mock docx")

    ts_sub_dir = ts_dir / station / month / date_str / "processed_testsheet" / "pdf"
    ts_sub_dir.mkdir(parents=True, exist_ok=True)
    ts_pdf_path = ts_sub_dir / f"{stem}.pdf"
    _create_synthetic_report_pdf(ts_pdf_path)

    # Setup RAW MATERIAL directory with US+TEV survey data
    raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / f"{sub_num:03d}. PE JENGKA 1" / "RAW DATA" / "US+TEV"
    _create_synthetic_survey(raw_sub_dir, create_wav=True)

    converter = ReportWithSoundDocConverter()
    workflow = FullReportPostProcessingWorkflow(converter=converter)

    result = workflow.process(target=docx_path, environment=env)

    assert result.is_success
    assert len(result.deliverables) == 1
    deliverable = result.deliverables[0]
    assert deliverable.exists()

    # Verify that sound annotations were injected into the deliverable PDF
    with fitz.open(deliverable) as doc:
        annots_found = [a for page in doc for a in page.annots() if a.type == (18, "Sound")]
        assert len(annots_found) > 0
        page1_annots = [a for a in doc[0].annots() if a.type == (18, "Sound")]
        page2_annots = [a for a in doc[1].annots() if a.type == (18, "Sound")]
        page3_annots = [a for a in doc[2].annots() if a.type == (18, "Sound")]
        assert len(page1_annots) == 1
        assert len(page2_annots) == 1
        assert len(page3_annots) == 0


def test_full_report_deliverable_valid_and_unmodified_when_survey_missing(tmp_path: Path):
    """Test Full Report deliverable remains valid and unmodified when survey data is missing."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    stem = "002. PE JENGKA 2"

    doc_dir = fr_dir / station / month / date_str
    doc_dir.mkdir(parents=True, exist_ok=True)
    docx_path = doc_dir / f"{stem}.docx"
    docx_path.write_bytes(b"mock docx")

    ts_sub_dir = ts_dir / station / month / date_str / "processed_testsheet" / "pdf"
    ts_sub_dir.mkdir(parents=True, exist_ok=True)
    ts_pdf_path = ts_sub_dir / f"{stem}.pdf"
    _create_synthetic_report_pdf(ts_pdf_path)

    converter = ReportWithSoundDocConverter()
    workflow = FullReportPostProcessingWorkflow(converter=converter)

    result = workflow.process(target=docx_path, environment=env)

    assert result.is_success
    assert len(result.deliverables) == 1
    deliverable = result.deliverables[0]
    assert deliverable.exists()

    with fitz.open(deliverable) as doc:
        annots_found = [a for page in doc for a in page.annots() if a.type == (18, "Sound")]
        assert len(annots_found) == 0


def test_quick_report_delivery_embeds_sound_when_survey_supplied(tmp_path: Path):
    """Test Quick Report deliverable includes sound annotations on CBM defect pages when survey data is supplied."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    sub_num = 1
    stem = "001. PE JENGKA 1"

    date_ts_dir = ts_dir / station / month / date_str
    date_ts_dir.mkdir(parents=True, exist_ok=True)
    ts_xlsx = date_ts_dir / f"{stem}.xlsx"
    _create_mock_xlsx(ts_xlsx)

    date_qr_dir = qr_dir / station / month / date_str
    date_qr_dir.mkdir(parents=True, exist_ok=True)
    qr_docx = date_qr_dir / f"{stem}.docx"
    qr_docx.write_bytes(b"mock docx")

    # Setup RAW MATERIAL directory with US+TEV survey data
    raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / f"{sub_num:03d}. PE JENGKA 1" / "RAW DATA" / "US+TEV"
    _create_synthetic_survey(raw_sub_dir, create_wav=True)

    pkg = SubstationPackage(
        testsheet_xlsx=ts_xlsx,
        quick_report_docx=qr_docx,
        date_folder=date_str,
        station_name=station,
        substation_number=sub_num,
    )

    converter = ReportWithSoundDocConverter()
    workflow = PostProcessingPipelineWorkflow(converter=converter)
    request = PostProcessingRequest(
        target_packages=(pkg,),
        apply_signatures=False,
        converter=converter,
    )

    summary = workflow.execute(env, request)

    assert len(summary.final_deliverables) == 1
    deliverable = summary.final_deliverables[0]
    assert deliverable.exists()

    with fitz.open(deliverable) as doc:
        annots_found = [a for page in doc for a in page.annots() if a.type == (18, "Sound")]
        assert len(annots_found) > 0
        # Defect/equipment pages have annotations while non-acoustic overview page remains unannotated
        page1_annots = [a for a in doc[0].annots() if a.type == (18, "Sound")]
        page2_annots = [a for a in doc[1].annots() if a.type == (18, "Sound")]
        page3_annots = [a for a in doc[2].annots() if a.type == (18, "Sound")]
        assert len(page1_annots) == 1
        assert len(page2_annots) == 1
        assert len(page3_annots) == 0


def test_quick_report_compiles_cleanly_when_survey_missing(tmp_path: Path):
    """Test Quick Report compiles cleanly when survey data is missing."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    sub_num = 2
    stem = "002. PE JENGKA 2"

    date_ts_dir = ts_dir / station / month / date_str
    date_ts_dir.mkdir(parents=True, exist_ok=True)
    ts_xlsx = date_ts_dir / f"{stem}.xlsx"
    _create_mock_xlsx(ts_xlsx)

    date_qr_dir = qr_dir / station / month / date_str
    date_qr_dir.mkdir(parents=True, exist_ok=True)
    qr_docx = date_qr_dir / f"{stem}.docx"
    qr_docx.write_bytes(b"mock docx")

    pkg = SubstationPackage(
        testsheet_xlsx=ts_xlsx,
        quick_report_docx=qr_docx,
        date_folder=date_str,
        station_name=station,
        substation_number=sub_num,
    )

    converter = ReportWithSoundDocConverter()
    workflow = PostProcessingPipelineWorkflow(converter=converter)
    request = PostProcessingRequest(
        target_packages=(pkg,),
        apply_signatures=False,
        converter=converter,
    )

    summary = workflow.execute(env, request)

    assert len(summary.final_deliverables) == 1
    deliverable = summary.final_deliverables[0]
    assert deliverable.exists()

    with fitz.open(deliverable) as doc:
        annots_found = [a for page in doc for a in page.annots() if a.type == (18, "Sound")]
        assert len(annots_found) == 0


def test_full_report_sound_embedding_guarded_execution_on_error(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """Test Full Report continues and logs warning if unexpected exception occurs during sound injection."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    sub_num = 1
    stem = "001. PE JENGKA 1"

    doc_dir = fr_dir / station / month / date_str
    doc_dir.mkdir(parents=True, exist_ok=True)
    docx_path = doc_dir / f"{stem}.docx"
    docx_path.write_bytes(b"mock docx")

    ts_sub_dir = ts_dir / station / month / date_str / "processed_testsheet" / "pdf"
    ts_sub_dir.mkdir(parents=True, exist_ok=True)
    ts_pdf_path = ts_sub_dir / f"{stem}.pdf"
    _create_synthetic_report_pdf(ts_pdf_path)

    raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / f"{sub_num:03d}. PE JENGKA 1" / "RAW DATA" / "US+TEV"
    _create_synthetic_survey(raw_sub_dir, create_wav=True)

    converter = ReportWithSoundDocConverter()
    workflow = FullReportPostProcessingWorkflow(converter=converter)

    with patch("src.workflows.full_report_postprocessing.embed_survey_ultrasound_into_pdf", side_effect=RuntimeError("Corrupt audio file")):
        with caplog.at_level(logging.WARNING):
            result = workflow.process(target=docx_path, environment=env)

    assert result.is_success
    assert len(result.deliverables) == 1
    assert "Sound embedding failed" in caplog.text


def test_quick_report_sound_embedding_guarded_execution_on_error(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """Test Quick Report continues and logs warning if unexpected exception occurs during sound injection."""
    env, ts_dir, qr_dir, fr_dir = _setup_test_environment(tmp_path)

    station = "JENGKA"
    month = "01. JANUARY"
    date_str = "15-01-2026"
    sub_num = 1
    stem = "001. PE JENGKA 1"

    date_ts_dir = ts_dir / station / month / date_str
    date_ts_dir.mkdir(parents=True, exist_ok=True)
    ts_xlsx = date_ts_dir / f"{stem}.xlsx"
    _create_mock_xlsx(ts_xlsx)

    date_qr_dir = qr_dir / station / month / date_str
    date_qr_dir.mkdir(parents=True, exist_ok=True)
    qr_docx = date_qr_dir / f"{stem}.docx"
    qr_docx.write_bytes(b"mock docx")

    raw_sub_dir = env.storage.get_raw_material_dir() / station / month / date_str / f"{sub_num:03d}. PE JENGKA 1" / "RAW DATA" / "US+TEV"
    _create_synthetic_survey(raw_sub_dir, create_wav=True)

    pkg = SubstationPackage(
        testsheet_xlsx=ts_xlsx,
        quick_report_docx=qr_docx,
        date_folder=date_str,
        station_name=station,
        substation_number=sub_num,
    )

    converter = ReportWithSoundDocConverter()
    workflow = PostProcessingPipelineWorkflow(converter=converter)
    request = PostProcessingRequest(
        target_packages=(pkg,),
        apply_signatures=False,
        converter=converter,
    )

    with patch("src.workflows.postprocessing_pipeline.embed_survey_ultrasound_into_pdf", side_effect=RuntimeError("Corrupt audio stream")):
        with caplog.at_level(logging.WARNING):
            summary = workflow.execute(env, request)

    assert len(summary.final_deliverables) == 1
    assert "Sound embedding failed" in caplog.text
