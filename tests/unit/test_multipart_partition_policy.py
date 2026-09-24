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
