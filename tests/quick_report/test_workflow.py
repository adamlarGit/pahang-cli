"""Tests for QuickReportWorkflow deep module interface and DocumentCompiler seam."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence
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

    @contextmanager
    def session(self) -> Iterator[FakeDocumentCompiler]:
        yield self

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

    class NonConformingCompiler:
        pass

    assert not isinstance(NonConformingCompiler(), DocumentCompiler)


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


def test_fake_document_compiler_standalone_and_session(tmp_path: Path):
    """Verify FakeDocumentCompiler produces valid stub files and supports session context manager headlessly."""
    compiler = FakeDocumentCompiler()
    p1 = tmp_path / "part1.docx"
    p1.touch()
    out1 = tmp_path / "out1.docx"
    out2 = tmp_path / "out2.docx"

    with compiler.session() as sess:
        assert sess is compiler
        res1 = compiler.compile([p1], out1)
        res2 = compiler.compile([p1], out2)

    assert res1 == out1
    assert res2 == out2
    assert out1.read_bytes().startswith(b"PK\x03\x04")
    assert out2.read_bytes().startswith(b"PK\x03\x04")
    assert len(compiler.compiled_calls) == 2


def test_word_com_document_compiler_session_batch_reuse(tmp_path: Path):
    """Verify WordComDocumentCompiler batch session reuses single Word app and isolates ActiveX containers."""
    p1 = tmp_path / "part1.docx"
    p1.touch()
    out1 = tmp_path / "out1.docx"
    out2 = tmp_path / "out2.docx"

    compiler = WordComDocumentCompiler()
    mock_word = MagicMock()
    mock_word.Hwnd = 5555
    mock_doc1 = MagicMock()
    mock_doc2 = MagicMock()
    mock_part = MagicMock()
    mock_rng = MagicMock()

    mock_word.Documents.Add.side_effect = [mock_doc1, mock_doc2]
    mock_word.Documents.Open.return_value = mock_part
    mock_doc1.Content = mock_rng
    mock_doc2.Content = mock_rng
    mock_doc1.Tables.Count = 0
    mock_doc2.Tables.Count = 0
    mock_rng.Information.return_value = False

    mock_win32 = MagicMock()
    mock_win32.client.Dispatch.return_value = mock_word

    with (
        patch("src.quick_report.compiler.win32com", mock_win32),
        patch("src.quick_report.compiler.pythoncom") as mock_pythoncom,
        patch("win32process.GetWindowThreadProcessId", return_value=(0, 5555)),
        patch("src.quick_report.compiler._terminate_word_process") as mock_terminate,
        patch("src.quick_report.compiler._clear_clipboard") as mock_clear_clip,
    ):
        with compiler.session() as sess:
            assert sess is compiler
            assert compiler._word_app is mock_word
            assert mock_word.Visible is False
            assert mock_word.ScreenUpdating is False
            assert mock_word.DisplayAlerts == 0

            # Compile report 1
            compiler.compile([p1], out1)
            # Compile report 2
            compiler.compile([p1], out2)

            # Word app must NOT be quit between compilations
            mock_word.Quit.assert_not_called()

        # After session exit
        assert compiler._word_app is None
        mock_word.Quit.assert_called_once()
        mock_terminate.assert_called_once_with(5555)
        mock_pythoncom.CoUninitialize.assert_called_once()

    # Verify 2 distinct Add() calls creating fresh OLE containers per ADR 0002
    assert mock_word.Documents.Add.call_count == 2
    mock_doc1.SaveAs2.assert_called_once_with(str(out1.resolve()))
    mock_doc2.SaveAs2.assert_called_once_with(str(out2.resolve()))
    mock_doc1.Close.assert_called_once_with(False)
    mock_doc2.Close.assert_called_once_with(False)
    # Clipboard cleared between parts and on doc close
    assert mock_clear_clip.call_count >= 4


def test_word_com_document_compiler_session_teardown_on_error(tmp_path: Path):
    """Verify WordComDocumentCompiler session cleans up resources when an exception is raised."""
    compiler = WordComDocumentCompiler()
    mock_word = MagicMock()
    mock_word.Hwnd = 7777
    mock_win32 = MagicMock()
    mock_win32.client.Dispatch.return_value = mock_word

    with (
        patch("src.quick_report.compiler.win32com", mock_win32),
        patch("src.quick_report.compiler.pythoncom") as mock_pythoncom,
        patch("win32process.GetWindowThreadProcessId", return_value=(0, 7777)),
        patch("src.quick_report.compiler._terminate_word_process") as mock_terminate,
    ):
        with pytest.raises(RuntimeError, match="Batch abort"):
            with compiler.session():
                raise RuntimeError("Batch abort")

        assert compiler._word_app is None
        mock_word.Quit.assert_called_once()
        mock_terminate.assert_called_once_with(7777)
        mock_pythoncom.CoUninitialize.assert_called_once()


def test_strict_date_validation_rejects_non_pahang_dates(tmp_path: Path):
    """Verify strict date validation enforces DD-MM-YYYY and rejects non-Pahang formats."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    invalid_dates = [
        "2026-09-01",  # YYYY-MM-DD
        "2026/09/01",  # YYYY/MM/DD
        "2026.09.01",  # YYYY.MM.DD
        "01/09/2026",  # DD/MM/YYYY
        "01.09.2026",  # DD.MM.YYYY
        "1-9-2026",    # D-M-YYYY
        "01-9-2026",   # DD-M-YYYY
        "1-09-2026",   # D-MM-YYYY
        "01-09-26",    # 2-digit year
        "20260901",    # YYYYMMDD
        "32-09-2026",  # Invalid calendar day
        "01-13-2026",  # Invalid calendar month
    ]

    for inv in invalid_dates:
        # Single string target
        with pytest.raises(ValueError, match="Invalid (date format|calendar date)"):
            workflow.inspect(inv, env)

        with pytest.raises(ValueError, match="Invalid (date format|calendar date)"):
            workflow.generate(inv, env)

        # Sequence target
        with pytest.raises(ValueError, match="Invalid (date format|calendar date)"):
            workflow.inspect([inv], env)

        with pytest.raises(ValueError, match="Invalid (date format|calendar date)"):
            workflow.generate([inv], env)

    # Valid Pahang date format DD-MM-YYYY does not raise ValueError
    with patch.object(workflow.extractor, "extract", return_value=[]):
        res = workflow.inspect("01-09-2026", env)
        assert isinstance(res, QuickReportInspection)


