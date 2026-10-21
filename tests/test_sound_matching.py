"""Unit tests for ultrasound measurement discovery, page inspection, and compartment matching.

Tests cover:
- Anchor detection centering speaker rectangle directly over visible icon image (or fallback cx = 210.30 pt).
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
import wave
try:
    import pymupdf as fitz
except ImportError:
    import fitz

from src.postprocessing.sound_embedder import (
    CHAMBER_COMPONENT_KEYWORDS,
    find_sound_clip_anchor,
    extract_page_equipment_context,
    resolve_measurement_audio_for_page,
    _normalize_tag,
    _extract_feeder_tokens,
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

def test_find_sound_clip_anchor_centers_speaker_rect_in_column_2_fallback():
    """Anchor detection locates 'Sound clip' and centers fallback rectangle in Column 2 (cx = 210.30)."""
    # Insert "Sound clip" at typical Row 31 position in Column 1 (x ~ 80, y ~ 650)
    doc = _create_synthetic_page([(80.0, 650.0, "Sound clip")])
    page = doc[0]

    rect = find_sound_clip_anchor(page)
    assert rect is not None
    assert isinstance(rect, fitz.Rect)

    # Asserts speaker annotation rectangle is strictly centered in Column 2 over cx = 210.30
    assert abs(rect.x0 - 201.30) < 1e-2
    assert abs(rect.x1 - 219.30) < 1e-2
    assert rect.width == 18.0
    assert rect.height == 18.0

    # Vertical alignment matches text instance center
    insts = page.search_for("Sound clip")
    assert len(insts) == 1
    inst = insts[0]
    expected_cy = (inst.y0 + inst.y1) / 2.0
    actual_cy = (rect.y0 + rect.y1) / 2.0
    assert abs(actual_cy - expected_cy) < 1e-2


def test_find_sound_clip_anchor_detects_visible_speaker_image_rect():
    """Anchor detection locates visible speaker image in Column 2 and centers hit box directly on top."""
    doc = fitz.open()
    page = doc.new_page(width=595.0, height=842.0)
    page.insert_text(fitz.Point(89.0, 605.0), "Sound clip", fontsize=10)

    # Insert a dummy image representing Word's embedded sound icon at [202.38, 596.58, 218.22, 612.36]
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16), 1)
    img_rect = fitz.Rect(202.38, 596.58, 218.22, 612.36)
    page.insert_image(img_rect, pixmap=pix)

    rect = find_sound_clip_anchor(page)
    assert rect is not None
    assert isinstance(rect, fitz.Rect)

    # Hit box is 18x18 pt centered directly over the image center (210.30, 604.47)
    cx = (img_rect.x0 + img_rect.x1) / 2.0
    cy = (img_rect.y0 + img_rect.y1) / 2.0
    assert abs(rect.x0 - (cx - 9.0)) < 1e-2
    assert abs(rect.x1 - (cx + 9.0)) < 1e-2
    assert abs(rect.y0 - (cy - 9.0)) < 1e-2
    assert abs(rect.y1 - (cy + 9.0)) < 1e-2
    assert rect.width == 18.0
    assert rect.height == 18.0


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


def test_extract_page_equipment_context_tier_2_substation_testsheet_package_data():
    """Tier 2 resolves SCADA code via SubstationTestsheetPackage possessing .data.equipment."""
    from src.testsheet.models import (
        SwitchgearPanelSpec,
        SubstationEquipmentPackage,
        SubstationTestsheetPackage,
        SwitchgearSpec,
        TestsheetData,
    )

    text_blocks = [
        (60.0, 100.0, "Panel No. : CKN05002"),
        (60.0, 120.0, "Panel Name : KLG JLN IM 16/2 NO 1"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT Area"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    pkg = SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("."),
        station="KUANTAN",
        month="01. AUGUST",
        date_str="11-08-2026",
        substation_number=56,
        data=TestsheetData(
            substation_number=56,
            substation_name_erms="CS KLG IM 16/2 NO 2",
            equipment=SubstationEquipmentPackage(
                switchgears=(
                    SwitchgearSpec(
                        panels=(
                            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN05002", name="KLG JLN IM 16/2 NO 1"),
                            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN05004", name="TX 1000KVA"),
                            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN05003", name="IM 14 RESIDENCE"),
                        )
                    ),
                )
            ),
        ),
    )

    ctx = extract_page_equipment_context(page, package=pkg)
    assert ctx["panel_no"] == 1
    assert ctx["raw_panel_no"] == "CKN05002"
    assert ctx["panel_name"] == "KLG JLN IM 16/2 NO 1"


def test_extract_page_equipment_context_tier_2_empty_raw_panel_matches_name():
    """Tier 2 matches panel catalog via panel_name when raw_panel_no is empty or dash."""
    from src.testsheet.models import (
        SwitchgearPanelSpec,
        SubstationEquipmentPackage,
        SwitchgearSpec,
        TestsheetData,
    )

    text_blocks = [
        (60.0, 100.0, "Panel No. : -"),
        (60.0, 120.0, "Panel Name : TX 1000KVA"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT"),
    ]
    doc = _create_synthetic_page(text_blocks)
    page = doc[0]

    tdata = TestsheetData(
        substation_number=56,
        substation_name_erms="TEST SUB",
        equipment=SubstationEquipmentPackage(
            switchgears=(
                SwitchgearSpec(
                    panels=(
                        SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN05002", name="FEEDER 1"),
                        SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN05004", name="TX 1000KVA"),
                    )
                ),
            )
        ),
    )

    ctx = extract_page_equipment_context(page, package=tdata)
    assert ctx["panel_no"] == 2
    assert ctx["panel_name"] == "TX 1000KVA"


def test_embed_survey_ultrasound_into_pdf_tier2_folder_name_matching_without_package(tmp_path: Path):
    """When package is None, Tier 2 matches survey folder names directly via panel_name or raw_panel_no."""
    from src.workflows.us_audio import embed_survey_ultrasound_into_pdf

    # Create synthetic survey directory with LINE_A and LINE_B
    survey_dir = tmp_path / "survey"
    survey_dir.mkdir()
    f1_dir = survey_dir / "SWG" / "LINE_A"
    f2_dir = survey_dir / "SWG" / "LINE_B"
    m1 = _create_synthetic_meas(f1_dir / "us1", "SWG_LINE_A_CABLE_BOX_US", "SWG", "LINE_A", "$CABLE_BOX")
    m2 = _create_synthetic_meas(f2_dir / "us2", "SWG_LINE_B_CABLE_BOX_US", "SWG", "LINE_B", "$CABLE_BOX")

    # Create survey_summary.js manifest
    manifest = {
        "assets": [
            {
                "$ASSET_NAME": "SWG",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "LINE_A",
                        "$MEASURES": [
                            {
                                "$MEASURE_TYPE": "$ULTRA",
                                "Data": "SWG/LINE_A/us1",
                                "$COMPONENT": "$CABLE_BOX",
                            }
                        ],
                    },
                    {
                        "$SUB_ASSET_NAME": "LINE_B",
                        "$MEASURES": [
                            {
                                "$MEASURE_TYPE": "$ULTRA",
                                "Data": "SWG/LINE_B/us2",
                                "$COMPONENT": "$CABLE_BOX",
                            }
                        ],
                    },
                ],
            }
        ]
    }
    import json
    (survey_dir / "survey_summary.js").write_text(
        f"var survey_summary = {json.dumps(manifest)};\n", encoding="utf-8"
    )

    # Overwrite dummy 8k.wav with valid 24-bit RIFF WAV so wave.open succeeds
    for m in (m1, m2):
        wav_p = m.meas_dir / "8k.wav"
        with wave.open(str(wav_p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(8000)
            wf.setcomptype("NONE", "not compressed")
            wf.writeframes(b"\x00\x00\x00" * 80)

    # Create 2-page PDF deliverable with unnumbered utility codes (CKN05002, CKN05004) and panel names
    doc = fitz.open()
    # Page 1: Panel 1
    p1 = doc.new_page(width=595.0, height=842.0)
    p1.insert_text(fitz.Point(60.0, 100.0), "Panel No. : CKN05002", fontsize=10)
    p1.insert_text(fitz.Point(60.0, 120.0), "Panel Name : LINE A", fontsize=10)
    p1.insert_text(fitz.Point(60.0, 140.0), "Area : CABLE COMPARTMENT", fontsize=10)
    p1.insert_text(fitz.Point(80.0, 650.0), "Sound clip", fontsize=10)

    # Page 2: Panel 2
    p2 = doc.new_page(width=595.0, height=842.0)
    p2.insert_text(fitz.Point(60.0, 100.0), "Panel No. : CKN05004", fontsize=10)
    p2.insert_text(fitz.Point(60.0, 120.0), "Panel Name : LINE B", fontsize=10)
    p2.insert_text(fitz.Point(60.0, 140.0), "Area : CABLE COMPARTMENT", fontsize=10)
    p2.insert_text(fitz.Point(80.0, 650.0), "Sound clip", fontsize=10)

    target_pdf = tmp_path / "report.pdf"
    doc.save(str(target_pdf))
    doc.close()

    # Embed with package=None
    count = embed_survey_ultrasound_into_pdf(target_pdf, survey_root=survey_dir, package=None)
    assert count == 2

    # Verify both pages have sound annotations
    reloaded = fitz.open(str(target_pdf))
    assert len(list(reloaded[0].annots())) == 1
    assert len(list(reloaded[1].annots())) == 1
    reloaded.close()


# ==============================================================================
# Seam 2 additions: Equipment Type, Model, and Manufacturer Context Extraction
# ==============================================================================

def test_extract_page_equipment_context_extracts_type_model_manufacturer_text():
    """Context extraction captures switchgear_type, model, and manufacturer from page text."""
    # Test colon-delimited format
    doc1 = _create_synthetic_page([
        (60.0, 80.0, "Equipment : RMU SF6"),
        (60.0, 100.0, "Manufacturer : INDKOM"),
        (60.0, 120.0, "Model : INS24"),
        (60.0, 140.0, "Panel No. : CKN03129"),
        (60.0, 160.0, "Panel Name : TX"),
        (60.0, 180.0, "Area : FUSE COMPARTMENT"),
    ])
    ctx1 = extract_page_equipment_context(doc1[0])
    assert ctx1["switchgear_type"] == "RMU SF6"
    assert ctx1["manufacturer"] == "INDKOM"
    assert ctx1["model"] == "INS24"
    assert ctx1["raw_panel_no"] == "CKN03129"
    assert ctx1["panel_name"] == "TX"
    assert ctx1["area"] == "FUSE COMPARTMENT"

    # Test newline-delimited format (common in Word table conversions)
    doc2 = _create_synthetic_page([
        (60.0, 80.0, "Equipment\nRMU SF6"),
        (60.0, 100.0, "Manufacturer\nINDKOM"),
        (60.0, 120.0, "Model\nINS24"),
        (60.0, 140.0, "Area\nFUSE COMPARTMENT"),
    ])
    ctx2 = extract_page_equipment_context(doc2[0])
    assert ctx2["switchgear_type"] == "RMU SF6"
    assert ctx2["manufacturer"] == "INDKOM"
    assert ctx2["model"] == "INS24"
    assert ctx2["area"] == "FUSE COMPARTMENT"


def test_extract_page_equipment_context_type_model_manufacturer_package_fallback():
    """Context extraction falls back to package metadata when absent in page text."""
    from src.testsheet.models import (
        SwitchgearPanelSpec,
        SubstationEquipmentPackage,
        SwitchgearSpec,
        TestsheetData,
    )
    doc = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : CKN03129"),
        (60.0, 120.0, "Panel Name : TX"),
        (60.0, 140.0, "Area : FUSE COMPARTMENT"),
    ])
    tdata = TestsheetData(
        substation_number=70,
        substation_name_erms="PUSAT KEBUDAYAAN CINA",
        equipment=SubstationEquipmentPackage(
            switchgears=(
                SwitchgearSpec(
                    switchgear_type="RMU SF6",
                    manufacturer="INDKOM",
                    model="INS24",
                    panels=(
                        SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN03130", name="FLAT POLIS"),
                        SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN03128", name="CAPITAL SQUARE"),
                        SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN03129", name="TX"),
                    ),
                ),
            )
        ),
    )
    ctx = extract_page_equipment_context(doc[0], package=tdata)
    assert ctx["panel_no"] == 3
    assert ctx["switchgear_type"] == "RMU SF6"
    assert ctx["manufacturer"] == "INDKOM"
    assert ctx["model"] == "INS24"


# ==============================================================================
# Seam 3 additions: INDKOM INS24 FUSE COMPARTMENT Ultrasound Resolution
# ==============================================================================

def test_indkom_ins24_fuse_compartment_resolves_cable_box_measurement(tmp_path: Path):
    """INDKOM INS24 TX panel with area='FUSE COMPARTMENT' resolves raw US measurement tagged as $CABLE_BOX."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "SWG" / "FEEDER_3"
    feeder_dir.mkdir(parents=True)

    meas_cable_box = _create_synthetic_meas(
        feeder_dir / "meas_us",
        label="SWG_FEEDER_3_CABLE_BOX_US",
        asset="SWG",
        subasset="FEEDER 3",
        component="$CABLE_BOX",
    )

    ctx = {
        "panel_no": 3,
        "panel_name": "TX",
        "raw_panel_no": "CKN03129",
        "area": "FUSE COMPARTMENT",
        "model": "INS24",
        "switchgear_type": "RMU SF6",
        "manufacturer": "INDKOM",
    }

    resolved = resolve_measurement_audio_for_page(survey_root, [meas_cable_box], ctx)
    assert resolved == meas_cable_box.meas_dir / "8k.wav"


