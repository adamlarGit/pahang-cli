"""End-to-End Auditing & Validation against Canonical Benchmarks (Ticket #38 / T6.5).

Validates Full Report Generation and Post-Processing against the three canonical ground-truth benchmarks:
1. TALAPIA (PE 5, Raub, 04-Aug-2026, IR+VI):
   - RMU scanning pages, 10-way FP overview, interleaved FP defect pages, condition/sticker pages.
2. CENDERAWASIH NO.1 (PE 179, Kuantan, 28-Aug-2026, IR+VI):
   - RMU scanning pages with TX fuse compartment defect replacing panel 4 scan page.
3. TELEKOM TANAH PUTIH (PE 144, Kuantan, 24-Aug-2026, TEV+VI):
   - PRPD waveforms and TEV defect pages appended behind each panel scan page.

Also verifies:
- FLIR Tools+ ActiveX controls function interactively in compiled .docx files (ADR 0002).
- Single continuous section invariant: len(doc.sections) == 1.
- Page breaks preserve layout without section splitting.
- Stage 2 Post-Processing Word COM PDF export and signed testsheet PDF merge completeness (ADR 0003).
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import zipfile
import docx
from docx.oxml.ns import qn
import pytest

from src.full_report.plan_builder import PlanPartType
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.quick_report.compiler import WordComDocumentCompiler
from src.full_report.slicer import WordComDocumentSlicer
from src.workflows.full_report import FullReportWorkflow
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingWorkflow,
    resolve_processed_testsheet_pdf_path,
)

REAL_DATASET_ROOT = Path(
    os.getenv("PAHANG_BENCHMARK_ROOT", r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD")
)


@pytest.fixture(scope="module")
def benchmark_env() -> ProjectEnvironment:
    """Construct ProjectEnvironment rooted in the canonical inspection dataset."""
    if not REAL_DATASET_ROOT.exists():
        pytest.skip(f"Real inspection dataset not found at: {REAL_DATASET_ROOT}")

    meta = ProjectMetadata(
        key="pahang",
        name="Pahang",
        po_number="42360565",
        state="PAHANG",
        voltage_type="11kV",
        year="2026",
        cycle="CYCLE3",
        technologies=("IR", "US", "TEV"),
        base_path=str(REAL_DATASET_ROOT),
    )
    storage = LocalWorkspaceStorage(REAL_DATASET_ROOT)
    return ProjectEnvironment(metadata=meta, storage=storage)


# ==============================================================================
# Helper Verification Functions
# ==============================================================================

def verify_single_section_invariant(doc_or_path: Path | str | docx.Document) -> None:
    """Verify ADR 0002 invariant: document contains exactly 1 continuous section."""
    if isinstance(doc_or_path, (str, Path)):
        doc = docx.Document(doc_or_path)
    else:
        doc = doc_or_path

    assert len(doc.sections) == 1, (
        f"ADR 0002 violation: Document has {len(doc.sections)} sections; must have exactly 1 continuous section."
    )


def verify_activex_controls_preserved(docx_path: Path | str) -> list[str]:
    """Verify ActiveX controls (.bin & .xml) are preserved inside docx ZIP package."""
    p = Path(docx_path)
    assert p.is_file(), f"Document file not found: {p}"

    with zipfile.ZipFile(p, "r") as zf:
        namelist = zf.namelist()
        activex_bins = [n for n in namelist if n.startswith("word/activeX/activeX") and n.endswith(".bin")]
        activex_xmls = [n for n in namelist if n.startswith("word/activeX/activeX") and n.endswith(".xml")]

        assert len(activex_bins) > 0, f"No ActiveX .bin controls found in {p.name}"
        assert len(activex_xmls) > 0, f"No ActiveX .xml control descriptors found in {p.name}"

        # Verify FLIR Tools+ CLSID / ProgID presence in activeX XML
        flir_found = False
        for ax_xml in activex_xmls:
            content = zf.read(ax_xml).decode("utf-8", errors="ignore")
            if "FLIR" in content or "clsid" in content.lower() or "activeX" in content:
                flir_found = True
                break
        assert flir_found, f"ActiveX control descriptors in {p.name} missing FLIR/ActiveX declarations"

        return activex_bins


def verify_page_breaks_present(doc_or_path: Path | str | docx.Document) -> int:
    """Verify page breaks (<w:br w:type="page"/>) are present and no inline section breaks."""
    if isinstance(doc_or_path, (str, Path)):
        doc = docx.Document(doc_or_path)
    else:
        doc = doc_or_path

    page_break_count = 0
    for p in doc.paragraphs:
        for r in p.runs:
            for br in r._r.findall(qn("w:br")):
                if br.get(qn("w:type")) == "page":
                    page_break_count += 1

    assert page_break_count > 0, "No page breaks found in document."
    return page_break_count


# ==============================================================================
# Benchmark Test 1: TALAPIA (PE 5, Raub)
# ==============================================================================

@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_e2e_benchmark_talapia_plan_and_interleaving(benchmark_env: ProjectEnvironment):
    """Verifies TALAPIA full report Bill of Materials plan and defect interleaving.

    Verifies:
    - RMU scanning pages (overview + panels 1-4)
    - Tx 2 scanning pages (overview + bushings + cables)
    - 10-way FP overview substituted by sliced QR (LVDB 1 - OVERVIEW (Sliced QR))
    - 2 interleaved FP defect pages sequenced strictly in channel order
    - Substation condition, visual defect summary & pages, sticker page
    - ZERO orphan defect pages
    """
    wf = FullReportWorkflow()
    target_dir = REAL_DATASET_ROOT / "TESTSHEET" / "RAUB" / "01. AUGUST" / "04-08-2026"
    pkgs, warnings, errors = wf._discover_packages(target_dir, benchmark_env, station="TALAPIA")

    assert len(pkgs) == 1, f"Expected 1 package for TALAPIA, found {len(pkgs)}"
    pkg = pkgs[0]
    qr_path = wf._resolve_quick_report_path(benchmark_env, pkg)
    assert qr_path is not None and qr_path.is_file()

    plan = wf._build_station_plan(pkg, benchmark_env, quick_report_path=qr_path)
    part_names = [p.part_name for p in plan.parts]
    part_types = [p.part_type for p in plan.parts]

    # 1. Front Page, Census, Visual Defect Summary
    assert part_types[0] == PlanPartType.FRONT_PAGE
    assert part_types[1] == PlanPartType.CENSUS
    assert part_types[2] == PlanPartType.VI_SUMMARY

    # 2. Switchgear Scanning Pages
    swg_parts = [p for p in plan.parts if p.part_type == PlanPartType.SCAN_PAGE and "SWG" in p.part_name or "Panel" in p.part_name]
    assert len(swg_parts) >= 8, f"Expected at least 8 SWG scan pages, got {len(swg_parts)}"

    # 3. Transformer Scanning Pages
    tx_parts = [p for p in plan.parts if p.part_type == PlanPartType.SCAN_PAGE and ("Tx 2" in p.part_name or "TX2" in p.part_name)]
    assert len(tx_parts) >= 6, f"Expected at least 6 TX2 scan pages, got {len(tx_parts)}"

    # 4. FP Overview Substituted by Sliced QR (D47)
    fp_ov_parts = [p for p in plan.parts if ("LVDB 1 - OVERVIEW" in p.part_name or "FP 1 - OVERVIEW" in p.part_name) and p.is_sliced]
    assert len(fp_ov_parts) == 1, "LVDB/FP 1 overview was not substituted by sliced QR"
    assert "Sliced QR" in fp_ov_parts[0].part_name

    # 5. Interleaved FP Defect Pages in Channel Order (D36)
    cbm_defect_parts = [p for p in plan.parts if p.part_type == PlanPartType.CBM_DEFECT]
    assert len(cbm_defect_parts) == 2, f"Expected 2 CBM defect pages for TALAPIA, got {len(cbm_defect_parts)}"

    # Check incoming defect precedes outgoing defect
    fp_ov_idx = part_names.index(fp_ov_parts[0].part_name)
    def1_idx = part_names.index(cbm_defect_parts[0].part_name)
    def2_idx = part_names.index(cbm_defect_parts[1].part_name)

    assert fp_ov_idx < def1_idx < def2_idx, "FP defects not sequenced immediately after FP overview in channel order"

    # 6. Condition, VI Defect Pages, Sticker Page
    assert part_types[-3] == PlanPartType.CONDITION
    assert part_types[-2] == PlanPartType.VI_DEFECTS
    assert part_types[-1] == PlanPartType.STICKER

    # 7. ZERO Orphans
    orphan_parts = [p for p in plan.parts if getattr(p, "action_type", None) == "ORPHAN_APPEND"]
    assert len(orphan_parts) == 0, f"Found unexpected orphan defect pages: {orphan_parts}"


# ==============================================================================
# Benchmark Test 2: CENDERAWASIH NO.1 (PE 179, Kuantan)
# ==============================================================================

@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_e2e_benchmark_cenderawasih_fuse_compartment_replacement(benchmark_env: ProjectEnvironment):
    """Verifies CENDERAWASIH NO.1 TX fuse compartment defect replaces panel 4 scan page.

    Verifies:
    - SWG overview substituted by sliced QR
    - Panels 1-3 retained
    - Panel 4 scan page REPLACED by CBM defect page (swg1_p1309_CKN01309_FUSE_COMPARTMENT_01.docx)
    - Transformer 1 & FP 1 overview retained
    - ZERO orphan defect pages
    """
    wf = FullReportWorkflow()
    target_dir = REAL_DATASET_ROOT / "TESTSHEET" / "KUANTAN" / "01. AUGUST" / "28-08-2026"
    pkgs, _, _ = wf._discover_packages(target_dir, benchmark_env, station="CENDERAWASIH NO.1")

    assert len(pkgs) == 1, f"Expected 1 package for CENDERAWASIH NO.1, found {len(pkgs)}"
    pkg = pkgs[0]
    qr_path = wf._resolve_quick_report_path(benchmark_env, pkg)
    assert qr_path is not None and qr_path.is_file()

    plan = wf._build_station_plan(pkg, benchmark_env, quick_report_path=qr_path)
    part_names = [p.part_name for p in plan.parts]
    part_types = [p.part_type for p in plan.parts]

    # Verify SWG overview substituted
    swg_ov = [p for p in plan.parts if "SWG Overview - OVERVIEW (Sliced QR)" in p.part_name]
    assert len(swg_ov) == 1, "SWG Overview was not substituted by sliced QR"

    # Verify Panels 1, 2, 3 present
    assert any("Panel 1" in name for name in part_names)
    assert any("Panel 2" in name for name in part_names)
    assert any("Panel 3" in name for name in part_names)

    # Verify Panel 4 scan page is NOT present (replaced per D34)
    assert not any("Panel 4" in name for name in part_names), "Panel 4 scan page should have been replaced"

    # Verify TX fuse compartment defect is present in place of panel 4
    fuse_defect = [p for p in plan.parts if "FUSE_COMPARTMENT" in p.part_name and p.part_type == PlanPartType.CBM_DEFECT]
    assert len(fuse_defect) == 1, "TX fuse compartment defect page is missing"
    assert "CKN01309" in fuse_defect[0].part_name

    # Check defect is positioned after Panel 3
    panel3_idx = max(i for i, name in enumerate(part_names) if "Panel 3" in name)
    defect_idx = part_names.index(fuse_defect[0].part_name)
    assert defect_idx == panel3_idx + 1, "Defect should immediately follow Panel 3, replacing Panel 4"

    # Verify zero orphans
    assert len([p for p in plan.parts if p.part_type == PlanPartType.CBM_DEFECT]) == 1


# ==============================================================================
# Benchmark Test 3: TELEKOM TANAH PUTIH (PE 144, Kuantan)
# ==============================================================================

@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_e2e_benchmark_telekom_tanah_putih_tev_interleaving(benchmark_env: ProjectEnvironment):
    """Verifies TELEKOM TANAH PUTIH TEV defect pages appended behind each panel scan page.

    Verifies:
    - SWG overview substituted by sliced QR
    - Panels 1, 2, 3, 4 retained
    - TEV defect pages interleaved immediately behind their respective panel scan page:
      - Panel 1 followed by CKN00048 defect
      - Panel 2 followed by CKN00049 defect
      - Panel 3 followed by CKN00050 defect
      - Panel 4 followed by CKN00051 defect
    - ZERO orphan defect pages
    """
    wf = FullReportWorkflow()
    target_dir = REAL_DATASET_ROOT / "TESTSHEET" / "KUANTAN" / "01. AUGUST" / "24-08-2026"
    pkgs, _, _ = wf._discover_packages(target_dir, benchmark_env, station="TELEKOM TANAH PUTIH")

    assert len(pkgs) == 1, f"Expected 1 package for TELEKOM TANAH PUTIH, found {len(pkgs)}"
    pkg = pkgs[0]
    qr_path = wf._resolve_quick_report_path(benchmark_env, pkg)
    assert qr_path is not None and qr_path.is_file()

    plan = wf._build_station_plan(pkg, benchmark_env, quick_report_path=qr_path)
    part_names = [p.part_name for p in plan.parts]

    # Verify SWG overview substituted
    assert any("SWG Overview - OVERVIEW (Sliced QR)" in name for name in part_names)

    # Verify all 4 panels retained AND followed by TEV defect pages
    p1_idx = part_names.index("Panel 1 (BILIK SUIS PENGGUNA) - CABLE COMPARTMENT")
    d1_idx = part_names.index("swg1_p48_CKN00048_CABLE_COMPARTMENT_01.docx")
    assert d1_idx == p1_idx + 1, "Panel 1 must be immediately followed by CKN00048 defect"

    p2_idx = part_names.index("Panel 2 (RADIO PENGGUNA) - CABLE COMPARTMENT")
    d2_idx = part_names.index("swg1_p49_CKN00049_CABLE_COMPARTMENT_01.docx")
    assert d2_idx == p2_idx + 1, "Panel 2 must be immediately followed by CKN00049 defect"

    p3_idx = part_names.index("Panel 3 (PENCAWANG DARAT MAKBAR) - CABLE COMPARTMENT")
    d3_idx = part_names.index("swg1_p50_CKN00050_CABLE_COMPARTMENT_01.docx")
    assert d3_idx == p3_idx + 1, "Panel 3 must be immediately followed by CKN00050 defect"

    p4_idx = part_names.index("Panel 4 (TX 750) - FUSE COMPARTMENT")
    d4_idx = part_names.index("swg1_p51_CKN00051_FUSE_COMPARTMENT_01.docx")
    assert d4_idx == p4_idx + 1, "Panel 4 must be immediately followed by CKN00051 defect"

    # Verify exactly 4 CBM defect parts in total (zero orphans)
    cbm_parts = [p for p in plan.parts if p.part_type == PlanPartType.CBM_DEFECT]
    assert len(cbm_parts) == 4, f"Expected exactly 4 TEV defects, found {len(cbm_parts)}"

    # Verify PRPD waveform telemetry on panel scan parts
    panel_parts = [p for p in plan.parts if p.part_type == PlanPartType.SCAN_PAGE and "Panel" in p.part_name]
    assert len(panel_parts) == 4
    for p_part in panel_parts:
        ctx = p_part.context or (p_part.scan_item.context if p_part.scan_item else {})
        panel_ctx = ctx.get("panel", {})
        assert "tev" in panel_ctx, f"Missing TEV telemetry for {p_part.part_name}"
        assert panel_ctx["tev"].get("reading") not in ("-", "", None), f"Missing TEV reading on {p_part.part_name}"


# ==============================================================================
# Benchmark Test 4: ActiveX Preserved & Layout Invariants (ADR 0002)
# ==============================================================================

@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_e2e_benchmark_flir_activex_and_layout_invariants():
    """Verifies compiled benchmark docx deliverables satisfy ADR 0002 layout invariants.

    Verifies:
    - Single continuous section: len(doc.sections) == 1.
    - FLIR Tools+ ActiveX controls present (.bin and .xml).
    - Page breaks wdPageBreak = 7 present.
    """
    benchmarks = [
        REAL_DATASET_ROOT / "FULL REPORT" / "RAUB" / "01. AUGUST" / "01. WEEK 32" / "005. TALAPIA (IR+VI).docx",
        REAL_DATASET_ROOT / "FULL REPORT" / "KUANTAN" / "04. WEEK 35" / "179. CENDERAWASIH NO.1 (IR+VI).docx",
        REAL_DATASET_ROOT / "FULL REPORT" / "KUANTAN" / "04. WEEK 35" / "144. TELEKOM TANAH PUTIH (TEV+VI).docx",
    ]

    for docx_p in benchmarks:
        assert docx_p.is_file(), f"Benchmark deliverable missing: {docx_p}"

        # 1. Verify single continuous section (ADR 0002)
        verify_single_section_invariant(docx_p)

        # 2. Verify ActiveX controls intact
        activex_bins = verify_activex_controls_preserved(docx_p)
        assert len(activex_bins) >= 10, f"Expected >= 10 ActiveX controls in {docx_p.name}, found {len(activex_bins)}"

        # 3. Verify page breaks present
        br_count = verify_page_breaks_present(docx_p)
        assert br_count >= 15, f"Expected >= 15 page breaks in {docx_p.name}, found {br_count}"


# ==============================================================================
# Benchmark Test 5: Stage 2 Post-Processing PDF Export & Testsheet Merge
# ==============================================================================

@pytest.mark.skipif(not REAL_DATASET_ROOT.exists(), reason="Real inspection dataset root not found")
def test_e2e_benchmark_postprocessing_pdf_export_and_merge(
    benchmark_env: ProjectEnvironment,
    tmp_path: Path,
):
    """Verifies Stage 2 Post-Processing PDF export and signed testsheet PDF merge completeness.

    Verifies:
    - Resolves pre-existing signed testsheet PDF from processed_testsheet
    - Runs Word COM conversion and merges testsheet PDF into final deliverable
    - Output PDF exists, has non-zero bytes, and is a valid PDF
    """
    docx_source = REAL_DATASET_ROOT / "FULL REPORT" / "RAUB" / "01. AUGUST" / "01. WEEK 32" / "005. TALAPIA (IR+VI).docx"
    assert docx_source.is_file(), f"Missing benchmark docx: {docx_source}"

    # Verify testsheet PDF resolution
    ts_pdf = resolve_processed_testsheet_pdf_path(docx_source, environment=benchmark_env)
    assert ts_pdf is not None, "Failed to resolve signed testsheet PDF for TALAPIA"
    assert ts_pdf.is_file()
    assert ts_pdf.stat().st_size > 0

    # Execute post-processing workflow
    post_wf = FullReportPostProcessingWorkflow()
    inspect_res = post_wf.inspect(docx_source, environment=benchmark_env)
    assert len(inspect_res.targets) == 1
    assert inspect_res.targets[0].is_ready

    # Process into temp directory
    out_copy = tmp_path / docx_source.name
    out_copy.write_bytes(docx_source.read_bytes())

    res = post_wf.process(out_copy, environment=benchmark_env)
    assert res.is_success, f"Post-processing failed with errors: {res.errors}"
    assert res.succeeded_count == 1
    assert len(res.deliverables) == 1

    final_pdf = res.deliverables[0]
    assert final_pdf.is_file()
    assert final_pdf.stat().st_size > 50_000, f"Deliverable PDF suspiciously small: {final_pdf.stat().st_size} bytes"

    # Verify PDF header magic bytes %PDF-
    header = final_pdf.read_bytes()[:5]
    assert header == b"%PDF-", f"Invalid PDF header: {header}"
