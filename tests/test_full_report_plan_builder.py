"""Unit tests for FullReportPlanBuilder Deep Module (Ticket #33 / T5.2).

Verifies:
1. Data structures: PlanPartType, PlanPartItem, FullReportStationPlan.
2. Canonical 8-part sequence assembly per D39.
3. Clean omission of vi_summary and vi_defect_pages when zero visual defects exist.
4. Component health evaluation and D47 overview page substitution (rendered vs sliced).
5. Defect interleaving within the component stream (D34, D35, D36, D38).
6. Benchmark topologies: Talapia, Cenderawasih No.1, Telekom Tanah Putih.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from src.full_report.plan_builder import (
    FullReportPlanBuilder,
    FullReportStationPlan,
    PlanPartItem,
    PlanPartType,
)
from src.full_report.slicer import SlicedSections
from src.full_report.defect_parser import CbmDefectSliceMetadata
from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBSpec,
    LVDBFeederSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


def test_plan_part_type_enum_members() -> None:
    """PlanPartType enum defines all canonical 8-part BOM categories."""
    assert PlanPartType.FRONT_PAGE.value == "FRONT_PAGE"
    assert PlanPartType.CENSUS.value == "CENSUS"
    assert PlanPartType.VI_SUMMARY.value == "VI_SUMMARY"
    assert PlanPartType.SCAN_PAGE.value == "SCAN_PAGE"
    assert PlanPartType.CBM_DEFECT.value == "CBM_DEFECT"
    assert PlanPartType.CONDITION.value == "CONDITION"
    assert PlanPartType.VI_DEFECTS.value == "VI_DEFECTS"
    assert PlanPartType.STICKER.value == "STICKER"


def test_plan_part_item_creation() -> None:
    """PlanPartItem holds metadata and source references for each planned document part."""
    item = PlanPartItem(
        part_type=PlanPartType.FRONT_PAGE,
        part_name="Front Page",
        source_path=Path("temp_parts/front_page.docx"),
        is_sliced=True,
    )
    assert item.part_type == PlanPartType.FRONT_PAGE
    assert item.part_name == "Front Page"
    assert item.is_sliced is True
    assert item.source_path == Path("temp_parts/front_page.docx")


def test_station_plan_properties() -> None:
    """FullReportStationPlan provides typed convenience accessors over parts."""
    parts = (
        PlanPartItem(part_type=PlanPartType.FRONT_PAGE, part_name="Front Page", is_sliced=True),
        PlanPartItem(part_type=PlanPartType.CENSUS, part_name="Census", is_sliced=False),
        PlanPartItem(part_type=PlanPartType.CONDITION, part_name="Condition", is_sliced=True),
        PlanPartItem(part_type=PlanPartType.STICKER, part_name="Sticker", is_sliced=True),
    )
    pkg = SubstationEquipmentPackage()
    plan = FullReportStationPlan(
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        month_folder="08. AUGUST",
        output_dir=Path("FULL REPORT/RAU/08. AUGUST/04-08-2026"),
        output_filename="005. PE TALAPIA (IR+VI).docx",
        final_output_path=Path("FULL REPORT/RAU/08. AUGUST/04-08-2026/005. PE TALAPIA (IR+VI).docx"),
        package=pkg,
        parts=parts,
    )

    assert len(plan) == 4
    assert plan.part_types == (
        PlanPartType.FRONT_PAGE,
        PlanPartType.CENSUS,
        PlanPartType.CONDITION,
        PlanPartType.STICKER,
    )
    assert plan.part_names == ("Front Page", "Census", "Condition", "Sticker")
    assert len(plan.get_parts_by_type(PlanPartType.FRONT_PAGE)) == 1
    assert len(plan.get_parts_by_type(PlanPartType.SCAN_PAGE)) == 0
    assert len(plan.sliced_parts) == 3
    assert len(plan.rendered_parts) == 1


def _make_sample_package() -> SubstationEquipmentPackage:
    """Create sample substation package with 1 SWG, 1 TX, 1 LVDB."""
    swg = SwitchgearSpec(
        switchgear_type="INDKOM",
        manufacturer="INDKOM",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="F1", name="SPARE", panel_type="INCOMING"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="F2", name="FEEDER 1", panel_type="FEEDER"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="1000")
    lvdb = LVDBSpec(name="FP 1", label="FP 1")
    return SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
    )


def test_canonical_sequence_healthy_substation_omits_vi(tmp_path: Path) -> None:
    """Zero VI defects cleanly omits vi_summary and vi_defect_pages per D39."""
    pkg = _make_sample_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        vi_summary=None,
        vi_defect_pages=None,
    )

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        substation_info={"name_erms": "PE TALAPIA", "date": "04-08-2026"},
    )

    # 1. First 2 parts must be Front Page and Census
    assert plan.part_types[0] == PlanPartType.FRONT_PAGE
    assert plan.part_types[1] == PlanPartType.CENSUS

    # 2. VI Summary must be omitted
    assert PlanPartType.VI_SUMMARY not in plan.part_types

    # 3. Component stream follows Census directly
    assert plan.part_types[2] == PlanPartType.SCAN_PAGE

    # 4. Last 2 parts must be Condition and Sticker (VI Defect Pages omitted)
    assert plan.part_types[-2] == PlanPartType.CONDITION
    assert plan.part_types[-1] == PlanPartType.STICKER
    assert PlanPartType.VI_DEFECTS not in plan.part_types


def test_canonical_sequence_with_vi_defects_includes_all_8_parts(tmp_path: Path) -> None:
    """When VI defects exist, vi_summary and vi_defect_pages are included at canonical indices per D39."""
    pkg = _make_sample_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        vi_summary=tmp_path / "vi_summary.docx",
        vi_defect_pages=tmp_path / "vi_defect_pages.docx",
    )
    vi_defects = [
        ViDefectRecord(
            equipment="SWITCHGEAR",
            defect_area="EARTHING",
            additional_remarks="Earthing lead disconnected",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=vi_defects,
        station="PE TALAPIA",
        substation_info={"name_erms": "PE TALAPIA", "date": "04-08-2026"},
    )

    # Sequence: Front Page -> Census -> VI Summary -> Components -> Condition -> VI Defect Pages -> Sticker
    assert plan.part_types[0] == PlanPartType.FRONT_PAGE
    assert plan.part_types[1] == PlanPartType.CENSUS
    assert plan.part_types[2] == PlanPartType.VI_SUMMARY

    # Components in the middle
    assert plan.part_types[3] == PlanPartType.SCAN_PAGE

    # Ending: Condition -> VI Defect Pages -> Sticker
    assert plan.part_types[-3] == PlanPartType.CONDITION
    assert plan.part_types[-2] == PlanPartType.VI_DEFECTS
    assert plan.part_types[-1] == PlanPartType.STICKER


# ==============================================================================
# Slice 3: D47 Component Health Evaluation & Overview Substitution
# ==============================================================================

def test_evaluate_component_health() -> None:
    """evaluate_component_health identifies active defects across equipment families (D47)."""
    builder = FullReportPlanBuilder()

    defects = [
        CbmDefectRecord(
            equipment="RMU TAMCO",
            equipment_id="PANEL 4",
            defect_area="CABLE COMPARTMENT",
            technology="IR",
        ),
        CbmDefectRecord(
            equipment="FEEDER PILLAR",
            equipment_id="FP 1",
            defect_area="FUSE BASE",
            technology="IR",
        ),
    ]

    # SWG has active defect -> defective
    assert builder.evaluate_component_health(category="swg", cbm_defects=defects) is True
    # FP has active defect -> defective
    assert builder.evaluate_component_health(category="fp", cbm_defects=defects) is True
    # TX has no defect -> healthy
    assert builder.evaluate_component_health(category="tx", cbm_defects=defects) is False
    # Battery has no defect -> healthy
    assert builder.evaluate_component_health(category="battery", cbm_defects=defects) is False


def test_d47_overview_substitution_when_defective(tmp_path: Path) -> None:
    """When an equipment group has active defect, overview is substituted with sliced QR file (D47)."""
    pkg = _make_sample_package()

    # Sliced SWG overview file
    cbm_dir = tmp_path / "cbm_defects"
    cbm_dir.mkdir(parents=True, exist_ok=True)
    sliced_swg_ov = cbm_dir / "swg1_p00_SWG1_OVERVIEW_01.docx"
    sliced_swg_ov.write_bytes(b"PK\x03\x04fake_swg_overview")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(sliced_swg_ov,),
    )

    cbm_defects = [
        CbmDefectRecord(
            equipment="RMU INDKOM",
            equipment_id="F2",
            defect_area="CABLE COMPARTMENT",
            technology="IR",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_defects,
        station="PE TALAPIA",
    )

    # Find SWG overview item (sequence p00)
    swg_ov = next(p for p in plan.parts if p.sequence == "p00")
    assert swg_ov.is_sliced is True
    assert swg_ov.is_overview is True
    assert swg_ov.source_path == sliced_swg_ov

    # Find TX overview item (sequence s00) - healthy -> rendered template
    tx_ov = next(p for p in plan.parts if p.sequence == "s00")
    assert tx_ov.is_sliced is False
    assert tx_ov.is_overview is True

    # Find FP overview item (sequence f00) - healthy -> rendered template
    fp_ov = next(p for p in plan.parts if p.sequence == "f00")
    assert fp_ov.is_sliced is False
    assert fp_ov.is_overview is True


def test_d47_all_healthy_overviews_rendered_templates(tmp_path: Path) -> None:
    """When all equipment groups are healthy, all overviews are rendered templates with green banners (D47)."""
    pkg = _make_sample_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(),
    )

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=(),
        station="PE TALAPIA",
    )

    overviews = [p for p in plan.parts if p.is_overview]
    assert len(overviews) >= 3  # SWG (p00), TX (s00, s01), FP (f00)
    assert all(not ov.is_sliced for ov in overviews)


# ==============================================================================
# Slice 4: Defect Interleaving within Component Stream (D34, D35, D36, D38)
# ==============================================================================

def test_swg_ir_defect_replaces_panel_in_plan(tmp_path: Path) -> None:
    """SWG IR defect replaces panel scan page with CBM_DEFECT part per D34."""
    pkg = _make_sample_package()
    d_path = tmp_path / "swg1_p02_F2_CABLE_COMPARTMENT_01.docx"
    d_path.write_bytes(b"PK\x03\x04fake_swg_defect")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(d_path,),
    )

    cbm_records = [
        CbmDefectRecord(
            equipment="RMU INDKOM",
            equipment_id="F2",
            defect_area="CABLE COMPARTMENT",
            technology="IR",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_records,
        station="PE TALAPIA",
    )

    # Panel 2 (F2) must be replaced by CBM_DEFECT
    cbm_parts = plan.get_parts_by_type(PlanPartType.CBM_DEFECT)
    assert len(cbm_parts) == 1
    assert cbm_parts[0].sequence == "p02"
    assert cbm_parts[0].is_sliced is True
    assert cbm_parts[0].source_path == d_path


def test_tx_defect_inserted_behind_component_in_plan(tmp_path: Path) -> None:
    """Transformer defect is inserted immediately behind the component scan page per D35."""
    pkg = _make_sample_package()
    d_path = tmp_path / "tx1_s05_TX1_LV_BUSHING_01.docx"
    d_path.write_bytes(b"PK\x03\x04fake_tx_defect")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(d_path,),
    )

    cbm_records = [
        CbmDefectRecord(
            equipment="TRANSFORMER",
            equipment_id="Tx 1",
            defect_area="LV BUSHING",
            technology="IR",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_records,
        station="PE TALAPIA",
    )

    # Find LV Bushing scan page index
    lv_idx = next(i for i, p in enumerate(plan.parts) if p.component_name == "LV BUSHING")
    # Defect must be immediately after LV Bushing
    assert plan.parts[lv_idx + 1].part_type == PlanPartType.CBM_DEFECT
    assert plan.parts[lv_idx + 1].sequence == "s05"


def test_fp_defects_sequenced_in_channel_order_in_plan(tmp_path: Path) -> None:
    """Feeder Pillar defects sequence after fp-overview.docx in channel order per D36."""
    fp = LVDBSpec(
        name="FP 1",
        label="FP 1",
        feeders=(
            LVDBFeederSpec(channel="IN1", cable_type="XLPE"),
            LVDBFeederSpec(channel="OT1", cable_type="XLPE"),
        ),
    )
    pkg = SubstationEquipmentPackage(lvdb_specs=(fp,))

    d_ot1 = tmp_path / "fp1_ot01_FEEDER_1_CABLE_01.docx"
    d_ot1.write_bytes(b"PK\x03\x04fake_ot1")
    d_in1 = tmp_path / "fp1_in01_INCOMER_1_CABLE_01.docx"
    d_in1.write_bytes(b"PK\x03\x04fake_in1")

    # Pass in reverse order to ensure sorting
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(d_ot1, d_in1),
    )

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[
            CbmDefectRecord(equipment="FEEDER PILLAR", equipment_id="OT1", defect_area="CABLE"),
            CbmDefectRecord(equipment="FEEDER PILLAR", equipment_id="IN1", defect_area="CABLE"),
        ],
        station="PE TALAPIA",
    )

    fp_ov_idx = next(i for i, p in enumerate(plan.parts) if p.sequence == "f00")
    # IN1 must be before OT1
    assert plan.parts[fp_ov_idx + 1].sequence == "in01"
    assert plan.parts[fp_ov_idx + 2].sequence == "ot01"


def test_orphan_defect_appended_before_condition_in_plan(tmp_path: Path) -> None:
    """Unmatched orphan defect is appended at end of component stream before Substation Condition per D38."""
    pkg = _make_sample_package()
    d_orphan = tmp_path / "unknown_x99_MISC_DEFECT_01.docx"
    d_orphan.write_bytes(b"PK\x03\x04fake_orphan")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(d_orphan,),
    )

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[CbmDefectRecord(equipment="UNKNOWN", equipment_id="X99", defect_area="MISC")],
        station="PE TALAPIA",
    )

    cond_idx = next(i for i, p in enumerate(plan.parts) if p.part_type == PlanPartType.CONDITION)
    # The part immediately before Condition must be the orphan CBM defect
    assert plan.parts[cond_idx - 1].part_type == PlanPartType.CBM_DEFECT
    assert plan.parts[cond_idx - 1].source_path == d_orphan


# ==============================================================================
# Slice 5: Canonical Benchmark Topologies
# ==============================================================================

def test_benchmark_talapia_topology(tmp_path: Path) -> None:
    """Benchmark: TALAPIA (PE 5, IR+VI) with Feeder Pillar defect and VI defects."""
    swg = SwitchgearSpec(
        switchgear_type="LUCY",
        manufacturer="LUCY",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="F1", name="SPARE"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="F2", name="TX 1"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="500")
    fp = LVDBSpec(
        name="FP 1",
        label="FP 1",
        feeders=(
            LVDBFeederSpec(channel="IN1", cable_type="XLPE"),
            LVDBFeederSpec(channel="OT1", cable_type="XLPE"),
        ),
    )
    pkg = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
    )

    fp_defect_docx = tmp_path / "fp1_ot01_FEEDER_1_FUSE_BASE_01.docx"
    fp_defect_docx.write_bytes(b"PK\x03\x04fake_fp_defect")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        vi_summary=tmp_path / "vi_summary.docx",
        vi_defect_pages=tmp_path / "vi_defect_pages.docx",
        cbm_defect_pages=(fp_defect_docx,),
    )

    cbm_defects = [
        CbmDefectRecord(
            equipment="FEEDER PILLAR",
            equipment_id="FP 1",
            defect_area="FUSE BASE",
            technology="IR",
        )
    ]
    vi_defects = [
        ViDefectRecord(
            equipment="TRANSFORMER",
            defect_area="SILICA GEL",
            additional_remarks="Silica gel turned pink",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_defects,
        vi_defects=vi_defects,
        station="PE TALAPIA",
        substation_info={"name_erms": "PE TALAPIA", "date": "04-08-2026", "pe_number": 5, "fl": "CRAU/PCE/J00251"},
    )

    # 1. Output file metadata
    assert plan.station == "PE TALAPIA"
    assert plan.station_code == "RAU"
    assert "005. PE TALAPIA" in plan.output_filename
    assert "(IR+VI)" in plan.output_filename

    # 2. Canonical BOM structure
    assert plan.part_types[0] == PlanPartType.FRONT_PAGE
    assert plan.part_types[1] == PlanPartType.CENSUS
    assert plan.part_types[2] == PlanPartType.VI_SUMMARY

    # Interleaved FP defect must be present in component stream
    assert PlanPartType.CBM_DEFECT in plan.part_types
    fp_def_item = next(p for p in plan.parts if p.part_type == PlanPartType.CBM_DEFECT)
    assert fp_def_item.source_path == fp_defect_docx

    # Ending sequence
    assert plan.part_types[-3] == PlanPartType.CONDITION
    assert plan.part_types[-2] == PlanPartType.VI_DEFECTS
    assert plan.part_types[-1] == PlanPartType.STICKER


def test_benchmark_cenderawasih_topology(tmp_path: Path) -> None:
    """Benchmark: CENDERAWASIH NO.1 (PE 179, IR+VI) with INDKOM SWG IR defect replacing Panel 4."""
    swg = SwitchgearSpec(
        switchgear_type="INDKOM",
        manufacturer="INDKOM",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN01308", name="SPARE"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN01310", name="TMN CENDRAWASIH 3"),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN01311", name="TAJ 33A LOT 11520"),
            SwitchgearPanelSpec(panel_no=4, panel_feeder_no="CKN01309", name="PANEL CKN01309 TX"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="1000")
    fp = LVDBSpec(name="FP 1", label="FP 1")
    pkg = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
    )

    # Sliced overview and sliced defect page
    swg_ov_docx = tmp_path / "swg1_p00_SWG1_OVERVIEW_01.docx"
    swg_ov_docx.write_bytes(b"PK\x03\x04fake_swg_overview")
    swg_d_docx = tmp_path / "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"
    swg_d_docx.write_bytes(b"PK\x03\x04fake_swg_defect")

    sliced = SlicedSections(
        station="PE CENDERAWASIH NO.1",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        vi_summary=tmp_path / "vi_summary.docx",
        vi_defect_pages=tmp_path / "vi_defect_pages.docx",
        cbm_defect_pages=(swg_ov_docx, swg_d_docx),
    )

    cbm_defects = [
        CbmDefectRecord(
            equipment="RMU INDKOM",
            equipment_id="CKN01309",
            defect_area="FUSE COMPARTMENT",
            technology="IR",
        )
    ]
    vi_defects = [
        ViDefectRecord(
            equipment="SWITCHGEAR",
            defect_area="EXTERNAL",
            additional_remarks="Rust on bottom panel",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_defects,
        vi_defects=vi_defects,
        station="PE CENDERAWASIH NO.1",
        substation_info={"name_erms": "PE CENDERAWASIH NO.1", "date": "28-08-2026", "pe_number": 179},
    )

    # 1. Output file metadata
    assert plan.station_code == "KTN"
    assert "179. PE CENDERAWASIH NO.1" in plan.output_filename

    # 2. D47: SWG Overview is sliced from QR
    swg_ov = next(p for p in plan.parts if p.sequence == "p00")
    assert swg_ov.is_sliced is True
    assert swg_ov.source_path == swg_ov_docx

    # 3. D34: Panel 4 is replaced by CBM_DEFECT
    panel_4_items = [p for p in plan.parts if p.sequence == "p04"]
    assert len(panel_4_items) == 1
    assert panel_4_items[0].part_type == PlanPartType.CBM_DEFECT
    assert panel_4_items[0].source_path == swg_d_docx

    # 4. TX and FP overviews are healthy rendered templates
    tx_ov = next(p for p in plan.parts if p.sequence == "s00")
    assert tx_ov.is_sliced is False
    fp_ov = next(p for p in plan.parts if p.sequence == "f00")
    assert fp_ov.is_sliced is False


def test_benchmark_telekom_tanah_putih_topology(tmp_path: Path) -> None:
    """Benchmark: TELEKOM TANAH PUTIH (PE 144, TEV+VI) with SWG TEV defect appended after panel."""
    swg = SwitchgearSpec(
        switchgear_type="TAMCO",
        manufacturer="TAMCO",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN00041", name="INCOMING 1"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN00042", name="FEEDER 2"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="1000")
    fp = LVDBSpec(name="FP 1", label="FP 1")
    pkg = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
    )

    swg_tev_docx = tmp_path / "swg1_p02_CKN00042_CABLE_COMPARTMENT_01.docx"
    swg_tev_docx.write_bytes(b"PK\x03\x04fake_swg_tev")

    sliced = SlicedSections(
        station="PE TELEKOM TANAH PUTIH",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        vi_summary=tmp_path / "vi_summary.docx",
        vi_defect_pages=tmp_path / "vi_defect_pages.docx",
        cbm_defect_pages=(swg_tev_docx,),
    )

    cbm_defects = [
        CbmDefectRecord(
            equipment="RMU TAMCO",
            equipment_id="CKN00042",
            defect_area="CABLE COMPARTMENT",
            technology="TEV",
            tev_reading="28",
        )
    ]
    vi_defects = [
        ViDefectRecord(
            equipment="FEEDER PILLAR",
            defect_area="BASE",
            additional_remarks="Grass overgrown",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_defects,
        vi_defects=vi_defects,
        station="PE TELEKOM TANAH PUTIH",
        substation_info={"name_erms": "PE TELEKOM TANAH PUTIH", "date": "24-08-2026", "pe_number": 144},
    )

    assert "(TEV+VI)" in plan.output_filename

    # D34 Rule: For TEV defects, panel scan page is RETAINED, followed immediately by TEV detail page
    p2_scan = next(p for p in plan.parts if p.sequence == "p02" and p.part_type == PlanPartType.SCAN_PAGE)
    assert p2_scan is not None
    p2_scan_idx = plan.parts.index(p2_scan)

    # Next item must be the TEV CBM_DEFECT
    next_item = plan.parts[p2_scan_idx + 1]
    assert next_item.part_type == PlanPartType.CBM_DEFECT
    assert next_item.sequence == "p02"
    assert next_item.source_path == swg_tev_docx


def test_battery_bank_ingestion_condition_d49(tmp_path: Path) -> None:
    """Battery Bank scanning page is included iff len(package.battery_banks) > 0 per D49."""
    sliced = SlicedSections(
        station="PE TEST",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )

    builder = FullReportPlanBuilder()

    # 1. Package WITH battery bank
    bb = BatteryBankSpec(name="BATTERY BANK 1", manufacturer="CHLORIDE")
    pkg_with_bb = SubstationEquipmentPackage(battery_banks=(bb,))
    plan_with_bb = builder.build(package=pkg_with_bb, sliced_sections=sliced, station="PE TEST")
    assert any(p.sequence == "b00" and p.equipment_category == "battery" for p in plan_with_bb.parts)

    # 2. Package WITHOUT battery bank
    pkg_without_bb = SubstationEquipmentPackage(battery_banks=())
    plan_without_bb = builder.build(package=pkg_without_bb, sliced_sections=sliced, station="PE TEST")
    assert not any(p.equipment_category == "battery" for p in plan_without_bb.parts)


def test_plan_part_item_render_method(tmp_path: Path) -> None:
    """PlanPartItem.render copies sliced files or delegates to renderers correctly."""
    src_file = tmp_path / "src.docx"
    src_file.write_bytes(b"PK\x03\x04original_payload")

    item = PlanPartItem(
        part_type=PlanPartType.FRONT_PAGE,
        part_name="Front Page",
        source_path=src_file,
        is_sliced=True,
    )

    out_file = tmp_path / "out" / "front_page.docx"
    rendered = item.render(out_file)
    assert rendered.exists()
    assert rendered.read_bytes() == b"PK\x03\x04original_payload"


def test_plan_render_all_method(tmp_path: Path) -> None:
    """FullReportStationPlan.render_all produces an ordered sequence of docx files."""
    pkg = _make_sample_package()
    sliced = SlicedSections(
        station="PE TEST",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    sliced.front_page.write_bytes(b"PK\x03\x04front")
    sliced.condition_pages.write_bytes(b"PK\x03\x04cond")
    sliced.sticker_page.write_bytes(b"PK\x03\x04stick")

    builder = FullReportPlanBuilder()
    plan = builder.build(package=pkg, sliced_sections=sliced, station="PE TEST")

    render_target = tmp_path / "rendered_target"
    rendered_files = plan.render_all(render_target)

    assert len(rendered_files) == len(plan.parts)
    assert all(p.exists() and p.is_file() for p in rendered_files)
    # Check that file prefixes maintain ordering
    for idx, f in enumerate(rendered_files, 1):
        assert f.name.startswith(f"{idx:03d}_")


# ==============================================================================
# Multi-Part Partition Policy Tests (Ticket #56)
# ==============================================================================

from src.full_report.plan_builder import PlanDocumentChunk, MultiPartPartitionPolicy
from src.core.topology import SwitchgearArchetype


def _make_vcb_5_panel_package() -> SubstationEquipmentPackage:
    """Create VCB substation with 5 panels including PT and transition bay."""
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="SCHNEIDER",
        model="BLOKSET",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMING 1", panel_type="VCB", cable_photo=1, breaker_photo=2, busbar_photo=3, secondary_photo=4),
            SwitchgearPanelSpec(panel_no=2, name="TX 1", panel_type="VCB", cable_photo=5, breaker_photo=6, busbar_photo=7, secondary_photo=8, pt_photo=9, has_pt_measurement=True),
            SwitchgearPanelSpec(panel_no=3, name="BUS COUPLER", panel_type="VCB", cable_photo=10, breaker_photo=11, busbar_photo=12, secondary_photo=13),
            SwitchgearPanelSpec(panel_no=4, name="OUTGOING 1", panel_type="VCB", cable_photo=14, breaker_photo=15, busbar_photo=16, secondary_photo=17),
            SwitchgearPanelSpec(panel_no=5, name="TRANSITION PANEL", panel_type="VCB", cable_photo=18, breaker_photo=19, secondary_photo=20),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="1000")
    lvdb = LVDBSpec(name="FP TX1", label="FP")
    bb = BatteryBankSpec(name="Battery Bank 1", manufacturer="HOPPECKE")
    return SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
        battery_banks=(bb,),
    )


def _make_rmu_package() -> SubstationEquipmentPackage:
    """Create RMU substation (single-chunk expected)."""
    swg = SwitchgearSpec(
        switchgear_type="INDKOM",
        manufacturer="INDKOM",
        model="JMW12",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMING", panel_type="LBS"),
            SwitchgearPanelSpec(panel_no=2, name="TX 1", panel_type="LBS"),
            SwitchgearPanelSpec(panel_no=3, name="OUTGOING", panel_type="LBS"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="500")
    return SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))


def test_plan_document_chunk_creation() -> None:
    """PlanDocumentChunk dataclass holds chunk metadata and parts."""
    chunk = PlanDocumentChunk(
        chunk_index=1,
        label="Part 01 - Summary",
        output_filename="005. PE TALAPIA (IR+VI) - Part 01.docx",
        destination_path=Path("FULL REPORT/RAUB/08. AUGUST/04-08-2026/005. PE TALAPIA (IR+VI) - Part 01.docx"),
        parts=(
            PlanPartItem(part_type=PlanPartType.FRONT_PAGE, part_name="Front Page", is_sliced=True),
            PlanPartItem(part_type=PlanPartType.CENSUS, part_name="Census", is_sliced=False),
        ),
    )
    assert chunk.chunk_index == 1
    assert chunk.label == "Part 01 - Summary"
    assert len(chunk.parts) == 2
    assert chunk.output_filename.endswith(".docx")


def test_multipart_vcb_produces_multiple_chunks(tmp_path: Path) -> None:
    """VCB substation with 5 panels partitions into 7 chunks (1 summary + 5 panels + 1 TX/Condition)."""
    pkg = _make_vcb_5_panel_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        output_dir=tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026",
        output_filename="005. PE TALAPIA.docx",
    )

    assert plan.is_multipart is True
    chunks = plan.chunks
    # 1 summary + 5 panels + 1 TX/Condition = 7 chunks
    assert len(chunks) == 7

    stem = "005. PE TALAPIA"
    # First chunk is summary
    assert chunks[0].label == "Part 01 - Summary"
    assert chunks[0].chunk_index == 1
    assert chunks[0].output_filename == f"{stem} - {chunks[0].label}.docx"

    # Panel chunks (2-6)
    for i, panel_chunk in enumerate(chunks[1:6], start=2):
        assert panel_chunk.chunk_index == i
        assert f"Part {i:02d}" in panel_chunk.output_filename
        assert "Panel" in panel_chunk.label
        assert panel_chunk.output_filename == f"{stem} - {panel_chunk.label}.docx"

    # Last chunk is TX and Condition
    assert chunks[6].label == "Part 07 - TX and Condition"
    assert chunks[6].chunk_index == 7
    assert chunks[6].output_filename == f"{stem} - {chunks[6].label}.docx"


def test_rmu_produces_single_chunk(tmp_path: Path) -> None:
    """RMU substation produces single chunk (not multipart)."""
    pkg = _make_rmu_package()
    sliced = SlicedSections(
        station="PE CHEROH",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE CHEROH",
        station_code="RAU",
        date_str="04-08-2026",
        output_dir=tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026",
        output_filename="002. PE CHEROH.docx",
    )

    assert plan.is_multipart is False
    chunks = plan.chunks
    assert len(chunks) == 1
    assert chunks[0].output_filename == "002. PE CHEROH.docx"
    assert len(chunks[0].parts) == len(plan.parts)


def test_multipart_chunk_output_filenames_use_stem(tmp_path: Path) -> None:
    """Multi-part chunk filenames follow pattern: {stem} - {label}.docx."""
    pkg = _make_vcb_5_panel_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        output_dir=tmp_path / "output",
        output_filename="005. PE TALAPIA (IR+VI).docx",
    )

    stem = "005. PE TALAPIA (IR+VI)"
    for chunk in plan.chunks:
        if plan.is_multipart:
            assert chunk.output_filename == f"{stem} - {chunk.label}.docx"
            assert chunk.destination_path == (tmp_path / "output" / f"{stem} - {chunk.label}.docx")


def test_multipart_summary_chunk_contains_front_page_and_census(tmp_path: Path) -> None:
    """Summary chunk (Part 01) contains Front Page, Census, and Overview pages."""
    pkg = _make_vcb_5_panel_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        output_dir=tmp_path / "output",
        output_filename="005. PE TALAPIA.docx",
    )

    summary_chunk = plan.chunks[0]
    summary_types = {p.part_type for p in summary_chunk.parts}
    assert PlanPartType.FRONT_PAGE in summary_types
    assert PlanPartType.CENSUS in summary_types


def test_multipart_last_chunk_contains_condition_and_sticker(tmp_path: Path) -> None:
    """Last chunk (TX and Condition) contains Condition, Sticker, and non-SWG equipment."""
    pkg = _make_vcb_5_panel_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        output_dir=tmp_path / "output",
        output_filename="005. PE TALAPIA.docx",
    )

    last_chunk = plan.chunks[-1]
    last_types = {p.part_type for p in last_chunk.parts}
    assert PlanPartType.CONDITION in last_types
    assert PlanPartType.STICKER in last_types


def test_multipart_all_parts_accounted_for(tmp_path: Path) -> None:
    """Sum of parts across all chunks equals total parts in plan."""
    pkg = _make_vcb_5_panel_package()
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=[],
        vi_defects=[],
        station="PE TALAPIA",
        output_dir=tmp_path / "output",
        output_filename="005. PE TALAPIA.docx",
    )

    total_parts_in_chunks = sum(len(c.parts) for c in plan.chunks)
    assert total_parts_in_chunks == len(plan.parts)


def test_multipart_vcb_with_inline_defect_pages_partitioning(tmp_path: Path) -> None:
    """VCB with 5 panels, PT, transition bay, and inline defect page partitions correctly."""
    pkg = _make_vcb_5_panel_package()

    # Sliced CBM defect page for panel 2 (TX 1)
    panel2_defect_docx = tmp_path / "swg1_p02_TX1_CABLE_COMPARTMENT_01.docx"
    panel2_defect_docx.write_bytes(b"PK\x03\x04fake_swg_defect")

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
        cbm_defect_pages=(panel2_defect_docx,),
    )
    for f in [sliced.front_page, sliced.condition_pages, sliced.sticker_page]:
        f.write_bytes(b"PK\x03\x04stub")

    cbm_defects = [
        CbmDefectRecord(
            equipment="SWITCHGEAR",
            equipment_id="TX 1",
            defect_area="CABLE COMPARTMENT",
            technology="IR",
        )
    ]

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        cbm_defects=cbm_defects,
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        output_dir=tmp_path / "output",
        output_filename="005. PE TALAPIA (IR).docx",
    )

    assert plan.is_multipart is True
    chunks = plan.chunks
    assert len(chunks) == 7

    # Chunk 1: Summary (Front Page, Census, SWG Overview)
    assert chunks[0].label == "Part 01 - Summary"
    assert any(p.part_type == PlanPartType.FRONT_PAGE for p in chunks[0].parts)
    assert any(p.part_type == PlanPartType.CENSUS for p in chunks[0].parts)

    # Chunk 3: Panel 2 (TX 1) contains the inline CBM defect page
    assert chunks[2].label == "Part 03 - Panel 2 (TX 1)"
    chunk3_types = [p.part_type for p in chunks[2].parts]
    assert PlanPartType.CBM_DEFECT in chunk3_types
    defect_part = next(p for p in chunks[2].parts if p.part_type == PlanPartType.CBM_DEFECT)
    assert defect_part.source_path == panel2_defect_docx

    # Chunk 6: Panel 5 (TRANSITION PANEL)
    assert "TRANSITION PANEL" in chunks[5].label

    # Chunk 7: TX and Condition
    assert chunks[6].label == "Part 07 - TX and Condition"
    chunk7_types = {p.part_type for p in chunks[6].parts}
    assert PlanPartType.CONDITION in chunk7_types
    assert PlanPartType.STICKER in chunk7_types

    # Invariant: all parts accounted for across chunks
    assert sum(len(c.parts) for c in chunks) == len(plan.parts)
    for c in chunks:
        assert c.output_filename == f"005. PE TALAPIA (IR) - {c.label}.docx"







