"""Unit and workflow tests for US+TEV graph generation workflow and dual-mode rendering engine (Ticket #73)."""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path
import struct
from unittest.mock import MagicMock, patch
import pytest

from src.workflows.us_tev_graphs import (
    BrowserPrerequisiteError,
    UsTevGraphWorkflow,
    UsTevWorkflowSummary,
    generate_substation_graphs,
)


def _build_synthetic_tev_flatbuffers() -> str:
    """Build a synthetic valid FlatBuffers binary buffer with UE01 identifier and 3 events."""
    events_data = bytearray()
    for peak, phase, cycle in [(25.5, 45, 1), (42.0, 180, 2), (25.5, 45, 3)]:
        events_data.extend(struct.pack("<fiHHHHff", peak, 100, phase, cycle, 10, 20, 0.5, 1.2))

    vector_bytes = bytearray(struct.pack("<I", 3)) + events_data
    vtable = struct.pack("<HH H H", 8, 8, 4, 0)
    root_table = struct.pack("<i I", 8, 4)

    buf = bytearray()
    buf.extend(struct.pack("<I", 24))
    buf.extend(b"UE01")
    buf.extend(b"\x00" * 8)
    buf.extend(vtable)
    buf.extend(root_table)
    buf.extend(vector_bytes)

    compressed = gzip.compress(bytes(buf))
    b64_str = base64.b64encode(compressed).decode("ascii")
    return f'var eventData="{b64_str}";\n'


def _setup_synthetic_survey(survey_root: Path) -> None:
    """Create a minimal synthetic survey folder with 1 TEV and 1 US measurement."""
    survey_root.mkdir(parents=True, exist_ok=True)
    tev_dir = survey_root / "VCB" / "PANEL_1" / "20260917T100000_TEV"
    tev_dir.mkdir(parents=True, exist_ok=True)
    (tev_dir / "TEV.html").write_text("<html><body>TEV</body></html>", encoding="utf-8")
    (tev_dir / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    us_dir = survey_root / "VCB" / "PANEL_1" / "20260917T100100_US"
    us_dir.mkdir(parents=True, exist_ok=True)
    (us_dir / "Ultrasonic.html").write_text("<html><body>US</body></html>", encoding="utf-8")
    us_content = 'var ultra_events = {"data": [[12.4, 60, 100], [-3.2, 210, 101]]};\n'
    (us_dir / "ultrasonic_phase_plot.js").write_text(us_content, encoding="utf-8")

    summary = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL_1",
                        "$MEASURES": [
                            {
                                "$COMPONENT": "$CIRCUIT_BREAKER",
                                "$MEASURE_TYPE": "$TEV",
                                "$SUB_LOC": "$NONE",
                                "Data": "VCB/PANEL_1/20260917T100000_TEV",
                            },
                            {
                                "$COMPONENT": "$UPPER_BUSBARS",
                                "$MEASURE_TYPE": "$ULTRA",
                                "$SUB_LOC": "$NONE",
                                "Data": "VCB/PANEL_1/20260917T100100_US",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(summary)};\n", encoding="utf-8")


def test_browser_prerequisite_error_raised_when_chrome_missing():
    """Verify BrowserPrerequisiteError is raised in Option C mode if Chromium is absent."""
    workflow = UsTevGraphWorkflow(mode="option_c")

    with patch("src.workflows.us_tev_graphs.find_chrome_executable", side_effect=FileNotFoundError("No Chrome found")):
        with pytest.raises(BrowserPrerequisiteError) as exc_info:
            workflow.check_browser_prerequisite()

        assert "Google Chrome or Microsoft Edge" in str(exc_info.value)
        assert "Option B" in str(exc_info.value)


def test_option_b_generates_prpd_graphs(tmp_path: Path):
    """Verify Option B generates Matplotlib graphs for TEV and US using canonical names."""
    survey_root = tmp_path / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey_root)
    output_dir = survey_root / "graphs"

    generated = generate_substation_graphs(survey_root, output_dir, mode="option_b")
    assert len(generated) == 2

    tev_png = output_dir / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png"
    us_png = output_dir / "VCB_PANEL_1_UPPER_BUSBARS_US.png"

    assert tev_png.exists()
    assert tev_png.stat().st_size > 0
    assert us_png.exists()
    assert us_png.stat().st_size > 0


def test_option_c_headless_rendering_pipeline(tmp_path: Path):
    """Verify Option C uses SurveyHttpServer and render_prpd_option_c_image."""
    survey_root = tmp_path / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey_root)
    output_dir = survey_root / "graphs"

    def mock_render(html_file, output_png, survey_root, http_port, **kwargs):
        p = Path(output_png)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\nfake_image_content")
        return p

    with patch("src.workflows.us_tev_graphs.render_prpd_option_c_image", side_effect=mock_render):
        generated = generate_substation_graphs(survey_root, output_dir, mode="option_c")

    assert len(generated) == 2
    assert (output_dir / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png").exists()
    assert (output_dir / "VCB_PANEL_1_UPPER_BUSBARS_US.png").exists()


def test_overwrite_idempotency(tmp_path: Path):
    """Verify re-running overwrites existing graph PNGs unconditionally."""
    survey_root = tmp_path / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey_root)
    output_dir = survey_root / "graphs"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_png = output_dir / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png"
    target_png.write_text("old content", encoding="utf-8")

    generate_substation_graphs(survey_root, output_dir, mode="option_b")

    # Content has been overwritten with valid binary PNG
    assert target_png.exists()
    assert target_png.read_bytes() != b"old content"


def test_zero_measurement_survey_returns_empty_list(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """Verify zero-measurement survey logs non-blocking warning and returns empty list."""
    survey_root = tmp_path / "EMPTY_SURVEY"
    survey_root.mkdir(parents=True)
    (survey_root / "survey_summary.js").write_text("var survey_summary = {'assets': []};\n", encoding="utf-8")

    output_dir = survey_root / "graphs"
    res = generate_substation_graphs(survey_root, output_dir, mode="option_b")

    assert res == []
    assert any("[WARN] No valid US/TEV measurements found" in record.message for record in caplog.records)


def test_batch_error_resilience(tmp_path: Path):
    """Verify SubstationIsolatedBatchResiliencePolicy isolates per-substation exceptions."""
    survey1 = tmp_path / "SUB1" / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey1)

    survey_bad = tmp_path / "SUB_BAD" / "RAW DATA" / "US+TEV"
    survey_bad.mkdir(parents=True, exist_ok=True)
    # Put a broken manifest that raises exception during generation
    (survey_bad / "survey_summary.js").write_text("CORRUPT", encoding="utf-8")

    survey2 = tmp_path / "SUB2" / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey2)

    workflow = UsTevGraphWorkflow(mode="option_b")

    # Mock run_substation to simulate an exception on SUB_BAD
    orig_run_substation = workflow.run_substation

    def faulty_run_substation(survey_root, output_dir=None):
        if "SUB_BAD" in str(survey_root):
            raise RuntimeError("Corrupted sensor payload")
        return orig_run_substation(survey_root, output_dir)

    workflow.run_substation = faulty_run_substation

    batch = [
        ("Substation 1", survey1),
        ("Substation Bad", survey_bad),
        ("Substation 2", survey2),
    ]

    summary = workflow.run_batch(batch)

    assert summary.total_substations == 3
    assert summary.total_graphs == 4  # 2 from sub1, 2 from sub2
    assert len(summary.errors) == 1
    assert "Substation Bad" in summary.errors[0]
