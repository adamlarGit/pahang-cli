"""Unit and regression tests for refactored PRPD Option C preview script (Ticket #75)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from scripts.generate_prpd_option_c_html import (
    auto_discover_measurements,
    find_survey_root,
    generate_all_survey_prpd_option_c,
)


def _setup_synthetic_survey(survey_root: Path) -> None:
    """Create a synthetic multi-point VCB survey tree."""
    survey_root.mkdir(parents=True, exist_ok=True)

    items = [
        ("VCB/PANEL_1/20260917T100000_TEV", "TEV", "$CIRCUIT_BREAKER"),
        ("VCB/PANEL_1/20260917T100100_TEV", "TEV", "$CABLE_BOX"),
        ("VCB/PANEL_1/20260917T100200_US", "US", "$UPPER_BUSBARS"),
    ]

    measures = []
    for rel_sub, tech, comp in items:
        meas_dir = survey_root / Path(rel_sub)
        meas_dir.mkdir(parents=True, exist_ok=True)
        html_name = "TEV.html" if tech == "TEV" else "Ultrasonic.html"
        (meas_dir / html_name).write_text(f"<html><body>{tech}</body></html>", encoding="utf-8")

        measures.append({
            "$COMPONENT": comp,
            "$MEASURE_TYPE": "$TEV" if tech == "TEV" else "$ULTRA",
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
                        "$MEASURES": measures,
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")


def test_auto_discover_measurements_uses_canonical_naming(tmp_path: Path):
    """Verify auto_discover_measurements produces canonical labels without blind _2 suffixes."""
    survey_root = tmp_path / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey_root)

    items = auto_discover_measurements(survey_root)
    assert len(items) == 3

    labels = [item[0] for item in items]
    assert "VCB_PANEL_1_CIRCUIT_BREAKER_TEV" in labels
    assert "VCB_PANEL_1_CABLE_BOX_TEV" in labels
    assert "VCB_PANEL_1_UPPER_BUSBARS_US" in labels


def test_generate_all_survey_prpd_option_c(tmp_path: Path):
    """Verify generate_all_survey_prpd_option_c produces canonical PNG files."""
    survey_root = tmp_path / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey_root)
    output_dir = tmp_path / "output_graphs"

    def mock_render(html_file, output_png, survey_root, http_port, **kwargs):
        p = Path(output_png)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\nfake_option_c")
        return p

    with patch("scripts.generate_prpd_option_c_html.render_prpd_option_c_image", side_effect=mock_render), \
         patch("scripts.generate_prpd_option_c_html.find_chrome_executable", return_value="fake_chrome.exe"), \
         patch("scripts.generate_prpd_option_c_html.is_blank_or_invalid_image", return_value=False):

        results = generate_all_survey_prpd_option_c(survey_root, output_dir)

    assert len(results) == 3
    for res in results:
        assert res["status"] == "SUCCESS"

    expected_files = [
        output_dir / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png",
        output_dir / "VCB_PANEL_1_CABLE_BOX_TEV.png",
        output_dir / "VCB_PANEL_1_UPPER_BUSBARS_US.png",
    ]
    for ef in expected_files:
        assert ef.exists()


def test_preview_script_cli_help():
    """Verify python scripts/generate_prpd_option_c_html.py --help succeeds."""
    cmd = [sys.executable, "scripts/generate_prpd_option_c_html.py", "--help"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--survey-dir" in proc.stdout
    assert "--output-dir" in proc.stdout
