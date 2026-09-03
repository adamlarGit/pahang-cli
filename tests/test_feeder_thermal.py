"""Unit tests for Feeder Pillar thermal synthesis and active feeder gating (TDD)."""

from __future__ import annotations

from src.testsheet.feeder_thermal import is_active_feeder_cable


def test_is_active_feeder_cable_valid_types() -> None:
    # Common cable insulation types in TNB testsheets
    assert is_active_feeder_cable("XLPE") is True
    assert is_active_feeder_cable("xlpe") is True
    assert is_active_feeder_cable(" PILC ") is True
    assert is_active_feeder_cable("ABC") is True
    assert is_active_feeder_cable("BUSBAR") is True
    assert is_active_feeder_cable("PVC") is True


def test_is_active_feeder_cable_inactive_sentinels() -> None:
    # Inactive, unused, or spare markers
    assert is_active_feeder_cable("") is False
    assert is_active_feeder_cable("   ") is False
    assert is_active_feeder_cable(None) is False
    assert is_active_feeder_cable("-") is False
    assert is_active_feeder_cable(" - ") is False
    assert is_active_feeder_cable("SPARE") is False
    assert is_active_feeder_cable("spare") is False
    assert is_active_feeder_cable("N/A") is False
    assert is_active_feeder_cable("n/a") is False
    assert is_active_feeder_cable("NA") is False


def test_synthesize_feeder_thermal_readings_indoor_invariants() -> None:
    from src.testsheet.feeder_thermal import synthesize_feeder_thermal_readings

    board_avg = 27.2
    res = synthesize_feeder_thermal_readings(
        board_avg_temp=board_avg,
        feeder_id="OT1",
        substation_type="INDOOR",
        seed_key="PE_TEST_001",
    )

    assert set(res.keys()) == {"AVG", "MAX", "REF", "DEL"}
    # Jitter for indoor must be within +/- 0.5
    assert 26.7 <= res["AVG"] <= 27.7

    # Strict invariant: DEL == MAX - REF
    assert round(res["MAX"] - res["REF"], 1) == res["DEL"]

    # DEL strictly between 0.2 and 0.8 (< 1.0)
    assert 0.2 <= res["DEL"] <= 0.8
    assert res["DEL"] < 1.0

    # Deterministic reproducibility with same seed
    res_repeat = synthesize_feeder_thermal_readings(
        board_avg_temp=board_avg,
        feeder_id="OT1",
        substation_type="INDOOR",
        seed_key="PE_TEST_001",
    )
    assert res == res_repeat


def test_synthesize_feeder_thermal_readings_outdoor_invariants() -> None:
    from src.testsheet.feeder_thermal import synthesize_feeder_thermal_readings

    board_avg = 31.0
    res = synthesize_feeder_thermal_readings(
        board_avg_temp=board_avg,
        feeder_id="OT2",
        substation_type="OUTDOOR",
        seed_key="CS_TEST_002",
    )

    # Jitter for outdoor must be within +/- 1.0
    assert 30.0 <= res["AVG"] <= 32.0

    # Strict invariant: DEL == MAX - REF < 1.0
    assert round(res["MAX"] - res["REF"], 1) == res["DEL"]
    assert 0.2 <= res["DEL"] <= 0.8
    assert res["DEL"] < 1.0


def test_parse_feeder_meter() -> None:
    from src.testsheet.feeder_thermal import parse_feeder_meter

    assert parse_feeder_meter("TH_FPIN1_AVG_PE13R") == ("IN1", "AVG")
    assert parse_feeder_meter("TH_FPIN2_MAX_PE13V") == ("IN2", "MAX")
    assert parse_feeder_meter("TH_FPIN3_REF_PE13R") == ("IN3", "REF")
    assert parse_feeder_meter("TH_FPOT1_DEL_PE13R") == ("OT1", "DEL")
    assert parse_feeder_meter("TH_FPOT10_AVG_PE13V") == ("OT10", "AVG")

    # Feeder out of supported range / earth meters
    assert parse_feeder_meter("TH_FPOT11_AVG_PE13R") is None
    assert parse_feeder_meter("TH_EARTH_AVG_PE13R") is None
    assert parse_feeder_meter("VI11_FP_PLOCK_RMU") is None
    assert parse_feeder_meter("") is None


def test_extract_board_average_temperature() -> None:
    from src.testsheet.feeder_thermal import extract_board_average_temperature

    assert extract_board_average_temperature(28.5) == 28.5
    assert extract_board_average_temperature("28.5") == 28.5
    assert extract_board_average_temperature("AVG 28.5") == 28.5
    assert extract_board_average_temperature("AVG 34.5") == 34.5
    assert extract_board_average_temperature("AVG  30.0") == 30.0
    assert extract_board_average_temperature("27.2 °C") == 27.2
    assert extract_board_average_temperature("Serial No. :") is None
    assert extract_board_average_temperature(None) is None
    assert extract_board_average_temperature("") is None
    assert extract_board_average_temperature("-") is None