def test_target_sequence_disambiguation_dates_vs_fls(tmp_path: Path):
    """Verify sequences of date strings or folder paths resolve as FOLDER, other strings as FL."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    # Sequence of date strings -> FOLDER
    req_dates = workflow._resolve_request(["01-09-2026", "02-09-2026"], env)
    assert req_dates.mode.value == "folder"
    assert req_dates.target_folders == ("01-09-2026", "02-09-2026")

    # Sequence of Paths -> FOLDER
    p1 = tmp_path / "TESTSHEET" / "ROMPIN"
    p2 = tmp_path / "TESTSHEET" / "KUANTAN"
    req_paths = workflow._resolve_request([p1, p2], env)
    assert req_paths.mode.value == "folder"
    assert req_paths.target_folders == (str(p1), str(p2))

    # Sequence of FL strings -> FL
    req_fls = workflow._resolve_request(["FL001", "FL002", "CCHL/PCE/J00059"], env)
    assert req_fls.mode.value == "fl"
    assert req_fls.target_package_names == ("FL001", "FL002", "CCHL/PCE/J00059")


def test_multi_station_date_resolution_discovers_all_stations_by_default(tmp_path: Path):
    """Verify bare date string matching multiple station folders discovers all stations by default."""
    env = _setup_mock_environment(tmp_path)
    testsheet_dir = env.get_testsheet_dir.return_value

    rompin_dir = testsheet_dir / "ROMPIN" / "09. SEPTEMBER" / "01-09-2026"
    kuantan_dir = testsheet_dir / "KUANTAN" / "09. SEPTEMBER" / "01-09-2026"
    rompin_dir.mkdir(parents=True, exist_ok=True)
    kuantan_dir.mkdir(parents=True, exist_ok=True)

    pkg_rompin = _make_mock_package(
        station="ROMPIN", substation_number=1, substation_name="PE ROMPIN 1", fl="ROMP/01"
    )
    pkg_kuantan = _make_mock_package(
        station="KUANTAN", substation_number=2, substation_name="PE KUANTAN 1", fl="KNTN/01"
    )

    def mock_discover(folder_path):
        f_str = str(folder_path)
        if "ROMPIN" in f_str:
            return [pkg_rompin]
        if "KUANTAN" in f_str:
            return [pkg_kuantan]
        return []

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch.object(workflow.extractor.repository, "discover_packages", side_effect=mock_discover),
        patch.object(workflow.extractor, "extract_defects", return_value=([], [])),
    ):
        inspection = workflow.inspect("01-09-2026", env)

    assert inspection.ready_to_generate is True
    assert len(inspection.targets) == 2
    stations = {t.substation_name for t in inspection.targets}
    assert stations == {"PE ROMPIN 1", "PE KUANTAN 1"}
    pe_numbers = {t.pe_number for t in inspection.targets}
    assert pe_numbers == {1, 2}
    # Dry-run: no compile calls
    assert len(compiler.compiled_calls) == 0


def test_station_filtering_inspect_and_generate(tmp_path: Path):
    """Verify station filter restricts package inclusion in both inspect() and generate()."""
    env = _setup_mock_environment(tmp_path)
    testsheet_dir = env.get_testsheet_dir.return_value

    rompin_dir = testsheet_dir / "ROMPIN" / "09. SEPTEMBER" / "01-09-2026"
    kuantan_dir = testsheet_dir / "KUANTAN" / "09. SEPTEMBER" / "01-09-2026"
    rompin_dir.mkdir(parents=True, exist_ok=True)
    kuantan_dir.mkdir(parents=True, exist_ok=True)

    pkg_rompin = _make_mock_package(
        station="ROMPIN", substation_number=1, substation_name="PE ROMPIN 1", fl="ROMP/01"
    )
    pkg_kuantan = _make_mock_package(
        station="KUANTAN", substation_number=2, substation_name="PE KUANTAN 1", fl="KNTN/01"
    )

    def mock_discover(folder_path):
        f_str = str(folder_path)
        if "ROMPIN" in f_str:
            return [pkg_rompin]
        if "KUANTAN" in f_str:
            return [pkg_kuantan]
        return []

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch.object(workflow.extractor.repository, "discover_packages", side_effect=mock_discover),
        patch.object(workflow.extractor, "extract_defects", return_value=([], [])),
    ):
        # 1. Filter inspect to ROMPIN
        insp_rompin = workflow.inspect("01-09-2026", env, station="ROMPIN")
        assert len(insp_rompin.targets) == 1
        assert insp_rompin.targets[0].substation_name == "PE ROMPIN 1"

        # 2. Filter generate to KUANTAN (case-insensitive)
        gen_kuantan = workflow.generate("01-09-2026", env, station="kuantan")
        assert gen_kuantan.is_success is True
        assert gen_kuantan.reports_generated == 1
        assert len(compiler.compiled_calls) == 1
        # Final output path should be under KUANTAN
        compiled_output = compiler.compiled_calls[0][1]
        assert "KUANTAN" in str(compiled_output)


def test_inspect_previews_expose_defect_counts_and_stem(tmp_path: Path):
    """Verify SubstationInspectionItem exposes sanitized name, stem, canonical suffix, and defect counts."""
    env = _setup_mock_environment(tmp_path)
    pkg = _make_mock_package(
        station="CAMERON HIGHLAND",
        substation_number=5,
        substation_name='PE TEST / DIRTY "NAME"?',
        fl="CCHL/PCE/J00059",
    )

    cbm_defects = [
        CbmDefectRecord(equipment="RMU", defect_area="Cable Box", technology="IR"),
        CbmDefectRecord(equipment="TRF", defect_area="Bushing", technology="US"),
    ]
    vi_defects = [
        ViDefectRecord(equipment="SWG", defect_area="Door", additional_remarks="Rust"),
    ]

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch.object(workflow.extractor, "extract", return_value=[pkg]),
        patch.object(workflow.extractor, "extract_defects", return_value=(cbm_defects, vi_defects)),
    ):
        inspection = workflow.inspect(["CCHL/PCE/J00059"], env)

    assert inspection.ready_to_generate is True
    assert len(inspection.targets) == 1
    target = inspection.targets[0]

    assert target.pe_number == 5
    # Sanitized name without illegal Windows filename chars (<>:"/\|?*)
    assert "/" not in target.substation_name
    assert '"' not in target.substation_name
    assert "?" not in target.substation_name
    assert target.substation_name == "PE TEST  DIRTY NAME"

    assert target.functional_location == "CCHL/PCE/J00059"
    assert target.defect_suffix == " (IR+US+VI)"
    assert target.stem == "005. PE TEST  DIRTY NAME (IR+US+VI)"
    assert target.cbm_defect_count == 2
    assert target.vi_defect_count == 1
    assert target.condition_pair_count > 0
    # No COM calls or disk writes
    assert len(compiler.compiled_calls) == 0

