"""Unit tests for Native Python PRPD Generator & Survey Discovery (Ticket 104)."""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path
import struct
import docx
from docxtpl import DocxTemplate
import pytest

from src.quick_report.prpd import (
    build_prpd_inline_images,
    decode_tev_event_data,
    decode_ultrasonic_phase_plot,
    discover_ultratev_survey_dir,
    find_latest_measurement_dir,
    find_swg_feeder_survey_dir,
    find_tx_survey_dir,
    generate_all_substation_prpd_graphs,
    generate_prpd_figure,
    generate_prpd_graphs_for_swg_panel,
    generate_prpd_graphs_for_transformer,
)


def _build_synthetic_tev_flatbuffers() -> str:
    """Build a synthetic valid FlatBuffers binary buffer with UE01 identifier and 3 events."""
    # 3 SingleEvent records (24 bytes each = 72 bytes)
    # "<fiHHHHff"
    # Event 1: peak=25.5, integral=100, phase=45, cycle=1, rise=10, width=20, tf_t=0.5, tf_f=1.2
    # Event 2: peak=42.0, integral=200, phase=180, cycle=2, rise=15, width=25, tf_t=0.6, tf_f=1.5
    # Event 3: peak=25.5, integral=100, phase=45, cycle=3, rise=10, width=20, tf_t=0.5, tf_f=1.2 (duplicate for binning)
    events_data = bytearray()
    for peak, phase, cycle in [(25.5, 45, 1), (42.0, 180, 2), (25.5, 45, 3)]:
        events_data.extend(struct.pack("<fiHHHHff", peak, 100, phase, cycle, 10, 20, 0.5, 1.2))

    # Vector layout: [vector_len (4 bytes)] + [elements]
    vector_bytes = bytearray(struct.pack("<I", 3)) + events_data

    # Build buffer layout:
    # Offset 0..4: root_offset = 24
    # Offset 4..8: identifier = "UE01"
    # Offset 8..16: padding
    # Offset 16..24: vtable [vtable_len=8, table_size=8, field0_offset=4, field1=0]
    # Offset 24..32: table [soffset = 8 (vtable at 16), field0 = vector offset (8 bytes relative)]
    # Offset 32+: vector [len=3] + events

    vtable = struct.pack("<HH H H", 8, 8, 4, 0)
    root_table = struct.pack("<i I", 8, 4)  # soffset=8 -> vtable_offset=24-8=16; field0=4 -> vector at 28+4=32

    buf = bytearray()
    buf.extend(struct.pack("<I", 24))  # 0..4
    buf.extend(b"UE01")  # 4..8
    buf.extend(b"\x00" * 8)  # 8..16 padding
    buf.extend(vtable)  # 16..24
    buf.extend(root_table)  # 24..32
    buf.extend(vector_bytes)  # 32..

    compressed = gzip.compress(bytes(buf))
    b64_str = base64.b64encode(compressed).decode("ascii")
    return f'var eventData="{b64_str}";\n'


def test_decode_tev_event_data(tmp_path: Path):
    """Test decoding synthetic FlatBuffers eventData.js."""
    js_file = tmp_path / "eventData.js"
    js_file.write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    events = decode_tev_event_data(js_file)
    assert len(events) == 3
    assert events[0]["phase"] == 45
    assert abs(events[0]["peak"] - 25.5) < 1e-4
    assert events[1]["phase"] == 180
    assert abs(events[1]["peak"] - 42.0) < 1e-4


def test_decode_ultrasonic_phase_plot(tmp_path: Path):
    """Test decoding JSON ultrasonic_phase_plot.js with 1/3 dB rounding."""
    js_content = 'var ultra_events = {"data": [[12.4, 60, 100], [-3.2, 210, 101]]};\n'
    js_file = tmp_path / "ultrasonic_phase_plot.js"
    js_file.write_text(js_content, encoding="utf-8")

    events = decode_ultrasonic_phase_plot(js_file)
    assert len(events) == 2
    assert events[0]["phase"] == 60
    assert events[0]["cycle"] == 100
    # 12.4 rounded to nearest 1/3 dB -> round(12.4 * 3)/3 = round(37.2)/3 = 37/3 = 12.3333...
    assert abs(events[0]["amplitude"] - 12.333333333333334) < 1e-4

    assert events[1]["phase"] == 210
    assert abs(events[1]["amplitude"] - (-3.3333333333333335)) < 1e-4


