"""Unit tests for Canonical Testsheet Reading Mapper (src/testsheet/mapper.py)."""

from __future__ import annotations

import pytest

from src.testsheet.mapper import (
    TestsheetReadingMapper,
    get_sheet_name,
    parse_equipment_index,
)


def test_parse_equipment_index() -> None:
    # 11KV Switchgear
    assert parse_equipment_index("/11KV/1") == ("11KV", 1)
    assert parse_equipment_index("/11KV/7") == ("11KV", 7)
    assert parse_equipment_index("11KV/3") == ("11KV", 3)
    assert parse_equipment_index("CCHL/PCEJ00002/11KV/2") == ("11KV", 2)

    # Transformers (TX / DTX)
    assert parse_equipment_index("/TX/DTX1") == ("TX", 1)
    assert parse_equipment_index("/TX/DTX2") == ("TX", 2)
    assert parse_equipment_index("TX/DTX1") == ("TX", 1)
    assert parse_equipment_index("CCHL/PCEJ00024/TX/DTX1") == ("TX", 1)
    assert parse_equipment_index("CRAU/PCEJ00112/TX/DTX2") == ("TX", 2)

    # Feeder Pillars (FP)
    assert parse_equipment_index("/FP/FP1") == ("FP", 1)
    assert parse_equipment_index("/FP/FP2") == ("FP", 2)
    assert parse_equipment_index("FP/FP1") == ("FP", 1)
    assert parse_equipment_index("CRAU/PCEJ00113/FP/FP1") == ("FP", 1)
    assert parse_equipment_index("CCHL/PCEJ00124/FP/FP2") == ("FP", 2)

    # Invalid locations raise ValueError
    with pytest.raises(ValueError):
        parse_equipment_index("INVALID/PATH/WITHOUT/EQ")
    with pytest.raises(ValueError):
        parse_equipment_index("")


def test_sheet_name_and_rollover_logic() -> None:
    assert get_sheet_name(1) == "PCE Testsheet"
    assert get_sheet_name(2) == "PCE Testsheet (2)"
    assert get_sheet_name(3) == "PCE Testsheet (3)"

    mapper = TestsheetReadingMapper()
    # Sheet 1: Panels 1-4
    assert mapper.resolve_panel_sheet_and_slot(1) == ("PCE Testsheet", 1)
    assert mapper.resolve_panel_sheet_and_slot(2) == ("PCE Testsheet", 2)
    assert mapper.resolve_panel_sheet_and_slot(3) == ("PCE Testsheet", 3)
    assert mapper.resolve_panel_sheet_and_slot(4) == ("PCE Testsheet", 4)

    # Sheet 2: Panels 5-8
    assert mapper.resolve_panel_sheet_and_slot(5) == ("PCE Testsheet (2)", 1)
    assert mapper.resolve_panel_sheet_and_slot(6) == ("PCE Testsheet (2)", 2)
    assert mapper.resolve_panel_sheet_and_slot(7) == ("PCE Testsheet (2)", 3)
    assert mapper.resolve_panel_sheet_and_slot(8) == ("PCE Testsheet (2)", 4)

    # Sheet 3: Panels 9-12
    assert mapper.resolve_panel_sheet_and_slot(9) == ("PCE Testsheet (3)", 1)
    assert mapper.resolve_panel_sheet_and_slot(12) == ("PCE Testsheet (3)", 4)