def test_indkom_ins24_fuse_compartment_resolves_fuse_measurement(tmp_path: Path):
    """INDKOM INS24 TX panel with area='FUSE COMPARTMENT' resolves raw US measurement tagged as $FUSE."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "SWG" / "FEEDER_3"
    feeder_dir.mkdir(parents=True)

    meas_fuse = _create_synthetic_meas(
        feeder_dir / "meas_us_fuse",
        label="SWG_FEEDER_3_FUSE_US",
        asset="SWG",
        subasset="FEEDER 3",
        component="$FUSE",
    )

    ctx = {
        "panel_no": 3,
        "panel_name": "TX",
        "raw_panel_no": "CKN03129",
        "area": "FUSE COMPARTMENT",
        "model": "INS24",
        "switchgear_type": "RMU SF6",
        "manufacturer": "INDKOM",
    }

    resolved = resolve_measurement_audio_for_page(survey_root, [meas_fuse], ctx)
    assert resolved == meas_fuse.meas_dir / "8k.wav"


def test_indkom_ins24_fuse_compartment_prioritizes_fuse_over_cable_box(tmp_path: Path):
    """When both $FUSE and $CABLE_BOX measurements exist, FUSE COMPARTMENT prioritizes $FUSE."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    feeder_dir = survey_root / "SWG" / "FEEDER_3"
    feeder_dir.mkdir(parents=True)

    meas_cable = _create_synthetic_meas(
        feeder_dir / "meas_cable",
        label="SWG_FEEDER_3_CABLE_BOX_US",
        asset="SWG",
        subasset="FEEDER 3",
        component="$CABLE_BOX",
        db_reading=25.0,  # Higher dB
    )
    meas_fuse = _create_synthetic_meas(
        feeder_dir / "meas_fuse",
        label="SWG_FEEDER_3_FUSE_US",
        asset="SWG",
        subasset="FEEDER 3",
        component="$FUSE",
        db_reading=15.0,  # Lower dB, but exact chamber match
    )

    ctx = {
        "panel_no": 3,
        "panel_name": "TX",
        "raw_panel_no": "CKN03129",
        "area": "FUSE COMPARTMENT",
        "model": "INS24",
        "switchgear_type": "RMU SF6",
    }

    resolved = resolve_measurement_audio_for_page(survey_root, [meas_cable, meas_fuse], ctx)
    assert resolved == meas_fuse.meas_dir / "8k.wav"


