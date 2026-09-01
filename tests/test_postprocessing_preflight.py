"""Unit tests for Pre-Flight Integrity Validator and File Filter in post-processing pipeline."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.postprocessing_preflight import (
    PreFlightValidationError,
    PreFlightValidationResult,
    filter_valid_quick_reports,
    filter_valid_raw_materials,
    filter_valid_testsheets,
    validate_postprocessing_preflight,
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


def test_preflight_validation_nested_pahang_hierarchy(mock_env: ProjectEnvironment) -> None:
    """3-tier Pahang hierarchy (<STATION>/<MONTH>/<DATE>/): Pre-flight resolves nested date directory."""
    date_str = "28-08-2026"
    station = "TEMERLOH"
    month = "08. AUGUST"
    
    ts_dir = mock_env.get_testsheet_dir() / station / month / date_str
    qr_dir = mock_env.get_quick_report_dir() / station / month / date_str
    raw_dir = mock_env.get_raw_material_dir() / station / month / date_str

    ts_dir.mkdir(parents=True)
    qr_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    for i in range(1, 4):
        (qr_dir / f"0{i}. PE STATION_{i} (VI).docx").write_text("dummy docx")
        (ts_dir / f"0{i}. PE STATION_{i}.xlsx").write_text("dummy xlsx")
        (raw_dir / f"0{i}. PE STATION_{i}").mkdir()

    result = validate_postprocessing_preflight(mock_env, date_str)

    assert result.date_folder == date_str
    assert result.quick_report_count == 3
    assert result.testsheet_count == 3
    assert result.raw_material_count == 3
    assert result.is_valid is True


def test_preflight_validation_happy_path_with_raw_material(mock_env: ProjectEnvironment) -> None:
    """Happy path: Identical counts across QUICK REPORT, TESTSHEET, and RAW MATERIAL passes cleanly."""
    date_str = "01-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str
    raw_dir = mock_env.get_raw_material_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    for i in range(1, 4):
        (qr_dir / f"0{i}. PE STATION_{i}.docx").write_text("dummy docx")
        (ts_dir / f"0{i}. PE STATION_{i}.xlsx").write_text("dummy xlsx")
        (raw_dir / f"0{i}. PE STATION_{i}").mkdir()

    result = validate_postprocessing_preflight(mock_env, date_str)

    assert isinstance(result, PreFlightValidationResult)
    assert result.date_folder == date_str
    assert result.quick_report_count == 3
    assert result.testsheet_count == 3
    assert result.raw_material_count == 3
    assert len(result.quick_reports) == 3
    assert len(result.testsheets) == 3
    assert len(result.raw_materials) == 3
    assert result.is_valid is True


def test_preflight_validation_happy_path_without_raw_material(mock_env: ProjectEnvironment) -> None:
    """Happy path: When RAW MATERIAL folder does not exist for the date, validation succeeds if QR == TS."""
    date_str = "02-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)

    for i in range(1, 3):
        (qr_dir / f"0{i}. PE STATION_{i}.docx").write_text("dummy docx")
        (ts_dir / f"0{i}. PE STATION_{i}.xlsx").write_text("dummy xlsx")

    result = validate_postprocessing_preflight(mock_env, date_str)

    assert result.date_folder == date_str
    assert result.quick_report_count == 2
    assert result.testsheet_count == 2
    assert result.raw_material_count is None
    assert len(result.raw_materials) == 0
    assert result.is_valid is True


def test_auxiliary_folder_isolation_in_testsheet_dir(mock_env: ProjectEnvironment) -> None:
    """Auxiliary subdirectories like processed_testsheet/, UNSORTED RAW DATA/, pdf/ inside TESTSHEET/<DATE>/ are ignored."""
    date_str = "03-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)

    # 2 valid testsheets and 2 valid quick reports
    (qr_dir / "01. PE ALPHA.docx").write_text("qr1")
    (qr_dir / "02. PE BETA.docx").write_text("qr2")
    (ts_dir / "01. PE ALPHA.xlsx").write_text("ts1")
    (ts_dir / "02. PE BETA.xlsx").write_text("ts2")

    # Auxiliary subdirectories inside TESTSHEET/<DATE>/
    proc_dir = ts_dir / "processed_testsheet"
    proc_dir.mkdir()
    (proc_dir / "01. PE ALPHA.xlsx").write_text("nested xlsx")
    (proc_dir / "pdf").mkdir()
    (proc_dir / "pdf" / "01. PE ALPHA.pdf").write_text("nested pdf")

    unsorted_dir = ts_dir / "UNSORTED RAW DATA"
    unsorted_dir.mkdir()
    (unsorted_dir / "FLIR001.jpg").write_text("img")

    arbitrary_dir = ts_dir / "some_other_folder"
    arbitrary_dir.mkdir()
    (arbitrary_dir / "extra.xlsx").write_text("nested extra")

    result = validate_postprocessing_preflight(mock_env, date_str)

    assert result.testsheet_count == 2
    assert [p.name for p in result.testsheets] == ["01. PE ALPHA.xlsx", "02. PE BETA.xlsx"]


def test_lock_files_and_non_target_extensions_isolation(mock_env: ProjectEnvironment) -> None:
    """Temporary lock files (~$*.xlsx, ~$*.docx), hidden files, and non-target file formats are ignored."""
    date_str = "04-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str
    raw_dir = mock_env.get_raw_material_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    # Valid files
    (qr_dir / "01. PE GAMMA.docx").write_text("qr1")
    (ts_dir / "01. PE GAMMA.xlsx").write_text("ts1")
    (raw_dir / "01. PE GAMMA").mkdir()

    # Noise in QUICK REPORT: lock file, pdf, hidden file, non-docx
    (qr_dir / "~$01. PE GAMMA.docx").write_text("lock docx")
    (qr_dir / ".hidden_report.docx").write_text("hidden")
    (qr_dir / "01. PE GAMMA.pdf").write_text("pdf")
    (qr_dir / "notes.txt").write_text("txt")

    # Noise in TESTSHEET: lock file, docx, pdf, hidden file, txt
    (ts_dir / "~$01. PE GAMMA.xlsx").write_text("lock xlsx")
    (ts_dir / ".hidden_sheet.xlsx").write_text("hidden")
    (ts_dir / "01. PE GAMMA.docx").write_text("misplaced docx")
    (ts_dir / "01. PE GAMMA.pdf").write_text("pdf")
    (ts_dir / "readme.txt").write_text("txt")

    # Noise in RAW MATERIAL: lock file, hidden folder, regular file
    (raw_dir / "~$lock_folder").mkdir()
    (raw_dir / ".hidden_folder").mkdir()
    (raw_dir / "stray_file.jpg").write_text("stray file")

    result = validate_postprocessing_preflight(mock_env, date_str)

    assert result.quick_report_count == 1
    assert result.testsheet_count == 1
    assert result.raw_material_count == 1
    assert [p.name for p in result.quick_reports] == ["01. PE GAMMA.docx"]
    assert [p.name for p in result.testsheets] == ["01. PE GAMMA.xlsx"]
    assert [p.name for p in result.raw_materials] == ["01. PE GAMMA"]


def test_fail_fast_on_count_mismatch_qr_vs_testsheet(mock_env: ProjectEnvironment) -> None:
    """PreFlightValidationError is raised when quick report count != testsheet count."""
    date_str = "05-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)

    # 3 QR vs 2 TS
    (qr_dir / "01. PE A.docx").write_text("qr1")
    (qr_dir / "02. PE B.docx").write_text("qr2")
    (qr_dir / "03. PE C.docx").write_text("qr3")

    (ts_dir / "01. PE A.xlsx").write_text("ts1")
    (ts_dir / "02. PE B.xlsx").write_text("ts2")

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_postprocessing_preflight(mock_env, date_str)

    err = exc_info.value
    assert err.date_folder == date_str
    assert err.quick_report_count == 3
    assert err.testsheet_count == 2
    assert "mismatch" in str(err).lower()
    assert "05-05-2026" in str(err)


def test_fail_fast_on_count_mismatch_raw_material(mock_env: ProjectEnvironment) -> None:
    """PreFlightValidationError is raised when RAW MATERIAL count mismatches QR/TS."""
    date_str = "06-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str
    raw_dir = mock_env.get_raw_material_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    # 2 QR, 2 TS, but only 1 Raw Material
    (qr_dir / "01. PE A.docx").write_text("qr1")
    (qr_dir / "02. PE B.docx").write_text("qr2")

    (ts_dir / "01. PE A.xlsx").write_text("ts1")
    (ts_dir / "02. PE B.xlsx").write_text("ts2")

    (raw_dir / "01. PE A").mkdir()

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_postprocessing_preflight(mock_env, date_str)

    err = exc_info.value
    assert err.date_folder == date_str
    assert err.quick_report_count == 2
    assert err.testsheet_count == 2
    assert err.raw_material_count == 1
    assert "raw material" in str(err).lower()


def test_fail_fast_missing_quick_report_directory(mock_env: ProjectEnvironment) -> None:
    """PreFlightValidationError is raised when QUICK REPORT/<DATE> directory does not exist."""
    date_str = "07-05-2026"
    ts_dir = mock_env.get_testsheet_dir() / date_str
    ts_dir.mkdir(parents=True)
    (ts_dir / "01. PE A.xlsx").write_text("ts1")

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_postprocessing_preflight(mock_env, date_str)

    assert exc_info.value.quick_report_count == 0
    assert "quick report" in str(exc_info.value).lower()


def test_fail_fast_missing_testsheet_directory(mock_env: ProjectEnvironment) -> None:
    """PreFlightValidationError is raised when TESTSHEET/<DATE> directory does not exist."""
    date_str = "08-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    qr_dir.mkdir(parents=True)
    (qr_dir / "01. PE A.docx").write_text("qr1")

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_postprocessing_preflight(mock_env, date_str)

    assert exc_info.value.testsheet_count == 0
    assert "testsheet" in str(exc_info.value).lower()


def test_fail_fast_empty_directory(mock_env: ProjectEnvironment) -> None:
    """PreFlightValidationError is raised when date folders exist but contain 0 valid target files."""
    date_str = "09-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_postprocessing_preflight(mock_env, date_str)

    assert exc_info.value.quick_report_count == 0
    assert exc_info.value.testsheet_count == 0


def test_date_folder_input_as_path(mock_env: ProjectEnvironment) -> None:
    """validate_postprocessing_preflight handles date_folder passed as Path object or absolute Path."""
    date_str = "10-05-2026"
    qr_dir = mock_env.get_quick_report_dir() / date_str
    ts_dir = mock_env.get_testsheet_dir() / date_str

    qr_dir.mkdir(parents=True)
    ts_dir.mkdir(parents=True)

    (qr_dir / "01. PE A.docx").write_text("qr1")
    (ts_dir / "01. PE A.xlsx").write_text("ts1")

    # Pass as relative Path
    res1 = validate_postprocessing_preflight(mock_env, Path(date_str))
    assert res1.date_folder == date_str
    assert res1.is_valid is True

    # Pass as absolute Path
    res2 = validate_postprocessing_preflight(mock_env, ts_dir)
    assert res2.date_folder == date_str
    assert res2.is_valid is True


def test_standalone_filter_functions(tmp_path: Path) -> None:
    """Standalone filter helpers correctly filter and sort items."""
    qr_dir = tmp_path / "QUICK REPORT"
    ts_dir = tmp_path / "TESTSHEET"
    raw_dir = tmp_path / "RAW MATERIAL"

    qr_dir.mkdir()
    ts_dir.mkdir()
    raw_dir.mkdir()

    # QUICK REPORT filtering
    (qr_dir / "02. PE B.docx").write_text("b")
    (qr_dir / "01. PE A.docx").write_text("a")
    (qr_dir / "~$01. PE A.docx").write_text("lock")
    (qr_dir / "file.pdf").write_text("pdf")
    (qr_dir / "subfolder").mkdir()

    qr_files = filter_valid_quick_reports(qr_dir)
    assert [p.name for p in qr_files] == ["01. PE A.docx", "02. PE B.docx"]

    # TESTSHEET filtering
    (ts_dir / "02. PE B.xlsx").write_text("b")
    (ts_dir / "01. PE A.xlsx").write_text("a")
    (ts_dir / "~$01. PE A.xlsx").write_text("lock")
    (ts_dir / "processed_testsheet").mkdir()
    (ts_dir / "UNSORTED RAW DATA").mkdir()
    (ts_dir / "01. PE A.docx").write_text("misplaced docx")

    ts_files = filter_valid_testsheets(ts_dir)
    assert [p.name for p in ts_files] == ["01. PE A.xlsx", "02. PE B.xlsx"]

    # RAW MATERIAL filtering
    (raw_dir / "02. PE B").mkdir()
    (raw_dir / "01. PE A").mkdir()
    (raw_dir / "~$lock").mkdir()
    (raw_dir / ".hidden").mkdir()
    (raw_dir / "stray.jpg").write_text("jpg")

    raw_folders = filter_valid_raw_materials(raw_dir)
    assert [p.name for p in raw_folders] == ["01. PE A", "02. PE B"]