def test_generate_prpd_figure_tev_and_us(tmp_path: Path):
    """Test generate_prpd_figure creates valid PNG files with 4-tier scatter bins."""
    tev_events = [
        {"phase": 45, "amplitude": 25.0},
        {"phase": 45, "amplitude": 25.0},  # duplicate count=2
        {"phase": 90, "amplitude": 35.0},
        {"phase": 270, "amplitude": 48.0},
    ]
    out_tev = tmp_path / "tev_graph.png"
    result_tev = generate_prpd_figure(tev_events, tech_type="TEV", output_path=out_tev)
    assert result_tev is not None
    assert out_tev.exists()
    assert out_tev.stat().st_size > 1000

    us_events = [
        {"phase": 30, "amplitude": 14.0},
        {"phase": 120, "amplitude": 22.5},
        {"phase": 300, "amplitude": -5.0},
    ]
    out_us = tmp_path / "us_graph.png"
    result_us = generate_prpd_figure(us_events, tech_type="US", output_path=out_us)
    assert result_us is not None
    assert out_us.exists()
    assert out_us.stat().st_size > 1000


def test_generate_prpd_figure_zero_events(tmp_path: Path):
    """Test generate_prpd_figure with empty events renders clean axes without crashing."""
    out_zero = tmp_path / "zero_graph.png"
    result = generate_prpd_figure([], tech_type="TEV", output_path=out_zero)
    assert result is not None
    assert out_zero.exists()
    assert out_zero.stat().st_size > 1000


def test_survey_discovery_and_swg_matching(tmp_path: Path):
    """Test discovering survey directory and matching feeders using 3-tier precedence."""
    survey_dir = tmp_path / "RAW DATA" / "US+TEV" / "20260810T104017_001-PE-TEST"
    swg_dir = survey_dir / "SWG"
    f1_dir = swg_dir / "FEEDER_1"
    f2_dir = swg_dir / "FEEDER_2"
    f3_dir = swg_dir / "FEEDER 3"
    inc_dir = swg_dir / "INCOMING_1"

    f1_dir.mkdir(parents=True)
    f2_dir.mkdir(parents=True)
    f3_dir.mkdir(parents=True)
    inc_dir.mkdir(parents=True)

    # 1. Root survey discovery
    discovered = discover_ultratev_survey_dir(tmp_path)
    assert discovered == survey_dir

    # 2. Tier 1: Match panel_no (Column A index = 1 -> FEEDER_1)
    matched_f1 = find_swg_feeder_survey_dir(survey_dir, panel_no=1)
    assert matched_f1 == f1_dir

    # Tier 1: Match panel_no with space (panel_no = 3 -> FEEDER 3)
    matched_f3 = find_swg_feeder_survey_dir(survey_dir, panel_no=3)
    assert matched_f3 == f3_dir

    # Tier 2: Match feeder_no digits (e.g. "F02" -> FEEDER_2)
    matched_f2 = find_swg_feeder_survey_dir(survey_dir, panel_no=99, feeder_no="F02")
    assert matched_f2 == f2_dir

    # Tier 3: Match exact name ("INCOMING 1" -> INCOMING_1)
    matched_inc = find_swg_feeder_survey_dir(survey_dir, panel_no=99, panel_name="INCOMING 1")
    assert matched_inc == inc_dir


def test_find_tx_survey_dir_1tx_and_2tx(tmp_path: Path):
    """Test transformer directory discovery across 1-TX and 2-TX survey structures."""
    # 1. Multi-TX structure
    survey_2tx = tmp_path / "2TX_SURVEY"
    tx1_dir = survey_2tx / "TX1" / "Transformer"
    tx2_dir = survey_2tx / "TX2" / "Transformer"
    tx1_dir.mkdir(parents=True)
    tx2_dir.mkdir(parents=True)

    assert find_tx_survey_dir(survey_2tx, tx_idx=1) == tx1_dir
    assert find_tx_survey_dir(survey_2tx, tx_idx=2) == tx2_dir

    # 2. Single-TX structure
    survey_1tx = tmp_path / "1TX_SURVEY"
    tx_single = survey_1tx / "TX" / "Transformer"
    tx_single.mkdir(parents=True)

    assert find_tx_survey_dir(survey_1tx, tx_idx=1) == tx_single


