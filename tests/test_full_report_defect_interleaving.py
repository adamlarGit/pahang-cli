"""Unit tests for Defect Interleaving Rules (Ticket #32 / T5.1).

Tests polymorphic defect interleaving rules per D34, D35, D36, D38:
- SWG IR defect replacement (D34)
- SWG TEV defect append (D34)
- Transformer component insertion (D35)
- Feeder Pillar channel sequencing (D36)
- Orphan defect safe append (D38)
- Benchmark scenarios: Talapia, Cenderawasih No.1, Telekom Tanah Putih
"""

from __future__ import annotations

from pathlib import Path
import pytest

from src.full_report.interleaving import (
    DefectInterleavingPolicy,
    InterleavingAction,
    InterleavingActionType,
    InterleavingResult,
    InterleavedPart,
)
from src.full_report.defect_parser import CbmDefectSliceMetadata
from src.full_report.scan_adapters import ScanRenderItem
from src.quick_report.defects import CbmDefectRecord


def _make_mock_swg_items() -> list[ScanRenderItem]:
    """Helper creating 4-panel INDKOM switchgear scan items (Cenderawasih topology)."""
    items = [
        ScanRenderItem(
            page_name="swg_overview",
            template_name="swg-overview.docx",
            equipment_category="swg",
            component_name="OVERVIEW",
            sequence="p00",
            is_overview=True,
            equipment_id="swg1",
        ),
        ScanRenderItem(
            page_name="swg_panel_1",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p01",
            equipment_id="swg1",
            panel_no=1,
            context={"panel": {"feeder_no": "CKN01308", "name": "SPARE"}},
        ),
        ScanRenderItem(
            page_name="swg_panel_2",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p02",
            equipment_id="swg1",
            panel_no=2,
            context={"panel": {"feeder_no": "CKN01310", "name": "TMN CENDRAWASIH 3"}},
        ),
        ScanRenderItem(
            page_name="swg_panel_3",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p03",
            equipment_id="swg1",
            panel_no=3,
            context={"panel": {"feeder_no": "CKN01311", "name": "TAJ 33A LOT 11520"}},
        ),
        ScanRenderItem(
            page_name="swg_panel_4",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="FUSE COMPARTMENT",
            sequence="p04",
            equipment_id="swg1",
            panel_no=4,
            context={"panel": {"feeder_no": "CKN01309", "name": "PANEL CKN01309 TX"}},
        ),
    ]
    return items


def test_swg_ir_defect_replaces_panel_page_d34() -> None:
    """Per D34: Standard SWG IR defects directly replace the swg-panel.docx page."""
    scan_items = _make_mock_swg_items()

    defect_meta = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p04",
        equipment_id="CKN01309",
        defect_area="FUSE_COMPARTMENT",
        filename="swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx",
        technology="IR",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=[defect_meta])

    assert isinstance(result, InterleavingResult)
    assert len(result.parts) == 5

    # Overview and Panels 1-3 are original scan pages
    assert result.parts[0].sequence == "p00"
    assert result.parts[0].is_defect is False
    assert result.parts[1].sequence == "p01"
    assert result.parts[1].is_defect is False
    assert result.parts[2].sequence == "p02"
    assert result.parts[2].is_defect is False
    assert result.parts[3].sequence == "p03"
    assert result.parts[3].is_defect is False

    # Panel 4 is replaced by the IR defect page
    p4_part = result.parts[4]
    assert p4_part.sequence == "p04"
    assert p4_part.is_defect is True
    assert p4_part.action_type == InterleavingActionType.REPLACE
    assert p4_part.part_name == "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"

    # Replaced items should contain original panel 4
    assert len(result.replaced_items) == 1
    assert result.replaced_items[0].sequence == "p04"
    assert result.replaced_items[0].panel_no == 4

    # Actions recorded
    assert len(result.actions) == 1
    assert isinstance(result.actions[0], InterleavingAction)
    assert result.actions[0].action_type == InterleavingActionType.REPLACE
    assert result.actions[0].target_sequence == "p04"