def test_rmu_audio_attribution_fuse_compartment_untagged_and_board_level(tmp_path: Path):
    """RMU feeder scanning recognizes FUSE COMPARTMENT for untagged feeder and board-level fallback."""
    # Part A: Untagged recording under FEEDER_3
    survey_root = tmp_path / "US+TEV_UNTAGGED"
    survey_root.mkdir()
    feeder3_dir = survey_root / "RMU" / "FEEDER_3"
    feeder3_dir.mkdir(parents=True)
    meas_untagged = _create_synthetic_meas(
        feeder3_dir / "meas_rmu3", "RMU_FEEDER_3_US", "RMU", "FEEDER_3", component=None
    )

    ctx_f3 = {
        "panel_no": 3,
        "panel_name": "TX",
        "raw_panel_no": "3",
        "area": "FUSE COMPARTMENT",
        "model": "INS24",
    }
    res_f3 = resolve_measurement_audio_for_page(survey_root, [meas_untagged], ctx_f3)
    assert res_f3 == meas_untagged.meas_dir / "8k.wav"

    # Part B: Board-level acoustic fallback for FUSE COMPARTMENT
    survey_root_board = tmp_path / "US+TEV_BOARD"
    survey_root_board.mkdir()
    rmu_board_dir = survey_root_board / "RMU"
    rmu_board_dir.mkdir()
    meas_board = _create_synthetic_meas(
        rmu_board_dir / "meas_board", "RMU_US", "RMU", "", component=None
    )

    res_board = resolve_measurement_audio_for_page(survey_root_board, [meas_board], ctx_f3)
    assert res_board == meas_board.meas_dir / "8k.wav"