def test_find_latest_measurement_dir_and_generation(tmp_path: Path):
    """Test selecting the latest timestamp run and generating PNG outputs."""
    feeder_dir = tmp_path / "SWG" / "FEEDER_1"
    run_early = feeder_dir / "20260810T104000_TEV"
    run_late = feeder_dir / "20260810T105322_TEV"
    run_us = feeder_dir / "20260810T104448_Ultrasonic"

    run_early.mkdir(parents=True)
    run_late.mkdir(parents=True)
    run_us.mkdir(parents=True)

    (run_early / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")
    (run_late / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")
    (run_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[10.0, 50, 1]]};', encoding="utf-8")

    latest_tev = find_latest_measurement_dir(feeder_dir, "TEV")
    assert latest_tev == run_late

    latest_us = find_latest_measurement_dir(feeder_dir, "US")
    assert latest_us == run_us

    out_dir = tmp_path / "prpd_out"
    survey_root = tmp_path
    us_png, tev_png = generate_prpd_graphs_for_swg_panel(
        survey_root=survey_root,
        panel_no=1,
        output_dir=out_dir,
    )
    assert us_png is not None and us_png.exists()
    assert tev_png is not None and tev_png.exists()


def test_build_prpd_inline_images_and_render_docx(tmp_path: Path):
    """Test binding InlineImage instances to DocxTemplate and saving rendered document."""
    template_path = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-panel.docx")
    if not template_path.exists():
        pytest.skip("swg-panel.docx template not found.")

    out_dir = tmp_path / "prpd_imgs"
    out_dir.mkdir(parents=True)
    us_png = out_dir / "us.png"
    tev_png = out_dir / "tev.png"

    generate_prpd_figure([{"phase": 45, "amplitude": 20.0}], tech_type="US", output_path=us_png)
    generate_prpd_figure([{"phase": 90, "amplitude": 30.0}], tech_type="TEV", output_path=tev_png)

    tpl = DocxTemplate(template_path)
    us_inline, tev_inline = build_prpd_inline_images(tpl, us_png, tev_png, width_mm=80.0)

    context = {
        "us": {"prpd": us_inline, "reading": "10.0", "char": "CORONA", "severity": ""},
        "tev": {"prpd": tev_inline, "reading": "20.0", "ppc": "50", "bg": "8", "severity": ""},
        "ir": {"reading": "50.0", "severity": ""},
        "panel": {"name": "INCOMING 1", "feeder_no": "F01", "type": "VCB"},
    }

    from src.quick_report.cbm_render import _build_jinja_env, _preserve_blank_render_values
    tpl.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env())

    out_docx = tmp_path / "swg_with_prpd.docx"
    tpl.save(out_docx)

    doc = docx.Document(out_docx)
    assert len(doc.inline_shapes) >= 2


def test_generate_all_substation_prpd_graphs(tmp_path: Path):
    """Test unified multi-feeder and multi-TX PRPD chart generation."""
    survey_root = tmp_path / "SURVEY"
    swg_dir = survey_root / "SWG"
    tx1_dir = survey_root / "TX1" / "Transformer"
    tx2_dir = survey_root / "TX2" / "Transformer"

    f1_dir = swg_dir / "FEEDER_1"
    f2_dir = swg_dir / "FEEDER_2"
    f3_dir = swg_dir / "FEEDER_3"
    f4_dir = swg_dir / "FEEDER_4"

    for d in (f1_dir, f2_dir, f3_dir, f4_dir, tx1_dir, tx2_dir):
        d.mkdir(parents=True)

    # Feeder 1 has US + TEV
    f1_us = f1_dir / "20260810T104448_Ultrasonic"
    f1_tev = f1_dir / "20260810T105322_TEV"
    f1_us.mkdir()
    f1_tev.mkdir()
    (f1_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[12.0, 45, 1]]};', encoding="utf-8")
    (f1_tev / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    # Feeder 2 has US only
    f2_us = f2_dir / "20260810T104500_Ultrasonic"
    f2_us.mkdir()
    (f2_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[8.0, 90, 1]]};', encoding="utf-8")

    # TX 1 has US + TEV
    tx1_us = tx1_dir / "20260810T110000_Ultrasonic"
    tx1_tev = tx1_dir / "20260810T110500_TEV"
    tx1_us.mkdir()
    tx1_tev.mkdir()
    (tx1_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[15.0, 180, 1]]};', encoding="utf-8")
    (tx1_tev / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    # TX 2 has US only
    tx2_us = tx2_dir / "20260810T111000_Ultrasonic"
    tx2_us.mkdir()
    (tx2_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[6.0, 270, 1]]};', encoding="utf-8")

    out_dir = tmp_path / "prpd_catalog_out"
    catalog = generate_all_substation_prpd_graphs(survey_root, out_dir)

    assert "swg" in catalog
    assert "tx" in catalog

    # SWG checks
    assert 1 in catalog["swg"]
    assert catalog["swg"][1]["us"] is not None and catalog["swg"][1]["us"].exists()
    assert catalog["swg"][1]["tev"] is not None and catalog["swg"][1]["tev"].exists()

    assert 2 in catalog["swg"]
    assert catalog["swg"][2]["us"] is not None and catalog["swg"][2]["us"].exists()
    assert catalog["swg"][2]["tev"] is None

    assert 3 in catalog["swg"]
    assert catalog["swg"][3]["us"] is None
    assert catalog["swg"][3]["tev"] is None

    # TX checks
    assert 1 in catalog["tx"]
    assert catalog["tx"][1]["us"] is not None and catalog["tx"][1]["us"].exists()
    assert catalog["tx"][1]["tev"] is not None and catalog["tx"][1]["tev"].exists()

    assert 2 in catalog["tx"]
    assert catalog["tx"][2]["us"] is not None and catalog["tx"][2]["us"].exists()
    assert catalog["tx"][2]["tev"] is None