def test_swg_tev_defect_appends_after_panel_page_d34() -> None:
    """Per D34: High TEV / PRPD defects retain swg-panel.docx and append the detail page immediately after."""
    scan_items = _make_mock_swg_items()

    # 4 TEV defect metadata items for panels 1 through 4 (Telekom Tanah Putih scenario)
    tev_defects = [
        CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg1",
            sequence=f"p{i:02d}",
            equipment_id=f"F{i}",
            defect_area="CABLE_COMPARTMENT" if i != 4 else "FUSE_COMPARTMENT",
            filename=f"swg1_p{i:02d}_F{i}_TEV_01.docx",
            technology="TEV",
        )
        for i in range(1, 5)
    ]

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=tev_defects)

    assert isinstance(result, InterleavingResult)
    # 1 overview + 4 * (1 panel + 1 defect) = 9 parts
    assert len(result.parts) == 9

    # Zero items were replaced
    assert len(result.replaced_items) == 0

    # Verify interleaved structure:
    # 0: Overview
    assert result.parts[0].sequence == "p00"
    assert result.parts[0].is_defect is False

    # 1: Panel 1 scan page (retained!)
    assert result.parts[1].sequence == "p01"
    assert result.parts[1].is_defect is False
    # 2: Panel 1 TEV defect (appended!)
    assert result.parts[2].sequence == "p01"
    assert result.parts[2].is_defect is True
    assert result.parts[2].action_type == InterleavingActionType.APPEND_AFTER
    assert result.parts[2].part_name == "swg1_p01_F1_TEV_01.docx"

    # 3: Panel 2 scan page (retained!)
    assert result.parts[3].sequence == "p02"
    assert result.parts[3].is_defect is False
    # 4: Panel 2 TEV defect (appended!)
    assert result.parts[4].sequence == "p02"
    assert result.parts[4].is_defect is True
    assert result.parts[4].action_type == InterleavingActionType.APPEND_AFTER

    # 5: Panel 3 scan page
    assert result.parts[5].sequence == "p03"
    assert result.parts[5].is_defect is False
    # 6: Panel 3 TEV defect
    assert result.parts[6].sequence == "p03"
    assert result.parts[6].is_defect is True

    # 7: Panel 4 scan page
    assert result.parts[7].sequence == "p04"
    assert result.parts[7].is_defect is False
    # 8: Panel 4 TEV defect
    assert result.parts[8].sequence == "p04"
    assert result.parts[8].is_defect is True

    # 4 actions, all APPEND_AFTER
    assert len(result.actions) == 4
    for a in result.actions:
        assert a.action_type == InterleavingActionType.APPEND_AFTER


def _make_mock_tx_items(tx_id: str = "Tx 1") -> list[ScanRenderItem]:
    """Helper creating 7 standard transformer scan items per D31 / ADR 0004."""
    components = (
        ("s00", "OVERVIEW", "tx-overview.docx", True),
        ("s01", "OVERVIEW TOP", "tx-overview.docx", False),
        ("s02", "HV BUSHING", "tx-hv-sides.docx", False),
        ("s03", "HV CABLE", "tx-hv-sides.docx", False),
        ("s04", "HV CABLE SPLIT", "tx-hv-sides.docx", False),
        ("s05", "LV BUSHING", "tx-lv-sides.docx", False),
        ("s06", "LV CABLE", "tx-lv-sides.docx", False),
    )
    items = [
        ScanRenderItem(
            page_name=f"{tx_id.lower().replace(' ', '_')}_{comp.lower().replace(' ', '_')}",
            template_name=tpl,
            equipment_category="tx",
            component_name=comp,
            sequence=seq,
            is_overview=is_ov,
            equipment_id=tx_id,
        )
        for seq, comp, tpl, is_ov in components
    ]
    return items


