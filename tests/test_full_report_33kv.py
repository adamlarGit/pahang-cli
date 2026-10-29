"""Comprehensive Test Suite for 33kV Full Report Compilation & Multi-Part Partitioning (Ticket #101).

Validates:
1. 33kV macro switchgear classification (VCB_CUBICLE, GIS_CUBICLE).
2. Dynamic compartment resolution for 33kV:
   All 6 physical compartments (BREAKER, CABLE, BUSBAR, PT, CABLE ENTRY, LINK BOX) + SECONDARY.
3. Multi-lineup dual-voltage partitioning (33kV GIS + 11kV VCB):
   - Chunk 1: Part 01 - Summary includes overviews from all active lineups.
   - Chunks 2..N+1: Part XX - Panel {no} ({voltage} - {name}) per bay cubicle.
   - Equipment ID isolation prevents panel collision across lineups.
4. Balance-of-plant dynamic chunk omission (Decision Q76):
   - Omitted when no balance-of-plant assets exist.
   - Included (Part N+2 - TX and Condition) when transformers/battery exist.
5. Power Transformer Spec (>= 5 MVA) scan adapter:
   - Auxiliary thermals: MARSHALLING KIOSK, CONSERVATOR TANK, COOLING FIN via tx-overview.docx.
   - HV/LV sides via tx-hv-sides.docx and tx-lv-sides.docx.
   - Ultrasound dB and characteristic mapping.
6. 2-digit zero-padding for 33kV filenames (f"{pe_number:02d}.") vs 3-digit for 11kV (Decision Q78).
7. Front page title replacement: QUICK SCANNING REPORT -> FULL SCANNING REPORT (Decision Q77).
8. End-to-end compilation with FullReportComposer for 33kV multi-part reports.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from src.core.topology import (
    SwitchgearArchetype,
    SwitchgearTopologyEngine,
    VoltageClass,
)
from src.full_report.composer import FullReportComposer
from src.quick_report.compiler import FakeDocumentCompiler
from src.full_report.defect_parser import CbmDefectSliceMetadata
from src.full_report.interleaving import (
    DefectInterleavingPolicy,
    InterleavingActionType,
)
from src.full_report.models import (
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
)
from src.full_report.plan_builder import (
    FullReportPlanBuilder,
    MultiPartPartitionPolicy,
    PlanPartItem,
    PlanPartType,
)
from src.full_report.scan_adapters import (
    ScanRenderItem,
    SwitchgearScanAdapter,
    TransformerScanAdapter,
)
from src.full_report.slicer import SlicedSections
from src.quick_report.defects import CbmDefectRecord
from src.testsheet.models import (
    BatteryBankSpec,
    PowerTransformerSpec,
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    TransformerSpec,
)


# ==============================================================================
# 1. 33kV Switchgear Topology & Compartment Resolution
# ==============================================================================

class TestSwitchgear33kvTopology:
    """Verify 33kV macro archetype classification and compartment resolution."""

    def test_classify_board_33kv_gis(self) -> None:
        """33kV GIS lineups are classified as GIS_CUBICLE."""
        board = SwitchgearTopologyEngine.classify_board(
            switchgear_type="GIS 33kV",
            manufacturer="ALSTOM",
            model="GV3",
            rating="33kV",
        )
        assert board.archetype == SwitchgearArchetype.GIS_CUBICLE
        assert board.voltage_class == VoltageClass.KV_33
        assert "OVERVIEW FRONT (LHS)" in board.overview_compartments
        assert "OVERVIEW FRONT (RHS)" in board.overview_compartments
        assert "OVERVIEW REAR (LHS)" in board.overview_compartments
        assert "OVERVIEW TOP (LHS)" in board.overview_compartments

    def test_classify_board_33kv_vcb(self) -> None:
        """33kV VCB lineups are classified as VCB_CUBICLE."""
        board = SwitchgearTopologyEngine.classify_board(
            switchgear_type="VCB 33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
        )
        assert board.archetype == SwitchgearArchetype.VCB_CUBICLE
        assert board.voltage_class == VoltageClass.KV_33

    def test_resolve_panel_compartments_33kv_six_physical_plus_secondary(self) -> None:
        """33kV panels resolve all 6 physical compartments + secondary compartment (Decisions Q74)."""
        panel = SwitchgearPanelScanSpec(
            panel_no=1,
            name="INCOMING 1",
            panel_type="VCB",
            voltage_class=VoltageClass.KV_33,
            archetype=SwitchgearArchetype.VCB_CUBICLE,
        )
        comps = SwitchgearTopologyEngine.resolve_panel_compartments(
            archetype=SwitchgearArchetype.VCB_CUBICLE,
            panel=panel,
            voltage_class=VoltageClass.KV_33,
            is_33kv=True,
        )
        expected = [
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "CABLE ENTRY",
            "LINK BOX",
            "SECONDARY COMPARTMENT",
        ]
        assert list(comps) == expected

    def test_classify_board_33kv_tamco_vh3_cubicle(self) -> None:
        """TAMCO 33kV switchgear is automatically classified as VCB_CUBICLE with canonical 33kV overview pages."""
        board = SwitchgearTopologyEngine.classify_board(
            switchgear_type="33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
        )
        assert board.archetype == SwitchgearArchetype.VCB_CUBICLE
        assert board.voltage_class == VoltageClass.KV_33
        assert "OVERVIEW FRONT (LHS)" in board.overview_compartments
        assert "OVERVIEW CABLE CELLAR (LHS)" in board.overview_compartments
        assert len(board.overview_compartments) == 12

    def test_resolve_panel_compartments_33kv_bus_section_resolves_all_six(self) -> None:
        """33kV Bus Section and Bus Coupler bays resolve all 6 physical compartments + secondary."""
        panel_bs = SwitchgearPanelSpec(
            panel_no=2,
            name="BUS SECTION 33kV",
            panel_type="GIS",
        )
        comps = SwitchgearTopologyEngine.resolve_panel_compartments(
            archetype=SwitchgearArchetype.GIS_CUBICLE,
            panel=panel_bs,
            voltage_class=VoltageClass.KV_33,
            is_33kv=True,
        )
        assert len(comps) == 7
        assert comps == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "CABLE ENTRY",
            "LINK BOX",
            "SECONDARY COMPARTMENT",
        )


# ==============================================================================
# 2. Multi-Part Partitioning & Multi-Lineup Support
# ==============================================================================

class TestMultiPartPartitionPolicy33kv:
    """Verify MultiPartPartitionPolicy for 33kV and dual-voltage switchgear lineups."""

    def test_resolve_archetype_detects_gis_cubicle(self) -> None:
        """Resolve archetype recognizes GIS_CUBICLE across switchgears list."""
        swg_33 = SwitchgearSpec(
            switchgear_type="GIS",
            manufacturer="ALSTOM",
            model="GV3",
            rating="33kV",
        )
        swg_11 = SwitchgearSpec(
            switchgear_type="VCB",
            manufacturer="SCHNEIDER",
            model="PIX",
            rating="11kV",
        )
        pkg = SubstationEquipmentPackage(switchgears=(swg_33, swg_11))
        arch = MultiPartPartitionPolicy.resolve_archetype(pkg)
        assert arch == SwitchgearArchetype.GIS_CUBICLE

    def test_dual_voltage_ppu_partitioning(self, tmp_path: Path) -> None:
        """Dual-voltage PPU (33kV GIS 2 bays + 11kV VCB 3 bays) partitions into 7 chunks with voltage labels."""
        swg_33 = SwitchgearSpec(
            switchgear_type="GIS 33kV",
            manufacturer="ALSTOM",
            model="GV3",
            rating="33kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="INCOMING 33kV", panel_type="GIS"),
                SwitchgearPanelSpec(panel_no=2, name="BUS SECTION 33kV", panel_type="GIS"),
            ),
        )
        swg_11 = SwitchgearSpec(
            switchgear_type="VCB 11kV",
            manufacturer="TAMCO",
            model="GV4",
            rating="11kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="TX1 INCOMING", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=2, name="FEEDER 1", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=3, name="BUS COUPLER", panel_type="VCB"),
            ),
        )
        tx = PowerTransformerSpec(tx_id="Tx 1", rating_kva="30000", manufacturer="ABB")
        pkg = SubstationEquipmentPackage(
            switchgears=(swg_33, swg_11),
            transformers=(tx,),
        )

        sliced = SlicedSections(
            station="PPU TELUK KALONG 33kV",
            front_page=tmp_path / "front_page.docx",
            condition_pages=tmp_path / "condition_pages.docx",
            sticker_page=tmp_path / "sticker_page.docx",
        )

        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=pkg,
            sliced_sections=sliced,
            station="PPU TELUK KALONG 33kV",
            substation_info={"pe_number": 6, "name": "PPU TELUK KALONG 33kV", "date": "11-10-2026"},
            output_dir=tmp_path / "output",
        )

        # Output filename has 2-digit zero padding (Decision Q78)
        assert plan.output_filename.startswith("06. PPU TELUK KALONG 33kV")

        chunks = MultiPartPartitionPolicy.partition(plan)
        # Expected chunks (Ticket #130 Option A: separate overview chunks per switchgear lineup):
        # Part 01: Summary (Front Page, Census, Visual Defect Summary)
        # Part 02: Switchgear 1 (33kV GIS) Overview
        # Part 03: Panel 1 (33kV GIS)
        # Part 04: Panel 2 (33kV GIS)
        # Part 05: Switchgear 2 (11kV VCB) Overview
        # Part 06: Panel 1 (11kV VCB)
        # Part 07: Panel 2 (11kV VCB)
        # Part 08: Panel 3 (11kV VCB)
        # Part 09: TX and Condition (Power Transformer, Condition, Sticker)
        assert len(chunks) == 9

        labels = [c.label for c in chunks]
        assert labels[0] == "Part 01 - Summary"
        assert "Part 02 - Switchgear 1" in labels[1] and "Overview" in labels[1]
        assert "Part 03 - Panel 1 (33kV - INCOMING 33kV)" in labels[2] or "Part 03 - Panel 1 (INCOMING 33kV)" in labels[2]
        assert "Part 05 - Switchgear 2" in labels[4] and "Overview" in labels[4]
        assert "Part 06 - Panel 1 (11kV - TX1 INCOMING)" in labels[5]
        assert "Part 07 - Panel 2 (11kV - FEEDER 1)" in labels[6]
        assert labels[8] == "Part 09 - TX and Condition"

        # Verify summary chunk contains front page and census
        summary_types = [p.part_type for p in chunks[0].parts]
        assert PlanPartType.FRONT_PAGE in summary_types
        assert PlanPartType.CENSUS in summary_types

        # Verify equipment_id isolation: Chunk 3 has swg1 parts, Chunk 6 has swg2 parts
        p1_swg33_parts = chunks[2].parts
        assert all(getattr(p, "equipment_id", "") in ("swg1", "") for p in p1_swg33_parts)
        p1_swg11_parts = chunks[5].parts
        assert all(getattr(p, "equipment_id", "") in ("swg2", "") for p in p1_swg11_parts)

    def test_dual_voltage_11kv_switchgear_preserves_standard_compartments(self, tmp_path: Path) -> None:
        """In a dual-voltage substation, 11kV switchgear must preserve 11kV compartments and not inherit CABLE ENTRY or LINK BOX."""
        swg_33 = SwitchgearSpec(
            switchgear_type="GIS 33kV",
            manufacturer="ALSTOM",
            model="GV3",
            rating="33kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="INCOMING 33kV", panel_type="GIS"),
                SwitchgearPanelSpec(panel_no=2, name="BUS SECTION 33kV", panel_type="GIS"),
            ),
        )
        swg_11 = SwitchgearSpec(
            switchgear_type="VCB 11kV",
            manufacturer="TAMCO",
            model="GV4",
            rating="11kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="TX1 INCOMING", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=2, name="FEEDER 1", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=3, name="BUS COUPLER", panel_type="VCB"),
            ),
        )
        pkg = SubstationEquipmentPackage(
            switchgears=(swg_33, swg_11),
        )

        sliced = SlicedSections(
            station="PPU TELUK KALONG 33kV",
            front_page=tmp_path / "front_page.docx",
            condition_pages=tmp_path / "condition_pages.docx",
            sticker_page=tmp_path / "sticker_page.docx",
        )

        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=pkg,
            sliced_sections=sliced,
            station="PPU TELUK KALONG 33kV",
            substation_info={"pe_number": 6, "name": "PPU TELUK KALONG 33kV", "date": "11-10-2026"},
            output_dir=tmp_path / "output",
        )

        # 33kV station context is True
        assert plan.is_33kv is True

        # Inspect adapted scan items for swg1 (33kV GIS) vs swg2 (11kV VCB)
        swg1_items = [p for p in plan.parts if p.part_type == PlanPartType.SCAN_PAGE and p.equipment_id == "swg1" and not p.is_overview]
        swg2_items = [p for p in plan.parts if p.part_type == PlanPartType.SCAN_PAGE and p.equipment_id == "swg2" and not p.is_overview]

        # 33kV panels must contain CABLE ENTRY and LINK BOX
        swg1_comps = {p.component_name for p in swg1_items}
        assert "CABLE ENTRY" in swg1_comps
        assert "LINK BOX" in swg1_comps
        assert "BREAKER COMPARTMENT" in swg1_comps

        # 11kV panels must NOT contain CABLE ENTRY or LINK BOX
        swg2_comps = {p.component_name for p in swg2_items}
        assert "CABLE ENTRY" not in swg2_comps
        assert "LINK BOX" not in swg2_comps

        # 11kV Panel 3 (BUS COUPLER) must preserve bus coupler rules (no cable compartment)
        coupler_items = [p for p in swg2_items if p.sequence == "p03"]
        coupler_comps = [p.component_name for p in coupler_items]
        assert "BREAKER COMPARTMENT" in coupler_comps
        assert "REAR COMPARTMENT" in coupler_comps
        assert "BUSBAR COMPARTMENT" in coupler_comps
        assert "SECONDARY COMPARTMENT" in coupler_comps
        assert "CABLE COMPARTMENT" not in coupler_comps

    def test_resolve_archetype_and_evaluate_package_wrapped_containers(self) -> None:
        """Verify MultiPartPartitionPolicy unwrap handles TestsheetData and SubstationTestsheetPackage."""
        from src.testsheet.models import TestsheetData, SubstationTestsheetPackage

        swg = SwitchgearSpec(
            switchgear_type="VCB 11kV",
            manufacturer="TAMCO",
            panels=(SwitchgearPanelSpec(panel_no=1, name="FEEDER 1"),),
        )
        eq_pkg = SubstationEquipmentPackage(switchgears=(swg,))

        # 1. Wrapped in TestsheetData
        data_wrapper = TestsheetData(
            substation_number=1,
            substation_name_erms="PE TEST",
            equipment=eq_pkg,
        )
        arch = MultiPartPartitionPolicy.resolve_archetype(data_wrapper)
        assert arch == SwitchgearArchetype.VCB_CUBICLE
        is_mp, p_count = MultiPartPartitionPolicy.evaluate_package(data_wrapper)
        assert is_mp is True
        assert p_count == 2  # 1 summary + 1 panel

        # 2. Wrapped in SubstationTestsheetPackage
        sub_pkg = SubstationTestsheetPackage(
            testsheet_path=Path("dummy.xlsx"),
            unsorted_raw_data_dir=Path("."),
            station="PE TEST",
            month="10. OCTOBER",
            date_str="11-10-2026",
            substation_number=1,
            data=data_wrapper,
        )
        arch_sub = MultiPartPartitionPolicy.resolve_archetype(sub_pkg)
        assert arch_sub == SwitchgearArchetype.VCB_CUBICLE
        is_mp_sub, p_count_sub = MultiPartPartitionPolicy.evaluate_package(sub_pkg)
        assert is_mp_sub is True
        assert p_count_sub == 2

    def test_dynamic_omission_when_balance_of_plant_absent(self, tmp_path: Path) -> None:
        """When station lacks balance-of-plant assets, Chunk N+2 is dynamically omitted (Decision Q76)."""
        swg = SwitchgearSpec(
            switchgear_type="VCB 33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="BAY 1", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=2, name="BAY 2", panel_type="VCB"),
            ),
        )
        # No transformers, no lvdb, no battery banks
        pkg = SubstationEquipmentPackage(switchgears=(swg,))

        # Evaluate package telemetry
        is_multipart, count = MultiPartPartitionPolicy.evaluate_package(pkg)
        assert is_multipart is True
        # Part 01 (Summary) + 2 panels = 3 parts (TX and Condition omitted)
        assert count == 3

        # Plan with NO balance-of-plant slices (no condition, no sticker, no VI)
        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=pkg,
            sliced_sections=None,
            station="SSU SWITCHING STATION 33kV",
            substation_info={"pe_number": 12, "name": "SSU SWITCHING STATION 33kV"},
            output_dir=tmp_path / "output",
        )

        chunks = MultiPartPartitionPolicy.partition(plan)
        # Part 01 Summary + Part 02 Panel 1 + Part 03 Panel 2 = 3 chunks (Chunk N+2 omitted!)
        assert len(chunks) == 3
        chunk_labels = [c.label for c in chunks]
        assert chunk_labels == [
            "Part 01 - Summary",
            "Part 02 - Panel 1 (33kV - BAY 1)",
            "Part 03 - Panel 2 (33kV - BAY 2)",
        ]

    def test_evaluate_package_polymorphic_with_station_plan(self, tmp_path: Path) -> None:
        """evaluate_package polymorphically accepts FullReportStationPlan returning (True, chunk_count)."""
        swg = SwitchgearSpec(
            switchgear_type="VCB 33kV",
            panels=(SwitchgearPanelSpec(panel_no=1, name="BAY 1", panel_type="VCB"),),
        )
        pkg = SubstationEquipmentPackage(switchgears=(swg,))
        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=pkg,
            station="SSU TEST 33kV",
            substation_info={"pe_number": 1, "name": "SSU TEST 33kV"},
            output_dir=tmp_path,
        )
        is_mp, count = MultiPartPartitionPolicy.evaluate_package(plan)
        assert is_mp is True
        assert count == len(plan.chunks)


# ==============================================================================
# 3. Power Transformer Scan Adapter (>= 5 MVA)
# ==============================================================================

class TestPowerTransformerScanAdapter:
    """Verify PowerTransformerSpec auxiliary thermals and ultrasound readings (Decision Q75)."""

    def test_power_transformer_auxiliary_thermals(self) -> None:
        """Power transformers render MARSHALLING KIOSK, CONSERVATOR TANK, and COOLING FIN."""
        ptx = PowerTransformerSpec(
            tx_id="Tx 1",
            rating_kva="30000",
            manufacturer="TAMCO",
            hv_cable_type="XLPE",
            lv_cable_type="XLPE",
            body_photo=10,
            marshalling_kiosk_photo=11,
            conservator_photo=12,
            cooling_fin_photo=13,
            hv_cable_photo=14,
            lv_cable_photo=15,
            hv_ultrasound="18",
            hv_ultrasound_char="Corona",
        )

        adapter = TransformerScanAdapter(
            tx=ptx,
            substation_info={"name": "PMU GBID CABIN 33kV", "date": "11-10-2026"},
        )
        res = adapter.adapt()
        comp_names = [it.component_name for it in res.items]

        # Verify all canonical auxiliary thermals are present
        assert "OVERVIEW" in comp_names
        assert "MARSHALLING KIOSK" in comp_names
        assert "CONSERVATOR TANK" in comp_names
        assert "COOLING FIN" in comp_names
        assert "HV BUSHING" in comp_names
        assert "HV CABLE" in comp_names
        assert "LV BUSHING" in comp_names
        assert "LV CABLE" in comp_names

        # Verify templates used: auxiliaries map to tx-overview.docx
        for it in res.items:
            if it.component_name in ("MARSHALLING KIOSK", "CONSERVATOR TANK", "COOLING FIN"):
                assert it.template_name == "tx-overview.docx"
            elif "HV" in it.component_name:
                assert it.template_name == "tx-hv-sides.docx"
            elif "LV" in it.component_name:
                assert it.template_name == "tx-lv-sides.docx"

        # Verify ultrasound mapping on HV side
        hv_item = next(it for it in res.items if it.component_name == "HV BUSHING")
        assert hv_item.context["us"]["reading"] == "18"
        assert hv_item.context["us"]["char"] == "CORONA DISCHARGE"

    def test_power_transformer_body_photo_none_fallback(self) -> None:
        """When body_photo is None, falls back to photo_numbers[0] without UnboundLocalError."""
        from unittest.mock import MagicMock
        ptx = PowerTransformerSpec(
            tx_id="Tx 1",
            rating_kva="30000",
            body_photo=None,
            photo_numbers=(105, 106, 107),
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve_ir_photo.return_value = "ir_105.jpg"
        mock_resolver.resolve_visual_photo.return_value = "vis_105.jpg"

        adapter = TransformerScanAdapter(
            tx=ptx,
            substation_info={"name": "TEST PMU 33kV"},
            photo_resolver=mock_resolver,
        )
        ir, vis = adapter._resolve_photos_for_component("OVERVIEW")
        assert ir == "ir_105.jpg"
        assert vis == "vis_105.jpg"
        mock_resolver.resolve_ir_photo.assert_called_with(105)

    def test_power_transformer_photo_resolution_no_cross_contamination(self) -> None:
        """Verify PowerTransformerSpec photo resolver does not cross-contaminate or fall through to 11kV logic."""
        from unittest.mock import MagicMock
        ptx = PowerTransformerSpec(
            tx_id="Tx 1",
            rating_kva="30000",
            body_photo=10,
            marshalling_kiosk_photo=11,
            conservator_photo=12,
            cooling_fin_photo=13,
            hv_cable_photo=14,
            lv_cable_photo=15,
            photo_numbers=(10, 15, 14, 12, 13, 11),  # arbitrary photo sequence
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve_ir_photo.side_effect = lambda n: f"ir_{n}.jpg"
        mock_resolver.resolve_visual_photo.side_effect = lambda n: f"vis_{n}.jpg"

        adapter = TransformerScanAdapter(
            tx=ptx,
            substation_info={"name": "TEST PMU 33kV"},
            photo_resolver=mock_resolver,
        )

        # 1. Directly mapped 33kV components resolve their explicit photos
        assert adapter._resolve_photos_for_component("OVERVIEW") == ("ir_10.jpg", "vis_10.jpg")
        assert adapter._resolve_photos_for_component("MARSHALLING KIOSK") == ("ir_11.jpg", "vis_11.jpg")
        assert adapter._resolve_photos_for_component("CONSERVATOR TANK") == ("ir_12.jpg", "vis_12.jpg")
        assert adapter._resolve_photos_for_component("COOLING FIN") == ("ir_13.jpg", "vis_13.jpg")
        assert adapter._resolve_photos_for_component("HV CABLE") == ("ir_14.jpg", "vis_14.jpg")
        assert adapter._resolve_photos_for_component("LV CABLE") == ("ir_15.jpg", "vis_15.jpg")

        # 2. Components not recorded in 33kV testsheets MUST return ("", "") and NEVER fall through to 11kV index mapping
        # Previously, HV BUSHING fell through to comp_index_map[1] -> nums[1] = 15 (LV CABLE)
        # and LV BUSHING fell through to comp_index_map[3] -> nums[3] = 12 (CONSERVATOR TANK)
        assert adapter._resolve_photos_for_component("HV BUSHING") == ("", "")
        assert adapter._resolve_photos_for_component("LV BUSHING") == ("", "")
        assert adapter._resolve_photos_for_component("HV CABLE SPLIT") == ("", "")
        assert adapter._resolve_photos_for_component("OVERVIEW TOP") == ("", "")
        assert adapter._resolve_photos_for_component("UNKNOWN COMPONENT") == ("", "")

        # 3. When a photo is None, returns ("", "") without falling through
        ptx_partial = PowerTransformerSpec(
            tx_id="Tx 2",
            rating_kva="30000",
            body_photo=None,
            hv_cable_photo=None,
            photo_numbers=(),
        )
        adapter_partial = TransformerScanAdapter(
            tx=ptx_partial,
            substation_info={"name": "TEST PMU 33kV"},
            photo_resolver=mock_resolver,
        )
        assert adapter_partial._resolve_photos_for_component("OVERVIEW") == ("", "")
        assert adapter_partial._resolve_photos_for_component("HV CABLE") == ("", "")



# ==============================================================================
# 4. 2-Digit Filename Zero-Padding & Front Page Title Replacement
# ==============================================================================

class TestFormattingAndParityRules:
    """Verify Decisions Q77 and Q78."""

    def test_2digit_zero_padding_for_33kv(self, tmp_path: Path) -> None:
        """33kV output filename strictly uses 2-digit padding f'{pe_number:02d}.' (Decision Q78)."""
        swg = SwitchgearSpec(switchgear_type="GIS 33kV", panels=())
        pkg = SubstationEquipmentPackage(switchgears=(swg,))
        builder = FullReportPlanBuilder()

        plan_33kv = builder.build(
            package=pkg,
            station="SSU FLEXSYS CHEMICAL 33kV",
            substation_info={"pe_number": 6, "name": "SSU FLEXSYS CHEMICAL 33kV"},
            output_dir=tmp_path,
        )
        assert plan_33kv.output_filename.startswith("06. SSU FLEXSYS CHEMICAL 33kV")

    def test_3digit_zero_padding_preserved_for_11kv(self, tmp_path: Path) -> None:
        """11kV output filename strictly preserves 3-digit padding f'{pe_number:03d}.'."""
        swg = SwitchgearSpec(switchgear_type="RMU", rating="11kV", panels=())
        pkg = SubstationEquipmentPackage(switchgears=(swg,))
        builder = FullReportPlanBuilder()

        plan_11kv = builder.build(
            package=pkg,
            station="PE TALAPIA",
            substation_info={"pe_number": 5, "name": "PE TALAPIA"},
            output_dir=tmp_path,
        )
        assert plan_11kv.output_filename.startswith("005. PE TALAPIA")

    def test_front_page_title_replacement(self, tmp_path: Path) -> None:
        """Front page docx replaces QUICK SCANNING REPORT with FULL SCANNING REPORT (Decision Q77)."""
        import docx

        front_docx = tmp_path / "mock_front.docx"
        doc = docx.Document()
        doc.add_heading("QUICK SCANNING REPORT", level=1)
        doc.add_paragraph("Site Inspection: QUICK SCANNING REPORT 2026")
        table = doc.add_table(rows=1, cols=1)
        table.rows[0].cells[0].text = "Header: QUICK SCANNING REPORT"
        doc.save(str(front_docx))

        part_item = PlanPartItem(
            part_type=PlanPartType.FRONT_PAGE,
            part_name="Front Page",
            source_path=front_docx,
            is_sliced=True,
        )

        output_part = tmp_path / "rendered_front.docx"
        part_item.render(output_part)

        # Inspect rendered output
        doc_res = docx.Document(str(output_part))
        all_text = " ".join([p.text for p in doc_res.paragraphs] + [c.text for tbl in doc_res.tables for row in tbl.rows for c in row.cells])
        assert "QUICK SCANNING REPORT" not in all_text
        assert "FULL SCANNING REPORT" in all_text

    def test_front_page_title_replacement_split_across_runs_preserves_formatting(self, tmp_path: Path) -> None:
        """When Word splits QUICK SCANNING REPORT across runs, formatting is strictly preserved."""
        import docx

        front_docx = tmp_path / "mock_split_front.docx"
        doc = docx.Document()
        p = doc.add_paragraph()
        r1 = p.add_run("QUICK ")
        r1.bold = True
        r2 = p.add_run("SCANNING REPORT")
        r2.bold = True
        doc.save(str(front_docx))

        part_item = PlanPartItem(
            part_type=PlanPartType.FRONT_PAGE,
            part_name="Front Page",
            source_path=front_docx,
            is_sliced=True,
        )

        output_part = tmp_path / "rendered_split_front.docx"
        part_item.render(output_part)

        doc_res = docx.Document(str(output_part))
        p_res = doc_res.paragraphs[0]
        assert "QUICK SCANNING REPORT" not in p_res.text
        assert "FULL SCANNING REPORT" in p_res.text
        # Bold formatting on the first run is strictly preserved
        assert p_res.runs[0].bold is True

    def test_is_33kv_substation_singular_switchgear(self) -> None:
        """Verify FullReportWorkflow._is_33kv_substation detects 33kV with singular switchgear fallback."""
        from unittest.mock import MagicMock
        from src.workflows.full_report import FullReportWorkflow
        wf = FullReportWorkflow(compiler=FakeDocumentCompiler())

        swg = SwitchgearSpec(switchgear_type="GIS 33kV", panels=())
        pkg = MagicMock()
        pkg.name = "PE KAMPUNG"
        pkg.substation_info = {"name": "PE KAMPUNG"}
        eq_mock = MagicMock()
        eq_mock.switchgears = ()
        eq_mock.switchgear = swg
        eq_mock.voltage_class = None
        eq_mock.transformers = ()
        pkg.data.equipment = eq_mock

        assert wf._is_33kv_substation(pkg) is True



# ==============================================================================
# 5. End-to-End Multi-Part Compilation for 33kV Station
# ==============================================================================

class TestFullReport33kvCompilationE2E:
    """Verify FullReportComposer successfully compiles modular docx files for 33kV station."""

    def test_compile_33kv_multipart_station(self, tmp_path: Path) -> None:
        """FullReportComposer compiles all chunks for a 33kV station with permanent file retention."""
        swg = SwitchgearSpec(
            switchgear_type="VCB 33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="BAY 1", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=2, name="BAY 2", panel_type="VCB"),
            ),
        )
        tx = PowerTransformerSpec(tx_id="Tx 1", rating_kva="30000")
        pkg = SubstationEquipmentPackage(
            switchgears=(swg,),
            transformers=(tx,),
        )

        out_dir = tmp_path / "FULL REPORT" / "GBID" / "10. OCTOBER" / "11-10-2026"
        out_dir.mkdir(parents=True, exist_ok=True)

        sliced = SlicedSections(
            station="PMU GBID CABIN 33kV",
            front_page=tmp_path / "front.docx",
            condition_pages=tmp_path / "cond.docx",
            sticker_page=tmp_path / "sticker.docx",
        )

        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=pkg,
            sliced_sections=sliced,
            station="PMU GBID CABIN 33kV",
            substation_info={"pe_number": 7, "name": "PMU GBID CABIN 33kV", "date": "11-10-2026"},
            output_dir=out_dir,
        )

        assert plan.is_multipart is True
        # Summary (1) + 2 bays + TX and Condition (1) = 4 chunks
        assert len(plan.chunks) == 4

        # Run compilation
        composer = FullReportComposer(compiler=FakeDocumentCompiler())
        res = composer.compose(plan)
        compiled_paths = res.chunk_paths

        # 4 docx files produced in destination directory
        assert len(compiled_paths) == 4
        for p in compiled_paths:
            assert p.is_file()
            assert p.parent == out_dir
            # Verify filename matches 07. PMU GBID CABIN 33kV
            assert p.name.startswith("07. PMU GBID CABIN 33kV")

        # Verify permanent retention (ADR 0005 & Decision Q79)
        docx_files = list(out_dir.glob("*.docx"))
        assert len(docx_files) == 4


# ==============================================================================
# 6. Dual-Voltage Lineup Defect Isolation & Wrapped Containers (Review Hardening)
# ==============================================================================

class TestDualVoltageLineupIsolationAndWrappedContainers:
    """Verify defect interleaving isolation and wrapped container handling in dual-voltage stations."""

    def test_defect_interleaving_dual_voltage_lineups_identical_panel_numbers(self) -> None:
        """When 33kV (swg1) and 11kV (swg2) both have active CBM defects on Panel 1, defects are not cross-wired."""
        d1 = CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg1",
            sequence="p01",
            equipment_id="GIS01",
            defect_area="CABLE_COMPARTMENT",
            filename="swg1_p01_GIS01_CABLE_COMPARTMENT_01.docx",
            slice_path=Path("swg1_p01.docx"),
        )
        d2 = CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg2",
            sequence="p01",
            equipment_id="VCB01",
            defect_area="CABLE_COMPARTMENT",
            filename="swg2_p01_VCB01_CABLE_COMPARTMENT_01.docx",
            slice_path=Path("swg2_p01.docx"),
        )

        item_swg1 = ScanRenderItem(
            page_name="SWG1 P1",
            template_name="tpl.docx",
            template_path=Path("tpl.docx"),
            context={"panel": {"panel_no": 1, "feeder_no": "GIS01"}},
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p01",
            panel_no=1,
            equipment_id="swg1",
        )
        item_swg2 = ScanRenderItem(
            page_name="SWG2 P1",
            template_name="tpl.docx",
            template_path=Path("tpl.docx"),
            context={"panel": {"panel_no": 1, "feeder_no": "VCB01"}},
            equipment_category="swg",
            component_name="CABLE COMPARTMENT",
            sequence="p01",
            panel_no=1,
            equipment_id="swg2",
        )

        policy = DefectInterleavingPolicy()
        # Pass d2 first to test that swg1 does not greedily consume d2
        res = policy.interleave(
            scan_items=[item_swg1, item_swg2],
            sliced_defects=[d2, d1],
        )

        assert len(res.parts) == 2
        # swg1 Panel 1 must be replaced strictly by swg1 defect
        assert res.parts[0].part_name == "swg1_p01_GIS01_CABLE_COMPARTMENT_01.docx"
        assert res.parts[0].equipment_id == "swg1"
        assert res.parts[0].action_type == InterleavingActionType.REPLACE

        # swg2 Panel 1 must be replaced strictly by swg2 defect
        assert res.parts[1].part_name == "swg2_p01_VCB01_CABLE_COMPARTMENT_01.docx"
        assert res.parts[1].equipment_id == "swg2"
        assert res.parts[1].action_type == InterleavingActionType.REPLACE

        # Zero orphans
        assert len(res.orphans) == 0

    def test_defect_interleaving_multi_lineup_overview_isolation(self) -> None:
        """Overview substitution on swg1 must not consume or swallow swg2 overview defect."""
        d1_ov = CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg1",
            sequence="p00",
            equipment_id="GIS",
            defect_area="OVERVIEW",
            filename="swg1_p00_GIS_OVERVIEW_01.docx",
            slice_path=Path("swg1_ov.docx"),
        )
        d2_ov = CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg2",
            sequence="p00",
            equipment_id="VCB",
            defect_area="OVERVIEW",
            filename="swg2_p00_VCB_OVERVIEW_01.docx",
            slice_path=Path("swg2_ov.docx"),
        )

        item_swg1_ov = ScanRenderItem(
            page_name="SWG1 OV",
            template_name="tpl.docx",
            template_path=Path("tpl.docx"),
            context={},
            equipment_category="swg",
            component_name="OVERVIEW FRONT",
            sequence="p00",
            is_overview=True,
            equipment_id="swg1",
        )
        item_swg2_ov = ScanRenderItem(
            page_name="SWG2 OV",
            template_name="tpl.docx",
            template_path=Path("tpl.docx"),
            context={},
            equipment_category="swg",
            component_name="OVERVIEW FRONT",
            sequence="p00",
            is_overview=True,
            equipment_id="swg2",
        )

        policy = DefectInterleavingPolicy()
        res = policy.interleave(
            scan_items=[item_swg1_ov, item_swg2_ov],
            sliced_defects=[d1_ov, d2_ov],
        )

        assert len(res.parts) == 2
        assert res.parts[0].part_name == "swg1_p00_GIS_OVERVIEW_01.docx"
        assert res.parts[0].equipment_id == "swg1"
        assert res.parts[0].action_type == InterleavingActionType.REPLACE

        assert res.parts[1].part_name == "swg2_p00_VCB_OVERVIEW_01.docx"
        assert res.parts[1].equipment_id == "swg2"
        assert res.parts[1].action_type == InterleavingActionType.REPLACE

    def test_defect_interleaving_multi_transformer_overview_isolation(self) -> None:
        """Overview substitution on tx1 must not consume or swallow tx2 overview defect."""
        d1_ov = CbmDefectSliceMetadata(
            equipment_category="tx",
            equipment_instance="tx1",
            sequence="s00",
            equipment_id="TX1",
            defect_area="OVERVIEW",
            filename="tx1_s00_TX1_OVERVIEW_01.docx",
            slice_path=Path("tx1_ov.docx"),
        )
        d2_ov = CbmDefectSliceMetadata(
            equipment_category="tx",
            equipment_instance="tx2",
            sequence="s00",
            equipment_id="TX2",
            defect_area="OVERVIEW",
            filename="tx2_s00_TX2_OVERVIEW_01.docx",
            slice_path=Path("tx2_ov.docx"),
        )

        item_tx1_ov = ScanRenderItem(
            page_name="TX1 OV",
            template_name="tx-overview.docx",
            template_path=Path("tx-overview.docx"),
            context={},
            equipment_category="tx",
            component_name="OVERVIEW",
            sequence="s00",
            is_overview=True,
            equipment_id="tx1",
        )
        item_tx2_ov = ScanRenderItem(
            page_name="TX2 OV",
            template_name="tx-overview.docx",
            template_path=Path("tx-overview.docx"),
            context={},
            equipment_category="tx",
            component_name="OVERVIEW",
            sequence="s00",
            is_overview=True,
            equipment_id="tx2",
        )

        policy = DefectInterleavingPolicy()
        res = policy.interleave(
            scan_items=[item_tx1_ov, item_tx2_ov],
            sliced_defects=[d1_ov, d2_ov],
        )

        assert len(res.parts) == 2
        assert res.parts[0].part_name == "tx1_s00_TX1_OVERVIEW_01.docx"
        assert res.parts[0].equipment_id == "tx1"
        assert res.parts[1].part_name == "tx2_s00_TX2_OVERVIEW_01.docx"
        assert res.parts[1].equipment_id == "tx2"

    def test_full_report_plan_builder_wrapped_testsheet_data(self, tmp_path: Path) -> None:
        """FullReportPlanBuilder.build() unwraps TestsheetData to SubstationEquipmentPackage without crashing."""
        swg = SwitchgearSpec(
            switchgear_type="VCB 33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
            panels=(
                SwitchgearPanelSpec(panel_no=1, name="BAY 1", panel_type="VCB"),
                SwitchgearPanelSpec(panel_no=2, name="BAY 2", panel_type="VCB"),
            ),
        )
        eq_pkg = SubstationEquipmentPackage(switchgears=(swg,))
        data_wrapper = TestsheetData(
            substation_number=7,
            substation_name_erms="PMU GBID CABIN 33kV",
            station_name="PMU GBID CABIN 33kV",
            equipment=eq_pkg,
        )

        builder = FullReportPlanBuilder()
        plan = builder.build(
            package=data_wrapper,
            station="PMU GBID CABIN 33kV",
            output_dir=tmp_path / "output",
        )

        assert plan.is_33kv is True
        assert plan.pe_number == 7
        assert plan.output_filename.startswith("07. PMU GBID CABIN 33kV")
        # Ensure switchgear scanning pages were generated
        swg_parts = [p for p in plan.parts if p.is_switchgear]
        assert len(swg_parts) > 0

        # MultiPart partitioning must correctly unwrap and yield panel chunks
        chunks = MultiPartPartitionPolicy.partition(plan)
        assert len(chunks) == 3  # Part 01 Summary + Part 02 Panel 1 + Part 03 Panel 2

    def test_evaluate_package_and_build_singular_transformer(self) -> None:
        """MultiPartPartitionPolicy.evaluate_package respects singular transformer attribute for BOP."""
        swg = SwitchgearSpec(
            switchgear_type="VCB 11kV",
            panels=(SwitchgearPanelSpec(panel_no=1, name="P1"),),
        )
        tx = TransformerSpec(tx_id="Tx 1")

        # Mock package with singular transformer attribute
        class MockPackageWithSingularTx:
            def __init__(self):
                self.switchgears = (swg,)
                self.transformers = ()
                self.transformer = tx
                self.lvdb_specs = ()
                self.battery_banks = ()

        pkg = MockPackageWithSingularTx()
        is_mp, count = MultiPartPartitionPolicy.evaluate_package(pkg)
        assert is_mp is True
        # 1 summary + 1 panel + 1 BOP chunk = 3 parts
        assert count == 3

    def test_switchgear_scan_adapter_preserves_33kv_when_classified_33kv(self) -> None:
        """When SwitchgearTopologyEngine classifies switchgear as 33kV, is_33kv is True regardless of default arg."""
        swg = SwitchgearSpec(
            switchgear_type="GIS 33kV",
            manufacturer="ALSTOM",
            model="GV3",
            rating="33kV",
            panels=(SwitchgearPanelSpec(panel_no=1, name="BAY 1", panel_type="GIS"),),
        )
        # Explicitly pass is_33kv=False to test that voltage_class KV_33 overrides it
        ad = SwitchgearScanAdapter(swg=swg, is_33kv=False)
        assert ad.voltage_class == VoltageClass.KV_33
        assert ad.is_33kv is True

    def test_switchgear_scan_adapter_cable_compartment_uses_cable_specific_readings(
        self, tmp_path: Path
    ) -> None:
        """Verify SwitchgearScanAdapter uses cable-specific TEV/US readings for Cable and Rear compartments."""
        panel = SwitchgearPanelSpec(
            panel_no=1,
            name="FEEDER 1",
            panel_type="VCB",
            us_reading="2.0",
            tev_reading="10.0",
            tev_ppc="5",
            cable_us_reading="6.5",
            cable_tev_reading="25.0",
            cable_tev_ppc="20",
        )
        swg = SwitchgearSpec(
            switchgear_type="VCB 33kV",
            manufacturer="TAMCO",
            model="VH3",
            rating="33kV",
            panels=(panel,),
        )
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        (templates_dir / "swg-overview.docx").write_text("dummy")
        (templates_dir / "swg-panel.docx").write_text("dummy")

        adapter = SwitchgearScanAdapter(
            swg=swg,
            substation_info={"substation_name": "TEST", "voltage_type": "33kV"},
            is_33kv=True,
            templates_dir=templates_dir,
        )
        res = adapter.adapt()
        comp_items = {item.component_name: item for item in res.items if not item.is_overview}

        # Breaker Compartment gets breaker readings
        breaker_item = comp_items["BREAKER COMPARTMENT"]
        assert breaker_item.context["panel"]["us"]["reading"] == "2"
        assert breaker_item.context["panel"]["tev"]["reading"] == "10"
        assert breaker_item.context["panel"]["tev"]["ppc"] == "5"

        # Cable Compartment gets cable-specific readings
        cable_item = comp_items["CABLE COMPARTMENT"]
        assert cable_item.context["panel"]["us"]["reading"] == "7"
        assert cable_item.context["panel"]["tev"]["reading"] == "25"
        assert cable_item.context["panel"]["tev"]["ppc"] == "20"


def test_full_report_ssu_lynas_compiles_intermediate_parts_and_chunks(tmp_path: Path) -> None:
    """Regression test (Ticket #138): SSU LYNAS 33kV intermediate parts and chunks compile without [Errno 22]."""
    from src.testsheet.parsers.ppu import PpuTestsheetParser
    from src.testsheet.extractor import TestsheetData
    from src.testsheet.models import (
        SubstationEquipmentPackage,
        SwitchgearSpec,
        SwitchgearPanelSpec,
    )

    ts_path = Path(
        r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\GEBENG\01. OCTOBER\07-10-2026\03. SSU LYNAS 33kV (VI).xlsx"
    )

    if ts_path.is_file():
        parser = PpuTestsheetParser()
        data = parser.extract_testsheet_data(ts_path)
    else:
        # Synthetic fallback with identical switchgear and panel topology
        panels = (
            SwitchgearPanelSpec(panel_no=1, name="SPARE", panel_feeder_no="5S5"),
            SwitchgearPanelSpec(panel_no=2, name="PMU GBNG (1L5)", panel_feeder_no="3S5"),
            SwitchgearPanelSpec(panel_no=3, name="CONSUMER 1", panel_feeder_no="1S5"),
            SwitchgearPanelSpec(panel_no=4, name="BUS - COUPLER", panel_feeder_no="1W0"),
            SwitchgearPanelSpec(panel_no=5, name="BUS - SECTION", panel_feeder_no="1S0"),
            SwitchgearPanelSpec(panel_no=6, name="33kV TRANSITION\n(BUS - SECTION)", panel_feeder_no="1S0"),
            SwitchgearPanelSpec(panel_no=7, name="CONSUMER 2", panel_feeder_no="2S5"),
            SwitchgearPanelSpec(panel_no=8, name="PMU GBID (2L5)", panel_feeder_no="4S5"),
            SwitchgearPanelSpec(panel_no=9, name="SPARE", panel_feeder_no="6S5"),
        )
        swg = SwitchgearSpec(
            switchgear_type="GIS",
            manufacturer="EPE",
            rating="36kV",
            panels=panels,
        )
        data = TestsheetData(
            substation_number=3,
            substation_name_erms="SSU LYNAS 33kV",
            station_name="SSU LYNAS 33kV",
            equipment=SubstationEquipmentPackage(switchgears=(swg,)),
        )

    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=data,
        station=data.station_name,
        output_dir=out_dir,
    )

    assert plan.is_33kv is True
    assert plan.is_multipart is True
    assert len(plan.chunks) == 10

    # Verify chunk labels and filenames have no control characters, colons, or un-sanitized newlines
    for c in plan.chunks:
        assert "\n" not in c.label
        assert "\r" not in c.label
        assert "\t" not in c.label
        assert ":" not in c.label
        assert ":" not in c.output_filename
        assert "\n" not in c.output_filename
        assert "\r" not in c.output_filename
        assert "\t" not in c.output_filename
        assert c.destination_path.name == c.output_filename

    # Chunk 7 (Panel 6) must cleanly sanitize the transition bus section
    chunk6 = plan.chunks[6]  # Index 6 is Part 07 - Panel 6
    assert "33kV TRANSITION (BUS - SECTION)" in chunk6.label
    assert "33kV TRANSITION (BUS - SECTION)" in chunk6.output_filename

    # Render intermediate scan parts: must execute without OSError: [Errno 22] Invalid argument
    rendered_dir = tmp_path / "rendered"
    rendered_paths = plan.render_all(rendered_dir)
    assert len(rendered_paths) > 0
    for p in rendered_paths:
        assert p.is_file()
        for forbidden in '<>:"/\\|?*':
            assert forbidden not in p.name
        for ch in p.name:
            assert ord(ch) >= 32

    # Compile chunks using headless FakeDocumentCompiler: all 10 chunks compile successfully to disk
    composer = FullReportComposer(compiler=FakeDocumentCompiler())
    res = composer.compose(plan, temp_dir=rendered_dir, base_dir=tmp_path)
    assert res.is_multipart is True
    assert len(res.chunk_paths) == 10
    for cp in res.chunk_paths:
        assert cp.is_file()
        assert cp.stat().st_size > 0


