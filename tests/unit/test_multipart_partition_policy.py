"""Unit tests for MultiPartPartitionPolicy chunk destination paths and panel name sanitization (#64)."""

from pathlib import Path

from src.full_report.plan_builder import (
    FullReportPlanBuilder,
    MultiPartPartitionPolicy,
    PlanDocumentChunk,
)
from src.full_report.slicer import SlicedSections
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


def _make_vcb_package_with_slash_panels() -> SubstationEquipmentPackage:
    """Create VCB package with panels containing path-unsafe characters."""
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="SCHNEIDER",
        model="PIX",
        panels=(
            SwitchgearPanelSpec(
                panel_no=1,
                name="INCOMING 1",
                panel_type="VCB",
            ),
            SwitchgearPanelSpec(
                panel_no=2,
                name="B/S",  # Slashes in panel name (Bus Section)
                panel_type="VCB",
            ),
            SwitchgearPanelSpec(
                panel_no=3,
                name="Panel/1",  # Another slash pattern
                panel_type="VCB",
            ),
            SwitchgearPanelSpec(
                panel_no=4,
                name=r"FEEDER\2",  # Backslash
                panel_type="VCB",
            ),
            SwitchgearPanelSpec(
                panel_no=5,
                name="11kV:BUS",  # Colon
                panel_type="VCB",
            ),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="1000")
    return SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))


def test_multipart_partition_sanitizes_panel_names(tmp_path: Path) -> None:
    """Ensure panels with path characters produce flat filenames without subdirectories."""
    dest_dir = tmp_path / "output_reports"
    dest_dir.mkdir(parents=True, exist_ok=True)

    pkg = _make_vcb_package_with_slash_panels()
    sliced = SlicedSections(
        station="PE TEST VCB",
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
        station="PE TEST VCB",
        substation_info={"name_erms": "PE TEST VCB", "date": "24-09-2026"},
        output_dir=dest_dir,
    )

    chunks = MultiPartPartitionPolicy.partition(plan)
    # Summary (1) + 5 panels + TX/Condition (1) = 7 chunks
    assert len(chunks) == 7

    # Verify each chunk
    for chunk in chunks:
        # Crucial invariant: destination_path.parent MUST strictly be dest_dir
        assert chunk.destination_path.parent == dest_dir, (
            f"Chunk {chunk.label} destination {chunk.destination_path} created subdirectories!"
        )
        # File name must not contain path separators
        assert "/" not in chunk.output_filename
        assert "\\" not in chunk.output_filename
        assert ":" not in chunk.output_filename

    # Specific panel checks
    panel_chunks = {c.chunk_index: c for c in chunks}

    # Panel 2: B/S -> B-S
    p2 = panel_chunks[3]  # Part 01 is summary, Part 02 is Panel 1, Part 03 is Panel 2 (B/S)
    assert "B-S" in p2.label
    assert "B-S" in p2.output_filename
    assert "/" not in p2.output_filename

    # Panel 3: Panel/1 -> Panel-1
    p3 = panel_chunks[4]
    assert "Panel-1" in p3.label
    assert "Panel-1" in p3.output_filename

    # Panel 4: FEEDER\2 -> FEEDER-2
    p4 = panel_chunks[5]
    assert "FEEDER-2" in p4.label
    assert "\\" not in p4.output_filename

    # Panel 5: 11kV:BUS -> 11kV-BUS
    p5 = panel_chunks[6]
    assert "11kV-BUS" in p5.label
    assert ":" not in p5.output_filename