def test_transformer_defect_inserted_behind_specific_component_d35() -> None:
    """Per D35: Transformer defect pages are inserted immediately behind the specific component scan page."""
    scan_items = _make_mock_tx_items("Tx 1")

    # Defect on HV Bushing (s02)
    tx_defect = CbmDefectSliceMetadata(
        equipment_category="tx",
        equipment_instance="tx1",
        sequence="s02",
        equipment_id="TX1",
        defect_area="HV_BUSHING",
        filename="tx1_s02_TX1_HV_BUSHING_01.docx",
        technology="IR",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=[tx_defect])

    assert isinstance(result, InterleavingResult)
    # 7 baseline components + 1 defect = 8 parts
    assert len(result.parts) == 8
    assert len(result.replaced_items) == 0

    # Parts order:
    # 0: OVERVIEW (s00)
    assert result.parts[0].component_name == "OVERVIEW"
    assert result.parts[0].is_defect is False

    # 1: OVERVIEW TOP (s01)
    assert result.parts[1].component_name == "OVERVIEW TOP"
    assert result.parts[1].is_defect is False

    # 2: HV BUSHING scan page (s02) (retained!)
    assert result.parts[2].component_name == "HV BUSHING"
    assert result.parts[2].is_defect is False

    # 3: HV BUSHING defect page (s02) (inserted behind!)
    assert result.parts[3].component_name == "HV BUSHING"
    assert result.parts[3].is_defect is True
    assert result.parts[3].action_type == InterleavingActionType.INSERT_BEHIND
    assert result.parts[3].part_name == "tx1_s02_TX1_HV_BUSHING_01.docx"

    # 4: HV CABLE scan page (s03)
    assert result.parts[4].component_name == "HV CABLE"
    assert result.parts[4].is_defect is False

    # 5: HV CABLE SPLIT (s04)
    assert result.parts[5].component_name == "HV CABLE SPLIT"
    assert result.parts[5].is_defect is False

    # 6: LV BUSHING (s05)
    assert result.parts[6].component_name == "LV BUSHING"
    assert result.parts[6].is_defect is False

    # 7: LV CABLE (s06)
    assert result.parts[7].component_name == "LV CABLE"
    assert result.parts[7].is_defect is False

    # Action verification
    assert len(result.actions) == 1
    assert result.actions[0].action_type == InterleavingActionType.INSERT_BEHIND
    assert result.actions[0].target_sequence == "s02"
    assert result.actions[0].target_component == "HV BUSHING"


def test_feeder_pillar_defect_channel_sequencing_d36() -> None:
    """Per D36: Feeder Pillar defects sequence after fp-overview.docx in left-to-right channel order."""
    fp_item = ScanRenderItem(
        page_name="fp_overview",
        template_name="fp-overview.docx",
        equipment_category="fp",
        component_name="OVERVIEW",
        sequence="f00",
        is_overview=True,
        equipment_id="fp1",
    )

    # Scrambled defect pages: OT05, F02 (Talapia F2), IN01
    defects_scrambled = [
        CbmDefectSliceMetadata(
            equipment_category="fp",
            equipment_instance="fp1",
            sequence="ot05",
            equipment_id="OUTGOING_F5",
            defect_area="FUSE_BASE",
            filename="fp1_ot05_OUTGOING_F5_FUSE_BASE_01.docx",
        ),
        CbmDefectSliceMetadata(
            equipment_category="fp",
            equipment_instance="fp1",
            sequence="f02",
            equipment_id="OUTGOING_F2",
            defect_area="FUSE_BASE",
            filename="fp1_f02_OUTGOING_F2_FUSE_BASE_01.docx",
        ),
        CbmDefectSliceMetadata(
            equipment_category="fp",
            equipment_instance="fp1",
            sequence="in01",
            equipment_id="INCOMER_1",
            defect_area="INCOMING_CABLE",
            filename="fp1_in01_INCOMER_1_INCOMING_CABLE_01.docx",
        ),
    ]

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=[fp_item], sliced_defects=defects_scrambled)

    assert isinstance(result, InterleavingResult)
    # 1 overview + 3 defects = 4 parts
    assert len(result.parts) == 4

    # 0: Overview
    assert result.parts[0].sequence == "f00"
    assert result.parts[0].is_defect is False

    # 1: IN01 defect (incomers first!)
    assert result.parts[1].sequence == "in01"
    assert result.parts[1].is_defect is True
    assert result.parts[1].part_name == "fp1_in01_INCOMER_1_INCOMING_CABLE_01.docx"

    # 2: F02 / OT02 defect (Talapia defect next!)
    assert result.parts[2].sequence == "f02"
    assert result.parts[2].is_defect is True
    assert result.parts[2].part_name == "fp1_f02_OUTGOING_F2_FUSE_BASE_01.docx"

    # 3: OT05 defect (higher outgoing channel next!)
    assert result.parts[3].sequence == "ot05"
    assert result.parts[3].is_defect is True
    assert result.parts[3].part_name == "fp1_ot05_OUTGOING_F5_FUSE_BASE_01.docx"

    # All 3 defect actions are APPEND_AFTER
    assert len(result.actions) == 3
    for a in result.actions:
        assert a.action_type == InterleavingActionType.APPEND_AFTER


