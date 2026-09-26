"""Unit tests for survey measurement discovery with multi-point component naming (Ticket #72)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.quick_report.prpd import (
    DiscoveredMeasurement,
    discover_survey_measurements,
    format_measurement_label,
)


# ==============================================================================
# Seam 1: Canonical Label Formatter Tests
# ==============================================================================

def test_format_measurement_label_vcb_multi_point():
    """Verify multi-point VCB panel labels preserve physical compartment names."""
    # Circuit Breaker TEV
    lbl1 = format_measurement_label("VCB", "PANEL_1", "$CIRCUIT_BREAKER", "TEV")
    assert lbl1 == "VCB_PANEL_1_CIRCUIT_BREAKER_TEV"

    # Cable Box TEV
    lbl2 = format_measurement_label("VCB", "PANEL_1", "$CABLE_BOX", "TEV")
    assert lbl2 == "VCB_PANEL_1_CABLE_BOX_TEV"

    # Upper Busbars US
    lbl3 = format_measurement_label("VCB", "PANEL_1", "$UPPER_BUSBARS", "US")
    assert lbl3 == "VCB_PANEL_1_UPPER_BUSBARS_US"

    # Lower Busbars US
    lbl4 = format_measurement_label("VCB", "PANEL_1", "$LOWER_BUSBARS", "US")
    assert lbl4 == "VCB_PANEL_1_LOWER_BUSBARS_US"

    # CT Chamber TEV
    lbl5 = format_measurement_label("VCB", "PANEL_1", "$CT_CHAMBER", "TEV")
    assert lbl5 == "VCB_PANEL_1_CT_CHAMBER_TEV"


def test_format_measurement_label_swg_feeder_single_point():
    """Verify SWG feeder labels cleanly omit component when missing or $NONE."""
    # When component is $NONE
    lbl1 = format_measurement_label("SWG", "FEEDER_1", "$NONE", "TEV")
    assert lbl1 == "SWG_FEEDER_1_TEV"

    # When component is None
    lbl2 = format_measurement_label("SWG", "FEEDER_1", None, "US")
    assert lbl2 == "SWG_FEEDER_1_US"

    # When component is empty string
    lbl3 = format_measurement_label("SWG", "FEEDER_1", "", "TEV")
    assert lbl3 == "SWG_FEEDER_1_TEV"

    # When component is valid compartment
    lbl4 = format_measurement_label("SWG", "FEEDER_1", "$CABLE_BOX", "TEV")
    assert lbl4 == "SWG_FEEDER_1_CABLE_BOX_TEV"


def test_format_measurement_label_sanitization():
    """Verify token sanitization strips $, whitespace, and special characters."""
    lbl = format_measurement_label(" $VCB-1 ", " Panel 01 ", " $Circuit_Breaker! ", "$TEV")
    assert lbl == "VCB_1_PANEL_01_CIRCUIT_BREAKER_TEV"

    lbl_us = format_measurement_label("TX 1", "Transformer", "$PRIMARY_CABLES", "$ULTRA")
    assert lbl_us == "TX_1_TRANSFORMER_PRIMARY_CABLES_US"


def test_format_measurement_label_transformer():
    """Verify transformer labels format properly with and without component."""
    lbl1 = format_measurement_label("TX1", "TRANSFORMER", "$PRIMARY_CABLES", "US")
    assert lbl1 == "TX1_TRANSFORMER_PRIMARY_CABLES_US"

    lbl2 = format_measurement_label("TX1", "TRANSFORMER", None, "US")
    assert lbl2 == "TX1_TRANSFORMER_US"


# ==============================================================================
# Helper to create synthetic survey directories
# ==============================================================================

def _create_synthetic_measurement(
    meas_dir: Path,
    tech: str,
    asset: str,
    subasset: str,
    component: str | None = None,
    sub_loc: str | None = None,
):
    """Helper creating a measurement directory with html and metadata."""
    meas_dir.mkdir(parents=True, exist_ok=True)
    html_name = "TEV.html" if tech == "TEV" else "Ultrasonic.html"
    (meas_dir / html_name).write_text(f"<html><body>{tech} Plot</body></html>", encoding="utf-8")

    meta_fields = [
        {"fieldname": "$ASSET_NAME", "data": asset},
        {"fieldname": "$SUB_ASSET_NAME", "data": subasset},
        {"fieldname": "$PANEL_NO", "data": subasset},
        {"fieldname": "$COMPONENT", "data": component if component else "$NONE"},
        {"fieldname": "$SUB_LOC", "data": sub_loc if sub_loc else "$NONE"},
    ]
    meta_payload = {
        "Trend": [],
        "measurement_fields": [{"fields": meta_fields}],
    }
    meta_js = f"var measurement_metadata = {json.dumps(meta_payload)};\n"
    (meas_dir / "measurement_metadata.js").write_text(meta_js, encoding="utf-8")


# ==============================================================================
# Seam 2 & 3: Manifest-driven Discovery (Tier 1) Tests
# ==============================================================================

def test_discover_survey_measurements_vcb_manifest(tmp_path: Path):
    """Test multi-point VCB survey with 5 measurements per panel via survey_summary.js."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    # Setup 5 measurements under VCB/PANEL_1
    components_techs = [
        ("$CIRCUIT_BREAKER", "$TEV", "TEV", "20260917T100000_TEV"),
        ("$CABLE_BOX", "$TEV", "TEV", "20260917T100100_TEV"),
        ("$CT_CHAMBER", "$TEV", "TEV", "20260917T100200_TEV"),
        ("$UPPER_BUSBARS", "$ULTRA", "US", "20260917T100300_US"),
        ("$LOWER_BUSBARS", "$ULTRA", "US", "20260917T100400_US"),
    ]

    meas_entries = []
    for comp, mtype, tech, folder_name in components_techs:
        rel_sub = f"VCB/PANEL_1/{folder_name}"
        m_dir = survey_root / "VCB" / "PANEL_1" / folder_name
        _create_synthetic_measurement(m_dir, tech, "VCB", "PANEL_1", comp)
        meas_entries.append({
            "$COMPONENT": comp,
            "$MEASURE_TYPE": mtype,
            "$SUB_LOC": "$NONE",
            "Data": rel_sub,
        })

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL_1",
                        "$MEASURES": meas_entries,
                    }
                ],
            }
        ]
    }
    manifest_file = survey_root / "survey_summary.js"
    manifest_file.write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 5

    labels = [m.label for m in discovered]
    assert "VCB_PANEL_1_CIRCUIT_BREAKER_TEV" in labels
    assert "VCB_PANEL_1_CABLE_BOX_TEV" in labels
    assert "VCB_PANEL_1_CT_CHAMBER_TEV" in labels
    assert "VCB_PANEL_1_UPPER_BUSBARS_US" in labels
    assert "VCB_PANEL_1_LOWER_BUSBARS_US" in labels

    for m in discovered:
        assert isinstance(m, DiscoveredMeasurement)
        assert m.meas_dir.exists()
        assert (m.meas_dir / m.html_file).exists()


