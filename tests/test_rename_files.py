"""Unit tests for rename_files_match workflow with target-type filtering and auxiliary folder isolation."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.workflows.rename_files import RenamePair, RenameFilesSummary, rename_files_match


def test_rename_files_testsheet_mode_ignores_auxiliary_subdirectories(tmp_path: Path) -> None:
    """Testsheet mode (.docx -> .xlsx): strictly ignores subdirectories like UNSORTED RAW DATA and processed_testsheet."""
    qr_dir = tmp_path / "QUICK_REPORT"
    ts_dir = tmp_path / "TESTSHEET"
    qr_dir.mkdir()
    ts_dir.mkdir()

    # 3 Quick Reports
    for i in range(1, 4):
        (qr_dir / f"0{i}. PE STATION_{i} (IR+VI).docx").write_text("docx")

    # 3 Testsheets
    for i in range(1, 4):
        (ts_dir / f"0{i}. OLD_NAME_{i}.xlsx").write_text("xlsx")

    # Auxiliary subdirectories in TESTSHEET/
    (ts_dir / "UNSORTED RAW DATA").mkdir()
    (ts_dir / "processed_testsheet").mkdir()
    (ts_dir / "pdf").mkdir()
    (ts_dir / "~$lock.xlsx").write_text("lock")

    summary = rename_files_match(qr_dir, ts_dir)

    assert isinstance(summary, RenameFilesSummary)
    assert len(summary.renamed) == 3
    assert (ts_dir / "01. PE STATION_1 (IR+VI).xlsx").exists()
    assert (ts_dir / "02. PE STATION_2 (IR+VI).xlsx").exists()
    assert (ts_dir / "03. PE STATION_3 (IR+VI).xlsx").exists()
    # Auxiliary folders remain intact
    assert (ts_dir / "UNSORTED RAW DATA").is_dir()
    assert (ts_dir / "processed_testsheet").is_dir()


def test_rename_files_raw_material_mode_ignores_loose_files(tmp_path: Path) -> None:
    """Raw material mode (.docx -> folders): strictly ignores loose files like desktop.ini and lock files."""
    qr_dir = tmp_path / "QUICK_REPORT"
    raw_dir = tmp_path / "RAW_MATERIAL"
    qr_dir.mkdir()
    raw_dir.mkdir()

    # 3 Quick Reports
    for i in range(1, 4):
        (qr_dir / f"0{i}. PE STATION_{i} (VI).docx").write_text("docx")

    # 3 Substation folders
    for i in range(1, 4):
        (raw_dir / f"0{i}. OLD_PE_{i}").mkdir()

    # Noise files in RAW MATERIAL/
    (raw_dir / "desktop.ini").write_text("[settings]")
    (raw_dir / "~$lock.tmp").write_text("lock")
    (raw_dir / ".DS_Store").write_text("ds")

    summary = rename_files_match(qr_dir, raw_dir)

    assert len(summary.renamed) == 3
    assert (raw_dir / "01. PE STATION_1 (VI)").is_dir()
    assert (raw_dir / "02. PE STATION_2 (VI)").is_dir()
    assert (raw_dir / "03. PE STATION_3 (VI)").is_dir()
    # Noise files untouched
    assert (raw_dir / "desktop.ini").exists()


def test_rename_files_explicit_target_type(tmp_path: Path) -> None:
    """Explicit target_type='xlsx' and target_type='dir' enforce exact item filtering."""
    qr_dir = tmp_path / "QUICK_REPORT"
    ts_dir = tmp_path / "TESTSHEET"
    qr_dir.mkdir()
    ts_dir.mkdir()

    (qr_dir / "01. STATION A (IR).docx").write_text("docx")
    (ts_dir / "01. OLD A.xlsx").write_text("xlsx")
    (ts_dir / "UNSORTED RAW DATA").mkdir()

    summary = rename_files_match(qr_dir, ts_dir, target_type="xlsx")
    assert len(summary.renamed) == 1
    assert (ts_dir / "01. STATION A (IR).xlsx").exists()


def test_rename_files_quantity_mismatch_error(tmp_path: Path) -> None:
    """Quantity mismatch raises descriptive ValueError when actual valid counts differ."""
    qr_dir = tmp_path / "QUICK_REPORT"
    ts_dir = tmp_path / "TESTSHEET"
    qr_dir.mkdir()
    ts_dir.mkdir()

    (qr_dir / "01. STATION A.docx").write_text("docx")
    (qr_dir / "02. STATION B.docx").write_text("docx")
    (ts_dir / "01. OLD A.xlsx").write_text("xlsx")

    with pytest.raises(ValueError, match="Quantity mismatch: Input directory has 2 item"):
        rename_files_match(qr_dir, ts_dir)