# ==============================================================================
# Ticket #109: FRONT & REAR Compartment Keywords Resolution
# ==============================================================================

def test_chamber_component_keywords_front_and_rear_mappings():
    """Verify CHAMBER_COMPONENT_KEYWORDS contains FRONT and REAR mapped correctly."""
    assert "FRONT" in CHAMBER_COMPONENT_KEYWORDS
    assert CHAMBER_COMPONENT_KEYWORDS["FRONT"] == ("CIRCUIT_BREAKER", "BREAKER", "CB")
    assert "REAR" in CHAMBER_COMPONENT_KEYWORDS
    assert CHAMBER_COMPONENT_KEYWORDS["REAR"] == ("CABLE_BOX", "CABLES", "CABLE")
    # Verify existing mappings remain intact
    assert CHAMBER_COMPONENT_KEYWORDS["BUSBAR"] == ("BUSBAR", "UPPER_BUSBARS", "LOWER_BUSBARS")
    assert CHAMBER_COMPONENT_KEYWORDS["BREAKER"] == ("CIRCUIT_BREAKER", "BREAKER")
    assert CHAMBER_COMPONENT_KEYWORDS["CABLE"] == ("CABLE_BOX", "CABLES", "CABLE")
    assert CHAMBER_COMPONENT_KEYWORDS["PT"] == ("VT_CHAMBER", "VOLTAGE_TRANSFORMER", "VT", "PT")
    assert CHAMBER_COMPONENT_KEYWORDS["VT"] == ("VT_CHAMBER", "VOLTAGE_TRANSFORMER", "VT", "PT")
    assert CHAMBER_COMPONENT_KEYWORDS["FUSE"] == ("FUSE", "CABLE_BOX", "CABLES", "CABLE")


