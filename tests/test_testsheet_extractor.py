"""Unit tests for TestsheetExtractor module in Pahang CLI."""

from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import openpyxl
import pytest

REAL_DATASET_ROOT = Path(
    os.getenv("PAHANG_BENCHMARK_ROOT", r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD")
)

from src.core.normalizers import (
    format_heater_amp,
    format_month_folder,
)
from src.testsheet.extractor import (
    TestsheetExtractor,
    clean_val,
    is_marked,
    normalize_building_type,
    normalize_fl_erms,
    to_excel_date,
)
from src.testsheet.models import PhotoRange, RawPhotoRanges, SwitchgearPanelSpec, TestsheetData


def test_format_month_folder() -> None:
    """Verify format_month_folder converts month inputs to XX. MONTH format."""
    assert format_month_folder("01. JAN") == "01. JANUARY"
    assert format_month_folder("01. JANUARY") == "01. JANUARY"
    assert format_month_folder("2026-01 (Jan)") == "01. JANUARY"
    assert format_month_folder("01-01-2026") == "01. JANUARY"
    assert format_month_folder("JANUARY") == "01. JANUARY"
    assert format_month_folder("january") == "01. JANUARY"
    assert format_month_folder("02. FEB") == "02. FEBRUARY"
    assert format_month_folder("03. MARCH") == "03. MARCH"
    assert format_month_folder("04. APRIL") == "04. APRIL"
    assert format_month_folder("05. MAY") == "05. MAY"
    assert format_month_folder("06. JUNE") == "06. JUNE"
    assert format_month_folder("07. JULY") == "07. JULY"
    assert format_month_folder("08. AUGUST") == "08. AUGUST"
    assert format_month_folder("09. SEPTEMBER") == "09. SEPTEMBER"
    assert format_month_folder("10. OCTOBER") == "10. OCTOBER"
    assert format_month_folder("11. NOVEMBER") == "11. NOVEMBER"
    assert format_month_folder("12. DECEMBER") == "12. DECEMBER"
    assert format_month_folder(date(2026, 3, 15)) == "03. MARCH"
    assert format_month_folder(datetime(2026, 12, 1, 10, 0)) == "12. DECEMBER"



def test_normalize_fl_erms() -> None:
    """Test normalize_fl_erms strips whitespace, handles .0 suffix, and handles None."""
    assert normalize_fl_erms("  CRAU-S001.0  ") == "CRAU-S001"
    assert normalize_fl_erms("CRAU-S001.0\t") == "CRAU-S001"
    assert normalize_fl_erms(None) == ""
    assert normalize_fl_erms("  TEST-FL  ") == "TEST-FL"
    assert normalize_fl_erms(12345) == "12345"


def test_clean_val() -> None:
    """Test clean_val returns None for empty/dash/NONE and strips whitespace."""
    assert clean_val(None) is None
    assert clean_val("") is None
    assert clean_val("   \t ") is None
    assert clean_val("-") is None
    assert clean_val("NONE") is None
    assert clean_val("None") is None
    assert clean_val("N/A") is None
    assert clean_val("#REF!") is None
    assert clean_val("nan") is None
    assert clean_val("  RM CHEROH \t ") == "RM CHEROH"


def test_is_marked() -> None:
    """Test is_marked returns True for checkmarks and False for empty/NO/N-A/0."""
    assert is_marked("/") is True
    assert is_marked("X") is True
    assert is_marked("YES") is True
    assert is_marked("TRUE") is True
    assert is_marked("v") is True

    assert is_marked(None) is False
    assert is_marked("") is False
    assert is_marked("  ") is False
    assert is_marked("NO") is False
    assert is_marked("N/A") is False
    assert is_marked("0") is False
    assert is_marked("-") is False
    assert is_marked("NONE") is False
    assert is_marked("FALSE") is False


def test_normalize_building_type() -> None:
    """Test normalize_building_type maps to ATTACH/INDOOR/OUTDOOR and None for empty/dash."""
    assert normalize_building_type("ATTACHED PE") == "ATTACH"
    assert normalize_building_type("INDOOR PE") == "INDOOR"
    assert normalize_building_type("BANGUNAN DALAMAN") == "INDOOR"
    assert normalize_building_type("OUTDOOR SUBSTATION") == "OUTDOOR"
    assert normalize_building_type("STESEN LUARAN") == "OUTDOOR"

    assert normalize_building_type(None) is None
    assert normalize_building_type("") is None
    assert normalize_building_type("-") is None
    assert normalize_building_type("NONE") is None
    assert normalize_building_type("N/A") is None


def test_to_excel_date() -> None:
    """Test to_excel_date handles datetime, date, string formats, and None."""
    dt = datetime(2026, 5, 1, 14, 30)
    assert to_excel_date(dt) == dt

    d = date(2026, 5, 1)
    assert to_excel_date(d) == datetime(2026, 5, 1, 0, 0)

    assert to_excel_date("01/05/2026") == datetime(2026, 5, 1)
    assert to_excel_date("01-05-2026") == datetime(2026, 5, 1)
    assert to_excel_date("2026-05-01") == datetime(2026, 5, 1)
    assert to_excel_date("01.05.2026") == datetime(2026, 5, 1)
    assert to_excel_date("01 May 2026") == datetime(2026, 5, 1)
    assert to_excel_date("01-May-2026") == datetime(2026, 5, 1)

    assert to_excel_date(None) is None
    assert to_excel_date("") is None
    assert to_excel_date("-") is None
    assert to_excel_date("invalid-date") is None


@pytest.fixture
def sample_testsheet_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "001. RM CHEROH.xlsx"
    wb = openpyxl.Workbook()

    # PCE Testsheet sheet with fixed cells
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"
    ws_pce["W5"] = "CRAU-S001"
    ws_pce["C5"] = "RM CHEROH"
    ws_pce["P4"] = "01-05-2026"
    ws_pce["P5"] = "1430"
    ws_pce["S6"] = "65.0"
    ws_pce["W6"] = "BACKGROUND TEMP : 23.2 °C"

    # PCE VI sheet with fixed cells
    ws_vi = wb.create_sheet(title="PCE VI")
    ws_vi["C7"] = "RM CHEROH SITE"
    ws_vi["C8"] = "3.8, 102.1"
    ws_vi["N1"] = "RM"
    ws_vi["C9"] = "OUTDOOR"
    ws_vi["D9"] = "/"

    # RAW DATA sheet with photo ranges only (schema: Row 1=[None, START, END], Row 2=[IR, start, end], Row 3=[DG, start, end])
    ws = wb.create_sheet(title="RAW DATA")
    ws.cell(1, 2, "START")
    ws.cell(1, 3, "END")
    ws.cell(2, 1, "IR")
    ws.cell(2, 2, 100)
    ws.cell(2, 3, 105)
    ws.cell(3, 1, "DG")
    ws.cell(3, 2, 500)
    ws.cell(3, 3, 510)

    wb.save(file_path)
    wb.close()
    return file_path


def test_extract_testsheet_data(sample_testsheet_file: Path) -> None:
    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(sample_testsheet_file)

    assert isinstance(data, TestsheetData)
    assert data.substation_number == 1
    assert data.substation_name_erms == "RM CHEROH"
    assert data.fl_erms == "CRAU-S001"
    assert data.date_str == ""
    assert data.cycle_1 == datetime(2026, 5, 1)
    assert data.substation_type == "RM"
    assert data.substation_name_site == "RM CHEROH SITE"
    assert data.gps_coordinate == "3.8, 102.1"
    assert data.building_type == "OUTDOOR"
    assert data.time == "02:30 PM"
    assert data.humidity == "65%"
    assert data.ambient == "23.2 °C"

    assert data.photo_ranges.ir == PhotoRange(start_num=100, end_num=105)
    assert data.photo_ranges.dg == PhotoRange(start_num=500, end_num=510)
    assert data.photo_ranges.ir.contains(102) is True
    assert data.photo_ranges.ir.contains(200) is False


def test_fixed_cell_extraction(tmp_path: Path) -> None:
    """Test fixed cell extraction from PCE Testsheet, PCE VI, and RAW DATA sheets."""
    file_path = tmp_path / "002. PPU BENTA.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: PCE Testsheet
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"
    ws_pce["W5"] = "  CRAU-S002.0  "
    ws_pce["C5"] = "PPU BENTA ERMS"
    ws_pce["P4"] = "15-06-2026"

    # Sheet 2: PCE VI
    ws_vi = wb.create_sheet(title="PCE VI")
    ws_vi["C7"] = "PPU BENTA SITE"
    ws_vi["C8"] = "3.8123, 102.1234"
    ws_vi["N1"] = "PPU"
    ws_vi["C9"] = "ATTACHED"
    ws_vi["D9"] = "/"

    # Sheet 3: RAW DATA
    ws_raw = wb.create_sheet(title="RAW DATA")
    ws_raw.cell(1, 2, "START")
    ws_raw.cell(1, 3, "END")
    ws_raw.cell(2, 1, "IR")
    ws_raw.cell(2, 2, 200)
    ws_raw.cell(2, 3, 210)
    ws_raw.cell(3, 1, "DG")
    ws_raw.cell(3, 2, 600)
    ws_raw.cell(3, 3, 615)

    wb.save(file_path)
    wb.close()

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(file_path)

    assert data.substation_number == 2
    assert data.fl_erms == "CRAU-S002"
    assert data.substation_name_erms == "PPU BENTA ERMS"
    assert data.substation_name_erms == "PPU BENTA ERMS"
    assert data.cycle_1 == datetime(2026, 6, 15)

    assert data.substation_name_site == "PPU BENTA SITE"
    assert data.gps_coordinate == "3.8123, 102.1234"
    assert data.substation_type == "PPU"
    assert data.substation_type == "PPU"
    assert data.building_type == "ATTACH"

    assert data.fl_erms == "CRAU-S002"
    assert data.date_str == ""

    assert data.photo_ranges.ir == PhotoRange(start_num=200, end_num=210)
    assert data.photo_ranges.dg == PhotoRange(start_num=600, end_num=615)


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


def test_grid_table_photo_range_extraction(tmp_path: Path) -> None:
    """Test extracting photo ranges from grid table format (Row 1: [None, 'START', 'END'], Row 2: ['IR', 49, 66])."""
    file_path = tmp_path / "001. GRID_TABLE.xlsx"
    wb = openpyxl.Workbook()

    ws_test = wb.active
    ws_test.title = "PCE Testsheet"
    ws_test.cell(1, 1, "PE NO")
    ws_test.cell(1, 2, 289)

    ws_raw = wb.create_sheet(title="RAW DATA")
    ws_raw.cell(1, 2, "START")
    ws_raw.cell(1, 3, "END")
    ws_raw.cell(2, 1, "IR")
    ws_raw.cell(2, 2, 49)
    ws_raw.cell(2, 3, 66)
    ws_raw.cell(3, 1, "DG")
    ws_raw.cell(3, 2, 1715)
    ws_raw.cell(3, 3, 1739)

    wb.save(file_path)
    wb.close()

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(file_path)

    assert data.photo_ranges.ir == PhotoRange(start_num=49, end_num=66)
    assert data.photo_ranges.dg == PhotoRange(start_num=1715, end_num=1739)


def test_extract_testsheet_metadata(sample_testsheet_file: Path) -> None:
    extractor = TestsheetExtractor()
    meta = extractor.extract_testsheet_metadata(sample_testsheet_file, station_hint="RAUB", date_hint="01-05-2026")

    assert isinstance(meta, TestsheetData)
    assert meta.substation_number == 1
    assert meta.substation_name_erms == "RM CHEROH"
    assert meta.fl_erms == "CRAU-S001"
    assert meta.date_str == "01-05-2026"
    assert meta.cycle_1 == datetime(2026, 5, 1)
    assert meta.substation_type == "RM"
    assert meta.station_name == "RAUB"


def test_switchgear_panel_spec_subrow_attributes() -> None:
    """Verify SwitchgearPanelSpec accepts and defaults sub-row photo attributes."""
    default_panel = SwitchgearPanelSpec()
    assert default_panel.cable_photo is None
    assert default_panel.breaker_photo is None
    assert default_panel.secondary_photo is None
    assert default_panel.busbar_photo is None
    assert default_panel.pt_photo is None
    assert default_panel.has_pt_measurement is False

    spec = SwitchgearPanelSpec(
        cable_photo=10,
        breaker_photo=11,
        secondary_photo=12,
        busbar_photo=13,
        pt_photo=14,
        has_pt_measurement=True,
    )
    assert spec.cable_photo == 10
    assert spec.breaker_photo == 11
    assert spec.secondary_photo == 12
    assert spec.busbar_photo == 13
    assert spec.pt_photo == 14
    assert spec.has_pt_measurement is True


def test_build_switchgear_panel_scan_spec_propagation() -> None:
    """Verify build_switchgear_panel_scan_spec propagates all 6 sub-row attributes."""
    from src.full_report.models import SwitchgearCategory, build_switchgear_panel_scan_spec

    panel = SwitchgearPanelSpec(
        panel_no=1,
        name="INCOMING",
        cable_photo=498,
        breaker_photo=493,
        secondary_photo=520,
        busbar_photo=503,
        pt_photo=526,
        has_pt_measurement=True,
    )
    scan_spec = build_switchgear_panel_scan_spec(panel, SwitchgearCategory.VCB)
    assert scan_spec.cable_photo == 498
    assert scan_spec.breaker_photo == 493
    assert scan_spec.secondary_photo == 520
    assert scan_spec.busbar_photo == 503
    assert scan_spec.pt_photo == 526
    assert scan_spec.has_pt_measurement is True


def test_parse_secondary_photo() -> None:
    """Verify parse_secondary_photo parses 'S.PANEL IR <num>', 'IR <num>', bare digits, and sentinels."""
    from src.testsheet.extractor import parse_secondary_photo

    assert parse_secondary_photo(None) is None
    assert parse_secondary_photo("") is None
    assert parse_secondary_photo("-") is None
    assert parse_secondary_photo("NONE") is None
    assert parse_secondary_photo("N/A") is None
    assert parse_secondary_photo("S.PANEL IR 520") == 520
    assert parse_secondary_photo("S PANEL IR 521") == 521
    assert parse_secondary_photo("SPANEL IR 522") == 522
    assert parse_secondary_photo("S. PANEL IR  523") == 523
    assert parse_secondary_photo("IR 524") == 524
    assert parse_secondary_photo("IR525") == 525
    assert parse_secondary_photo("526") == 526
    assert parse_secondary_photo(527) == 527
    assert parse_secondary_photo(528.0) == 528
    assert parse_secondary_photo("CABLE") is None


def test_parse_photo_numbers_six_digit_concatenation() -> None:
    """Verify parse_photo_numbers splits 6-digit concatenated photo numbers (e.g. 485489.0 -> 485, 489)."""
    from src.testsheet.extractor import parse_photo_numbers

    assert parse_photo_numbers(485489.0) == (485, 489)
    assert parse_photo_numbers(488492.0) == (488, 492)
    assert parse_photo_numbers(140145) == (140, 145)
    assert parse_photo_numbers(142176) == (142, 176)
    assert parse_photo_numbers("485489") == (485, 489)


def test_extract_overview_photos_rows_26_27_28() -> None:
    """Verify _extract_overview_photos extracts Row 27 (Front), Row 26 (Rear), Row 28 (Top)."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"

    # VCB multi-overview case: Row 27 (Front), Row 26 (Rear), Row 28 (Top)
    ws_pce["O27"] = 485
    ws_pce["O26"] = 488
    ws_pce["O28"] = 491

    swgs = extractor._extract_switchgear_specs(wb, ws_vi=None, pce_sheets=[ws_pce])
    assert len(swgs) == 1
    assert swgs[0].photo_numbers == (485, 488, 491)

    # RMU case where Row 27 is empty
    wb_rmu = openpyxl.Workbook()
    ws_rmu = wb_rmu.active
    ws_rmu.title = "PCE Testsheet"
    ws_rmu["O26"] = 28
    ws_rmu["O28"] = 33

    swgs_rmu = extractor._extract_switchgear_specs(wb_rmu, ws_vi=None, pce_sheets=[ws_rmu])
    assert len(swgs_rmu) == 1
    assert swgs_rmu[0].photo_numbers == (28, 33)


def test_extract_panels_subrow_extraction() -> None:
    """Verify _extract_panels extracts all 4 sub-rows, Col P, PT measurements, distinct photo_numbers, and exclusion."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PCE Testsheet"

    # Panel 1: Complete 4-row sub-grid (without PT)
    ws["B10"] = "F01"
    ws["C10"] = "FEEDER 1"
    ws["O10"] = 100
    ws["O11"] = 101
    ws["P11"] = "S.PANEL IR 102"
    ws["O12"] = 103

    # Panel 2: With PT photo and PT measurement
    ws["B14"] = "F02"
    ws["C14"] = "FEEDER 2"
    ws["O14"] = 104
    ws["O15"] = 105
    ws["O16"] = 106
    ws["O17"] = 107
    ws["K17"] = 35.0  # PT measurement reading

    # Panel 3: Valid panel with blank top metadata but photo in sub-row 19 (r+1)
    ws["O19"] = 200

    # Panel 4: Completely blank slot (r=22..25) - must be excluded

    panels = extractor._extract_panels([ws])
    assert len(panels) == 3

    p1 = panels[0]
    assert p1.cable_photo == 100
    assert p1.breaker_photo == 101
    assert p1.secondary_photo == 102
    assert p1.busbar_photo == 103
    assert p1.pt_photo is None
    assert p1.has_pt_measurement is False
    assert p1.photo_numbers == (100, 101, 102, 103)

    p2 = panels[1]
    assert p2.cable_photo == 104
    assert p2.breaker_photo == 105
    assert p2.secondary_photo is None
    assert p2.busbar_photo == 106
    assert p2.pt_photo == 107
    assert p2.has_pt_measurement is True
    assert p2.photo_numbers == (104, 105, 106, 107)

    p3 = panels[2]
    assert p3.breaker_photo == 200
    assert p3.photo_numbers == (200,)


@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_benchmark_157_perpustakaan_awam_subrow_extraction() -> None:
    """Verify sub-row and overview photo extraction against PE 157 Perpustakaan Awam benchmark."""
    workbook_path = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "KUANTAN"
        / "01. AUGUST"
        / "25-08-2026"
        / "157. PERPUSTAKAAN AWAM(VCB).xlsx"
    )
    assert workbook_path.is_file(), f"Benchmark workbook missing: {workbook_path}"

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(workbook_path)
    assert len(data.equipment.switchgears) >= 1
    swg = data.equipment.switchgears[0]

    # Overview extraction captures Row 27 photo 485, Row 26 photo 488, Row 28 photo 491
    assert swg.photo_numbers == (485, 488, 491)

    # Panels 1 to 4 assertions
    assert len(swg.panels) == 5

    # Panel 1: secondary_photo == 520 (parsed from 'S.PANEL IR 520')
    p1 = swg.panels[0]
    assert p1.cable_photo == 498
    assert p1.breaker_photo == 493
    assert p1.secondary_photo == 520
    assert p1.busbar_photo == 503
    assert p1.pt_photo is None
    assert p1.has_pt_measurement is False
    assert p1.photo_numbers == (498, 493, 520, 503)

    # Panel 2: secondary_photo == 521
    p2 = swg.panels[1]
    assert p2.cable_photo == 499
    assert p2.breaker_photo == 494
    assert p2.secondary_photo == 521
    assert p2.busbar_photo == 504
    assert p2.pt_photo is None
    assert p2.has_pt_measurement is False
    assert p2.photo_numbers == (499, 494, 521, 504)

    # Panel 3: secondary_photo == 522
    p3 = swg.panels[2]
    assert p3.cable_photo == 500
    assert p3.breaker_photo == 495
    assert p3.secondary_photo == 522
    assert p3.busbar_photo == 505
    assert p3.pt_photo is None
    assert p3.has_pt_measurement is False
    assert p3.photo_numbers == (500, 495, 522, 505)

    # Panel 4: secondary_photo == 523, pt_photo == 526, has_pt_measurement is True
    p4 = swg.panels[3]
    assert p4.cable_photo == 501
    assert p4.breaker_photo == 496
    assert p4.secondary_photo == 523
    assert p4.busbar_photo == 506
    assert p4.pt_photo == 526
    assert p4.has_pt_measurement is True
    assert p4.photo_numbers == (501, 496, 523, 506, 526)


