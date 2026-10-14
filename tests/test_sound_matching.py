"""Unit tests for ultrasound measurement discovery, page inspection, and compartment matching.

Tests cover:
- Anchor detection centering speaker rectangle inside Column 2 (x in [236, 254] pt).
- Anchor detection returns None on pages without "Sound clip".
- TwoTierPanelMatchingPolicy across bare digits, prefixed codes, and unnumbered SCADA codes.
- VcbAudioAttributionPolicy (1-to-1 chamber mapping, zero cross-chamber leakage, tie-breaking).
- TransformerAudioAttributionPolicy (prefixed and bare numbers, sharing across HV side pages).
- RmuAudioAttributionPolicy (untagged US matches cable compartment, board-level fallback).
- Mandatory 8k.wav presence invariant raising FileNotFoundError.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pytest
import fitz

from src.postprocessing.sound_embedder import (
    find_sound_clip_anchor,
    extract_page_equipment_context,
    resolve_measurement_audio_for_page,
)
from src.quick_report.prpd import DiscoveredMeasurement


# ==============================================================================
# Helper Mock Objects for Tests
# ==============================================================================

@dataclass
class MockPanel:
    panel_no: int
    panel_feeder_no: str
    name: str = ""


@dataclass
class MockSwitchgear:
    panels: list[MockPanel]


@dataclass
class MockEquipment:
    switchgears: list[MockSwitchgear]


@dataclass
class MockPackage:
    equipment: MockEquipment


def _create_synthetic_page(text_blocks: list[tuple[float, float, str]]) -> fitz.Document:
    """Creates an in-memory 1-page PDF document with specified text strings at given coordinates."""
    doc = fitz.open()
    page = doc.new_page(width=595.0, height=842.0)  # Standard A4
    for x, y, text in text_blocks:
        page.insert_text(fitz.Point(x, y), text, fontsize=10)
    return doc


# ==============================================================================
# Seam 1: Anchor Detection Tests
# ==============================================================================

def test_find_sound_clip_anchor_centers_speaker_rect_in_column_2():
    """Anchor detection locates 'Sound clip' and centers rectangle inside Column 2 (x in [236, 254])."""
    # Insert "Sound clip" at typical Row 31 position in Column 1 (x ~ 80, y ~ 650)
    doc = _create_synthetic_page([(80.0, 650.0, "Sound clip")])
    page = doc[0]

    rect = find_sound_clip_anchor(page)
    assert rect is not None
    assert isinstance(rect, fitz.Rect)

    # Asserts speaker annotation rectangle is strictly centered in Column 2
    assert rect.x0 == 236.0
    assert rect.x1 == 254.0
    assert rect.width == 18.0

    # Vertical alignment matches text instance y0 - 2, y1 + 2
    insts = page.search_for("Sound clip")
    assert len(insts) == 1
    inst = insts[0]
    assert abs(rect.y0 - (inst.y0 - 2)) < 1e-3
    assert abs(rect.y1 - (inst.y1 + 2)) < 1e-3


def test_find_sound_clip_anchor_returns_none_when_marker_absent():
    """Anchor detection returns None on pages lacking 'Sound clip' marker."""
    # Test on overview / condition page text
    doc = _create_synthetic_page([
        (50.0, 100.0, "SUBSTATION OVERVIEW CONDITION ASSESSMENT"),
        (50.0, 150.0, "Visual Inspection Summary"),
    ])
    page = doc[0]

    rect = find_sound_clip_anchor(page)
    assert rect is None


# ==============================================================================
# Seam 2: Page Equipment Context Extraction & TwoTierPanelMatchingPolicy Tests
# ==============================================================================

def test_extract_page_equipment_context_tier_1_bare_digit():
    """Tier 1 extracts explicit bare digit from 'Panel No. : 1'."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : 1"),
        (60.0, 120.0, "Panel Name : 1L5 PMU GBID (9L5)"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT Panel"),
        (60.0, 650.0, "Sound clip"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    ctx = extract_page_equipment_context(page)
    assert ctx["panel_no"] == 1
    assert ctx["panel_name"] == "1L5 PMU GBID (9L5)"
    assert ctx["area"] == "CABLE COMPARTMENT"
    assert ctx["tx_idx"] is None


def test_extract_page_equipment_context_tier_1_prefixed_code():
    """Tier 1 extracts digit 1 from 'Panel No. : 1 (CRB70001)'."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : 1 (CRB70001)"),
        (60.0, 120.0, "Panel Name : INCOMER 1"),
        (60.0, 140.0, "Area : BREAKER COMPARTMENT IR Camera"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    ctx = extract_page_equipment_context(page)
    assert ctx["panel_no"] == 1
    assert ctx["panel_name"] == "INCOMER 1"
    assert ctx["area"] == "BREAKER COMPARTMENT"


def test_extract_page_equipment_context_tier_1_panel_word_prefix():
    """Tier 1 extracts digit 2 from 'Panel No. : Panel 2'."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : Panel 2"),
        (60.0, 120.0, "Panel Name : 1L5 PMU GBID (9L5)"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT Panel"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    ctx = extract_page_equipment_context(page)
    assert ctx["panel_no"] == 2
    assert ctx["panel_name"] == "1L5 PMU GBID (9L5)"
    assert ctx["area"] == "CABLE COMPARTMENT"



def test_extract_page_equipment_context_tier_2_scada_code_with_package():
    """Tier 2 resolves unnumbered SCADA code 'CRB00764' to panel_no 3 via package fallback."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : CRB00764"),
        (60.0, 120.0, "Panel Name : FEEDER TELOK"),
        (60.0, 140.0, "Area : BUSBAR COMPARTMENT Time"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    mock_pkg = MockPackage(
        equipment=MockEquipment(
            switchgears=[
                MockSwitchgear(
                    panels=[
                        MockPanel(panel_no=1, panel_feeder_no="CRB00760", name="INCOMER 1"),
                        MockPanel(panel_no=2, panel_feeder_no="CRB00762", name="TIE"),
                        MockPanel(panel_no=3, panel_feeder_no="CRB00764", name="FEEDER TELOK"),
                    ]
                )
            ]
        )
    )

    ctx = extract_page_equipment_context(page, package=mock_pkg)
    assert ctx["panel_no"] == 3
    assert ctx["panel_name"] == "FEEDER TELOK"
    assert ctx["area"] == "BUSBAR COMPARTMENT"


def test_extract_page_equipment_context_tier_2_decoupled_without_package():
    """Without package, unnumbered SCADA code preserves panel_name for directory lookup."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : CRB00764"),
        (60.0, 120.0, "Panel Name : FEEDER TELOK"),
        (60.0, 140.0, "Area : PT COMPARTMENT Model"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    ctx = extract_page_equipment_context(page, package=None)
    assert ctx["panel_no"] is None
    assert ctx["raw_panel_no"] == "CRB00764"
    assert ctx["panel_name"] == "FEEDER TELOK"
    assert ctx["area"] == "PT COMPARTMENT"


def test_extract_page_equipment_context_transformer_prefix_tolerance():
    """Extracts transformer unit index across bare numbers and prefixed 'TX1' / 'TX2'."""
    # Case 1: Bare digit
    doc1 = _create_synthetic_page([
        (60.0, 100.0, "Tx No. : 1"),
        (60.0, 140.0, "Area : HV CABLE Tx"),
    ])
    ctx1 = extract_page_equipment_context(doc1[0])
    assert ctx1["tx_idx"] == 1
    assert ctx1["area"] == "HV CABLE"

    # Case 2: Prefixed TX2
    doc2 = _create_synthetic_page([
        (60.0, 100.0, "Tx No. : TX2"),
        (60.0, 140.0, "Area : HV BUSHING Model"),
    ])
    ctx2 = extract_page_equipment_context(doc2[0])
    assert ctx2["tx_idx"] == 2
    assert ctx2["area"] == "HV BUSHING"

    # Case 3: TRANSFORMER 1 prefix
    doc3 = _create_synthetic_page([
        (60.0, 100.0, "Tx No. : TRANSFORMER 1"),
        (60.0, 140.0, "Area : HV CABLE SPLIT"),
    ])
    ctx3 = extract_page_equipment_context(doc3[0])
    assert ctx3["tx_idx"] == 1
    assert ctx3["area"] == "HV CABLE SPLIT"


# ==============================================================================
# Seam 3: Resolver & Attribution Policy Tests (VCB, Transformer, RMU)
# ==============================================================================

def _create_synthetic_meas(
    meas_dir: Path,
    label: str,
    asset: str,
    subasset: str,
    component: str | None,
    tech: str = "US",
    db_reading: float = 10.0,
    create_8k_wav: bool = True,
    wav_size: int = 100,
) -> DiscoveredMeasurement:
    meas_dir.mkdir(parents=True, exist_ok=True)
    if create_8k_wav:
        (meas_dir / "8k.wav").write_bytes(b"\x00" * wav_size)

    js_content = f'var ultra_events = {{"data": [[{db_reading}, 60, 100]]}};\n'
    (meas_dir / "ultrasonic_phase_plot.js").write_text(js_content, encoding="utf-8")

    return DiscoveredMeasurement(
        label=label,
        asset=asset,
        subasset=subasset,
        component=component,
        sub_loc=None,
        tech=tech,
        html_file="Ultrasonic.html" if tech == "US" else "TEV.html",
        data_rel_path=meas_dir.name,
        meas_dir=meas_dir,
    )


def test_vcb_audio_attribution_strict_chamber_mapping_and_zero_leakage(tmp_path: Path):
    """VCB policy asserts strict 1-to-1 chamber mapping, zero cross-chamber leaking, and skips secondary compartment."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()

    feeder_dir = survey_root / "VCB" / "PANEL_1"
    feeder_dir.mkdir(parents=True)

    meas_cb = _create_synthetic_meas(
        feeder_dir / "meas_cb", "VCB_PANEL_1_CIRCUIT_BREAKER_US", "VCB", "PANEL_1", "$CIRCUIT_BREAKER"
    )
    meas_cable = _create_synthetic_meas(
        feeder_dir / "meas_cable", "VCB_PANEL_1_CABLE_BOX_US", "VCB", "PANEL_1", "$CABLE_BOX"
    )
    meas_pt = _create_synthetic_meas(
        feeder_dir / "meas_pt", "VCB_PANEL_1_VT_CHAMBER_US", "VCB", "PANEL_1", "$VT_CHAMBER"
    )

    all_meas = [meas_cb, meas_cable, meas_pt]

    # 1. Breaker compartment matches CB recording
    ctx_breaker = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "BREAKER COMPARTMENT"}
    res_breaker = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_breaker)
    assert res_breaker == meas_cb.meas_dir / "8k.wav"

    # 2. Cable compartment matches Cable recording
    ctx_cable = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "CABLE COMPARTMENT"}
    res_cable = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_cable)
    assert res_cable == meas_cable.meas_dir / "8k.wav"

    # 3. PT compartment matches VT recording
    ctx_pt = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "PT COMPARTMENT"}
    res_pt = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_pt)
    assert res_pt == meas_pt.meas_dir / "8k.wav"

    # 4. Secondary compartment is non-acoustic -> returns None
    ctx_sec = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "SECONDARY COMPARTMENT"}
    assert resolve_measurement_audio_for_page(survey_root, all_meas, ctx_sec) is None

    # 5. Busbar compartment unmeasured on Panel 1 -> returns None (zero cross-chamber leakage!)
    ctx_busbar = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "BUSBAR COMPARTMENT"}
    assert resolve_measurement_audio_for_page(survey_root, all_meas, ctx_busbar) is None


def test_vcb_audio_attribution_tie_breaking(tmp_path: Path):
    """VCB policy prioritizes $UPPER_BUSBARS > $LOWER_BUSBARS, and picks highest dB for duplicates."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "VCB" / "PANEL_1"
    feeder_dir.mkdir(parents=True)

    # Busbar tie-breaking: lower busbar has 25 dB, upper busbar has 10 dB -> upper wins
    meas_bb_lower = _create_synthetic_meas(
        feeder_dir / "meas_bb_lower", "VCB_PANEL_1_LOWER_BUSBARS_US", "VCB", "PANEL_1", "$LOWER_BUSBARS", db_reading=25.0
    )
    meas_bb_upper = _create_synthetic_meas(
        feeder_dir / "meas_bb_upper", "VCB_PANEL_1_UPPER_BUSBARS_US", "VCB", "PANEL_1", "$UPPER_BUSBARS", db_reading=10.0
    )

    # Duplicate component tie-breaking: cb1 has 5 dB, cb2 has 19.5 dB -> cb2 wins
    meas_cb1 = _create_synthetic_meas(
        feeder_dir / "meas_cb1", "VCB_PANEL_1_CIRCUIT_BREAKER_US", "VCB", "PANEL_1", "$CIRCUIT_BREAKER", db_reading=5.0
    )
    meas_cb2 = _create_synthetic_meas(
        feeder_dir / "meas_cb2", "VCB_PANEL_1_CIRCUIT_BREAKER_US_2", "VCB", "PANEL_1", "$CIRCUIT_BREAKER", db_reading=19.5
    )

    all_meas = [meas_bb_lower, meas_bb_upper, meas_cb1, meas_cb2]

    # Test Busbar prioritization
    ctx_busbar = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "BUSBAR COMPARTMENT"}
    res_busbar = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_busbar)
    assert res_busbar == meas_bb_upper.meas_dir / "8k.wav"

    # Test Duplicate highest dB
    ctx_breaker = {"panel_no": 1, "panel_name": "INCOMER", "raw_panel_no": "1", "area": "BREAKER COMPARTMENT"}
    res_breaker = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_breaker)
    assert res_breaker == meas_cb2.meas_dir / "8k.wav"


