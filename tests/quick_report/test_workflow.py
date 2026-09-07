"""Tests for QuickReportWorkflow deep module interface and DocumentCompiler seam."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
from unittest.mock import MagicMock, patch
from docx import Document
import pytest

from src.project.environment import ProjectEnvironment
from src.quick_report.compiler import DocumentCompiler, WordComDocumentCompiler
from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.workflows.models import (
    QuickReportInspection,
    QuickReportResult,
    SubstationInspectionItem,
)
from src.workflows.quick_report import QuickReportWorkflow


class FakeDocumentCompiler:
    """Test adapter: records parts and writes a minimal valid .docx stub to output_path."""

    def __init__(self) -> None:
        self.compiled_calls: list[tuple[tuple[Path, ...], Path]] = []

    def compile(self, parts: Sequence[Path], output_path: Path) -> Path:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Minimal zip header bytes simulating a .docx container
        output_path.write_bytes(b"PK\x03\x04stub_docx_payload")
        self.compiled_calls.append((tuple(parts), output_path))
        return output_path


def _make_mock_package(
    station: str = "CAMERON HIGHLAND",
    substation_number: int = 1,
    substation_name: str = "PE TEST SUBSTATION",
    fl: str = "CCHL/PCE/J00059",
    date_str: str = "01-09-2026",
) -> SubstationTestsheetPackage:
    data = TestsheetData(
        substation_number=substation_number,
        substation_name_erms=substation_name,
        fl_erms=fl,
        fl_site=fl,
        date_str=date_str,
        station_name=station,
    )
    return SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("dummy_raw"),
        station=station,
        month="09. SEPTEMBER",
        date_str=date_str,
        substation_number=substation_number,
        data=data,
    )


def _setup_mock_environment(tmp_path: Path) -> MagicMock:
    tpl_file = tmp_path / "templates" / "template.docx"
    tpl_file.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_paragraph("Mock Template")
    doc.save(tpl_file)

    env = MagicMock(spec=ProjectEnvironment)
    env.po_number = "42360565"
    env.state = "PAHANG"
    env.get_quick_report_dir.return_value = tmp_path / "QUICK REPORT"
    env.get_testsheet_dir.return_value = tmp_path / "TESTSHEET"
    env.get_vi_front_page_template.return_value = tpl_file
    env.get_cbm_summary_template.return_value = tpl_file
    env.get_vi_summary_template.return_value = tpl_file
    env.get_vi_defect_template.return_value = tpl_file
    env.get_template.return_value = tpl_file
    env.get_sub_cond_dir.return_value = tmp_path / "templates"
    env.storage = MagicMock()
    env.storage.get_substation_raw_data_dir.return_value = tmp_path / "raw_data"
    return env


def test_compiler_protocol_conformance():
    """Verify WordComDocumentCompiler and FakeDocumentCompiler satisfy DocumentCompiler protocol."""
    fake = FakeDocumentCompiler()
    assert isinstance(fake, DocumentCompiler)

    com = WordComDocumentCompiler()
    assert isinstance(com, DocumentCompiler)


def test_inspect_returns_targets_for_known_fl(tmp_path: Path):
    """Verify inspect() generates correct SubstationInspectionItem without COM calls or disk writes."""
    env = _setup_mock_environment(tmp_path)
    pkg = _make_mock_package()

    cbm_defects = [
        CbmDefectRecord(
            equipment="RMU",
            defect_area="Cable Box",
            technology="IR",
            raw_measurement="55.0",
        )
    ]
    vi_defects = [
        ViDefectRecord(
            equipment="SWG",
            defect_area="Door",
            additional_remarks="Loose hinge",
        )
    ]

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch.object(workflow.extractor, "extract", return_value=[pkg]),
        patch.object(workflow.extractor, "extract_defects", return_value=(cbm_defects, vi_defects)),
    ):
        inspection = workflow.inspect(["CCHL/PCE/J00059"], env)

    assert isinstance(inspection, QuickReportInspection)
    assert inspection.ready_to_generate is True
    assert len(inspection.missing_templates) == 0
    assert len(inspection.errors) == 0
    assert len(inspection.targets) == 1

    target = inspection.targets[0]
    assert isinstance(target, SubstationInspectionItem)
    assert target.pe_number == 1
    assert target.substation_name == "PE TEST SUBSTATION"
    assert target.functional_location == "CCHL/PCE/J00059"
    assert target.defect_suffix == " (IR+VI)"
    assert "001. PE TEST SUBSTATION (IR+VI)" in target.stem
    assert target.cbm_defect_count == 1
    assert target.vi_defect_count == 1
    # COM compiler must not have been invoked
    assert len(compiler.compiled_calls) == 0


def test_inspect_ready_to_generate_false_when_template_missing(tmp_path: Path):
    """Verify inspect() marks ready_to_generate as False when a required template is missing."""
    env = _setup_mock_environment(tmp_path)
    # Point front page template to a non-existent file
    env.get_vi_front_page_template.return_value = tmp_path / "nonexistent_front_page.docx"

    pkg = _make_mock_package()
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    with (
        patch.object(workflow.extractor, "extract", return_value=[pkg]),
        patch.object(workflow.extractor, "extract_defects", return_value=([], [])),
    ):
        inspection = workflow.inspect(["CCHL/PCE/J00059"], env)

    assert inspection.ready_to_generate is False
    assert len(inspection.missing_templates) > 0
    assert any("VI front page" in t for t in inspection.missing_templates)


def test_generate_produces_result_for_known_fl(tmp_path: Path):
    """Verify generate() produces verified QuickReportResult across the FakeDocumentCompiler seam."""
    env = _setup_mock_environment(tmp_path)
    pkg = _make_mock_package()

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch.object(workflow.extractor, "extract", return_value=[pkg]),
        patch.object(workflow.extractor, "extract_defects", return_value=([], [])),
    ):
        progress_messages: list[str] = []
        result = workflow.generate(
            ["CCHL/PCE/J00059"],
            env,
            progress_sink=progress_messages.append,
        )

    assert isinstance(result, QuickReportResult)
    assert result.is_success is True
    assert result.reports_generated == 1
    assert len(result.generated_paths) == 1
    assert len(result.errors) == 0

    generated_path = result.generated_paths[0]
    assert generated_path.exists()
    assert generated_path.stat().st_size > 0
    assert len(compiler.compiled_calls) == 1
    assert any("Generating quick report" in m for m in progress_messages)


def test_generate_batch_resilience_continues_past_station_failure(tmp_path: Path):
    """Verify SubstationIsolatedBatchResiliencePolicy: station failure does not halt subsequent stations."""
    env = _setup_mock_environment(tmp_path)

    pkg1 = _make_mock_package(substation_number=1, substation_name="FAILING SUB", fl="FL1")
    pkg2 = _make_mock_package(substation_number=2, substation_name="SUCCESS SUB", fl="FL2")

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    def mock_extract_defects(pkg, environment):
        if pkg.substation_number == 1:
            raise RuntimeError("Database connection corrupted for substation 1")
        return ([], [])

    with (
        patch.object(workflow.extractor, "extract", return_value=[pkg1, pkg2]),
        patch.object(workflow.extractor, "extract_defects", side_effect=mock_extract_defects),
    ):
        result = workflow.generate(["FL1", "FL2"], env)

    assert result.reports_generated == 1
    assert len(result.generated_paths) == 1
    assert len(result.errors) == 1
    assert "Database connection corrupted" in result.errors[0]
    assert result.is_success is False  # is_success requires zero errors


def test_generate_returns_error_when_no_packages_found(tmp_path: Path):
    """Verify generate() returns error outcome when no packages are found for target."""
    env = _setup_mock_environment(tmp_path)

    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    with patch.object(workflow.extractor, "extract", return_value=[]):
        result = workflow.generate(["UNKNOWN_FL"], env)

    assert result.reports_generated == 0
    assert len(result.generated_paths) == 0
    assert len(result.errors) == 1
    assert "No testsheet packages found" in result.errors[0]
    assert result.is_success is False


def test_target_polymorphism(tmp_path: Path):
    """Verify ReportTarget polymorphism correctly dispatches Path, str, and Sequence[str]."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    # Case 1: Path target
    folder_path = tmp_path / "TESTSHEET" / "01-09-2026"
    req_path = workflow._resolve_request(folder_path, env)
    assert req_path.mode.value == "folder"
    assert req_path.target_folders == (str(folder_path),)

    # Case 2: str target (date string)
    req_str = workflow._resolve_request("01-09-2026", env)
    assert req_str.mode.value == "folder"
    assert req_str.target_folders == ("01-09-2026",)

    # Case 3: Sequence[str] target (FLs)
    req_seq = workflow._resolve_request(["FL001", "FL002"], env)
    assert req_seq.mode.value == "fl"
    assert req_seq.target_package_names == ("FL001", "FL002")

    # Case 4: Invalid target type raises TypeError
    with pytest.raises(TypeError, match="Unsupported target type"):
        workflow._resolve_request(12345, env)  # type: ignore[arg-type]