@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_benchmark_082_ssu_pam_air_kobat_subrow_extraction() -> None:
    """Verify sub-row and overview photo extraction against PE 082 SSU Pam Air Kobat benchmark."""
    workbook_path = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "KUANTAN"
        / "01. AUGUST"
        / "14-08-2026"
        / "082. SSU PAM AIR KOBAT.xlsx"
    )
    assert workbook_path.is_file(), f"Benchmark workbook missing: {workbook_path}"

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(workbook_path)
    assert len(data.equipment.switchgears) >= 1
    swg = data.equipment.switchgears[0]

    # Overview photos: Front (Row 27: 140), Rear (Row 26: 142), Top (Row 28: 147)
    assert swg.photo_numbers == (140, 142, 147)

    # Panel 1 (L / TX): cable=177 (from 177193), breaker=148, sec=217, bus=162
    p1 = swg.panels[0]
    assert p1.cable_photo == 177
    assert p1.breaker_photo == 148
    assert p1.secondary_photo == 217
    assert p1.busbar_photo == 162
    assert p1.pt_photo is None
    assert p1.has_pt_measurement is False

    # Transition Panel: secondary_photo is None
    transition_panel = [p for p in swg.panels if "TRANSITION" in p.name.upper()][0]
    assert transition_panel.cable_photo == 183
    assert transition_panel.breaker_photo == 154
    assert transition_panel.secondary_photo is None
    assert transition_panel.busbar_photo == 168

    # Bus Section Panel: secondary_photo == 223
    bs_panel = [p for p in swg.panels if p.name.upper() == "B/S"][0]
    assert bs_panel.cable_photo == 184
    assert bs_panel.breaker_photo == 155
    assert bs_panel.secondary_photo == 223

    # PT Panel (MSB PENGGUNA 1): pt_photo == 232, has_pt_measurement is True
    pt_panel = [p for p in swg.panels if "MSB PENGGUNA 1" in p.name.upper()][0]
    assert pt_panel.pt_photo == 232
    assert pt_panel.has_pt_measurement is True