def test_resolve_measurement_audio_front_compartment_resolves_circuit_breaker(tmp_path: Path):
    """Transition or B/S panel with area='FRONT COMPARTMENT' resolves $CIRCUIT_BREAKER audio."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    panel_dir = survey_root / "VCB" / "PANEL_4"
    panel_dir.mkdir(parents=True)

    meas_cb = _create_synthetic_meas(
        panel_dir / "meas_cb",
        label="VCB_PANEL_4_CIRCUIT_BREAKER_US",
        asset="VCB",
        subasset="PANEL 4",
        component="$CIRCUIT_BREAKER",
    )
    meas_cable = _create_synthetic_meas(
        panel_dir / "meas_cable",
        label="VCB_PANEL_4_CABLE_BOX_US",
        asset="VCB",
        subasset="PANEL 4",
        component="$CABLE_BOX",
    )

    ctx = {
        "panel_no": 4,
        "panel_name": "BUS SECTION",
        "raw_panel_no": "4",
        "area": "FRONT COMPARTMENT",
    }

    resolved = resolve_measurement_audio_for_page(survey_root, [meas_cb, meas_cable], ctx)
    assert resolved == meas_cb.meas_dir / "8k.wav"


def test_resolve_measurement_audio_rear_compartment_resolves_cable_box(tmp_path: Path):
    """Transition or B/S panel with area='REAR COMPARTMENT' resolves $CABLE_BOX audio."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    panel_dir = survey_root / "VCB" / "PANEL_4"
    panel_dir.mkdir(parents=True)

    meas_cb = _create_synthetic_meas(
        panel_dir / "meas_cb",
        label="VCB_PANEL_4_CIRCUIT_BREAKER_US",
        asset="VCB",
        subasset="PANEL 4",
        component="$CIRCUIT_BREAKER",
    )
    meas_cable = _create_synthetic_meas(
        panel_dir / "meas_cable",
        label="VCB_PANEL_4_CABLE_BOX_US",
        asset="VCB",
        subasset="PANEL 4",
        component="$CABLE_BOX",
    )

    ctx = {
        "panel_no": 4,
        "panel_name": "BUS SECTION",
        "raw_panel_no": "4",
        "area": "REAR COMPARTMENT",
    }

    resolved = resolve_measurement_audio_for_page(survey_root, [meas_cb, meas_cable], ctx)
    assert resolved == meas_cable.meas_dir / "8k.wav"


