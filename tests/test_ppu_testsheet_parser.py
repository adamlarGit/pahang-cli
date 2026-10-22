"""Unit tests for PpuTestsheetParser (Ticket #092)."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.testsheet.models import (
    SwitchgearPanelSpec,
    TestsheetData,
    VisualInspectionFinding,
)
from src.testsheet.parsers.ppu import PpuTestsheetParser
from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook


def test_ppu_can_handle_sheets() -> None:
    parser = PpuTestsheetParser()
    assert parser.can_handle_sheets(["33kV (Main)", "Visual Inspec."]) is True
    assert parser.can_handle_sheets(["33kV (Extra)"]) is True
    assert parser.can_handle_sheets(["11kV (Main)"]) is True
    assert parser.can_handle_sheets(["11kV (Extra)"]) is True
    assert parser.can_handle_sheets(["11kV (Extra) (2)"]) is True
    assert parser.can_handle_sheets(["PCE Testsheet"]) is False
    assert parser.can_handle_sheets(["RAW DATA", "Sheet1"]) is False


def test_ppu_substation_number_resolution_hierarchy(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()

    # 1. Cell V2 on 33kV (Main) takes precedence
    wb1_path = tmp_path / "99. UNRELATED_FILENAME.xlsx"
    create_ppu_testsheet_workbook(
        path=wb1_path,
        v2_substation_num_33kv=5,
        v2_substation_num_11kv=10,
    )
    data1 = parser.extract_testsheet_data(wb1_path)
    assert data1.substation_number == 5

    # 2. Cell V2 on 11kV (Main) used when 33kV V2 is absent
    wb2_path = tmp_path / "99. UNRELATED_FILENAME.xlsx"
    create_ppu_testsheet_workbook(
        path=wb2_path,
        v2_substation_num_33kv=None,
        v2_substation_num_11kv=12,
    )
    data2 = parser.extract_testsheet_data(wb2_path)
    assert data2.substation_number == 12

    # 3. Filename prefix used when both V2 cells are missing/blank
    wb3_path = tmp_path / "07. PPU APMM 33-11kV.xlsx"
    create_ppu_testsheet_workbook(
        path=wb3_path,
        v2_substation_num_33kv=None,
        v2_substation_num_11kv=None,
    )
    data3 = parser.extract_testsheet_data(wb3_path)
    assert data3.substation_number == 7

    # 4. ValueError raised when all resolution attempts fail
    wb4_path = tmp_path / "NO_NUMBER_PPU.xlsx"
    create_ppu_testsheet_workbook(
        path=wb4_path,
        v2_substation_num_33kv="",
        v2_substation_num_11kv=None,
    )
    with pytest.raises(ValueError, match="Unable to determine substation number for NO_NUMBER_PPU.xlsx"):
        parser.extract_testsheet_data(wb4_path)


def test_ppu_metadata_header_extraction_and_fallback(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()

    # Case A: 33kV present -> extracts header metadata from 33kV (Main)
    wb_33_path = tmp_path / "01. PPU DUAL.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_33_path,
        substation_name="PPU GEBENG 33kV",
        fl_number="CGBG-PPU-GBNG",
        date_val="2026-10-15",
        time_val="11:45 AM",
        ambient_temp="31.2",
        humidity="60%",
        background_tev="4",
        gps_coordinate="3.987, 103.456",
    )
    data = parser.extract_testsheet_data(wb_33_path)
    assert data.substation_name_site == "PPU GEBENG 33kV"
    assert data.fl_site == "CGBG-PPU-GBNG"
    assert data.date_str == "15-10-2026"
    assert data.time == "11:45 AM"
    assert "31.2" in data.ambient
    assert data.humidity == "60%"
    assert data.tev_background == "4"
    assert data.gps_coordinate == "3.987, 103.456"

    # Case B: 11kV-only station (33kV absent) -> falls back to 11kV (Main)
    wb_11_path = tmp_path / "02. SSU 11KV ONLY.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_11_path,
        has_33kv=False,
        has_11kv=True,
        substation_name="SSU INDUSTRIAL 11kV",
        fl_number="CGBG-SSU-IND",
        date_val="2026-10-16",
        ambient_temp="29.8",
        humidity="70%",
    )
    data_11 = parser.extract_testsheet_data(wb_11_path)
    assert data_11.substation_name_site == "SSU INDUSTRIAL 11kV"
    assert data_11.fl_site == "CGBG-SSU-IND"
    assert data_11.date_str == "16-10-2026"
    assert "29.8" in data_11.ambient
    assert data_11.humidity == "70%"


def test_ppu_dual_voltage_switchgear_assembly(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()

    # 1. Dual-voltage station: both 33kV and 11kV lineups present
    wb_dual = tmp_path / "01. PPU DUAL.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_dual,
        has_33kv=True,
        has_11kv=True,
        panels_33kv=2,
        panels_11kv=3,
        extra_panels_33kv=([[{"feeder_no": "3P3", "name": "EXTRA 33kV"}]]),
    )
    data_dual = parser.extract_testsheet_data(wb_dual)
    assert len(data_dual.equipment.switchgears) == 2
    swg_33, swg_11 = data_dual.equipment.switchgears

    assert swg_33.switchgear_type == "GIS"
    # 2 main panels + 1 extra panel = 3 panels
    panel_names_33 = [p.name for p in swg_33.panels]
    assert "EXTRA 33kV" in panel_names_33
    assert len(panel_names_33) == 3

    assert swg_11.switchgear_type == "VCB"
    assert len(swg_11.panels) == 3

    # 2. 33kV only
    wb_33_only = tmp_path / "02. 33KV ONLY.xlsx"
    create_ppu_testsheet_workbook(path=wb_33_only, has_33kv=True, has_11kv=False, panels_33kv=2)
    data_33 = parser.extract_testsheet_data(wb_33_only)
    assert len(data_33.equipment.switchgears) == 1
    assert data_33.equipment.switchgears[0].switchgear_type == "GIS"

    # 3. 11kV only
    wb_11_only = tmp_path / "03. 11KV ONLY.xlsx"
    create_ppu_testsheet_workbook(path=wb_11_only, has_33kv=False, has_11kv=True, panels_11kv=2)
    data_11 = parser.extract_testsheet_data(wb_11_only)
    assert len(data_11.equipment.switchgears) == 1
    assert data_11.equipment.switchgears[0].switchgear_type == "VCB"

    # 4. Neither populated -> raises ValueError
    wb_empty = tmp_path / "04. EMPTY.xlsx"
    create_ppu_testsheet_workbook(path=wb_empty, has_33kv=True, has_11kv=True, panels_33kv=0, panels_11kv=0)
    with pytest.raises(ValueError, match="No populated 33kV or 11kV switchgear lineups found"):
        parser.extract_testsheet_data(wb_empty)


def test_ppu_panel_stride_and_compartment_mapping(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "01. PPU STRIDE.xlsx"

    panel_custom = [
        {
            "feeder_no": "3P1",
            "name": "INCOMING 33kV",
            "status": "CLOSE",
            "load_amp": "250A",
            "cable_type": "XLPE 1C 500mm2",
            "heater_amp": "0.5A",
            "panel_type": "GIS",
            "breaker_serial": "CB-SN-3301",
            "breaker_photo": 11,
            "cable_photo": 12,
            "busbar_photo": 13,
            "pt_photo": 14,
            "cable_entry_photo": 15,
            "link_box_photo": 16,
            "secondary_photo": 17,
            "has_pt_measurement": True,
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=panel_custom,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    assert len(swg.panels) == 1
    panel = swg.panels[0]

    assert panel.panel_feeder_no == "3P1"
    assert panel.name == "INCOMING 33kV"
    assert panel.status == "CLOSE"
    assert panel.load_amp == "250"
    assert panel.cable_type == "XLPE 1C 500mm2"
    assert panel.heater_amp == "0.5A"
    assert panel.panel_type == "GIS"
    assert panel.serial_no == "CB-SN-3301"

    # Verify 6 physical compartments + secondary panel
    assert panel.breaker_photo == 11
    assert panel.cable_photo == 12
    assert panel.busbar_photo == 13
    assert panel.pt_photo == 14
    assert panel.cable_entry_photo == 15
    assert panel.link_box_photo == 16
    assert panel.secondary_photo == 17
    assert panel.has_pt_measurement is True

    # photo_numbers contains all distinct photo integers
    assert panel.photo_numbers == (11, 12, 13, 14, 15, 16, 17)


def test_ppu_overview_bays_and_photo_numbers(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "01. PPU OVERVIEW.xlsx"

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=1,
        overview_rhs_photos_33kv=[201, 202, 203],
        overview_lhs_photos_33kv=[204, 205],
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]

    # Overview photos aggregated in SwitchgearSpec.photo_numbers
    assert 201 in swg.photo_numbers
    assert 202 in swg.photo_numbers
    assert 203 in swg.photo_numbers
    assert 204 in swg.photo_numbers
    assert 205 in swg.photo_numbers

    # Overview compartments stored on SwitchgearSpec without injecting fake panels
    assert len(swg.overview_compartments) > 0
    assert any("OVERVIEW FRONT" in c for c in swg.overview_compartments)
    panel_names = [p.name for p in swg.panels]
    assert "OVERVIEW RHS" not in panel_names
    assert panel_names[0] == "FEEDER 33kV 1"


def test_ppu_visual_inspection_findings(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "01. PPU VI.xlsx"

    checklist_items = [
        {"category": "1. CIVIL", "item_no": "1.1", "description": "Door locked", "status": "YES", "remarks": ""},
        {"category": "1. CIVIL", "item_no": "1.2", "description": "Roof leakage", "status": "NO", "remarks": "Active leak above TX"},
        {"category": "2. SWITCHGEAR", "item_no": "2.1", "description": "Labeling missing", "status": "YES", "remarks": "Repasted label"},
        {"category": "2. SWITCHGEAR", "item_no": "2.2", "description": "Earthing intact", "status": "YES", "remarks": ""},
    ]
    other_findings = [
        "Oil spillage observed near cable trench",
        "Signs of rodent nesting behind battery rack",
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        visual_checklist_items=checklist_items,
        other_findings=other_findings,
    )

    data = parser.extract_testsheet_data(wb_path)
    findings = data.visual_findings

    # Checklist: 1.2 (marked NO) and 2.1 (non-empty remark) recorded. 1.1 and 2.2 omitted.
    item_nos = [f.item_no for f in findings]
    assert "1.2" in item_nos
    assert "2.1" in item_nos
    assert "1.1" not in item_nos
    assert "2.2" not in item_nos

    # Other findings recorded under Category "Other Findings"
    other_f = [f for f in findings if f.category == "Other Findings"]
    assert len(other_f) == 2
    assert any("Oil spillage" in f.remarks for f in other_f)
    assert any("rodent nesting" in f.remarks for f in other_f)


def test_ppu_raw_data_photo_ranges(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "01. PPU RAW.xlsx"

    create_ppu_testsheet_workbook(
        path=wb_path,
        raw_photo_bounds={"ir_start": 101, "ir_end": 145, "dg_start": 2001, "dg_end": 2045},
    )

    ranges = parser.extract_photo_ranges(wb_path)
    assert ranges.ir.start_num == 101
    assert ranges.ir.end_num == 145
    assert ranges.dg.start_num == 2001
    assert ranges.dg.end_num == 2045


def test_ppu_fast_metadata_extraction(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "05. PPU META.xlsx"

    create_ppu_testsheet_workbook(
        path=wb_path,
        substation_number=5,
        substation_name="PPU META TEST",
        fl_number="FL-META-005",
        date_val="2026-10-18",
    )

    meta = parser.extract_testsheet_metadata(wb_path)
    assert isinstance(meta, TestsheetData)
    assert meta.substation_number == 5
    assert meta.substation_name_site == "PPU META TEST"
    assert meta.fl_site == "FL-META-005"
    assert meta.date_str == "18-10-2026"
    assert len(meta.equipment.switchgears) == 1
    assert meta.equipment.switchgears[0].switchgear_type == "GIS"


def test_ppu_factory_transformer_ratings(tmp_path: Path) -> None:
    wb_path = tmp_path / "06. PPU TX TEST.xlsx"
    wb = create_ppu_testsheet_workbook(
        path=wb_path,
        transformer_ratings=["15MVA", "30MVA"],
    )
    assert "TX" in wb.sheetnames
    ws_tx = wb["TX"]
    assert ws_tx["G8"].value == "15MVA"
    assert ws_tx["K8"].value == "30MVA"


def test_ppu_overview_only_without_panels_raises_value_error(tmp_path: Path) -> None:
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "07. PPU OVERVIEW ONLY.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_path,
        panels_33kv=0,
        panels_11kv=0,
        overview_rhs_photos_33kv=[501, 502],
    )
    with pytest.raises(ValueError, match="No populated 33kV or 11kV switchgear lineups found"):
        parser.extract_testsheet_data(wb_path)


def test_ppu_cable_compartment_readings_extraction(tmp_path: Path) -> None:
    """Verify Row 16 (r+1) Cable Compartment TEV, PPC, and US readings are parsed into cable_* fields."""
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "08. PPU CABLE READINGS.xlsx"

    panel_custom = [
        {
            "feeder_no": "3P1",
            "name": "FEEDER 1 33kV",
            "status": "CLOSE",
            "tev_reading": "12",
            "tev_ppc": "5",
            "us_reading": "3",
            "cable_tev_reading": "24",
            "cable_tev_ppc": "18",
            "cable_us_reading": "7",
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=panel_custom,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    panel = swg.panels[0]

    # Breaker readings from Row 15
    assert panel.tev_reading == "12"
    assert panel.tev_ppc == "5"
    assert panel.us_reading == "3"

    # Cable Compartment readings from Row 16 (r+1)
    assert panel.cable_tev_reading == "24"
    assert panel.cable_tev_ppc == "18"
    assert panel.cable_us_reading == "7"