def test_discover_survey_prioritizes_latest_timestamp(tmp_path: Path):
    """Test discover_ultratev_survey_dir prioritizes latest timestamped survey."""
    raw_root = tmp_path / "RAW DATA" / "US+TEV"
    early_survey = raw_root / "20260810T090000_001-PE-TEST"
    late_survey = raw_root / "20260810T110000_001-PE-TEST"

    (early_survey / "SWG").mkdir(parents=True)
    (late_survey / "SWG").mkdir(parents=True)

    discovered = discover_ultratev_survey_dir(tmp_path)
    assert discovered == late_survey


def test_discover_ultratev_survey_dir_vcb_and_rmu(tmp_path: Path):
    """Test discovering survey directory when only VCB or RMU folders are present."""
    vcb_survey = tmp_path / "RAW DATA" / "US+TEV" / "20260904T122744_228-SSU-GALI-TENGAH"
    (vcb_survey / "VCB" / "PANEL_2").mkdir(parents=True)
    (vcb_survey / "TX1" / "Transformer").mkdir(parents=True)

    discovered = discover_ultratev_survey_dir(tmp_path)
    assert discovered == vcb_survey


def test_find_swg_feeder_survey_dir_vcb_and_rmu(tmp_path: Path):
    """Test find_swg_feeder_survey_dir correctly resolves VCB and RMU switchgear folders."""
    survey_dir = tmp_path / "SURVEY_VCB"
    vcb_dir = survey_dir / "VCB"
    p2_dir = vcb_dir / "PANEL_2"
    p2_dir.mkdir(parents=True)

    # Match panel_no = 2 against VCB/PANEL_2
    matched_p2 = find_swg_feeder_survey_dir(survey_dir, panel_no=2)
    assert matched_p2 == p2_dir

    # RMU test
    rmu_survey = tmp_path / "SURVEY_RMU"
    rmu_dir = rmu_survey / "RMU"
    f1_dir = rmu_dir / "FEEDER_1"
    f1_dir.mkdir(parents=True)

    matched_rmu = find_swg_feeder_survey_dir(rmu_survey, panel_no=1)
    assert matched_rmu == f1_dir


