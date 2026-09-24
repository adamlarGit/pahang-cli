"""End-to-End Multi-Part Full Report Verification & Regression Suite (Ticket #58).

Validates:
1. Synthetic VCB benchmark fixture in tests/benchmarks/pe157_perpustakaan_awam/:
   - 5-panel TAMCO VCB 11kV lineup with transition bay, PT on panel 4, 1 transformer, 1 feeder pillar, and 1 inline CBM defect page.
2. CLI dry-run telemetry:
   - _print_full_report_dry_run_telemetry displays [Multi-part: X files] for multi-part substations.
   - _print_full_report_postprocessing_dry_run_telemetry displays [X docx parts -> 1 pdf deliverable].
3. Full lifecycle execution on 5-panel VCB switchgear:
   - Stage 1 generates 7 modular Word documents with descriptive names.
   - Inline CBM defect page remains attached to its parent panel bay (Panel 2).
   - Transition bay and PT chamber are correctly assembled in their panel parts.
   - Stage 2 post-processing discovers all 7 parts, converts in numerical order, merges via merge_pdfs_batch,
     appends signed testsheet PDF, and produces a single unified <STEM>.pdf deliverable.
   - Intermediate Word part files remain intact on disk.
4. Regression validation:
   - Standard RMU benchmarks (PE 005 TALAPIA, PE 144 TELEKOM TANAH PUTIH, PE 179 CENDERAWASIH NO. 1)
     remain single-document deliverables without unintended partitioning.
"""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import pytest

from src.core.topology import SwitchgearArchetype, SwitchgearTopologyEngine
from src.full_report.composer import FullReportComposer
from src.full_report.plan_builder import FullReportPlanBuilder, PlanPartType
from src.full_report.slicer import FakeDocumentSlicer
from src.postprocessing.converters import FakeDocumentConverter
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.project_workflow_actions import (
    _print_full_report_dry_run_telemetry,
    _print_full_report_postprocessing_dry_run_telemetry,
)
from src.quick_report.compiler import FakeDocumentCompiler
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)
from src.workflows.full_report import (
    FullReportInspection,
    FullReportSubstationTelemetry,
    FullReportWorkflow,
)
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingInspection,
    FullReportPostProcessingTelemetry,
    FullReportPostProcessingWorkflow,
    TestsheetPdfValidationResult,
)
from tests.benchmarks.pe157_fixture import (
    create_pe157_quick_report_docx,
    create_pe157_sliced_sections,
    create_pe157_testsheet_pdf,
    create_pe157_testsheet_workbook,
    materialize_pe157_benchmark_fixture,
    setup_pe157_benchmark_environment,
)


# ==============================================================================
# 1. Synthetic VCB Benchmark Fixture Integrity
# ==============================================================================