def test_orphan_defect_safe_append_with_warning_d38(caplog: pytest.LogCaptureFixture) -> None:
    """Per D38: Unmatched defect pages safely append at the end of the scan stream with a warning."""
    scan_items = _make_mock_swg_items()[:2]  # Just overview and panel 1

    # Unmatched / unparseable orphan defect
    orphan_meta = CbmDefectSliceMetadata(
        equipment_category="generator",
        equipment_instance="gen1",
        sequence="g01",
        equipment_id="GEN1",
        defect_area="ROTOR",
        filename="gen1_g01_GEN1_ROTOR_01.docx",
    )

    policy = DefectInterleavingPolicy()
    with caplog.at_level("WARNING"):
        result = policy.interleave(scan_items=scan_items, sliced_defects=[orphan_meta])

    assert isinstance(result, InterleavingResult)
    # 2 baseline items + 1 orphan = 3 parts
    assert len(result.parts) == 3

    # Baseline items untouched
    assert result.parts[0].sequence == "p00"
    assert result.parts[1].sequence == "p01"

    # Orphan appended at stream end
    orphan_part = result.parts[2]
    assert orphan_part.is_defect is True
    assert orphan_part.action_type == InterleavingActionType.ORPHAN_APPEND
    assert orphan_part.part_name == "gen1_g01_GEN1_ROTOR_01.docx"

    # Present in result.orphans
    assert len(result.orphans) == 1
    assert result.orphans[0].part_name == "gen1_g01_GEN1_ROTOR_01.docx"

    # Verify warning logged per D38
    assert "Unmatched orphan CBM defect page" in caplog.text
    assert "gen1_g01_GEN1_ROTOR_01.docx" in caplog.text


# ==============================================================================
# Canonical Benchmark Scenarios
# ==============================================================================