@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_benchmark_156_ssu_wisma_mpk_subrow_extraction() -> None:
    """Verify sub-row and overview photo extraction against PE 156 SSU Wisma MPK benchmark."""
    workbook_path = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "KUANTAN"
        / "01. AUGUST"
        / "25-08-2026"
        / "156. SSU WISMA MPK.xlsx"
    )
    assert workbook_path.is_file(), f"Benchmark workbook missing: {workbook_path}"

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(workbook_path)
    assert len(data.equipment.switchgears) >= 1
    swg = data.equipment.switchgears[0]

    # Overview photos: Front (Row 27: 424), Rear (Row 26: 427), Top (Row 28: 426)
    assert swg.photo_numbers == (424, 427, 426)

    # Panel 1 (MSB): cable=442, breaker=432, secondary=475, busbar=452, pt=462, has_pt=True
    p1 = swg.panels[0]
    assert p1.cable_photo == 442
    assert p1.breaker_photo == 432
    assert p1.secondary_photo == 475
    assert p1.busbar_photo == 452
    assert p1.pt_photo == 462
    assert p1.has_pt_measurement is True

    # Transition panel: secondary_photo is None
    transition_panel = [p for p in swg.panels if "TRANSITION" in p.name.upper()][0]
    assert transition_panel.secondary_photo is None

    # Bus Section Panel: secondary_photo == 479
    bs_panel = [p for p in swg.panels if p.name.upper() == "B/S"][0]
    assert bs_panel.secondary_photo == 479


