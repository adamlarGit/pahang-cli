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

    cond_file = tmp_path / "templates" / "MASTER_SUBSTATION_CONDITION.docx"
    doc_cond = Document()
    doc_cond.add_paragraph("Mock Condition")
    doc_cond.save(cond_file)

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
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=(cbm_defects, vi_defects)),
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
    assert target.station == "CAMERON HIGHLAND"
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
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
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
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
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
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg1, pkg2]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", side_effect=mock_extract_defects),
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

    with patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[]):
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
    folders, fls = workflow._resolve_target(folder_path, env)
    assert folders == (str(folder_path),)
    assert fls is None

    # Case 2: str target (date string)
    folders, fls = workflow._resolve_target("01-09-2026", env)
    assert folders == ("01-09-2026",)
    assert fls is None

    # Case 3: Sequence[str] target (FLs)
    folders, fls = workflow._resolve_target(["FL001", "FL002"], env)
    assert folders is None
    assert fls == ("FL001", "FL002")

    # Case 4: Single str target (FL)
    folders, fls = workflow._resolve_target("FL001", env)
    assert folders is None
    assert fls == ["FL001"]

    # Case 5: Invalid target type raises TypeError
    with pytest.raises(TypeError, match="Unsupported target type"):
        workflow._resolve_target(12345, env)  # type: ignore[arg-type]


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


def test_non_matching_date_formats_treated_as_fls(tmp_path: Path):
    """Verify non-matching date formats (e.g. 2026-09-01) resolve as FLs without raising ValueError."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    formats = [
        "2026-09-01",  # YYYY-MM-DD
        "01/09/2026",  # DD/MM/YYYY
        "20260901",    # YYYYMMDD
    ]

    for fmt in formats:
        folders, fls = workflow._resolve_target(fmt, env)
        assert folders is None
        assert fls == [fmt]

        res = workflow.generate(fmt, env)
        assert res.reports_generated == 0
        assert any(f"No testsheet packages found for target: {fmt}" in err for err in res.errors)

    # Any DD-MM-YYYY string matches daily date folder pattern without calendar date validation
    folders, fls = workflow._resolve_target("32-09-2026", env)
    assert folders == ("32-09-2026",)
    assert fls is None

    # When generated, missing date folder returns error outcome rather than ValueError
    res_cal = workflow.generate("32-09-2026", env)
    assert res_cal.reports_generated == 0
    assert any("No testsheet packages found for target: 32-09-2026" in err for err in res_cal.errors)

    # Valid daily date format DD-MM-YYYY resolves as folder target
    with patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[]):
        res = workflow.inspect("01-09-2026", env)
        assert isinstance(res, QuickReportInspection)


def test_explicit_missing_path_target_raises_file_not_found(tmp_path: Path):
    """Verify generate() raises FileNotFoundError when an explicit Path target is missing."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    missing_path = tmp_path / "NONEXISTENT_DIR"
    with pytest.raises(FileNotFoundError, match="Target path does not exist"):
        workflow.generate(missing_path, env)

    with pytest.raises(FileNotFoundError, match="Target path does not exist"):
        workflow.generate([missing_path], env)