def test_canonical_benchmark_talapia_interleaving() -> None:
    """Benchmark TALAPIA: TAMCO RMU (10 pages), 1 TX (7 pages), FP with F2 defect (2 pages), Battery (1 page) = 20 pages."""
    # 1. TAMCO 4 panels (2 overview + 4 * 2 compartments = 10 pages)
    swg_items = [
        ScanRenderItem(
            page_name="swg_overview",
            template_name="swg-overview.docx",
            equipment_category="swg",
            component_name="OVERVIEW",
            sequence="p00",
            is_overview=True,
            equipment_id="swg1",
        ),
        ScanRenderItem(
            page_name="swg_overview_bottom",
            template_name="swg-overview.docx",
            equipment_category="swg",
            component_name="OVERVIEW BOTTOM",
            sequence="p00_01",
            is_overview=True,
            equipment_id="swg1",
        ),
    ]
    for p_num in range(1, 5):
        for comp in ("CABLE COMPARTMENT", "CABLE ENTRY"):
            swg_items.append(
                ScanRenderItem(
                    page_name=f"swg_p{p_num}_{comp.lower().replace(' ', '_')}",
                    template_name="swg-panel.docx",
                    equipment_category="swg",
                    component_name=comp,
                    sequence=f"p{p_num:02d}",
                    panel_no=p_num,
                    equipment_id="swg1",
                )
            )

    # 2. TX (7 pages)
    tx_items = _make_mock_tx_items("Tx 1")

    # 3. FP (1 page overview)
    fp_item = ScanRenderItem(
        page_name="fp_overview",
        template_name="fp-overview.docx",
        equipment_category="fp",
        component_name="OVERVIEW",
        sequence="f00",
        is_overview=True,
        equipment_id="fp1",
    )

    # 4. Battery Bank (1 page overview)
    batt_item = ScanRenderItem(
        page_name="battery_overview",
        template_name="battery-overview.docx",
        equipment_category="battery",
        component_name="OVERVIEW",
        sequence="b00",
        is_overview=True,
        equipment_id="batt1",
    )

    all_scan_items = swg_items + tx_items + [fp_item, batt_item]
    assert len(all_scan_items) == 19

    # Sliced CBM Defect: FP F2 defect (Fuse Base)
    fp_f2_defect = CbmDefectSliceMetadata(
        equipment_category="fp",
        equipment_instance="fp1",
        sequence="f02",
        equipment_id="OUTGOING_F2",
        defect_area="FUSE_BASE",
        filename="fp1_f02_OUTGOING_F2_FUSE_BASE_01.docx",
        technology="IR",
    )

    qr_record = CbmDefectRecord(
        equipment="FEEDER PILLAR",
        equipment_id="F2",
        defect_area="Fuse Contact",
        technology="IR",
        ir_reading="78.4",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(
        scan_items=all_scan_items,
        sliced_defects=[fp_f2_defect],
        cbm_records=[qr_record],
    )

    # 10 (SWG) + 7 (TX) + 2 (FP OV + F2 Defect) + 1 (Battery) = 20 pages
    assert len(result.parts) == 20
    assert len(result.replaced_items) == 0

    # Index 17 is FP overview, Index 18 is FP F2 defect, Index 19 is Battery overview
    assert result.parts[17].sequence == "f00"
    assert result.parts[17].is_defect is False

    assert result.parts[18].sequence == "f02"
    assert result.parts[18].is_defect is True
    assert result.parts[18].action_type == InterleavingActionType.APPEND_AFTER
    assert result.parts[18].part_name == "fp1_f02_OUTGOING_F2_FUSE_BASE_01.docx"

    assert result.parts[19].sequence == "b00"
    assert result.parts[19].is_defect is False


def test_canonical_benchmark_cenderawasih_interleaving() -> None:
    """Benchmark CENDERAWASIH NO.1: INDKOM RMU (5 pages with panel 4 replaced), 1 TX (7 pages), FP (1 page) = 13 pages."""
    swg_items = _make_mock_swg_items()  # 5 pages: 1 overview + 4 panels
    tx_items = _make_mock_tx_items("Tx 1")  # 7 pages
    fp_item = ScanRenderItem(
        page_name="fp_overview",
        template_name="fp-overview.docx",
        equipment_category="fp",
        component_name="OVERVIEW",
        sequence="f00",
        is_overview=True,
        equipment_id="fp1",
    )

    all_scan_items = swg_items + tx_items + [fp_item]
    assert len(all_scan_items) == 13

    # Defect: RMU Panel 4 CKN01309 TX fuse compartment IR defect
    swg_defect = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p04",
        equipment_id="CKN01309",
        defect_area="FUSE_COMPARTMENT",
        filename="swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx",
        technology="IR",
    )

    qr_record = CbmDefectRecord(
        equipment="RMU SF6",
        equipment_id="CKN01309",
        defect_area="FUSE COMPARTMENT",
        technology="IR",
        ir_reading="65.4",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(
        scan_items=all_scan_items,
        sliced_defects=[swg_defect],
        cbm_records=[qr_record],
    )

    # 5 SWG (with panel 4 replaced) + 7 TX + 1 FP = 13 pages
    assert len(result.parts) == 13
    assert len(result.replaced_items) == 1
    assert result.replaced_items[0].panel_no == 4

    # Part 4 is the replaced panel 4 defect page
    assert result.parts[4].sequence == "p04"
    assert result.parts[4].is_defect is True
    assert result.parts[4].action_type == InterleavingActionType.REPLACE
    assert result.parts[4].part_name == "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"


def test_canonical_benchmark_telekom_tanah_putih_interleaving() -> None:
    """Benchmark TELEKOM TANAH PUTIH: INDKOM RMU (5 pages + 4 TEV appends = 9 pages), 1 TX (7 pages), LVDB (1 page), Battery (1 page) = 18 pages."""
    swg_items = _make_mock_swg_items()  # 5 pages: 1 overview + 4 panels
    tx_items = _make_mock_tx_items("Tx 1")  # 7 pages
    lvdb_item = ScanRenderItem(
        page_name="lvdb_overview",
        template_name="fp-overview.docx",
        equipment_category="fp",
        component_name="OVERVIEW",
        sequence="f00",
        is_overview=True,
        equipment_id="lvdb1",
    )
    batt_item = ScanRenderItem(
        page_name="battery_overview",
        template_name="battery-overview.docx",
        equipment_category="battery",
        component_name="OVERVIEW",
        sequence="b00",
        is_overview=True,
        equipment_id="batt1",
    )

    all_scan_items = swg_items + tx_items + [lvdb_item, batt_item]
    assert len(all_scan_items) == 14

    # 4 TEV defects across panels 1 to 4
    tev_defects = [
        CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg1",
            sequence=f"p{i:02d}",
            equipment_id=f"F{i}",
            defect_area="CABLE_COMPARTMENT" if i != 4 else "FUSE_COMPARTMENT",
            filename=f"swg1_p{i:02d}_F{i}_TEV_01.docx",
            technology="TEV",
        )
        for i in range(1, 5)
    ]

    cbm_records = [
        CbmDefectRecord(
            equipment="RMU SF6",
            equipment_id=f"F{i}",
            defect_area="CABLE COMPARTMENT" if i != 4 else "FUSE COMPARTMENT",
            technology="TEV",
            tev_reading="24.0",
        )
        for i in range(1, 5)
    ]

    policy = DefectInterleavingPolicy()
    result = policy.interleave(
        scan_items=all_scan_items,
        sliced_defects=tev_defects,
        cbm_records=cbm_records,
    )

    # 9 SWG (1 ov + 4*(panel+defect)) + 7 TX + 1 LVDB + 1 Battery = 18 pages
    assert len(result.parts) == 18
    assert len(result.replaced_items) == 0
    assert len(result.actions) == 4
    for a in result.actions:
        assert a.action_type == InterleavingActionType.APPEND_AFTER