def test_multipart_partition_dual_switchgear_option_a(tmp_path: Path) -> None:
    """Ticket #130: Dual-switchgear produces dedicated overview chunks per lineup prioritizing 33kV before 11kV."""
    dest_dir = tmp_path / "output_reports"
    dest_dir.mkdir(parents=True, exist_ok=True)

    swg_33 = SwitchgearSpec(
        switchgear_type="GIS",
        manufacturer="TAMCO",
        model="GV3",
        rating="36kV",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="BURSTING PANEL", panel_type="GIS"),
            SwitchgearPanelSpec(panel_no=2, name="FEEDER 1", panel_type="GIS"),
        ),
    )
    swg_11 = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH4",
        rating="12kV",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMER TX", panel_type="VCB"),
            SwitchgearPanelSpec(panel_no=2, name="SPARE", panel_type="VCB"),
            SwitchgearPanelSpec(panel_no=3, name="FEEDER 2", panel_type="VCB"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="1000")
    # Provide 11kV first to verify voltage priority sorting ensures 33kV is partitioned first
    pkg = SubstationEquipmentPackage(switchgears=(swg_11, swg_33), transformers=(tx,))

    # evaluate_package: 1 Summary + 2 Overview chunks (1 per lineup) + 5 panels + 1 TX = 9
    is_multi, count = MultiPartPartitionPolicy.evaluate_package(pkg)
    assert is_multi is True
    assert count == 9

    sliced = SlicedSections(
        station="PMU DUAL SWG TEST",
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
        station="PMU DUAL SWG TEST",
        substation_info={"name_erms": "PMU DUAL SWG TEST", "date": "25-10-2026"},
        output_dir=dest_dir,
    )

    chunks = MultiPartPartitionPolicy.partition(plan)
    assert len(chunks) == 9

    labels = [c.label for c in chunks]
    assert labels[0] == "Part 01 - Summary"
    assert labels[1] == "Part 02 - Switchgear 1 (33kV - GIS) Overview"
    assert labels[2] == "Part 03 - Panel 1 (33kV - BURSTING PANEL)"
    assert labels[3] == "Part 04 - Panel 2 (33kV - FEEDER 1)"
    assert labels[4] == "Part 05 - Switchgear 2 (11kV - VCB) Overview"
    assert labels[5] == "Part 06 - Panel 1 (11kV - INCOMER TX)"
    assert labels[6] == "Part 07 - Panel 2 (11kV - SPARE)"
    assert labels[7] == "Part 08 - Panel 3 (11kV - FEEDER 2)"
    assert labels[8] == "Part 09 - TX and Condition"


def test_census_builder_dual_switchgear_voltage_priority() -> None:
    """Ticket #130: Census summary table consistently orders 33kV switchgear & panels before 11kV."""
    from src.full_report.census import ExecutiveSummaryCensusBuilder

    swg_11 = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH4",
        rating="12kV",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMER 11kV", panel_type="VCB"),
        ),
    )
    swg_33 = SwitchgearSpec(
        switchgear_type="GIS",
        manufacturer="TAMCO",
        model="GV3",
        rating="36kV",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="FEEDER 33kV", panel_type="GIS"),
        ),
    )
    pkg = SubstationEquipmentPackage(switchgears=(swg_11, swg_33))
    cb = ExecutiveSummaryCensusBuilder()
    rows = cb.build_census_rows(pkg)

    overview_rows = [r for r in rows if r.is_overview]
    assert len(overview_rows) >= 2
    # 33kV GIS must be the first overview group
    assert overview_rows[0].eq_group_key == "swg_1_overview"
    assert "36kV GIS" in overview_rows[0].equipment or "33kV GIS" in overview_rows[0].equipment
    # 11kV VCB must follow as second overview group
    vcb_row = next(r for r in overview_rows if r.eq_group_key == "swg_2_overview")
    assert "VCB" in vcb_row.equipment


def test_multipart_partition_live_jengka_chunk_structure() -> None:
    """Ticket #130: Live end-to-end plan chunk sequence verification on CJEN/PMU/J00001 (PMU JENGKA)."""
    from src.testsheet.parsers.ppu import PpuTestsheetParser
    import pytest

    ts_path = Path(r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\JENGKA\01. OCTOBER\25-10-2026\40. PMU JENGKA 132-11-33kV (VI).xlsx")
    if not ts_path.exists():
        pytest.skip("Testsheet missing for PMU JENGKA")

    data = PpuTestsheetParser().extract_testsheet_data(ts_path)
    is_multi, count = MultiPartPartitionPolicy.evaluate_package(data.equipment)
    assert is_multi is True
    # 1 Summary + 1 33kV Overview + 8 33kV Panels + 1 11kV Overview + 29 11kV Panels + 1 TX/Condition = 41
    assert count == 41

    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=data.equipment,
        station="PMU JENGKA",
        substation_info={"name_erms": "PMU JENGKA", "date": "25-10-2026"},
        output_dir=Path("tmp_test"),
    )

    assert len(plan.chunks) == 41
    assert plan.chunks[0].label == "Part 01 - Summary"
    assert plan.chunks[1].label == "Part 02 - Switchgear 1 (33kV - GIS) Overview"
    assert plan.chunks[2].label == "Part 03 - Panel 1 (33kV - BURSTING PANEL)"
    assert plan.chunks[9].label == "Part 10 - Panel 8 (33kV - SPARE)"
    assert plan.chunks[10].label == "Part 11 - Switchgear 2 (11kV - VCB) Overview"
    assert plan.chunks[11].label == "Part 12 - Panel 1 (11kV - INCOMER TX)"
    assert plan.chunks[39].label == "Part 40 - Panel 29 (11kV - LOCAL TX)"
    assert plan.chunks[40].label == "Part 41 - TX and Condition"