@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_benchmark_lvdb_and_heater_and_load_amp_real_workbooks() -> None:
    """Verify LVDB naming, model extraction, and panel load/heater amp formatting across real testsheets."""
    p251 = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "RAUB"
        / "02. SEPTEMBER"
        / "13-09-2026"
        / "251. PUSAT SERENTI SG RUAN.xlsx"
    )
    p259 = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "RAUB"
        / "02. SEPTEMBER"
        / "13-09-2026"
        / "259. SUNGAI RUAN BARU (IR).xlsx"
    )
    p157 = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "KUANTAN"
        / "01. AUGUST"
        / "25-08-2026"
        / "157. PERPUSTAKAAN AWAM(VCB).xlsx"
    )

    extractor = TestsheetExtractor()

    # 1. 251: LVDB name is "LVDB TX1", model is "J-SLOTTED"
    if p251.is_file():
        d251 = extractor.extract_testsheet_data(p251)
        assert len(d251.equipment.lvdb_specs) >= 1
        lvdb251 = d251.equipment.lvdb_specs[0]
        assert lvdb251.name == "LVDB TX1"
        assert lvdb251.model == "J-SLOTTED"

    # 2. 259: LVDB name is "FP TX1", model is "J-SLOTTED"
    if p259.is_file():
        d259 = extractor.extract_testsheet_data(p259)
        assert len(d259.equipment.lvdb_specs) >= 1
        lvdb259 = d259.equipment.lvdb_specs[0]
        assert lvdb259.name == "FP TX1"
        assert lvdb259.model == "J-SLOTTED"

    # 3. 157: Panel load_amp is "17" and "0" (not "17.0" or "0.0"), and heater formats to 2 decimal places
    if p157.is_file():
        d157 = extractor.extract_testsheet_data(p157)
        assert len(d157.equipment.switchgears) >= 1
        swg157 = d157.equipment.switchgears[0]
        loads = [p.load_amp for p in swg157.panels]
        assert "17" in loads
        assert "0" in loads
        assert "17.0" not in loads
        assert "0.0" not in loads

        # Check heater formatting
        for p in swg157.panels:
            if p.heater_amp:
                h_formatted = format_heater_amp(p.heater_amp, is_vcb=True)
                assert h_formatted.startswith("ON:")
                assert h_formatted.endswith("A/OFF:0.0A")
                val_part = h_formatted.split("ON:")[1].split("A/OFF:")[0]
                assert "." in val_part
                assert len(val_part.split(".")[1]) == 2