def test_interleave_with_directory_of_files(tmp_path: Path) -> None:
    """Policy reads a directory containing sliced docx files directly."""
    cbm_dir = tmp_path / "cbm_defects"
    cbm_dir.mkdir()

    f1 = cbm_dir / "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"
    f1.write_text("mock content", encoding="utf-8")

    scan_items = _make_mock_swg_items()
    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=cbm_dir)

    assert len(result.parts) == 5
    assert result.parts[4].is_defect is True
    assert result.parts[4].action_type == InterleavingActionType.REPLACE


def test_multi_compartment_tamco_panel_defect_no_duplication() -> None:
    """Multi-compartment panel defect replaces only the matching compartment without duplicating on CABLE ENTRY."""
    items = [
        ScanRenderItem(
            page_name="swg_p1_cable_compartment",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p01",
            panel_no=1,
            equipment_id="swg1",
        ),
        ScanRenderItem(
            page_name="swg_p1_cable_entry",
            template_name="swg-panel.docx",
            equipment_category="swg",
            component_name="CABLE ENTRY",
            sequence="p01",
            panel_no=1,
            equipment_id="swg1",
        ),
    ]

    defect = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p01",
        equipment_id="SWG1",
        defect_area="CABLE_COMPARTMENT",
        filename="swg1_p01_SWG1_CABLE_COMPARTMENT_01.docx",
        technology="IR",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=items, sliced_defects=[defect])

    # CABLE COMPARTMENT replaced by defect, CABLE ENTRY kept intact = 2 parts total
    assert len(result.parts) == 2
    assert result.parts[0].is_defect is True
    assert result.parts[0].action_type == InterleavingActionType.REPLACE
    assert result.parts[0].part_name == "swg1_p01_SWG1_CABLE_COMPARTMENT_01.docx"

    assert result.parts[1].is_defect is False
    assert result.parts[1].component_name == "CABLE ENTRY"
    assert len(result.replaced_items) == 1


