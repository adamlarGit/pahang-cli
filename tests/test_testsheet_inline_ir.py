"""Unit tests for PCE Testsheet inline IR photo number extraction (Ticket #24)."""

from __future__ import annotations

from pathlib import Path
import openpyxl
import pytest

from src.testsheet.extractor import TestsheetExtractor, parse_photo_numbers
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBSpec,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


# ==============================================================================
# 1. parse_photo_numbers unit tests
# ==============================================================================

def test_parse_photo_numbers_empty_and_sentinels() -> None:
    """Verify parse_photo_numbers handles None, blanks, and sentinel strings."""
    assert parse_photo_numbers(None) == ()
    assert parse_photo_numbers("") == ()
    assert parse_photo_numbers("   ") == ()
    assert parse_photo_numbers("-") == ()
    assert parse_photo_numbers("NONE") == ()
    assert parse_photo_numbers("N/A") == ()
    assert parse_photo_numbers("#REF!") == ()
    assert parse_photo_numbers("nan") == ()
    assert parse_photo_numbers(False) == ()
    assert parse_photo_numbers(True) == ()


def test_parse_photo_numbers_integers_and_floats() -> None:
    """Verify parse_photo_numbers handles raw int and float cell values."""
    assert parse_photo_numbers(9) == (9,)
    assert parse_photo_numbers(101) == (101,)
    assert parse_photo_numbers(9.0) == (9,)
    assert parse_photo_numbers(105.0) == (105,)
    assert parse_photo_numbers(float("nan")) == ()
    assert parse_photo_numbers(float("inf")) == ()
    assert parse_photo_numbers("9.5") == (9,)


def test_parse_photo_numbers_comma_separated() -> None:
    """Verify parse_photo_numbers parses comma-separated strings via re.findall."""
    assert parse_photo_numbers("9,10") == (9, 10)
    assert parse_photo_numbers("9, 10") == (9, 10)
    assert parse_photo_numbers("9, 10, 11") == (9, 10, 11)
    assert parse_photo_numbers("09, 10") == (9, 10)
    assert parse_photo_numbers("IR 9, 10") == (9, 10)
    assert parse_photo_numbers("IR-9, IR-10") == (9, 10)


# ==============================================================================
# 2. Domain model photo_numbers default and immutability tests
# ==============================================================================

def test_models_photo_numbers_defaults() -> None:
    """Verify all 5 target models default photo_numbers to empty tuple ()."""
    assert SwitchgearPanelSpec().photo_numbers == ()
    assert SwitchgearSpec().photo_numbers == ()
    assert TransformerSpec().photo_numbers == ()
    assert LVDBSpec().photo_numbers == ()
    assert BatteryBankSpec().photo_numbers == ()


def test_models_photo_numbers_custom_values() -> None:
    """Verify all 5 target models accept custom photo_numbers tuples."""
    panel = SwitchgearPanelSpec(panel_no=1, name="INC", photo_numbers=(10, 11))
    assert panel.photo_numbers == (10, 11)

    swg = SwitchgearSpec(switchgear_type="VCB", photo_numbers=(1, 2))
    assert swg.photo_numbers == (1, 2)

    tx = TransformerSpec(tx_id="Tx 1", photo_numbers=(3, 4, 5))
    assert tx.photo_numbers == (3, 4, 5)

    lvdb = LVDBSpec(name="FP 1", photo_numbers=(6,))
    assert lvdb.photo_numbers == (6,)

    bb = BatteryBankSpec(name="BATTERY 1", photo_numbers=(7, 8))
    assert bb.photo_numbers == (7, 8)


# ==============================================================================
# 3. Switchgear panel extraction tests (Col O, Rows 10, 14, 18, 22)
# ==============================================================================

def test_extract_panels_inline_ir_numbers() -> None:
    """Verify SWG panel IR numbers parsed from Column O (Rows 10, 14, 18, 22)."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PCE Testsheet"

    # Panel 1 (Row 10) - Single number
    ws["B10"] = "F01"
    ws["C10"] = "INCOMING 1"
    ws["I10"] = "SN-01"
    ws["O10"] = 12

    # Panel 2 (Row 14) - Comma separated string
    ws["B14"] = "F02"
    ws["C14"] = "OUTGOING 1"
    ws["I14"] = "SN-02"
    ws["O14"] = "13, 14"

    # Panel 3 (Row 18) - Comma separated with prefix
    ws["B18"] = "F03"
    ws["C18"] = "TX 1"
    ws["I18"] = "SN-03"
    ws["O18"] = "15,16"

    # Panel 4 (Row 22) - Blank Column O
    ws["B22"] = "F04"
    ws["C22"] = "BUS COUPLER"
    ws["I22"] = "SN-04"
    ws["O22"] = None

    panels = extractor._extract_panels([ws])
    assert len(panels) == 4
    assert panels[0].photo_numbers == (12,)
    assert panels[1].photo_numbers == (13, 14)
    assert panels[2].photo_numbers == (15, 16)
    assert panels[3].photo_numbers == ()


# ==============================================================================
# 4. Switchgear Overview extraction tests (Row 26 Col O, Row 28 Col O/J)
# ==============================================================================

def test_extract_switchgear_overview_ir_numbers_col_o() -> None:
    """Verify SWG Overview IR numbers parsed from Row 26 Col O and Row 28 Col O."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"

    ws_pce["O26"] = 5
    ws_pce["O28"] = 6

    swgs = extractor._extract_switchgear_specs(wb, ws_vi=None, pce_sheets=[ws_pce])
    assert len(swgs) == 1
    assert swgs[0].photo_numbers == (5, 6)