def test_transformer_audio_attribution_shares_across_hv_side_pages(tmp_path: Path):
    """Transformer policy shares single TX recording across HV CABLE, HV BUSHING, and HV CABLE SPLIT."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    tx1_dir = survey_root / "TX1" / "Transformer"
    tx1_dir.mkdir(parents=True)

    meas_tx1 = _create_synthetic_meas(
        tx1_dir / "meas_tx", "TX1_TRANSFORMER_PRIMARY_CABLES_US", "TX1", "TRANSFORMER", "$PRIMARY_CABLES"
    )

    # All three scanning pages for TX1 resolve to the same audio file
    for area in ["HV CABLE", "HV BUSHING", "HV CABLE SPLIT"]:
        ctx = {"panel_no": None, "panel_name": "", "raw_panel_no": "", "area": area, "tx_idx": 1}
        res = resolve_measurement_audio_for_page(survey_root, [meas_tx1], ctx)
        assert res == meas_tx1.meas_dir / "8k.wav"

    # TX2 scanning page with only TX1 present returns None
    ctx_tx2 = {"panel_no": None, "panel_name": "", "raw_panel_no": "", "area": "HV CABLE", "tx_idx": 2}
    assert resolve_measurement_audio_for_page(survey_root, [meas_tx1], ctx_tx2) is None


def test_rmu_audio_attribution_untagged_and_board_level_fallback(tmp_path: Path):
    """RMU policy matches untagged measurements to cable compartment and uses board-level fallback."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()

    # Part A: Untagged recording under FEEDER_1
    feeder1_dir = survey_root / "RMU" / "FEEDER_1"
    feeder1_dir.mkdir(parents=True)
    meas_untagged = _create_synthetic_meas(
        feeder1_dir / "meas_rmu1", "RMU_FEEDER_1_US", "RMU", "FEEDER_1", component=None
    )

    ctx_feeder1 = {"panel_no": 1, "panel_name": "RING 1", "raw_panel_no": "1", "area": "CABLE COMPARTMENT"}
    res_f1 = resolve_measurement_audio_for_page(survey_root, [meas_untagged], ctx_feeder1)
    assert res_f1 == meas_untagged.meas_dir / "8k.wav"

    # Part B: Board-level acoustic fallback when feeder subfolders are absent
    survey_root_board = tmp_path / "US+TEV_BOARD"
    survey_root_board.mkdir()
    rmu_board_dir = survey_root_board / "RMU"
    rmu_board_dir.mkdir()
    meas_board = _create_synthetic_meas(
        rmu_board_dir / "meas_board", "RMU_US", "RMU", "", component=None
    )

    # Both FEEDER 1 and FEEDER 2 cable scanning pages fall back to board-level measurement
    for p_no in [1, 2]:
        ctx_cable = {"panel_no": p_no, "panel_name": f"WAY {p_no}", "raw_panel_no": str(p_no), "area": "CABLE COMPARTMENT"}
        res_board = resolve_measurement_audio_for_page(survey_root_board, [meas_board], ctx_cable)
        assert res_board == meas_board.meas_dir / "8k.wav"