def test_interleaved_part_properties() -> None:
    """InterleavedPart.is_sliced accurately reflects defect, sliced file, or scan item state."""
    p1 = InterleavedPart(
        part_name="test.docx",
        is_defect=True,
        equipment_category="swg",
        sequence="p01",
        component_name="CABLE COMPARTMENT",
    )
    assert p1.is_sliced is True

    p2 = InterleavedPart(
        part_name="normal.docx",
        is_defect=False,
        equipment_category="swg",
        sequence="p01",
        component_name="CABLE COMPARTMENT",
    )
    assert p2.is_sliced is False


def test_empty_scan_items_and_defects() -> None:
    """Empty inputs yield clean empty or pass-through results."""
    policy = DefectInterleavingPolicy()

    # Both empty
    r1 = policy.interleave(scan_items=[], sliced_defects=[])
    assert len(r1.parts) == 0
    assert len(r1.actions) == 0

    # Only scan items
    scan_items = _make_mock_swg_items()
    r2 = policy.interleave(scan_items=scan_items, sliced_defects=[])
    assert len(r2.parts) == len(scan_items)
    assert all(not p.is_defect for p in r2.parts)


def test_swg_multiple_ir_defects_on_same_panel() -> None:
    """When multiple IR defects exist on the same panel, the 1st replaces and the 2nd appends."""
    scan_items = _make_mock_swg_items()

    d1 = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p04",
        equipment_id="CKN01309",
        defect_area="FUSE_COMPARTMENT",
        index=1,
        filename="swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx",
        technology="IR",
    )
    d2 = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p04",
        equipment_id="CKN01309",
        defect_area="FUSE_COMPARTMENT",
        index=2,
        filename="swg1_p04_CKN01309_FUSE_COMPARTMENT_02.docx",
        technology="IR",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=[d1, d2])

    # 4 panels: ov + p1 + p2 + p3 + replaced p4 (d1) + appended p4 (d2) = 6 parts
    assert len(result.parts) == 6
    assert result.parts[4].action_type == InterleavingActionType.REPLACE
    assert result.parts[4].part_name == "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"

    assert result.parts[5].action_type == InterleavingActionType.APPEND_AFTER
    assert result.parts[5].part_name == "swg1_p04_CKN01309_FUSE_COMPARTMENT_02.docx"


def test_overview_defect_substitution_not_duplicated() -> None:
    """Overview defect pages in cbm_defects replace unsliced overview without duplication."""
    scan_items = _make_mock_swg_items()

    ov_defect = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p00",
        equipment_id="SWG1",
        defect_area="OVERVIEW",
        filename="swg1_p00_SWG1_OVERVIEW_01.docx",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=scan_items, sliced_defects=[ov_defect])

    # Should still be 5 parts, overview replaced
    assert len(result.parts) == 5
    assert result.parts[0].sequence == "p00"
    assert result.parts[0].part_name == "swg1_p00_SWG1_OVERVIEW_01.docx"
    assert len(result.orphans) == 0