def test_resolve_feeder_channel_msms_meters() -> None:
    from src.testsheet.feeder_thermal import resolve_feeder_channel

    res_in1 = resolve_feeder_channel("TH_FPIN1_AVG_PE13R")
    assert res_in1 is not None
    assert res_in1.pillar_index == 1
    assert res_in1.channel == "IN1"
    assert res_in1.feederno_label == "INCOMING 1"
    assert res_in1.column_letter == "D"
    assert res_in1.cable_cell == "D45"
    assert res_in1.board_temp_cell == "R50"

    res_ot2 = resolve_feeder_channel("TH_FPOT2_MAX_PE13V")
    assert res_ot2 is not None
    assert res_ot2.pillar_index == 1
    assert res_ot2.channel == "OT2"
    assert res_ot2.feederno_label == "OUTGOING F2"
    assert res_ot2.column_letter == "J"
    assert res_ot2.cable_cell == "J45"
    assert res_ot2.board_temp_cell == "R50"

    res_ot10 = resolve_feeder_channel("TH_FPOT10_DEL_PE13R")
    assert res_ot10 is not None
    assert res_ot10.channel == "OT10"
    assert res_ot10.feederno_label == "OUTGOING F10"
    assert res_ot10.column_letter == "R"
    assert res_ot10.cable_cell == "R45"


def test_resolve_feeder_channel_cbm_defect_ids() -> None:
    from src.testsheet.feeder_thermal import resolve_feeder_channel

    # FP TX1 - OUTGOING F1 -> pillar 1, OT1
    res1 = resolve_feeder_channel("FP TX1 - OUTGOING F1")
    assert res1 is not None
    assert res1.pillar_index == 1
    assert res1.channel == "OT1"
    assert res1.feederno_label == "OUTGOING F1"
    assert res1.column_letter == "I"
    assert res1.cable_cell == "I45"
    assert res1.board_temp_cell == "R50"

    # FP TX2 - OUTGOING F3 -> pillar 2, OT3
    res2 = resolve_feeder_channel("FP TX2 - OUTGOING F3")
    assert res2 is not None
    assert res2.pillar_index == 2
    assert res2.channel == "OT3"
    assert res2.feederno_label == "OUTGOING F3"
    assert res2.column_letter == "K"
    assert res2.cable_cell == "K47"
    assert res2.board_temp_cell == "R54"

    # LVDB 2 - INC 2 -> pillar 2, IN2
    res3 = resolve_feeder_channel("LVDB 2 - INC 2")
    assert res3 is not None
    assert res3.pillar_index == 2
    assert res3.channel == "IN2"
    assert res3.feederno_label == "INCOMING 2"
    assert res3.column_letter == "E"
    assert res3.cable_cell == "E47"
    assert res3.board_temp_cell == "R54"


def test_resolve_feeder_channel_partial_and_bay_texts() -> None:
    from src.testsheet.feeder_thermal import resolve_feeder_channel

    # OUTGOING F1
    res = resolve_feeder_channel("OUTGOING F1")
    assert res is not None
    assert res.channel == "OT1"
    assert res.feederno_label == "OUTGOING F1"
    assert res.pillar_index == 1

    # OUTGOING F2
    res = resolve_feeder_channel("OUTGOING F2")
    assert res is not None
    assert res.channel == "OT2"
    assert res.feederno_label == "OUTGOING F2"

    # F1, F2, F10
    res_f1 = resolve_feeder_channel("F1")
    assert res_f1 is not None
    assert res_f1.channel == "OT1"

    res_f2 = resolve_feeder_channel("F2")
    assert res_f2 is not None
    assert res_f2.channel == "OT2"

    res_f10 = resolve_feeder_channel("F10")
    assert res_f10 is not None
    assert res_f10.channel == "OT10"

    # INC 1, INCOMING 1
    res_inc1 = resolve_feeder_channel("INC 1")
    assert res_inc1 is not None
    assert res_inc1.channel == "IN1"
    assert res_inc1.feederno_label == "INCOMING 1"

    res_inc2 = resolve_feeder_channel("INCOMING 1")
    assert res_inc2 is not None
    assert res_inc2.channel == "IN1"
    assert res_inc2.feederno_label == "INCOMING 1"


def test_resolve_feeder_channel_invalid_and_empty() -> None:
    from src.testsheet.feeder_thermal import resolve_feeder_channel

    assert resolve_feeder_channel("") is None
    assert resolve_feeder_channel("   ") is None
    assert resolve_feeder_channel("FP TX1") is None
    assert resolve_feeder_channel("TRANSFORMER 1") is None
    assert resolve_feeder_channel("SWITCHGEAR") is None
    assert resolve_feeder_channel("F11") is None