def test_discover_survey_measurements_rmu_swg_single_point(tmp_path: Path):
    """Test single-point RMU/SWG survey where feeders have 1 TEV and 1 US point."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    feeders = ["FEEDER_1", "FEEDER_2"]
    sub_assets = []
    for f in feeders:
        rel_tev = f"SWG/{f}/20260917T110000_TEV"
        rel_us = f"SWG/{f}/20260917T110100_US"
        _create_synthetic_measurement(survey_root / "SWG" / f / "20260917T110000_TEV", "TEV", "SWG", f, "$NONE")
        _create_synthetic_measurement(survey_root / "SWG" / f / "20260917T110100_US", "US", "SWG", f, "$NONE")

        sub_assets.append({
            "$SUB_ASSET_NAME": f,
            "$MEASURES": [
                {"$COMPONENT": "$NONE", "$MEASURE_TYPE": "$TEV", "$SUB_LOC": "$NONE", "Data": rel_tev},
                {"$COMPONENT": "$NONE", "$MEASURE_TYPE": "$ULTRA", "$SUB_LOC": "$NONE", "Data": rel_us},
            ],
        })

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "SWG",
                "$SUB_ASSETS": sub_assets,
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 4
    labels = [m.label for m in discovered]
    assert labels == [
        "SWG_FEEDER_1_TEV",
        "SWG_FEEDER_1_US",
        "SWG_FEEDER_2_TEV",
        "SWG_FEEDER_2_US",
    ]


def test_discover_survey_measurements_transformer(tmp_path: Path):
    """Test transformer measurements discovery."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    rel_us = "TX1/TRANSFORMER/20260917T120000_US"
    _create_synthetic_measurement(
        survey_root / "TX1" / "TRANSFORMER" / "20260917T120000_US",
        "US",
        "TX1",
        "TRANSFORMER",
        "$PRIMARY_CABLES",
    )

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "TX1",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "TRANSFORMER",
                        "$MEASURES": [
                            {
                                "$COMPONENT": "$PRIMARY_CABLES",
                                "$MEASURE_TYPE": "$ULTRA",
                                "$SUB_LOC": "$NONE",
                                "Data": rel_us,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 1
    assert discovered[0].label == "TX1_TRANSFORMER_PRIMARY_CABLES_US"
    assert discovered[0].tech == "US"


def test_discover_survey_measurements_trailing_garbage_resilience(tmp_path: Path):
    """Test resilient parsing of survey_summary.js when corrupted trailer bytes exist."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    rel_tev = "VCB/PANEL_1/20260917T130000_TEV"
    _create_synthetic_measurement(
        survey_root / "VCB" / "PANEL_1" / "20260917T130000_TEV",
        "TEV",
        "VCB",
        "PANEL_1",
        "$CIRCUIT_BREAKER",
    )

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL_1",
                        "$MEASURES": [
                            {"$COMPONENT": "$CIRCUIT_BREAKER", "$MEASURE_TYPE": "$TEV", "Data": rel_tev}
                        ],
                    }
                ],
            }
        ]
    }
    # Simulate software glitch appending corrupted bytes or duplicated trailer
    corrupted_content = f"var survey_summary = {json.dumps(summary)};\n}};\n// GARBAGE_TRAILER_DATA!#$%^&*()"
    (survey_root / "survey_summary.js").write_text(corrupted_content, encoding="utf-8")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 1
    assert discovered[0].label == "VCB_PANEL_1_CIRCUIT_BREAKER_TEV"


def test_discover_survey_measurements_deduplication(tmp_path: Path):
    """Test deduplication appends incrementing counter _2, _3 for identical component labels."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    rel1 = "VCB/PANEL_1/20260917T140000_TEV"
    rel2 = "VCB/PANEL_1/20260917T140100_TEV"
    rel3 = "VCB/PANEL_1/20260917T140200_TEV"

    _create_synthetic_measurement(survey_root / rel1, "TEV", "VCB", "PANEL_1", "$CIRCUIT_BREAKER")
    _create_synthetic_measurement(survey_root / rel2, "TEV", "VCB", "PANEL_1", "$CIRCUIT_BREAKER")
    _create_synthetic_measurement(survey_root / rel3, "TEV", "VCB", "PANEL_1", "$CIRCUIT_BREAKER")

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL_1",
                        "$MEASURES": [
                            {"$COMPONENT": "$CIRCUIT_BREAKER", "$MEASURE_TYPE": "$TEV", "Data": rel1},
                            {"$COMPONENT": "$CIRCUIT_BREAKER", "$MEASURE_TYPE": "$TEV", "Data": rel2},
                            {"$COMPONENT": "$CIRCUIT_BREAKER", "$MEASURE_TYPE": "$TEV", "Data": rel3},
                        ],
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 3
    assert discovered[0].label == "VCB_PANEL_1_CIRCUIT_BREAKER_TEV"
    assert discovered[1].label == "VCB_PANEL_1_CIRCUIT_BREAKER_TEV_2"
    assert discovered[2].label == "VCB_PANEL_1_CIRCUIT_BREAKER_TEV_3"


def test_discover_survey_measurements_zero_returns_empty_list(tmp_path: Path):
    """Test empty survey returns empty list without raising exception."""
    empty_root = tmp_path / "EMPTY_SURVEY"
    empty_root.mkdir(parents=True)

    # Empty dir without any files
    res = discover_survey_measurements(empty_root)
    assert res == []

    # Survey summary with empty assets
    (empty_root / "survey_summary.js").write_text("var survey_summary = {'assets': []};\n", encoding="utf-8")
    res2 = discover_survey_measurements(empty_root)
    assert res2 == []


# ==============================================================================
# Seam 4: Deterministic Fallback Traversal (Tier 2) Tests
# ==============================================================================

def test_discover_survey_measurements_fallback_reading_metadata(tmp_path: Path):
    """Test fallback traversal when survey_summary.js is absent, reading measurement_metadata.js."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True)

    # Notice: NO survey_summary.js created here!
    # Create VCB panel with 3 measurements
    m1 = survey_root / "VCB" / "PANEL_1" / "20260917T150000_TEV"
    m2 = survey_root / "VCB" / "PANEL_1" / "20260917T150100_TEV"
    m3 = survey_root / "VCB" / "PANEL_1" / "20260917T150200_US"

    _create_synthetic_measurement(m1, "TEV", "VCB", "PANEL_1", "$CIRCUIT_BREAKER")
    _create_synthetic_measurement(m2, "TEV", "VCB", "PANEL_1", "$CABLE_BOX")
    _create_synthetic_measurement(m3, "US", "VCB", "PANEL_1", "$UPPER_BUSBARS")

    # Create TX measurement
    m4 = survey_root / "TX1" / "TRANSFORMER" / "20260917T150300_US"
    _create_synthetic_measurement(m4, "US", "TX1", "TRANSFORMER", "$PRIMARY_CABLES")

    discovered = discover_survey_measurements(survey_root)
    assert len(discovered) == 4

    labels = [m.label for m in discovered]
    assert "VCB_PANEL_1_CIRCUIT_BREAKER_TEV" in labels
    assert "VCB_PANEL_1_CABLE_BOX_TEV" in labels
    assert "VCB_PANEL_1_UPPER_BUSBARS_US" in labels
    assert "TX1_TRANSFORMER_PRIMARY_CABLES_US" in labels

    for m in discovered:
        assert isinstance(m, DiscoveredMeasurement)
        assert m.meas_dir.exists()
