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
    discover_us_tev_candidate_substations,
    generate_substation_graphs,
    resolve_us_tev_graphs_output_dir,
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


def test_output_directory_resolution_for_nested_survey_archive(tmp_path: Path):
    """Verify output directory strictly resolves to <SUBSTATION>/RAW DATA/US+TEV/graphs/
    even when survey is nested inside <SUBSTATION>/RAW DATA/US+TEV/<ZIP_STEM>/.
    """
    sub_raw_us_tev = tmp_path / "PE_001" / "RAW DATA" / "US+TEV"
    nested_zip_stem = sub_raw_us_tev / "20260917_SURVEY_ARCHIVE"
    _setup_synthetic_survey(nested_zip_stem)

    workflow = UsTevGraphWorkflow(mode="option_b")

    # 1. run_substation with nested survey directory directly and output_dir=None
    paths = workflow.run_substation(nested_zip_stem)
    assert len(paths) == 2
    canonical_graphs_dir = sub_raw_us_tev / "graphs"
    assert canonical_graphs_dir.exists()
    for p in paths:
        assert p.parent == canonical_graphs_dir
        assert p.exists()

    # 2. run_substation passing parent US+TEV directory and output_dir=None
    paths_from_parent = workflow.run_substation(sub_raw_us_tev)
    assert len(paths_from_parent) == 2
    for p in paths_from_parent:
        assert p.parent == canonical_graphs_dir

    # 3. run_batch with 3-tuple (item, nested_zip_stem, explicit_graphs_dir)
    custom_graphs = tmp_path / "CUSTOM_GRAPHS"
    batch_3_tuple = [("PE 001", nested_zip_stem, custom_graphs)]
    summary = workflow.run_batch(batch_3_tuple)
    assert summary.total_substations == 1
    assert summary.total_graphs == 2
    assert (custom_graphs / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png").exists()

    # 4. run_batch with 2-tuple (item, nested_zip_stem) without explicit output_dir
    batch_2_tuple = [("PE 001", nested_zip_stem)]
    summary_2 = workflow.run_batch(batch_2_tuple)
    assert summary_2.total_substations == 1
    assert summary_2.total_graphs == 2
    assert (canonical_graphs_dir / "VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png").exists()


def test_resolve_us_tev_graphs_output_dir_2_level_bounded_check(tmp_path: Path):
    """Ticket #127: Verify 2-level bounded container check for US and US+TEV output resolution."""
    # Level 1: survey_dir.name is US
    p_us = tmp_path / "PE_001" / "RAW DATA" / "US"
    assert resolve_us_tev_graphs_output_dir(p_us) == p_us / "graphs"

    # Level 1: survey_dir.name is US+TEV
    p_us_tev = tmp_path / "PE_002" / "RAW DATA" / "US+TEV"
    assert resolve_us_tev_graphs_output_dir(p_us_tev) == p_us_tev / "graphs"

    # Level 2: survey_dir.parent.name is US
    p_us_nested = p_us / "20261022_SURVEY"
    assert resolve_us_tev_graphs_output_dir(p_us_nested) == p_us / "graphs"

    # Level 2: survey_dir.parent.name is US+TEV
    p_us_tev_nested = p_us_tev / "20260917_SURVEY"
    assert resolve_us_tev_graphs_output_dir(p_us_tev_nested) == p_us_tev / "graphs"

    # Neither container detected -> raises ValueError
    p_invalid = tmp_path / "PE_003" / "RAW DATA" / "OTHER_CONTAINER" / "SURVEY"
    with pytest.raises(ValueError, match="Neither 'US' nor 'US\\+TEV' container detected"):
        resolve_us_tev_graphs_output_dir(p_invalid)


def test_run_substation_polymorphic_33kv_us(tmp_path: Path):
    """Ticket #127: Verify run_substation resolves output to <SUBSTATION>/RAW DATA/US/graphs/ for 33kV."""
    sub_raw_us = tmp_path / "PE_33KV" / "RAW DATA" / "US"
    _setup_synthetic_survey(sub_raw_us)

    workflow = UsTevGraphWorkflow(mode="option_b")
    paths = workflow.run_substation(sub_raw_us)
    assert len(paths) == 2
    canonical_graphs_dir = sub_raw_us / "graphs"
    assert canonical_graphs_dir.exists()
    for p in paths:
        assert p.parent == canonical_graphs_dir
        assert p.exists()


def test_run_substation_raises_value_error_on_invalid_container(tmp_path: Path):
    """Ticket #127: Verify run_substation raises ValueError if neither US nor US+TEV container is detected."""
    sub_raw_invalid = tmp_path / "PE_INVALID" / "RAW DATA" / "OTHER"
    _setup_synthetic_survey(sub_raw_invalid)

    workflow = UsTevGraphWorkflow(mode="option_b")
    with pytest.raises(ValueError, match="Neither 'US' nor 'US\\+TEV' container detected"):
        workflow.run_substation(sub_raw_invalid)


def test_run_batch_resilience_isolates_invalid_container(tmp_path: Path):
    """Ticket #127: Verify SubstationIsolatedBatchResiliencePolicy isolates ValueError from invalid container."""
    # Sub 1: Valid US+TEV (11kV)
    survey1 = tmp_path / "SUB1" / "RAW DATA" / "US+TEV"
    _setup_synthetic_survey(survey1)

    # Sub 2: Invalid container (raises ValueError)
    survey_invalid = tmp_path / "SUB_INVALID" / "RAW DATA" / "OTHER"
    _setup_synthetic_survey(survey_invalid)

    # Sub 3: Valid US (33kV)
    survey3 = tmp_path / "SUB3" / "RAW DATA" / "US"
    _setup_synthetic_survey(survey3)

    workflow = UsTevGraphWorkflow(mode="option_b")
    batch = [
        ("Substation 1", survey1),
        ("Substation Invalid", survey_invalid),
        ("Substation 3", survey3),
    ]

    summary = workflow.run_batch(batch)
    assert summary.total_substations == 3
    assert summary.total_graphs == 4  # 2 from sub1, 2 from sub3
    assert len(summary.errors) == 1
    assert "Substation Invalid" in summary.errors[0]
    assert "Neither 'US' nor 'US+TEV' container detected" in summary.errors[0]