def test_multi_transformer_defect_isolation() -> None:
    """Defects for TX1 and TX2 are routed strictly to their respective transformers."""
    tx1_items = _make_mock_tx_items("Tx 1")
    tx2_items = _make_mock_tx_items("Tx 2")

    d_tx1 = CbmDefectSliceMetadata(
        equipment_category="tx",
        equipment_instance="tx1",
        sequence="s02",
        equipment_id="TX1",
        defect_area="HV_BUSHING",
        filename="tx1_s02_TX1_HV_BUSHING_01.docx",
    )
    d_tx2 = CbmDefectSliceMetadata(
        equipment_category="tx",
        equipment_instance="tx2",
        sequence="s05",
        equipment_id="TX2",
        defect_area="LV_BUSHING",
        filename="tx2_s05_TX2_LV_BUSHING_01.docx",
    )

    policy = DefectInterleavingPolicy()
    result = policy.interleave(scan_items=tx1_items + tx2_items, sliced_defects=[d_tx1, d_tx2])

    # 7 + 1 + 7 + 1 = 16 parts
    assert len(result.parts) == 16

    # TX1 defect is behind TX1 HV Bushing (index 3)
    assert result.parts[2].component_name == "HV BUSHING"
    assert result.parts[2].equipment_category == "tx"
    assert result.parts[3].part_name == "tx1_s02_TX1_HV_BUSHING_01.docx"

    # TX2 defect is behind TX2 LV Bushing
    tx2_lv_idx = next(
        i for i, p in enumerate(result.parts)
        if p.component_name == "LV BUSHING" and p.scan_item and p.scan_item.equipment_id == "Tx 2"
    )
    assert result.parts[tx2_lv_idx + 1].part_name == "tx2_s05_TX2_LV_BUSHING_01.docx"


def test_parse_d37_filename_helper() -> None:
    """parse_d37_filename decomposes D37 filenames cleanly."""
    from src.full_report.defect_parser import parse_d37_filename

    m1 = parse_d37_filename("swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx")
    assert m1 is not None
    assert m1.equipment_category == "swg"
    assert m1.equipment_instance == "swg1"
    assert m1.sequence == "p04"
    assert m1.equipment_id == "CKN01309"
    assert m1.defect_area == "FUSE_COMPARTMENT"
    assert m1.index == 1

    m2 = parse_d37_filename("fp1_in01_INCOMER_1_INCOMING_CABLE_02.docx")
    assert m2 is not None
    assert m2.equipment_category == "fp"
    assert m2.sequence == "in01"
    assert m2.index == 2

    # Non-docx or invalid format returns None
    assert parse_d37_filename("invalid_name.txt") is None
    assert parse_d37_filename("short_01.docx") is None


def test_get_feeder_channel_sort_key_helper() -> None:
    """get_feeder_channel_sort_key orders incomers, outgoings, and overview."""
    from src.full_report.interleaving import get_feeder_channel_sort_key

    k_ov = get_feeder_channel_sort_key("f00")
    k_in1 = get_feeder_channel_sort_key("in01")
    k_in2 = get_feeder_channel_sort_key("in02")
    k_ot1 = get_feeder_channel_sort_key("ot01")
    k_ot2 = get_feeder_channel_sort_key("ot02")
    k_f2 = get_feeder_channel_sort_key("f02")

    # Order: overview (-1) < in1 (0, 1) < in2 (0, 2) < ot1 (1, 1) < f2 (1, 2)
    assert k_ov < k_in1 < k_in2 < k_ot1 < k_ot2
    assert k_ot2[:2] == k_f2[:2] == (1, 2)