class TestSyntheticVcbBenchmarkFixture:
    """Validate PE 157 PERPUSTAKAAN AWAM synthetic benchmark fixture."""

    def test_materialized_fixture_files_and_models(self) -> None:
        """Verify persistent benchmark files exist and extract 5-panel VCB topology."""
        fixture_dir = materialize_pe157_benchmark_fixture()
        assert fixture_dir.is_dir()

        # 1. Testsheet Excel workbook
        ts_path = fixture_dir / "157. PERPUSTAKAAN AWAM(VCB).xlsx"
        assert ts_path.is_file()

        extractor = TestsheetExtractor()
        data = extractor.extract_testsheet_data(ts_path)
        assert len(data.equipment.switchgears) == 1
        swg = data.equipment.switchgears[0]

        # Topology classification
        board = SwitchgearTopologyEngine.classify_board(
            switchgear_type=swg.switchgear_type,
            manufacturer=swg.manufacturer,
            model=swg.model,
            rating=swg.rating,
            swg=swg,
        )
        assert board.archetype == SwitchgearArchetype.VCB_CUBICLE
        assert len(swg.panels) == 5

        # Bay roles and chambers
        p1, p2, p3, p4, p5 = swg.panels
        assert p1.name == "SSU IBU PEJABAT MPK CB5"
        assert p1.cable_photo == 498 and p1.breaker_photo == 493 and p1.secondary_photo == 520 and p1.busbar_photo == 503

        assert p2.name == "SSU IBU PEJABAT MPK CB8"
        assert p2.cable_photo == 499 and p2.breaker_photo == 494 and p2.secondary_photo == 521 and p2.busbar_photo == 504

        # Transition panel
        assert p3.name == "TRANSITION PANEL"
        assert p3.is_transition_panel is True
        assert p3.cable_photo == 500 and p3.breaker_photo == 495 and p3.secondary_photo == 522 and p3.busbar_photo == 505

        # PT on Panel 4
        assert p4.name == "MSB"
        assert p4.is_transition_panel is False
        assert p4.has_pt_measurement is True
        assert p4.pt_photo == 526

        # Panel 5
        assert p5.name == "TX 300KVA"
        assert p5.cable_photo == 502 and p5.breaker_photo == 497 and p5.secondary_photo == 524 and p5.busbar_photo == 507

        # Overviews: Front, Rear, Top
        assert swg.photo_numbers == (485, 488, 491)

        # Transformer and LVDB
        assert len(data.equipment.transformers) == 1
        assert "1000" in data.equipment.transformers[0].rating_kva
        assert len(data.equipment.lvdb_specs) == 1
        assert data.equipment.lvdb_specs[0].rating == "800A"

        # 2. Stub photos in IR and DG
        photo_dir = fixture_dir / "photos"
        assert (photo_dir / "IR").is_dir()
        assert (photo_dir / "DG").is_dir()
        ir_photos = list((photo_dir / "IR").glob("*.jpg"))
        dg_photos = list((photo_dir / "DG").glob("*.jpg"))
        assert len(ir_photos) >= 20
        assert len(dg_photos) >= 20

        # 3. Slices & Inline CBM defect
        slices_dir = fixture_dir / "slices"
        assert (slices_dir / "front_page.docx").is_file()
        assert (slices_dir / "condition_pages.docx").is_file()
        assert (slices_dir / "sticker_page.docx").is_file()
        inline_defect = slices_dir / "cbm_defects" / "swg1_p02_CKN03901_CABLE_COMPARTMENT_01.docx"
        assert inline_defect.is_file()

        # 4. Processed testsheet PDF
        ts_pdf = fixture_dir / "processed_testsheet" / "pdf" / "157. PERPUSTAKAAN AWAM (IR+VI).pdf"
        assert ts_pdf.is_file()


# ==============================================================================
# 2. CLI Dry-Run Telemetry Tests
# ==============================================================================