def test_rmu_sf6_fixed_slot_mapping() -> None:
    mapper = TestsheetReadingMapper()

    # 1. RMU Body (Overview row 26 & background)
    assert mapper.get_target("TH_S11_RMU_AVG_PE13R", "/11KV/1") == ("PCE Testsheet", "N26")
    assert mapper.get_target("TH_S11_RMU_MAX_PE13R", "/11KV/1") is None
    assert mapper.get_target("TH_S11_RMU_REF_PE13R", "/11KV/1") is None
    assert mapper.get_target("TH_S11_RMU_DIF_PE13R", "/11KV/1") is None
    assert mapper.get_target("TV_S11_RMU_PE13R", "/11KV/1") == ("PCE Testsheet", "P6")
    assert mapper.get_target("TV_S11_RMU_PUL_PE13R", "/11KV/1") is None
    assert mapper.get_target("US_S11_RMU_PE13R", "/11KV/1") is None

    # 2. RMU Cable Compartment 1 (Slot 1, row 10)
    assert mapper.get_target("TH_S11_RMUCBL1_AVG_PE13R", "/11KV/1") == ("PCE Testsheet", "N10")
    assert mapper.get_target("TH_S11_RMUCBL1_MAX_PE13R", "/11KV/1") == ("PCE Testsheet", "L10")
    assert mapper.get_target("TH_S11_RMUCBL1_REF_PE13R", "/11KV/1") == ("PCE Testsheet", "K10")
    assert mapper.get_target("TH_S11_RMUCBL1_DIF_PE13R", "/11KV/1") == ("PCE Testsheet", "M10")
    assert mapper.get_target("TV_S11_CBL_PE13R", "/11KV/1") == ("PCE Testsheet", "T10")
    assert mapper.get_target("TV_S11_CBL_PUL_PE13R", "/11KV/1") == ("PCE Testsheet", "U10")
    assert mapper.get_target("US_S11_CBL_PE13R", "/11KV/1") == ("PCE Testsheet", "Q10")

    # 3. RMU Cable Compartment 2 (Slot 2, row 14)
    assert mapper.get_target("TH_S11_RMUCBL2_AVG_PE13R", "/11KV/1") == ("PCE Testsheet", "N14")
    assert mapper.get_target("TH_S11_RMUCBL2_MAX_PE13R", "/11KV/1") == ("PCE Testsheet", "L14")
    assert mapper.get_target("TH_S11_RMUCBL2_REF_PE13R", "/11KV/1") == ("PCE Testsheet", "K14")
    assert mapper.get_target("TH_S11_RMUCBL2_DIF_PE13R", "/11KV/1") == ("PCE Testsheet", "M14")
    assert mapper.get_target("TV_S11_CBL2_PE13R", "/11KV/1") == ("PCE Testsheet", "T14")
    assert mapper.get_target("TV_S11_CBL2_PUL_PE13R", "/11KV/1") == ("PCE Testsheet", "U14")
    assert mapper.get_target("US_S11_CBL2_PE13R", "/11KV/1") == ("PCE Testsheet", "Q14")

    # 4. RMU Cable Compartment 3 (Slot 3, row 18)
    assert mapper.get_target("TH_S11_RMUCBL3_AVG_PE13R", "/11KV/1") == ("PCE Testsheet", "N18")
    assert mapper.get_target("TH_S11_RMUCBL3_MAX_PE13R", "/11KV/1") == ("PCE Testsheet", "L18")
    assert mapper.get_target("TH_S11_RMUCBL3_REF_PE13R", "/11KV/1") == ("PCE Testsheet", "K18")
    assert mapper.get_target("TH_S11_RMUCBL3_DIF_PE13R", "/11KV/1") == ("PCE Testsheet", "M18")
    assert mapper.get_target("TV_S11_CBL3_PE13R", "/11KV/1") == ("PCE Testsheet", "T18")
    assert mapper.get_target("TV_S11_CBL3_PUL_PE13R", "/11KV/1") == ("PCE Testsheet", "U18")
    assert mapper.get_target("US_S11_CBL3_PE13R", "/11KV/1") == ("PCE Testsheet", "Q18")

    # 5. RMU Fuse Compartment 1 (Slot 4, row 22)
    assert mapper.get_target("TH_S11_RMUFS1_AVG_PE13R", "/11KV/1") == ("PCE Testsheet", "N22")
    assert mapper.get_target("TH_S11_RMUFS1_MAX_PE13R", "/11KV/1") == ("PCE Testsheet", "L22")
    assert mapper.get_target("TH_S11_RMUFS1_REF_PE13R", "/11KV/1") == ("PCE Testsheet", "K22")
    assert mapper.get_target("TH_S11_RMUFS1_DIF_PE13R", "/11KV/1") == ("PCE Testsheet", "M22")
    assert mapper.get_target("TV_S11_FS1_PE13R", "/11KV/1") == ("PCE Testsheet", "T22")
    assert mapper.get_target("TV_S11_FS1_PUL_PE13R", "/11KV/1") == ("PCE Testsheet", "U22")
    assert mapper.get_target("US_S11_FS1_PE13R", "/11KV/1") == ("PCE Testsheet", "Q22")

    # 6. RMU Fuse Compartment 2 (Slot 5 -> Rollover to Sheet 2, row 10)
    assert mapper.get_target("TH_S11_RMUFS2_AVG_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "N10")
    assert mapper.get_target("TH_S11_RMUFS2_MAX_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "L10")
    assert mapper.get_target("TH_S11_RMUFS2_REF_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "K10")
    assert mapper.get_target("TH_S11_RMUFS2_DIF_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "M10")
    assert mapper.get_target("TV_S11_FS2_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "T10")
    assert mapper.get_target("TV_S11_FS2_PUL_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "U10")
    assert mapper.get_target("US_S11_FS2_PE13R", "/11KV/1") == ("PCE Testsheet (2)", "Q10")

    # 7. RMU Oil Stub
    assert mapper.get_target("TH_S11_RMU_AVG_PE13O", "/11KV/1") is None


def test_vcb_dynamic_panel_slot_mapping() -> None:
    mapper = TestsheetReadingMapper()

    # Panel 1: rows 10-13 on Sheet 1
    # Cable (+0 -> row 10)
    assert mapper.get_target("TH_S11_CBL_AVG_PE13V", "/11KV/1") == ("PCE Testsheet", "N10")
    assert mapper.get_target("TH_S11_CBL_MAX_PE13V", "/11KV/1") == ("PCE Testsheet", "L10")
    assert mapper.get_target("TH_S11_CBL_REF_PE13V", "/11KV/1") == ("PCE Testsheet", "K10")
    assert mapper.get_target("TH_S11_CBL_DIF_PE13V", "/11KV/1") == ("PCE Testsheet", "M10")
    assert mapper.get_target("TV_S11_CBL_PE13V", "/11KV/1") == ("PCE Testsheet", "T10")
    assert mapper.get_target("TV_S11_CBL_PUL_PE13V", "/11KV/1") == ("PCE Testsheet", "U10")
    assert mapper.get_target("US_S11_CBL_PE13V", "/11KV/1") == ("PCE Testsheet", "Q10")

    # Breaker (+1 -> row 11)
    assert mapper.get_target("TH_S11_BR_AVG_PE13V", "/11KV/1") == ("PCE Testsheet", "N11")
    assert mapper.get_target("TH_S11_BR_MAX_PE13V", "/11KV/1") == ("PCE Testsheet", "L11")
    assert mapper.get_target("TH_S11_BR_REF_PE13V", "/11KV/1") == ("PCE Testsheet", "K11")
    assert mapper.get_target("TH_S11_BR_DIF_PE13V", "/11KV/1") == ("PCE Testsheet", "M11")
    assert mapper.get_target("TV_S11_BR_PE13V", "/11KV/1") == ("PCE Testsheet", "T11")
    assert mapper.get_target("TV_S11_BR_PUL_PE13V", "/11KV/1") == ("PCE Testsheet", "U11")
    assert mapper.get_target("US_S11_BR_PE13V", "/11KV/1") == ("PCE Testsheet", "Q11")

    # Top Panel / Busbar (+2 -> row 12)
    assert mapper.get_target("TH_S11_BB_AVG_PE13V", "/11KV/1") == ("PCE Testsheet", "N12")
    assert mapper.get_target("TH_S11_BB_MAX_PE13V", "/11KV/1") == ("PCE Testsheet", "L12")
    assert mapper.get_target("TV_S11_BB_PE13V", "/11KV/1") == ("PCE Testsheet", "T12")
    assert mapper.get_target("TV_S11_BB_PUL_PE13V", "/11KV/1") == ("PCE Testsheet", "U12")
    assert mapper.get_target("US_S11_BB_PE13V", "/11KV/1") == ("PCE Testsheet", "Q12")

    # PT (+3 -> row 13)
    assert mapper.get_target("TH_S11_PT_AVG_PE13V2", "/11KV/1") == ("PCE Testsheet", "N13")
    assert mapper.get_target("TH_S11_PT_MAX_PE13V2", "/11KV/1") == ("PCE Testsheet", "L13")
    assert mapper.get_target("TH_S11_PT_REF_PE13V2", "/11KV/1") == ("PCE Testsheet", "K13")
    assert mapper.get_target("TH_S11_PT_DIF_PE13V2", "/11KV/1") == ("PCE Testsheet", "M13")
    assert mapper.get_target("TV_S11_PT_PE13V", "/11KV/1") == ("PCE Testsheet", "T13")
    assert mapper.get_target("TV_S11_PT_PUL_PE13V", "/11KV/1") == ("PCE Testsheet", "U13")
    assert mapper.get_target("US_S11_PT_PE13V", "/11KV/1") == ("PCE Testsheet", "Q13")

    # LV Control (Stub)
    assert mapper.get_target("TH_S11_LV_AVG_PE13V", "/11KV/1") is None
    assert mapper.get_target("TH_S11_LV_MAX_PE13V", "/11KV/1") is None

    # Panel 4: rows 22-25 on Sheet 1
    assert mapper.get_target("TH_S11_CBL_AVG_PE13V", "/11KV/4") == ("PCE Testsheet", "N22")
    assert mapper.get_target("TH_S11_BR_AVG_PE13V", "/11KV/4") == ("PCE Testsheet", "N23")
    assert mapper.get_target("TH_S11_BB_AVG_PE13V", "/11KV/4") == ("PCE Testsheet", "N24")
    assert mapper.get_target("TH_S11_PT_AVG_PE13V2", "/11KV/4") == ("PCE Testsheet", "N25")

    # Panel 5: Sheet 2, Slot 1 -> rows 10-13 on Sheet 2
    assert mapper.get_target("TH_S11_CBL_AVG_PE13V", "/11KV/5") == ("PCE Testsheet (2)", "N10")
    assert mapper.get_target("TH_S11_BR_AVG_PE13V", "/11KV/5") == ("PCE Testsheet (2)", "N11")
    assert mapper.get_target("TH_S11_BB_AVG_PE13V", "/11KV/5") == ("PCE Testsheet (2)", "N12")
    assert mapper.get_target("TH_S11_PT_AVG_PE13V2", "/11KV/5") == ("PCE Testsheet (2)", "N13")

    # Panel 7: Sheet 2, Slot 3 -> rows 18-21 on Sheet 2
    assert mapper.get_target("TH_S11_CBL_AVG_PE13V", "/11KV/7") == ("PCE Testsheet (2)", "N18")
    assert mapper.get_target("TH_S11_BR_AVG_PE13V", "/11KV/7") == ("PCE Testsheet (2)", "N19")
    assert mapper.get_target("TH_S11_BB_AVG_PE13V", "/11KV/7") == ("PCE Testsheet (2)", "N20")
    assert mapper.get_target("TH_S11_PT_AVG_PE13V2", "/11KV/7") == ("PCE Testsheet (2)", "N21")
    assert mapper.get_target("TV_S11_BB_PE13V", "/11KV/7") == ("PCE Testsheet (2)", "T20")
    assert mapper.get_target("US_S11_PT_PE13V", "/11KV/7") == ("PCE Testsheet (2)", "Q21")


def test_transformer_mapping() -> None:
    mapper = TestsheetReadingMapper()

    # 1. DTX1 (/TX/DTX1 -> rows 33-37)
    # HV -> HT Cable row 33
    assert mapper.get_target("TH_DTX_HV_AVG_PE13R", "/TX/DTX1") == ("PCE Testsheet", "I33")
    assert mapper.get_target("TH_DTX_HV_MAX_PE13V", "/TX/DTX1") == ("PCE Testsheet", "G33")
    assert mapper.get_target("TH_DTX_HV_REF_PE13R", "/TX/DTX1") == ("PCE Testsheet", "F33")
    assert mapper.get_target("TH_DTX_HV_DIF_PE13V", "/TX/DTX1") == ("PCE Testsheet", "H33")
    assert mapper.get_target("US_DTX_HV_PE13R", "/TX/DTX1") == ("PCE Testsheet", "K33")
    assert mapper.get_target("US_DTX_PE13V", "/TX/DTX1") == ("PCE Testsheet", "K33")

    # LV -> LV Cable row 35
    assert mapper.get_target("TH_DTX_LV_AVG_PE13R", "/TX/DTX1") == ("PCE Testsheet", "I35")
    assert mapper.get_target("TH_DTX_LV_MAX_PE13V", "/TX/DTX1") == ("PCE Testsheet", "G35")
    assert mapper.get_target("TH_DTX_LV_REF_PE13R", "/TX/DTX1") == ("PCE Testsheet", "F35")
    assert mapper.get_target("TH_DTX_LV_DIF_PE13V", "/TX/DTX1") == ("PCE Testsheet", "H35")

    # Body -> Body row 37
    assert mapper.get_target("TH_TX_RMU_AVG_PE13R", "/TX/DTX1") == ("PCE Testsheet", "I37")
    assert mapper.get_target("TH_S11_VCB_AVG_PE13V", "/TX/DTX1") == ("PCE Testsheet", "I37")
    assert mapper.get_target("TH_TX_RMU_MAX_PE13R", "/TX/DTX1") == ("PCE Testsheet", "G37")
    assert mapper.get_target("TH_S11_VCB_REF_PE13V", "/TX/DTX1") == ("PCE Testsheet", "F37")
    assert mapper.get_target("TH_S11_VCB_DIF_PE13V", "/TX/DTX1") == ("PCE Testsheet", "H37")

    # 2. DTX2 (/TX/DTX2 -> rows 38-42)
    # HV -> HT Cable row 38
    assert mapper.get_target("TH_DTX_HV_AVG_PE13R", "/TX/DTX2") == ("PCE Testsheet", "I38")
    assert mapper.get_target("US_DTX_HV_PE13R", "/TX/DTX2") == ("PCE Testsheet", "K38")
    # LV -> LV Cable row 40
    assert mapper.get_target("TH_DTX_LV_AVG_PE13R", "/TX/DTX2") == ("PCE Testsheet", "I40")
    # Body -> Body row 42
    assert mapper.get_target("TH_TX_RMU_AVG_PE13R", "/TX/DTX2") == ("PCE Testsheet", "I42")
    assert mapper.get_target("TH_S11_VCB_AVG_PE13V", "/TX/DTX2") == ("PCE Testsheet", "I42")


def test_feeder_pillar_stubs() -> None:
    mapper = TestsheetReadingMapper()

    # All Feeder Pillar numeric thermal meters must return None
    assert mapper.get_target("TH_FPIN1_AVG_PE13R", "/FP/FP1") is None
    assert mapper.get_target("TH_FPIN1_MAX_PE13V", "/FP/FP1") is None
    assert mapper.get_target("TH_FPIN1_REF_PE13R", "/FP/FP1") is None
    assert mapper.get_target("TH_FPIN1_DEL_PE13V", "/FP/FP1") is None

    assert mapper.get_target("TH_FPIN2_AVG_PE13O", "/FP/FP1") is None
    assert mapper.get_target("TH_FPIN3_AVG_PE13R", "/FP/FP2") is None
    assert mapper.get_target("TH_FPOT1_AVG_PE13R", "/FP/FP1") is None
    assert mapper.get_target("TH_FPOT10_AVG_PE13R", "/FP/FP2") is None
    assert mapper.get_target("TH_FPOT12_DEL_PE13V", "/FP/FP2") is None

    assert mapper.get_target("TH_EARTH_AVG_PE13R", "/FP/FP1") is None
    assert mapper.get_target("TH_EARTH_DEL_PE13V", "/FP/FP2") is None


def test_background_and_metadata_mapping() -> None:
    mapper = TestsheetReadingMapper()

    assert mapper.get_target("BG_ROOM_TV") == ("PCE Testsheet", "P6")
    assert mapper.get_target("BG_ROOM_HUM") == ("PCE Testsheet", "S6")
    assert mapper.get_target("BG_ROOM_TEM") == ("PCE Testsheet", "W6")
    assert mapper.get_target("EXECUTION_DATE") == ("PCE Testsheet", "P4")
    assert mapper.get_target("TIME_IN") == ("PCE Testsheet", "P5")
    assert mapper.get_target("TIME_OUT") == ("PCE Testsheet", "S5")


def test_unmapped_and_is_stub() -> None:
    mapper = TestsheetReadingMapper()

    assert mapper.get_target("UNKNOWN_METER_XYZ", "/11KV/1") is None
    assert mapper.get_target("", "/11KV/1") is None
    assert mapper.is_stub("TH_FPIN1_AVG_PE13R", "/FP/FP1") is True
    assert mapper.is_stub("TH_S11_LV_AVG_PE13V", "/11KV/1") is True
    assert mapper.is_stub("TH_S11_CBL_AVG_PE13V", "/11KV/1") is False