def test_vcb_untagged_measurement_does_not_leak_to_cable_compartment(tmp_path: Path):
    """VCB policy strictly enforces 1-to-1 chamber isolation and does NOT match untagged measurements."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "VCB" / "PANEL_1"
    feeder_dir.mkdir(parents=True)

    meas_untagged = _create_synthetic_meas(
        feeder_dir / "meas_untagged", "VCB_PANEL_1_US", "VCB", "PANEL_1", component=None
    )

    ctx_cable = {"panel_no": 1, "panel_name": "INCOMER 1", "raw_panel_no": "1", "area": "CABLE COMPARTMENT"}
    # Untagged measurement on VCB does NOT match CABLE COMPARTMENT
    assert resolve_measurement_audio_for_page(survey_root, [meas_untagged], ctx_cable) is None


def test_switchgear_feeder_name_tx_does_not_trigger_transformer_attribution(tmp_path: Path):
    """Feeder named 'TX 1 INCOMER' on switchgear does not trigger transformer attribution."""
    text_blocks = [
        (60.0, 100.0, "Panel No. : 1"),
        (60.0, 120.0, "Panel Name : TX 1 INCOMER"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT"),
    ]
    doc = _create_synthetic_page(text_blocks)
    ctx = extract_page_equipment_context(doc[0])
    assert ctx["panel_no"] == 1
    assert ctx["panel_name"] == "TX 1 INCOMER"
    # tx_idx should be None because there is no 'Tx No.' marker on this switchgear page
    assert ctx["tx_idx"] is None


def test_mandatory_8k_wav_fail_loud_invariant(tmp_path: Path):

    """Resolver raises FileNotFoundError if 8k.wav is missing or empty (0 bytes)."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "VCB" / "PANEL_1"
    feeder_dir.mkdir(parents=True)

    # 1. Missing 8k.wav
    meas_missing = _create_synthetic_meas(
        feeder_dir / "meas_missing", "VCB_PANEL_1_CABLE_BOX_US", "VCB", "PANEL_1", "$CABLE_BOX", create_8k_wav=False
    )
    ctx = {"panel_no": 1, "panel_name": "", "raw_panel_no": "1", "area": "CABLE COMPARTMENT"}
    with pytest.raises(FileNotFoundError, match="Missing mandatory 8k.wav"):
        resolve_measurement_audio_for_page(survey_root, [meas_missing], ctx)

    # 2. Empty (0 bytes) 8k.wav
    meas_empty = _create_synthetic_meas(
        feeder_dir / "meas_empty", "VCB_PANEL_1_CIRCUIT_BREAKER_US", "VCB", "PANEL_1", "$CIRCUIT_BREAKER", wav_size=0
    )
    ctx_cb = {"panel_no": 1, "panel_name": "", "raw_panel_no": "1", "area": "BREAKER COMPARTMENT"}
    with pytest.raises(FileNotFoundError, match="Mandatory 8k.wav is empty"):
        resolve_measurement_audio_for_page(survey_root, [meas_empty], ctx_cb)

