"""Unit tests for TestsheetExtractor module in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
import openpyxl
import pytest

from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import PhotoRange, RawPhotoRanges, TestsheetData


@pytest.fixture
def sample_testsheet_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "001. RM CHEROH.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "RAW DATA"

    # Add metadata and photo range labels
    ws.cell(1, 1, "PE NO")
    ws.cell(1, 2, 1)

    ws.cell(2, 1, "SUBSTATION NAME")
    ws.cell(2, 2, "RM CHEROH")

    ws.cell(3, 1, "FL NUMBER")
    ws.cell(3, 2, "CRAU-S001")

    ws.cell(4, 1, "DATE")
    ws.cell(4, 2, "01-05-2026")

    ws.cell(5, 1, "TYPE")
    ws.cell(5, 2, "RM")

    ws.cell(6, 1, "WO")
    ws.cell(6, 2, "4001234")

    ws.cell(8, 1, "IR START")
    ws.cell(8, 2, 100)
    ws.cell(8, 3, "IR END")
    ws.cell(8, 4, 105)

    ws.cell(9, 1, "DG START")
    ws.cell(9, 2, 500)
    ws.cell(9, 3, "DG END")
    ws.cell(9, 4, 510)

    wb.save(file_path)
    wb.close()
    return file_path


def test_extract_testsheet_data(sample_testsheet_file: Path) -> None:
    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(sample_testsheet_file)

    assert isinstance(data, TestsheetData)
    assert data.pe_number == 1
    assert data.substation_name == "RM CHEROH"
    assert data.fl_number == "CRAU-S001"
    assert data.date_str == "01-05-2026"
    assert data.type_code == "RM"
    assert data.wo_number == "4001234"

    assert data.photo_ranges.ir == PhotoRange(start_num=100, end_num=105)
    assert data.photo_ranges.dg == PhotoRange(start_num=500, end_num=510)
    assert data.photo_ranges.ir.contains(102) is True
    assert data.photo_ranges.ir.contains(200) is False


def test_extract_photo_ranges(sample_testsheet_file: Path) -> None:
    extractor = TestsheetExtractor()
    ranges = extractor.extract_photo_ranges(sample_testsheet_file)

    assert isinstance(ranges, RawPhotoRanges)
    assert ranges.ir.start_num == 100
    assert ranges.ir.end_num == 105
    assert ranges.dg.start_num == 500
    assert ranges.dg.end_num == 510


def test_single_photo_range() -> None:
    single_start = PhotoRange(start_num=42, end_num=None)
    assert single_start.is_valid is True
    assert single_start.contains(42) is True
    assert single_start.contains(43) is False

    single_end = PhotoRange(start_num=None, end_num=99)
    assert single_end.is_valid is True
    assert single_end.contains(99) is True
    assert single_end.contains(98) is False