def test_direct_path_target_discovers_packages(tmp_path: Path):
    """Verify passing a direct Path target discovers packages and generates report."""
    env = _setup_mock_environment(tmp_path)
    target_folder = tmp_path / "TESTSHEET" / "ROMPIN" / "09. SEPTEMBER" / "01-09-2026"
    target_folder.mkdir(parents=True, exist_ok=True)

    pkg = _make_mock_package(station="ROMPIN", substation_number=1, substation_name="PE ROMPIN")
    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch("src.testsheet.repository.SubstationTestsheetRepository.discover_packages", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        insp = workflow.inspect(target_folder, env)
        assert insp.ready_to_generate is True
        assert len(insp.targets) == 1
        assert insp.targets[0].station == "ROMPIN"

        res = workflow.generate(target_folder, env)
        assert res.is_success is True
        assert res.reports_generated == 1


def test_target_sequence_disambiguation_dates_vs_fls(tmp_path: Path):
    """Verify sequences of date strings or folder paths resolve as FOLDER, other strings as FL."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())

    # Sequence of date strings -> FOLDER
    folders, fls = workflow._resolve_target(["01-09-2026", "02-09-2026"], env)
    assert folders == ("01-09-2026", "02-09-2026")
    assert fls is None

    # Sequence of Paths -> FOLDER
    p1 = tmp_path / "TESTSHEET" / "ROMPIN"
    p2 = tmp_path / "TESTSHEET" / "KUANTAN"
    folders, fls = workflow._resolve_target([p1, p2], env)
    assert folders == (str(p1), str(p2))
    assert fls is None

    # Sequence of FL strings -> FL
    folders, fls = workflow._resolve_target(["FL001", "FL002", "CCHL/PCE/J00059"], env)
    assert folders is None
    assert fls == ("FL001", "FL002", "CCHL/PCE/J00059")


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
        patch("src.testsheet.repository.SubstationTestsheetRepository.discover_packages", side_effect=mock_discover),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
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
        patch("src.testsheet.repository.SubstationTestsheetRepository.discover_packages", side_effect=mock_discover),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
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
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=(cbm_defects, vi_defects)),
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


def test_generate_fails_fast_with_file_not_found_error_on_missing_templates(tmp_path: Path):
    """Verify generate() fails fast by raising FileNotFoundError before launching compiler when template missing."""
    env = _setup_mock_environment(tmp_path)
    env.get_vi_front_page_template.return_value = tmp_path / "missing_front_page.docx"

    pkg = _make_mock_package()
    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]):
        with pytest.raises(FileNotFoundError, match="VI front page template missing"):
            workflow.generate(["CCHL/PCE/J00059"], env)

    # Must fail fast before session or compile is called
    assert len(compiler.compiled_calls) == 0


def test_generate_end_to_end_batch_mirrored_hierarchy(tmp_path: Path):
    """Verify generate() writes deliverables to mirrored hierarchy QUICK REPORT/<STATION>/<MONTH>/<DATE>/."""
    env = _setup_mock_environment(tmp_path)
    pkg1 = _make_mock_package(
        station="CAMERON HIGHLAND", substation_number=1, substation_name="PE 1", fl="FL1", date_str="01-09-2026"
    )
    pkg2 = _make_mock_package(
        station="CAMERON HIGHLAND", substation_number=2, substation_name="PE 2", fl="FL2", date_str="01-09-2026"
    )

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg1, pkg2]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        result = workflow.generate(["FL1", "FL2"], env)

    assert result.is_success is True
    assert result.reports_generated == 2
    assert len(result.generated_paths) == 2
    assert len(result.errors) == 0

    for path in result.generated_paths:
        assert path.exists()
        assert path.stat().st_size > 0
        # Verify mirrored hierarchy: QUICK REPORT / CAMERON HIGHLAND / 09. SEPTEMBER / 01-09-2026
        assert "QUICK REPORT" in path.parts
        assert "CAMERON HIGHLAND" in path.parts
        assert "09. SEPTEMBER" in path.parts
        assert "01-09-2026" in path.parts

    # Both documents compiled
    assert len(compiler.compiled_calls) == 2


def test_generate_batch_fault_isolation_during_compilation(tmp_path: Path):
    """Verify SubstationIsolatedBatchResiliencePolicy when compilation of one substation fails."""
    env = _setup_mock_environment(tmp_path)
    pkg1 = _make_mock_package(substation_number=1, substation_name="FAILING SUB", fl="FL1")
    pkg2 = _make_mock_package(substation_number=2, substation_name="SUCCESS SUB", fl="FL2")

    class FailingOnFirstSubstationCompiler(FakeDocumentCompiler):
        def compile(self, parts: Sequence[Path], output_path: Path) -> Path:
            if "FAILING SUB" in str(output_path):
                raise RuntimeError("Word COM HRESULT 0x80010108 RPC_E_DISCONNECTED")
            return super().compile(parts, output_path)

    compiler = FailingOnFirstSubstationCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg1, pkg2]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        result = workflow.generate(["FL1", "FL2"], env)

    assert result.reports_generated == 1
    assert len(result.generated_paths) == 1
    assert len(result.errors) == 1
    assert "RPC_E_DISCONNECTED" in result.errors[0]
    assert result.is_success is False


def test_generate_multi_defect_same_equipment_family_cbm(tmp_path: Path):
    """Verify compiling report with multiple defects in same CBM family generates valid deliverable."""
    env = _setup_mock_environment(tmp_path)
    pkg = _make_mock_package(
        station="ROMPIN", substation_number=10, substation_name="PE MULTI DEFECT", fl="ROMP/10"
    )

    # 2 defects in same SWG family (one IR, one US)
    cbm_defects = [
        CbmDefectRecord(equipment="SWG", defect_area="Cable Box 1", technology="IR"),
        CbmDefectRecord(equipment="SWG", defect_area="Cable Box 2", technology="US"),
    ]

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=(cbm_defects, [])),
    ):
        result = workflow.generate(["ROMP/10"], env)

    assert result.is_success is True
    assert result.reports_generated == 1
    output_path = result.generated_paths[0]
    assert output_path.exists()
    assert "(IR+US)" in output_path.name


def test_hyphenated_fl_strings_not_rejected_by_date_validation(tmp_path: Path):
    """Verify hyphenated FL strings (e.g. CCHL/PCE/J00059-01) in sequences are treated as FLs, not rejected."""
    env = _setup_mock_environment(tmp_path)
    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())
    fl_inputs = ["CCHL/PCE/J00059-01", "ROMP/PCE/J00120"]

    folders, fls = workflow._resolve_target(fl_inputs, env)
    assert folders is None
    assert fls == tuple(fl_inputs)

    pkg = _make_mock_package(fl="CCHL/PCE/J00059-01")
    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        inspection = workflow.inspect(fl_inputs, env)
        assert inspection.ready_to_generate is True
        assert len(inspection.targets) == 1
        assert inspection.targets[0].functional_location == "CCHL/PCE/J00059-01"


def test_missing_condition_template_inspection_and_generate(tmp_path: Path):
    """Verify missing condition template marks inspect() not ready and fails fast in generate()."""
    env = _setup_mock_environment(tmp_path)
    cond_file = tmp_path / "templates" / "MASTER_SUBSTATION_CONDITION.docx"
    if cond_file.exists():
        cond_file.unlink()

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    pkg = _make_mock_package()
    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        # 1. inspect() records missing template and marks ready_to_generate as False without raising
        inspection = workflow.inspect(["CCHL/PCE/J00059"], env)
        assert inspection.ready_to_generate is False
        assert any("Substation condition template missing" in t for t in inspection.missing_templates)
        assert len(compiler.compiled_calls) == 0

        # 2. generate() raises FileNotFoundError before running compiler
        with pytest.raises(FileNotFoundError, match="Substation condition template missing"):
            workflow.generate(["CCHL/PCE/J00059"], env)
        assert len(compiler.compiled_calls) == 0


def test_multi_station_sequence_filtering(tmp_path: Path):
    """Verify passing a Sequence[str] of stations in generate() and inspect() filters correctly."""
    env = _setup_mock_environment(tmp_path)
    pkg_rompin = _make_mock_package(station="ROMPIN", substation_number=1, substation_name="PE ROMPIN")
    pkg_kuantan = _make_mock_package(station="KUANTAN", substation_number=2, substation_name="PE KUANTAN")
    pkg_cameron = _make_mock_package(station="CAMERON HIGHLAND", substation_number=3, substation_name="PE CAMERON")

    compiler = FakeDocumentCompiler()
    workflow = QuickReportWorkflow(compiler=compiler)

    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg_rompin, pkg_kuantan, pkg_cameron]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        # inspect() with sequence of stations
        insp = workflow.inspect("01-09-2026", env, station=["kuantan", "rompin"])
        assert len(insp.targets) == 2
        stations_found = {t.station for t in insp.targets}
        assert stations_found == {"KUANTAN", "ROMPIN"}

        # generate() with sequence of stations
        res = workflow.generate("01-09-2026", env, station=["KUANTAN", "ROMPIN"])
        assert res.is_success is True
        assert res.reports_generated == 2
        assert len(compiler.compiled_calls) == 2
        out_paths_str = [str(call[1]) for call in compiler.compiled_calls]
        assert any("KUANTAN" in p for p in out_paths_str)
        assert any("ROMPIN" in p for p in out_paths_str)
        assert not any("CAMERON HIGHLAND" in p for p in out_paths_str)


def test_substation_inspection_item_station_populated(tmp_path: Path):
    """Verify SubstationInspectionItem.station is accurately populated during dry-run inspection."""
    env = _setup_mock_environment(tmp_path)
    pkg = _make_mock_package(station="ROMPIN", substation_name="PE ROMPIN TEST", fl="ROMP/01")

    workflow = QuickReportWorkflow(compiler=FakeDocumentCompiler())
    with (
        patch("src.quick_report.extractor.QuickReportExtractor.extract", return_value=[pkg]),
        patch("src.quick_report.extractor.QuickReportExtractor.extract_defects", return_value=([], [])),
    ):
        inspection = workflow.inspect(["ROMP/01"], env)
        assert len(inspection.targets) == 1
        item = inspection.targets[0]
        assert item.station == "ROMPIN"
        assert item.substation_name == "PE ROMPIN TEST"