class TestCliDryRunTelemetry:
    """Verify CLI dry-run inspection prompts for Stage 1 and Stage 2."""

    def test_print_full_report_dry_run_telemetry_multipart(self) -> None:
        """Display multi-part indicator [Multi-part: X files] when substation is planned for partitioning."""
        t_multi = FullReportSubstationTelemetry(
            substation_number=157,
            substation_name="PERPUSTAKAAN AWAM",
            functional_location="CKTN039",
            station="KUANTAN",
            month="01. AUGUST",
            date_str="25-08-2026",
            quick_report_path=Path("mock_qr.docx"),
            is_quick_report_valid=True,
            preflight_result=None,
            target_output_path=Path("out.docx"),
            stem="157. PERPUSTAKAAN AWAM (IR+VI)",
            defect_suffix="(IR+VI)",
            cbm_defect_count=1,
            vi_defect_count=0,
            is_multipart=True,
            part_count=7,
        )
        t_single = FullReportSubstationTelemetry(
            substation_number=5,
            substation_name="TALAPIA",
            functional_location="CRAU005",
            station="RAUB",
            month="01. AUGUST",
            date_str="04-08-2026",
            quick_report_path=Path("mock_qr.docx"),
            is_quick_report_valid=True,
            preflight_result=None,
            target_output_path=Path("out.docx"),
            stem="005. TALAPIA (IR+VI)",
            defect_suffix="(IR+VI)",
            cbm_defect_count=0,
            vi_defect_count=0,
            is_multipart=False,
            part_count=1,
        )

        inspection = FullReportInspection(targets=(t_multi, t_single))

        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            _print_full_report_dry_run_telemetry(inspection)
        finally:
            sys.stdout = old_stdout

        output = buf.getvalue()
        assert "[Multi-part: 7 files]" in output
        assert "PE 157 - PERPUSTAKAAN AWAM [Multi-part: 7 files]" in output
        # Single document has no multipart indicator
        assert "PE 5 - TALAPIA" in output
        assert "PE 5 - TALAPIA [Multi-part:" not in output

    def test_print_full_report_postprocessing_dry_run_telemetry_multipart(self) -> None:
        """Display multi-part file grouping [X docx parts -> 1 pdf deliverable]."""
        p1 = Path("157. PERPUSTAKAAN AWAM - Part 01 - Summary.docx")
        p2 = Path("157. PERPUSTAKAAN AWAM - Part 02 - Panel 1.docx")
        p3 = Path("157. PERPUSTAKAAN AWAM - Part 03 - Panel 2.docx")

        val_res = TestsheetPdfValidationResult(
            path=Path("ts.pdf"),
            is_valid=True,
            exists=True,
            size_bytes=15_420,
        )

        t_multi = FullReportPostProcessingTelemetry(
            docx_path=p1,
            testsheet_pdf_path=Path("ts.pdf"),
            target_pdf_path=Path("out.pdf"),
            stem="157. PERPUSTAKAAN AWAM",
            is_testsheet_pdf_valid=True,
            validation_result=val_res,
            is_multipart=True,
            part_docx_paths=(p1, p2, p3),
        )
        t_single = FullReportPostProcessingTelemetry(
            docx_path=Path("005. TALAPIA (IR+VI).docx"),
            testsheet_pdf_path=Path("ts2.pdf"),
            target_pdf_path=Path("out2.pdf"),
            stem="005. TALAPIA (IR+VI)",
            is_testsheet_pdf_valid=True,
            validation_result=val_res,
            is_multipart=False,
            part_docx_paths=(Path("005. TALAPIA (IR+VI).docx"),),
        )

        inspection = FullReportPostProcessingInspection(targets=(t_multi, t_single))

        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            _print_full_report_postprocessing_dry_run_telemetry(inspection)
        finally:
            sys.stdout = old_stdout

        output = buf.getvalue()
        assert "[3 docx parts -> 1 pdf deliverable]" in output
        assert "157. PERPUSTAKAAN AWAM [3 docx parts -> 1 pdf deliverable]" in output
        assert "005. TALAPIA (IR+VI).docx" in output
        assert "005. TALAPIA (IR+VI).docx [" not in output

    def test_workflow_inspect_evaluates_multipart_status(self, tmp_path: Path) -> None:
        """FullReportWorkflow.inspect() correctly flags VCB as multi-part with part count."""
        env, file_map = setup_pe157_benchmark_environment(tmp_path)
        wf = FullReportWorkflow()

        target_dir = file_map["testsheet"].parent
        inspection = wf.inspect(target_dir, env)

        assert len(inspection.targets) == 1
        telem = inspection.targets[0]
        assert telem.substation_number == 157
        assert telem.is_multipart is True
        assert telem.part_count == 7  # 1 summary + 5 panels + 1 tx/condition


# ==============================================================================
# 3. End-to-End VCB Multi-Part Lifecycle Verification
# ==============================================================================