def test_extract_switchgear_overview_ir_numbers_row28_col_j() -> None:
    """Verify SWG Overview Secondary parsed from Row 28 Col J when Col O is empty."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"

    ws_pce["O26"] = "7,8"
    ws_pce["O28"] = None
    ws_pce["J28"] = 9

    swgs = extractor._extract_switchgear_specs(wb, ws_vi=None, pce_sheets=[ws_pce])
    assert len(swgs) == 1
    assert swgs[0].photo_numbers == (7, 8, 9)


# ==============================================================================
# 5. Transformer extraction tests (Col J, Rows 33–37)
# ==============================================================================

def test_extract_transformer_inline_ir_numbers() -> None:
    """Verify Transformer IR numbers parsed from Column J (Rows 33–37)."""
    extractor = TestsheetExtractor()
    wb_vi = openpyxl.Workbook()
    ws_vi = wb_vi.active
    ws_vi["C17"] = 1
    ws_vi["D18"] = "HERMETIC"
    ws_vi["F18"] = "1000kVA"

    wb_pce = openpyxl.Workbook()
    ws_pce = wb_pce.active
    ws_pce["J33"] = 21        # HT CABLE
    ws_pce["J34"] = "22, 23"   # HT BUSHING
    ws_pce["J35"] = None       # LV CABLE
    ws_pce["J36"] = 24         # LV BUSHING
    ws_pce["J37"] = 25         # BODY

    specs = extractor._extract_transformer_specs(ws_vi, ws_pce=ws_pce)
    assert len(specs) == 1
    assert specs[0].photo_numbers == (21, 22, 23, 24, 25)


# ==============================================================================
# 6. Feeder Pillar extraction tests (Col S, Rows 49, 53)
# ==============================================================================

def test_extract_feeder_pillar_inline_ir_numbers() -> None:
    """Verify Feeder Pillar IR numbers parsed from Column S (Rows 49, 53)."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws_pce = wb.active

    # Slot 1
    ws_pce["R48"] = "FP"
    ws_pce["T48"] = "TX1"
    ws_pce["S49"] = "31, 32"
    ws_pce["U49"] = "TAMCO"

    # Slot 2
    ws_pce["R52"] = "FP"
    ws_pce["T52"] = "TX2"
    ws_pce["S53"] = 33
    ws_pce["U53"] = "ABB"

    lvdb_specs = extractor._extract_lvdb_specs(ws_pce=ws_pce)
    assert len(lvdb_specs) == 2
    assert lvdb_specs[0].photo_numbers == (31, 32)
    assert lvdb_specs[1].photo_numbers == (33,)


# ==============================================================================
# 7. Battery Bank extraction tests (Row 59 Col H)
# ==============================================================================

def test_extract_battery_bank_inline_ir_numbers() -> None:
    """Verify Battery Bank IR numbers parsed from Row 59 Col H."""
    extractor = TestsheetExtractor()
    wb = openpyxl.Workbook()
    ws_pce = wb.active

    ws_pce["B59"] = "BATTERY BANK 1"
    ws_pce["H59"] = "41, 42"
    ws_pce["J59"] = "CHLORIDE"

    bb_specs = extractor._extract_battery_banks(ws_pce=ws_pce)
    assert len(bb_specs) == 1
    assert bb_specs[0].photo_numbers == (41, 42)


# ==============================================================================
# 8. Full Workbook integration test
# ==============================================================================

def test_extract_testsheet_data_all_inline_ir_numbers(tmp_path: Path) -> None:
    """Integration test verifying full extract_testsheet_data parses all inline IR numbers."""
    wb_path = tmp_path / "001. TEST_INLINE_IR.xlsx"
    wb = openpyxl.Workbook()

    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"
    ws_pce["C5"] = "PE INLINE TEST"
    ws_pce["W5"] = "FL-TEST-001"
    ws_pce["P4"] = "2026-05-10"

    # SWG Panels
    ws_pce["B10"] = "F01"
    ws_pce["C10"] = "INCOMING"
    ws_pce["O10"] = "10,11"

    # SWG Overview
    ws_pce["O26"] = 1
    ws_pce["O28"] = 2

    # Transformer
    ws_pce["J33"] = 20

    # Feeder Pillar
    ws_pce["R48"] = "FP"
    ws_pce["T48"] = "TX1"
    ws_pce["S49"] = 30

    # Battery
    ws_pce["B59"] = "BATTERY BANK 1"
    ws_pce["H59"] = 40

    # PCE VI
    ws_vi = wb.create_sheet(title="PCE VI")
    ws_vi["C17"] = 1
    ws_vi["D18"] = "HERMETIC"
    ws_vi["F18"] = "1000kVA"
    ws_vi["J11"] = "/"  # VCB

    wb.save(wb_path)
    wb.close()

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(wb_path)

    # Assertions across equipment package
    assert data.equipment.switchgear.photo_numbers == (1, 2)
    assert len(data.equipment.switchgear.panels) == 1
    assert data.equipment.switchgear.panels[0].photo_numbers == (10, 11)

    assert len(data.equipment.transformers) == 1
    assert data.equipment.transformers[0].photo_numbers == (20,)

    assert len(data.equipment.lvdb_specs) == 1
    assert data.equipment.lvdb_specs[0].photo_numbers == (30,)

    assert len(data.equipment.battery_banks) == 1
    assert data.equipment.battery_banks[0].photo_numbers == (40,)
