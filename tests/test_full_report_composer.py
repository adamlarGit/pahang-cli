"""Unit tests for FullReportComposer module (Ticket #34 / T6.1).

Verifies:
1. Implements FullReportComposer(compiler: DocumentCompiler | None = None).
2. Supports swappable compiler seam (WordComDocumentCompiler vs FakeDocumentCompiler).
3. Compiles all planned parts into master document via compiler.compile(parts, output_path).
4. Automatically cleans up temp_parts/ in a finally block unless keep_temp is set per D14.
5. Preserves temp_parts/ when keep_temp=True per D14.
6. Cleans up temp_parts/ even when compilation raises an error.
7. End-to-end compilation flow with FakeDocumentCompiler on realistic FullReportStationPlan.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.full_report.composer import (
    FullReportCompilationResult,
    FullReportComposer,
    composer_temp_workspace,
)
from src.full_report.plan_builder import (
    FullReportPlanBuilder,
    FullReportStationPlan,
    PlanPartItem,
    PlanPartType,
)
from src.full_report.slicer import SlicedSections, get_temp_parts_dir
from src.quick_report.compiler import (
    DocumentCompiler,
    FakeDocumentCompiler,
    WordComDocumentCompiler,
)
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


def _make_dummy_plan(tmp_path: Path) -> FullReportStationPlan:
    """Create a minimal FullReportStationPlan with stub docx files."""
    part1 = tmp_path / "part1.docx"
    part2 = tmp_path / "part2.docx"
    part1.write_bytes(b"PK\x03\x04part1")
    part2.write_bytes(b"PK\x03\x04part2")

    items = (
        PlanPartItem(
            part_type=PlanPartType.FRONT_PAGE,
            part_name="Front Page",
            source_path=part1,
            is_sliced=True,
        ),
        PlanPartItem(
            part_type=PlanPartType.STICKER,
            part_name="Sticker Page",
            source_path=part2,
            is_sliced=True,
        ),
    )

    out_dir = tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026"
    out_file = "005. PE TALAPIA (IR+VI).docx"
    final_path = out_dir / out_file

    return FullReportStationPlan(
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        month_folder="08. AUGUST",
        output_dir=out_dir,
        output_filename=out_file,
        final_output_path=final_path,
        package=SubstationEquipmentPackage(),
        parts=items,
    )


def test_composer_init_default_compiler() -> None:
    """FullReportComposer defaults to WordComDocumentCompiler when compiler is None."""
    composer = FullReportComposer()
    assert isinstance(composer.compiler, WordComDocumentCompiler)


def test_composer_init_custom_compiler() -> None:
    """FullReportComposer accepts a custom DocumentCompiler implementation."""
    fake = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake)
    assert composer.compiler is fake
    assert isinstance(composer.compiler, DocumentCompiler)


def test_composer_swappable_compiler_seam() -> None:
    """Compiler seam can be hot-swapped or injected for headless CI execution."""
    fake1 = FakeDocumentCompiler()
    fake2 = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake1)
    assert composer.compiler is fake1
    composer.compiler = fake2
    assert composer.compiler is fake2


def test_composer_temp_workspace_cleanup_by_default(tmp_path: Path) -> None:
    """composer_temp_workspace creates directory and cleans it up upon exit when keep_temp=False."""
    target_temp = tmp_path / "temp_parts"
    with composer_temp_workspace(temp_dir=target_temp, keep_temp=False) as active_dir:
        assert active_dir.exists()
        (active_dir / "part1.docx").write_bytes(b"dummy")
        assert (active_dir / "part1.docx").exists()

    assert not target_temp.exists()


def test_composer_temp_workspace_keep_temp(tmp_path: Path) -> None:
    """composer_temp_workspace preserves directory and files when keep_temp=True per D14."""
    target_temp = tmp_path / "temp_parts"
    with composer_temp_workspace(temp_dir=target_temp, keep_temp=True) as active_dir:
        assert active_dir.exists()
        (active_dir / "part1.docx").write_bytes(b"dummy")

    assert target_temp.exists()
    assert (target_temp / "part1.docx").exists()


def test_composer_temp_workspace_cleanup_on_exception(tmp_path: Path) -> None:
    """composer_temp_workspace cleans up directory even if an exception is raised."""
    target_temp = tmp_path / "temp_parts"
    with pytest.raises(RuntimeError, match="compilation error"):
        with composer_temp_workspace(temp_dir=target_temp, keep_temp=False) as active_dir:
            (active_dir / "part1.docx").write_bytes(b"dummy")
            raise RuntimeError("compilation error")

    assert not target_temp.exists()


def test_composer_temp_workspace_defaults_to_d14_location(tmp_path: Path) -> None:
    """composer_temp_workspace defaults to .temp/temp_parts/<STATION>/ per D14."""
    station = "PE TALAPIA"
    with composer_temp_workspace(station=station, base_dir=tmp_path, keep_temp=True) as active_dir:
        expected = get_temp_parts_dir(station, base_dir=tmp_path)
        assert active_dir == expected
        assert active_dir.exists()

    assert expected.exists()


def test_composer_compiles_all_planned_parts(tmp_path: Path) -> None:
    """FullReportComposer compiles all planned parts into master document via FakeDocumentCompiler."""
    plan = _make_dummy_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    result = composer.compose(plan, base_dir=tmp_path)

    assert isinstance(result, FullReportCompilationResult)
    assert result.station == "PE TALAPIA"
    assert result.output_path == plan.final_output_path
    assert result.output_path.exists()
    assert result.part_count == 2
    assert len(result.parts) == 2

    # Verify FakeDocumentCompiler recorded the call
    assert len(fake_compiler.compiled_calls) == 1
    compiled_parts, out_dest = fake_compiler.compiled_calls[0]
    assert len(compiled_parts) == 2
    assert out_dest == plan.final_output_path.resolve()


def test_composer_cleans_up_temp_parts_by_default(tmp_path: Path) -> None:
    """FullReportComposer cleans up temp_parts/ in finally block by default (keep_temp=False)."""
    plan = _make_dummy_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    temp_dir = get_temp_parts_dir(plan.station, base_dir=tmp_path)
    composer.compose(plan, base_dir=tmp_path, keep_temp=False)

    assert not temp_dir.exists()


def test_composer_preserves_temp_parts_when_keep_temp_set(tmp_path: Path) -> None:
    """FullReportComposer preserves temp_parts/ when keep_temp=True per D14."""
    plan = _make_dummy_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    temp_dir = get_temp_parts_dir(plan.station, base_dir=tmp_path)
    result = composer.compose(plan, base_dir=tmp_path, keep_temp=True)

    assert temp_dir.exists()
    assert result.temp_dir == temp_dir.resolve()
    rendered_files = list(temp_dir.glob("*.docx"))
    assert len(rendered_files) == 2


def test_composer_cleans_up_temp_parts_on_compilation_error(tmp_path: Path) -> None:
    """FullReportComposer cleans up temp_parts/ in finally block even when compiler fails."""
    plan = _make_dummy_plan(tmp_path)
    mock_compiler = MagicMock()
    mock_compiler.compile.side_effect = RuntimeError("COM OLE automation crash")
    composer = FullReportComposer(compiler=mock_compiler)

    temp_dir = get_temp_parts_dir(plan.station, base_dir=tmp_path)
    with pytest.raises(RuntimeError, match="COM OLE automation crash"):
        composer.compose(plan, base_dir=tmp_path, keep_temp=False)

    assert not temp_dir.exists()


def test_composer_load_convenience_method(tmp_path: Path) -> None:
    """FullReportComposer.load() returns final output Path matching QuickReportComposer."""
    plan = _make_dummy_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    out = composer.load(plan, base_dir=tmp_path)
    assert out == plan.final_output_path
    assert out.exists()


def test_composer_session_context_manager() -> None:
    """FullReportComposer.session() yields the composer and manages compiler session."""
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    with composer.session() as active_composer:
        assert active_composer is composer


def test_composer_custom_output_path_override(tmp_path: Path) -> None:
    """FullReportComposer respects explicit output_path parameter."""
    plan = _make_dummy_plan(tmp_path)
    custom_out = tmp_path / "custom_output" / "report.docx"
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    result = composer.compose(plan, base_dir=tmp_path, output_path=custom_out)
    assert result.output_path == custom_out.resolve()
    assert custom_out.exists()


def test_composer_end_to_end_with_plan_builder(tmp_path: Path) -> None:
    """End-to-end integration test: FullReportPlanBuilder -> FullReportComposer -> FakeDocumentCompiler."""
    # Build package
    swg = SwitchgearSpec(
        switchgear_type="TAMCO",
        manufacturer="TAMCO",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="F1", name="INCOMING 1", panel_type="INCOMING"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="F2", name="OUTGOING 1", panel_type="OUTGOING"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="1000")
    pkg = SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))

    # Sliced mock sections
    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    sliced.front_page.write_bytes(b"PK\x03\x04front")
    sliced.condition_pages.write_bytes(b"PK\x03\x04cond")
    sliced.sticker_page.write_bytes(b"PK\x03\x04sticker")

    # Generate plan
    builder = FullReportPlanBuilder()
    plan = builder.build(
        package=pkg,
        sliced_sections=sliced,
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        output_dir=tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026",
        output_filename="005. PE TALAPIA (IR+VI).docx",
    )

    assert len(plan.parts) > 0

    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)

    result = composer.compose(plan, base_dir=tmp_path, keep_temp=False)

    assert result.part_count == len(plan.parts)
    assert result.output_path == plan.final_output_path
    assert result.output_path.exists()
    assert len(fake_compiler.compiled_calls) == 1
    compiled_parts, out_dest = fake_compiler.compiled_calls[0]
    assert len(compiled_parts) == len(plan.parts)
    assert out_dest == plan.final_output_path.resolve()

    # Ensure D14 temp workspace is cleaned up
    temp_dir = get_temp_parts_dir(plan.station, base_dir=tmp_path)
    assert not temp_dir.exists()


# ==============================================================================
# Multi-Part Composer Chunking Tests (Ticket #56)
# ==============================================================================


def _make_vcb_multipart_plan(tmp_path: Path) -> FullReportStationPlan:
    """Create a VCB plan that will partition into multiple chunks."""
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="SCHNEIDER",
        model="BLOKSET",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMING 1", panel_type="VCB", cable_photo=1, breaker_photo=2, busbar_photo=3, secondary_photo=4),
            SwitchgearPanelSpec(panel_no=2, name="TX 1", panel_type="VCB", cable_photo=5, breaker_photo=6, busbar_photo=7, secondary_photo=8),
            SwitchgearPanelSpec(panel_no=3, name="OUTGOING 1", panel_type="VCB", cable_photo=9, breaker_photo=10, busbar_photo=11, secondary_photo=12),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="1000")
    pkg = SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))

    sliced = SlicedSections(
        station="PE TALAPIA",
        front_page=tmp_path / "front_page.docx",
        condition_pages=tmp_path / "condition_pages.docx",
        sticker_page=tmp_path / "sticker_page.docx",
    )
    for f in [sliced.front_page, sliced.condition_pages, sliced.sticker_page]:
        f.write_bytes(b"PK\x03\x04stub")

    builder = FullReportPlanBuilder()
    return builder.build(
        package=pkg,
        sliced_sections=sliced,
        station="PE TALAPIA",
        station_code="RAU",
        date_str="04-08-2026",
        output_dir=tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026",
        output_filename="005. PE TALAPIA.docx",
    )


def test_composer_multipart_compiles_each_chunk_separately(tmp_path: Path) -> None:
    """Multi-part plan causes multiple compiler.compile() calls."""
    plan = _make_vcb_multipart_plan(tmp_path)
    assert plan.is_multipart is True
    stem = plan.output_filename.removesuffix(".docx")
    for chunk in plan.chunks:
        assert chunk.output_filename == f"{stem} - {chunk.label}.docx"

    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)
    result = composer.compose(plan, base_dir=tmp_path)
    assert result.is_multipart is True
    assert len(result.chunk_paths) == len(plan.chunks)
    assert len(fake_compiler.compiled_calls) == len(plan.chunks)
    for cp, chunk in zip(result.chunk_paths, plan.chunks):
        assert cp.name == f"{stem} - {chunk.label}.docx"


def test_composer_multipart_primary_output_is_part_01(tmp_path: Path) -> None:
    """Multi-part compilation sets output_path to Part 01."""
    plan = _make_vcb_multipart_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)
    result = composer.compose(plan, base_dir=tmp_path)
    assert result.output_path == plan.chunks[0].destination_path


def test_composer_multipart_chunk_paths_all_exist(tmp_path: Path) -> None:
    """All chunk paths exist on disk after multi-part compilation."""
    plan = _make_vcb_multipart_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)
    result = composer.compose(plan, base_dir=tmp_path)
    for cp in result.chunk_paths:
        assert cp.exists()


def test_composer_singlepart_rmu_backward_compatible(tmp_path: Path) -> None:
    """RMU plan compiles as single document with backward-compatible result."""
    plan = _make_dummy_plan(tmp_path)
    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)
    result = composer.compose(plan, base_dir=tmp_path)
    assert result.is_multipart is False
    assert result.chunk_paths == ()
    assert len(fake_compiler.compiled_calls) == 1


def test_composer_purge_existing_parts(tmp_path: Path) -> None:
    """Pre-purge deletes existing part files matching exact stem."""
    dest_dir = tmp_path / "output"
    dest_dir.mkdir(parents=True)
    stem = "005. PE TALAPIA (IR+VI)"
    (dest_dir / f"{stem} - Part 01.docx").write_bytes(b"old")
    (dest_dir / f"{stem} - Part 02.docx").write_bytes(b"old")
    (dest_dir / f"{stem} - Part 01 - Summary.docx").write_bytes(b"old")
    unrelated = dest_dir / "other_report.docx"
    unrelated.write_bytes(b"keep")
    FullReportComposer._purge_existing_parts(dest_dir, stem)
    assert not (dest_dir / f"{stem} - Part 01.docx").exists()
    assert not (dest_dir / f"{stem} - Part 02.docx").exists()
    assert not (dest_dir / f"{stem} - Part 01 - Summary.docx").exists()
    assert unrelated.exists()


def test_composer_multipart_vcb_5_panel_with_defect_pages_compilation(tmp_path: Path) -> None:
    """VCB with 5 panels, PT, transition bay, and inline defect compiles each chunk via FakeDocumentCompiler."""
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
    pkg = SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))

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

    from src.quick_report.defects import CbmDefectRecord
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
        output_dir=tmp_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / "04-08-2026",
        output_filename="005. PE TALAPIA (IR).docx",
    )

    assert plan.is_multipart is True
    assert len(plan.chunks) == 7

    fake_compiler = FakeDocumentCompiler()
    composer = FullReportComposer(compiler=fake_compiler)
    result = composer.compose(plan, base_dir=tmp_path)

    assert result.is_multipart is True
    assert len(result.chunk_paths) == 7
    assert len(fake_compiler.compiled_calls) == 7

    # Verify primary output is Part 01
    assert result.output_path == plan.chunks[0].destination_path

    # Verify chunk 3 call contains the defect page
    chunk3_call_parts = fake_compiler.compiled_calls[2][0]
    assert any("swg1_p02_tx1_cable_compartment" in p.name.lower() or "cbm_defect" in p.name.lower() for p in chunk3_call_parts)

    # Verify all chunk outputs exist
    for cp in result.chunk_paths:
        assert cp.exists()