def test_generate_all_substation_prpd_graphs_vcb(tmp_path: Path):
    """Test generate_all_substation_prpd_graphs when substation uses VCB switchgear layout."""
    survey_root = tmp_path / "SURVEY_228"
    p2_dir = survey_root / "VCB" / "PANEL_2"
    tx1_dir = survey_root / "TX1" / "Transformer"
    p2_dir.mkdir(parents=True)
    tx1_dir.mkdir(parents=True)

    # Add TEV and US to VCB Panel 2
    tev_run = p2_dir / "20260904T125310_TEV"
    us_run = p2_dir / "20260904T123837_Ultrasonic"
    tev_run.mkdir()
    us_run.mkdir()
    (tev_run / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")
    (us_run / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[15.0, 45, 1]]};', encoding="utf-8")

    # Add US to TX1
    tx_us = tx1_dir / "20260904T124600_Ultrasonic"
    tx_us.mkdir()
    (tx_us / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": [[-6.0, 90, 1]]};', encoding="utf-8")

    out_dir = tmp_path / "prpd_vcb_out"
    catalog = generate_all_substation_prpd_graphs(survey_root, out_dir)

    assert 2 in catalog["swg"]
    assert catalog["swg"][2]["us"] is not None and catalog["swg"][2]["us"].exists()
    assert catalog["swg"][2]["tev"] is not None and catalog["swg"][2]["tev"].exists()

    assert 1 in catalog["tx"]
    assert catalog["tx"][1]["us"] is not None and catalog["tx"][1]["us"].exists()


def test_auto_discover_measurements_option_c_and_b(tmp_path: Path):
    """Test auto_discover_measurements in Option C and Option B scripts with survey_summary.js and fallback."""
    from scripts.generate_prpd_option_c_html import auto_discover_measurements as discover_c
    from scripts.generate_prpd_option_b import auto_discover_measurements as discover_b

    survey_root = tmp_path / "SURVEY_TEST"
    tev_dir = survey_root / "VCB" / "PANEL_2" / "20260904T125310_TEV"
    us_dir = survey_root / "VCB" / "PANEL_2" / "20260904T123837_Ultrasonic"
    tx_us_dir = survey_root / "TX1" / "Transformer" / "20260904T124600_Ultrasonic"

    for d in (tev_dir, us_dir, tx_us_dir):
        d.mkdir(parents=True)

    # Option C HTML files
    (tev_dir / "TEV.html").write_text("<html></html>", encoding="utf-8")
    (us_dir / "Ultrasonic.html").write_text("<html></html>", encoding="utf-8")
    (tx_us_dir / "Ultrasonic.html").write_text("<html></html>", encoding="utf-8")

    # Option B data files
    (tev_dir / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")
    (us_dir / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": []};', encoding="utf-8")
    (tx_us_dir / "ultrasonic_phase_plot.js").write_text('var ultra_events = {"data": []};', encoding="utf-8")

    # 1. Test fallback traversal (before survey_summary.js exists)
    items_c_fallback = discover_c(survey_root)
    assert len(items_c_fallback) == 3
    labels_c = {item[0] for item in items_c_fallback}
    assert "VCB_PANEL_2_TEV" in labels_c
    assert "VCB_PANEL_2_US" in labels_c
    assert "TX1_TRANSFORMER_US" in labels_c

    items_b_fallback = discover_b(survey_root)
    assert len(items_b_fallback) == 3
    labels_b = {item[0] for item in items_b_fallback}
    assert "VCB_PANEL_2_TEV" in labels_b
    assert "VCB_PANEL_2_US" in labels_b
    assert "TX1_TRANSFORMER_US" in labels_b

    # 2. Test primary manifest parsing with survey_summary.js
    manifest_data = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL 2",
                        "$PANEL_NO": "2",
                        "$MEASURES": [
                            {"$MEASURE_TYPE": "$TEV", "Data": "VCB/PANEL_2/20260904T125310_TEV"},
                            {"$MEASURE_TYPE": "$ULTRA", "Data": "VCB/PANEL_2/20260904T123837_Ultrasonic"},
                        ],
                    }
                ],
            },
            {
                "$ASSET_NAME": "TX1",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "Transformer",
                        "$PANEL_NO": "1",
                        "$MEASURES": [
                            {"$MEASURE_TYPE": "$ULTRA", "Data": "TX1/Transformer/20260904T124600_Ultrasonic"}
                        ],
                    }
                ],
            },
        ]
    }
    (survey_root / "survey_summary.js").write_text(
        f"var survey_summary = {json.dumps(manifest_data)};", encoding="utf-8"
    )

    items_c_manifest = discover_c(survey_root)
    assert len(items_c_manifest) == 3
    assert items_c_manifest[0] == ("VCB_PANEL_2_TEV", "VCB/PANEL_2/20260904T125310_TEV", "TEV.html", "TEV")
    assert items_c_manifest[1] == ("VCB_PANEL_2_US", "VCB/PANEL_2/20260904T123837_Ultrasonic", "Ultrasonic.html", "US")
    assert items_c_manifest[2] == ("TX1_TRANSFORMER_US", "TX1/Transformer/20260904T124600_Ultrasonic", "Ultrasonic.html", "US")

    items_b_manifest = discover_b(survey_root)
    assert len(items_b_manifest) == 3
    assert items_b_manifest[0][0] == "VCB_PANEL_2_TEV"
    assert items_b_manifest[0][2] == "TEV"
    assert items_b_manifest[1][0] == "VCB_PANEL_2_US"
    assert items_b_manifest[1][2] == "US"
    assert items_b_manifest[2][0] == "TX1_TRANSFORMER_US"
    assert items_b_manifest[2][2] == "US"


