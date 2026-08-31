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