def test_resolve_measurement_audio_front_and_rear_zero_leakage_and_variants(tmp_path: Path):
    """Zero leakage for unmeasured compartments, and support for CB / CABLES variants."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()
    panel_dir = survey_root / "VCB" / "PANEL_5"
    panel_dir.mkdir(parents=True)

    meas_cb_variant = _create_synthetic_meas(
        panel_dir / "meas_cb_short",
        label="VCB_PANEL_5_CB_US",
        asset="VCB",
        subasset="PANEL 5",
        component="$CB",
    )
    meas_cable_variant = _create_synthetic_meas(
        panel_dir / "meas_cables",
        label="VCB_PANEL_5_CABLES_US",
        asset="VCB",
        subasset="PANEL 5",
        component="$CABLES",
    )

    # FRONT resolves $CB
    ctx_front = {"panel_no": 5, "panel_name": "TRANSITION", "raw_panel_no": "5", "area": "FRONT COMPARTMENT"}
    assert resolve_measurement_audio_for_page(survey_root, [meas_cb_variant], ctx_front) == meas_cb_variant.meas_dir / "8k.wav"

    # REAR resolves $CABLES
    ctx_rear = {"panel_no": 5, "panel_name": "TRANSITION", "raw_panel_no": "5", "area": "REAR COMPARTMENT"}
    assert resolve_measurement_audio_for_page(survey_root, [meas_cable_variant], ctx_rear) == meas_cable_variant.meas_dir / "8k.wav"

    # Zero cross-chamber leakage: FRONT does not match CABLE, REAR does not match CB
    assert resolve_measurement_audio_for_page(survey_root, [meas_cable_variant], ctx_front) is None
    assert resolve_measurement_audio_for_page(survey_root, [meas_cb_variant], ctx_rear) is None


# ==============================================================================
# Seam 5: Catalog-First Feeder Tag Normalization & Bus Section Audio Resolution (#110)
# ==============================================================================

def test_feeder_normalization_embedded_newlines_and_whitespace():
    """Whitespace in feeder tags is normalized to single spaces during catalog lookup."""
    # Unit level assertion on normalization helper
    assert _normalize_tag("30A\n(CKN00053)") == "30A (CKN00053)"
    assert _normalize_tag("30B\r\n(CKN70058)") == "30B (CKN70058)"
    assert _normalize_tag("  30C \t \n (CKN70063)  ") == "30C (CKN70063)"
    assert _normalize_tag("BUS  SECTION\n \tA") == "BUS SECTION A"

    # Verify matching across rendered PDF text and testsheet catalog with embedded newlines
    doc = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : 30A (CKN00053)"),
        (60.0, 120.0, "Panel Name : BUS SECTION A"),
        (60.0, 140.0, "Area : BREAKER COMPARTMENT"),
    ])
    page = doc[0]

    mock_pkg = MockPackage(
        equipment=MockEquipment(
            switchgears=[
                MockSwitchgear(
                    panels=[
                        MockPanel(panel_no=5, panel_feeder_no="30A\n(CKN00053)", name="BUS SECTION A"),
                    ]
                )
            ]
        )
    )

    ctx = extract_page_equipment_context(page, package=mock_pkg)
    assert ctx["panel_no"] == 5
    assert ctx["raw_panel_no"] == "30A (CKN00053)"
    assert ctx["panel_name"] == "BUS SECTION A"


def test_catalog_first_matching_prevents_raw_regex_hijacking():
    """Catalog feeder tag matching runs prior to fallback regex, preventing digits from hijacking panel_no."""
    # Feeder 15 on Panel 8 in a switchgear where Panel 15 also exists
    doc = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : 15"),
        (60.0, 120.0, "Panel Name : FEEDER 15"),
        (60.0, 140.0, "Area : CABLE COMPARTMENT"),
    ])
    page = doc[0]

    mock_pkg = MockPackage(
        equipment=MockEquipment(
            switchgears=[
                MockSwitchgear(
                    panels=[
                        MockPanel(panel_no=8, panel_feeder_no="15", name="FEEDER 15"),
                        MockPanel(panel_no=15, panel_feeder_no="CRB70015", name="INCOMER 2"),
                    ]
                )
            ]
        )
    )

    ctx = extract_page_equipment_context(page, package=mock_pkg)
    assert ctx["panel_no"] == 8  # Resolved to catalog panel 8, NOT hijacked to panel 15!


def test_alphanumeric_feeder_codes_do_not_hijack_panel_index_without_package():
    """Alphanumeric codes (30A, 30B, 30C, 15A) do not match naive digit regex when package is None."""
    # 30A (CKN00053) without package must NOT match 30
    doc_bs_a = _create_synthetic_page([(60.0, 100.0, "Panel No. : 30A (CKN00053)")])
    ctx_bs_a = extract_page_equipment_context(doc_bs_a[0], package=None)
    assert ctx_bs_a["panel_no"] is None

    # Bare 30A without package must NOT match 30
    doc_30a = _create_synthetic_page([(60.0, 100.0, "Panel No. : 30A")])
    ctx_30a = extract_page_equipment_context(doc_30a[0], package=None)
    assert ctx_30a["panel_no"] is None

    # Panel 30A without package must NOT match 30
    doc_p30a = _create_synthetic_page([(60.0, 100.0, "Panel No. : Panel 30A")])
    ctx_p30a = extract_page_equipment_context(doc_p30a[0], package=None)
    assert ctx_p30a["panel_no"] is None

    # 15A without package must NOT match 15
    doc_15a = _create_synthetic_page([(60.0, 100.0, "Panel No. : 15A")])
    ctx_15a = extract_page_equipment_context(doc_15a[0], package=None)
    assert ctx_15a["panel_no"] is None

    # Valid bare digits and 'Panel N' must still match as expected
    doc_valid = _create_synthetic_page([(60.0, 100.0, "Panel No. : 15")])
    assert extract_page_equipment_context(doc_valid[0], package=None)["panel_no"] == 15

    doc_panel_word = _create_synthetic_page([(60.0, 100.0, "Panel No. : Panel 7")])
    assert extract_page_equipment_context(doc_panel_word[0], package=None)["panel_no"] == 7


def test_bus_section_feeder_token_matching_erms_and_code():
    """Token matching resolves ERMS link number or alphanumeric feeder code against catalog feeder tag."""
    mock_pkg = MockPackage(
        equipment=MockEquipment(
            switchgears=[
                MockSwitchgear(
                    panels=[
                        MockPanel(panel_no=5, panel_feeder_no="30A (CKN00053)", name="B/S A"),
                    ]
                )
            ]
        )
    )

    # 1. Matching via feeder code token "30A"
    doc_code = _create_synthetic_page([(60.0, 100.0, "Panel No. : 30A")])
    assert extract_page_equipment_context(doc_code[0], package=mock_pkg)["panel_no"] == 5

    # 2. Matching via ERMS link number token "CKN00053"
    doc_erms = _create_synthetic_page([(60.0, 100.0, "Panel No. : CKN00053")])
    assert extract_page_equipment_context(doc_erms[0], package=mock_pkg)["panel_no"] == 5

    # 3. Catalog with concise feeder code matches page with full ERMS tag
    mock_pkg_concise = MockPackage(
        equipment=MockEquipment(
            switchgears=[
                MockSwitchgear(
                    panels=[
                        MockPanel(panel_no=5, panel_feeder_no="30A", name="B/S A"),
                    ]
                )
            ]
        )
    )
    doc_full = _create_synthetic_page([(60.0, 100.0, "Panel No. : 30A (CKN00053)")])
    assert extract_page_equipment_context(doc_full[0], package=mock_pkg_concise)["panel_no"] == 5


def test_bus_section_audio_resolution_panels_5_11_17(tmp_path: Path):
    """Deliverable PDF pages for 30A, 30B, and 30C correctly resolve to PANEL_5, PANEL_11, and PANEL_17 survey audio."""
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir()

    # Create 22-panel switchgear layout with B/S A (Panel 5), B/S B (Panel 11), B/S C (Panel 17)
    panels = []
    for i in range(1, 23):
        if i == 5:
            panels.append(MockPanel(panel_no=5, panel_feeder_no="30A\n(CKN00053)", name="B/S A"))
        elif i == 11:
            panels.append(MockPanel(panel_no=11, panel_feeder_no="30B\n(CKN70058)", name="B/S B"))
        elif i == 17:
            panels.append(MockPanel(panel_no=17, panel_feeder_no="30C\n(CKN70063)", name="B/S C"))
        else:
            panels.append(MockPanel(panel_no=i, panel_feeder_no=f"CRB{70000+i}", name=f"FEEDER {i}"))

    mock_pkg = MockPackage(equipment=MockEquipment(switchgears=[MockSwitchgear(panels=panels)]))

    # Create synthetic survey recordings for Bus Section panels
    feeder_dir_5 = survey_root / "VCB" / "PANEL_5"
    feeder_dir_11 = survey_root / "VCB" / "PANEL_11"
    feeder_dir_17 = survey_root / "VCB" / "PANEL_17"
    for d in (feeder_dir_5, feeder_dir_11, feeder_dir_17):
        d.mkdir(parents=True)

    meas_bs_a = _create_synthetic_meas(
        feeder_dir_5 / "meas_a",
        label="VCB_PANEL_5_CIRCUIT_BREAKER_US",
        asset="VCB",
        subasset="PANEL_5",
        component="$CIRCUIT_BREAKER",
    )
    meas_bs_b = _create_synthetic_meas(
        feeder_dir_11 / "meas_b",
        label="VCB_PANEL_11_CIRCUIT_BREAKER_US",
        asset="VCB",
        subasset="PANEL_11",
        component="$CIRCUIT_BREAKER",
    )
    meas_bs_c = _create_synthetic_meas(
        feeder_dir_17 / "meas_c",
        label="VCB_PANEL_17_CIRCUIT_BREAKER_US",
        asset="VCB",
        subasset="PANEL_17",
        component="$CIRCUIT_BREAKER",
    )
    all_meas = [meas_bs_a, meas_bs_b, meas_bs_c]

    # Rendered PDF Page A: 30A (CKN00053)
    doc_a = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : 30A (CKN00053)"),
        (60.0, 120.0, "Panel Name : BUS SECTION A"),
        (60.0, 140.0, "Area : BREAKER COMPARTMENT"),
        (60.0, 650.0, "Sound clip"),
    ])
    ctx_a = extract_page_equipment_context(doc_a[0], package=mock_pkg)
    assert ctx_a["panel_no"] == 5
    resolved_a = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_a)
    assert resolved_a == meas_bs_a.meas_dir / "8k.wav"

    # Rendered PDF Page B: 30B (CKN70058)
    doc_b = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : 30B (CKN70058)"),
        (60.0, 120.0, "Panel Name : BUS SECTION B"),
        (60.0, 140.0, "Area : BREAKER COMPARTMENT"),
        (60.0, 650.0, "Sound clip"),
    ])
    ctx_b = extract_page_equipment_context(doc_b[0], package=mock_pkg)
    assert ctx_b["panel_no"] == 11
    resolved_b = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_b)
    assert resolved_b == meas_bs_b.meas_dir / "8k.wav"

    # Rendered PDF Page C: 30C (CKN70063)
    doc_c = _create_synthetic_page([
        (60.0, 100.0, "Panel No. : 30C (CKN70063)"),
        (60.0, 120.0, "Panel Name : BUS SECTION C"),
        (60.0, 140.0, "Area : BREAKER COMPARTMENT"),
        (60.0, 650.0, "Sound clip"),
    ])
    ctx_c = extract_page_equipment_context(doc_c[0], package=mock_pkg)
    assert ctx_c["panel_no"] == 17
    resolved_c = resolve_measurement_audio_for_page(survey_root, all_meas, ctx_c)
    assert resolved_c == meas_bs_c.meas_dir / "8k.wav"