def test_auto_discover_measurements_malformed_manifest_fallback(tmp_path: Path):
    """Test auto_discover_measurements gracefully falls back to filesystem traversal on corrupted JSON."""
    from scripts.generate_prpd_option_c_html import auto_discover_measurements as discover_c
    from scripts.generate_prpd_option_b import auto_discover_measurements as discover_b

    survey_root = tmp_path / "SURVEY_CORRUPT"
    tev_dir = survey_root / "VCB" / "PANEL_1" / "20260904T120000_TEV"
    tev_dir.mkdir(parents=True)
    (tev_dir / "TEV.html").write_text("<html></html>", encoding="utf-8")
    (tev_dir / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    # Write corrupt survey_summary.js
    (survey_root / "survey_summary.js").write_text("var survey_summary = { NOT_VALID_JSON !!!", encoding="utf-8")

    items_c = discover_c(survey_root)
    assert len(items_c) == 1
    assert items_c[0][0] == "VCB_PANEL_1_TEV"

    items_b = discover_b(survey_root)
    assert len(items_b) == 1
    assert items_b[0][0] == "VCB_PANEL_1_TEV"


def test_auto_discover_measurements_missing_and_special_char_attributes(tmp_path: Path):
    """Test manifest parsing with missing attributes and special characters in asset names."""
    from scripts.generate_prpd_option_c_html import auto_discover_measurements as discover_c
    from scripts.generate_prpd_option_b import auto_discover_measurements as discover_b

    survey_root = tmp_path / "SURVEY_SPECIAL"
    sub_dir = survey_root / "FEEDERS" / "RUN1"
    sub_dir.mkdir(parents=True)
    (sub_dir / "TEV.html").write_text("<html></html>", encoding="utf-8")
    (sub_dir / "eventData.js").write_text(_build_synthetic_tev_flatbuffers(), encoding="utf-8")

    manifest = {
        "assets": [
            "invalid_asset_element_string",
            None,
            {
                "$ASSET_NAME": "RMU #1 / 11kV",
                "$SUB_ASSETS": [
                    None,
                    {
                        "$SUB_ASSET_NAME": "Panel:A (Incomer)",
                        "$MEASURES": [
                            {"$MEASURE_TYPE": "UNKNOWN", "Data": "FEEDERS/RUN1"},
                            {"$MEASURE_TYPE": "$TEV", "Data": ""},
                            {"$MEASURE_TYPE": "$TEV", "Data": "FEEDERS/RUN1"},
                        ],
                    },
                ],
            },
        ]
    }
    (survey_root / "survey_summary.js").write_text(f"var survey_summary = {json.dumps(manifest)};", encoding="utf-8")

    items_c = discover_c(survey_root)
    assert len(items_c) == 1
    # Check that special characters (#, /, :, (, )) were cleanly sanitized
    label_c = items_c[0][0]
    assert label_c == "RMU_1_11KV_PANEL_A_INCOMER_TEV"
    assert "/" not in label_c
    assert ":" not in label_c

    items_b = discover_b(survey_root)
    assert len(items_b) == 1
    label_b = items_b[0][0]
    assert label_b == "RMU_1_11KV_PANEL_A_INCOMER_TEV"


def test_find_swg_feeder_survey_dir_hyphen_and_zero_padding(tmp_path: Path):
    """Test find_swg_feeder_survey_dir with hyphenated and zero-padded directory names."""
    survey_dir = tmp_path / "SURVEY_HYPHEN"
    (survey_dir / "SWG" / "PANEL-2").mkdir(parents=True)
    (survey_dir / "SWG" / "FEEDER-03").mkdir(parents=True)

    # Panel 2 via hyphenated name
    m2 = find_swg_feeder_survey_dir(survey_dir, panel_no=2)
    assert m2 is not None
    assert m2.name == "PANEL-2"

    # Feeder 3 via zero-padded hyphenated name
    m3 = find_swg_feeder_survey_dir(survey_dir, panel_no=3)
    assert m3 is not None
    assert m3.name == "FEEDER-03"