class TestFullReportMultipartLifecycleE2E:
    """Test full lifecycle: Stage 1 multi-part generation + Stage 2 post-processing merge."""

    def test_vcb_5_panel_lifecycle_generation_and_stitching(self, tmp_path: Path) -> None:
        """Full end-to-end lifecycle verification on synthetic 5-panel VCB benchmark."""
        env, file_map = setup_pe157_benchmark_environment(tmp_path)

        slices = create_pe157_sliced_sections(file_map["slices_dir"])
        fake_slicer = FakeDocumentSlicer(mock_cbm_defects=slices.cbm_defect_pages)
        fake_compiler = FakeDocumentCompiler()
        composer = FullReportComposer(compiler=fake_compiler)
        pb = FullReportPlanBuilder(slicer=fake_slicer)

        wf = FullReportWorkflow(
            compiler=fake_compiler,
            composer=composer,
            plan_builder=pb,
            slicer=fake_slicer,
        )

        # ----------------------------------------------------------------------
        # Stage 1: Word Multi-Part Generation
        # ----------------------------------------------------------------------
        target_dir = file_map["testsheet"].parent
        gen_result = wf.generate(target_dir, env)

        assert gen_result.succeeded_count == 1
        assert gen_result.failed_count == 0
        assert len(gen_result.station_results) == 1

        st_res = gen_result.station_results[0]
        assert st_res.is_multipart is True
        assert len(st_res.chunk_paths) == 7

        stem = "157. PERPUSTAKAAN AWAM"
        expected_part_filenames = [
            f"{stem} - Part 01 - Summary.docx",
            f"{stem} - Part 02 - Panel 1 (SSU IBU PEJABAT MPK CB5).docx",
            f"{stem} - Part 03 - Panel 2 (SSU IBU PEJABAT MPK CB8).docx",
            f"{stem} - Part 04 - Panel 3 (TRANSITION PANEL).docx",
            f"{stem} - Part 05 - Panel 4 (MSB).docx",
            f"{stem} - Part 06 - Panel 5 (TX 300KVA).docx",
            f"{stem} - Part 07 - TX and Condition.docx",
        ]

        # Verify all 7 parts exist on disk and match filenames
        for expected_name, chunk_path in zip(expected_part_filenames, st_res.chunk_paths):
            assert chunk_path.name == expected_name
            assert chunk_path.is_file()

        # Primary output path is Part 01
        assert st_res.output_path == st_res.chunk_paths[0]

        # Verify compilation calls occurred for all 7 chunks
        assert len(fake_compiler.compiled_calls) == 7

        # Chunk 1 (Summary): contains front page and census
        chunk1_parts = fake_compiler.compiled_calls[0][0]
        assert any("front_page" in p.name for p in chunk1_parts)
        assert any("census" in p.name for p in chunk1_parts)

        # Chunk 3 (Panel 2): contains the inline CBM defect page for panel 2!
        chunk3_parts = fake_compiler.compiled_calls[2][0]
        assert any("swg1_p02" in p.name.lower() or "cbm_defect" in p.name.lower() for p in chunk3_parts)

        # Chunk 4 (Panel 3): Transition Bay has 4 compartments
        chunk4_parts = fake_compiler.compiled_calls[3][0]
        assert len(chunk4_parts) == 4

        # Chunk 5 (Panel 4): MSB has 5 compartments (including PT)
        chunk5_parts = fake_compiler.compiled_calls[4][0]
        assert len(chunk5_parts) == 5

        # Chunk 7 (TX & Condition): contains TX, FP, Battery, Condition, Sticker
        chunk7_parts = fake_compiler.compiled_calls[6][0]
        assert any("condition" in p.name.lower() for p in chunk7_parts)
        assert any("sticker" in p.name.lower() for p in chunk7_parts)

        # ----------------------------------------------------------------------
        # Stage 2: Post-Processing Multi-Part Discovery and PDF Stitching
        # ----------------------------------------------------------------------
        fr_date_dir = env.get_full_report_dir() / "KUANTAN" / "01. AUGUST" / "25-08-2026"
        fake_converter = FakeDocumentConverter()
        pp_wf = FullReportPostProcessingWorkflow(converter=fake_converter)

        # Dry-run inspection
        pp_inspection = pp_wf.inspect(fr_date_dir, env)
        assert len(pp_inspection.targets) == 1
        pp_target = pp_inspection.targets[0]
        assert pp_target.stem == stem
        assert pp_target.is_multipart is True
        assert len(pp_target.part_docx_paths) == 7
        assert pp_target.is_ready is True
        assert pp_target.testsheet_pdf_path == file_map["testsheet_pdf"]

        # Execution
        pp_result = pp_wf.execute(fr_date_dir, env)
        assert pp_result.is_success is True
        assert pp_result.succeeded_count == 1
        assert pp_result.failed_count == 0

        # Deliverable PDF is <STEM>.pdf
        expected_pdf_deliverable = fr_date_dir / f"{stem}.pdf"
        assert expected_pdf_deliverable in pp_result.deliverables
        assert expected_pdf_deliverable.is_file()

        # Batch merge call verified
        assert len(fake_converter.merge_pdfs_batch_calls) == 1
        batch_inputs, master_tmp_out = fake_converter.merge_pdfs_batch_calls[0]
        assert len(batch_inputs) == 7
        assert master_tmp_out.name == f".tmp_conv_{stem}_master.pdf"

        # 2-input merge call (testsheet append) verified
        assert len(fake_converter.merge_calls) == 1
        ts_append_input1, ts_append_input2, final_out = fake_converter.merge_calls[0]
        assert ts_append_input1 == master_tmp_out
        assert ts_append_input2 == file_map["testsheet_pdf"]
        assert final_out == expected_pdf_deliverable

        # All 7 Word part files remain untouched on disk for field inspectors
        for chunk_path in st_res.chunk_paths:
            assert chunk_path.is_file(), f"Intermediate Word part missing: {chunk_path.name}"


# ==============================================================================
# 4. Regression Validation: RMU Benchmarks Remain Single Documents
# ==============================================================================

class TestRmuSingleDocumentRegression:
    """Verify standard RMU benchmarks (PE 005, PE 144, PE 179) remain single documents."""

    @pytest.mark.parametrize(
        ("pe_num", "station_name", "swg_mfg", "panel_names"),
        [
            (
                5,
                "TALAPIA",
                "TAMCO",
                ("PE KG ASLI BATU BALONG", "TX B", "TX A", "CS LDG BILUT"),
            ),
            (
                144,
                "TELEKOM TANAH PUTIH",
                "INDKOM",
                ("BILIK SUIS PENGGUNA", "RADIO PENGGUNA", "PENCAWANG DARAT MAKBAR", "TX 750"),
            ),
            (
                179,
                "CENDERAWASIH NO.1",
                "INDKOM",
                ("SPARE", "TMN CENDRAWASIH 3", "TAJ 33A LOT 11520", "PANEL CKN01309 TX"),
            ),
        ],
    )
    def test_rmu_benchmarks_not_partitioned(
        self,
        tmp_path: Path,
        pe_num: int,
        station_name: str,
        swg_mfg: str,
        panel_names: tuple[str, ...],
    ) -> None:
        """Standard RMU switchboards always generate as single consolidated documents."""
        swg = SwitchgearSpec(
            switchgear_type="RMU SF6",
            manufacturer=swg_mfg,
            model="STANDARD",
            panels=tuple(
                SwitchgearPanelSpec(panel_no=i, name=name, cable_photo=100 + i)
                for i, name in enumerate(panel_names, start=1)
            ),
        )
        tx = TransformerSpec(tx_id="Tx 1", rating_kva="1000", manufacturer="EWT")
        fp = LVDBSpec(name="FP 1", label="FP", source="TX1")

        eq_pkg = SubstationEquipmentPackage(
            switchgears=(swg,),
            transformers=(tx,),
            lvdb_specs=(fp,),
        )

        # Check archetype is RMU
        board = SwitchgearTopologyEngine.classify_board(
            switchgear_type=swg.switchgear_type,
            manufacturer=swg.manufacturer,
            model=swg.model,
            swg=swg,
        )
        assert board.archetype in (
            SwitchgearArchetype.RMU_STANDARD,
            SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
            SwitchgearArchetype.RMU_FUSE_CANISTER,
        )

        stem = f"{pe_num:03d}. {station_name}"
        out_dir = tmp_path / "FULL REPORT" / "TEST" / "01. AUGUST" / "01-08-2026"
        out_file = f"{stem}.docx"

        fake_slicer = FakeDocumentSlicer()
        pb = FullReportPlanBuilder(slicer=fake_slicer)

        plan = pb.build(
            package=eq_pkg,
            station=station_name,
            station_code="TST",
            date_str="01-08-2026",
            month="01. AUGUST",
            output_dir=out_dir,
            output_filename=out_file,
            quick_report_path=tmp_path / "dummy_qr.docx",
            temp_parts_dir=tmp_path / "temp_parts",
        )

        # Invariant: Standard RMU never partitions into multi-part
        assert plan.is_multipart is False
        assert len(plan.chunks) == 1
        assert plan.chunks[0].output_filename == out_file

        # Headless compilation
        fake_compiler = FakeDocumentCompiler()
        composer = FullReportComposer(compiler=fake_compiler)
        res = composer.compose(plan, base_dir=tmp_path)

        assert res.is_multipart is False
        assert res.chunk_paths == ()
        assert res.output_path == out_dir / out_file
        assert len(fake_compiler.compiled_calls) == 1
        assert (out_dir / out_file).is_file()

        # Post-processing discovery
        fake_converter = FakeDocumentConverter()
        pp_wf = FullReportPostProcessingWorkflow(converter=fake_converter)
        groups = pp_wf._group_multipart_targets([out_dir / out_file])
        assert len(groups) == 1
        assert groups[0].is_multipart is False
        assert groups[0].docx_paths == ((out_dir / out_file).resolve(),)
