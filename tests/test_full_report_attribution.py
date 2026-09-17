"""Unit tests for Full Report substation attribution and structural guards (Ticket #44 / Seam 1)."""

from __future__ import annotations

from pathlib import Path
import docx
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import pytest

from src.full_report.attribution import (
    is_substation_attribution_match,
    normalize_substation_tokens,
    verify_cbm_defect_attribution,
    verify_condition_pages_structure,
    verify_front_page_attribution,
    verify_sticker_page_structure,
    verify_vi_defect_pages_structure,
    verify_vi_summary_structure,
)
from src.full_report.defect_parser import CbmDefectSliceMetadata


def test_normalize_substation_tokens_strips_prefixes_suffixes_and_pe_numbers():
    """Verify normalize_substation_tokens strips PE prefixes, electrical tags, and parenthesized suffixes."""
    assert normalize_substation_tokens("005. TALAPIA") == {"TALAPIA"}
    assert normalize_substation_tokens("PE 144 TELEKOM TANAH PUTIH") == {"TELEKOM", "TANAH", "PUTIH"}
    assert normalize_substation_tokens("P/E 179 CENDERAWASIH NO.1") == {"CENDERAWASIH", "NO", "1"} or normalize_substation_tokens("P/E 179 CENDERAWASIH NO.1") == {"CENDERAWASIH", "1"}
    assert normalize_substation_tokens("SSU KOTA PERDANA") == {"KOTA", "PERDANA"}
    assert normalize_substation_tokens("PPU BENTONG") == {"BENTONG"}
    assert normalize_substation_tokens("PMU MARAN") == {"MARAN"}
    assert normalize_substation_tokens("S/S JAYA") == {"JAYA"}
    assert normalize_substation_tokens("TALAPIA (VCB)") == {"TALAPIA"}
    assert normalize_substation_tokens("TALAPIA (IR+VI)") == {"TALAPIA"}
    assert normalize_substation_tokens("PERPUSTAKAAN AWAM (IR+US+TEV)") == {"PERPUSTAKAAN", "AWAM"}
    assert normalize_substation_tokens("TAMAN TAS (F/P)") == {"TAMAN", "TAS"}


def test_is_substation_attribution_match():
    """Verify is_substation_attribution_match matches targets and rejects foreign substations."""
    # Target subset or exact match
    assert is_substation_attribution_match("TALAPIA", "005. PE TALAPIA (IR+VI)") is True
    assert is_substation_attribution_match("TALAPIA", "TALAPIA") is True
    assert is_substation_attribution_match("TALAPIA", "PE 5 TALAPIA RAUB") is True
    assert is_substation_attribution_match("PE 5 TALAPIA", "TALAPIA") is True
    assert is_substation_attribution_match("CENDERAWASIH NO.1", "PE 179 CENDERAWASIH NO. 1") is True

    # Benign blank/empty/dash values allowed
    assert is_substation_attribution_match("PERPUSTAKAAN AWAM", "") is True
    assert is_substation_attribution_match("PERPUSTAKAAN AWAM", "-") is True
    assert is_substation_attribution_match("PERPUSTAKAAN AWAM", None) is True

    # Explicit foreign conflict rejected
    assert is_substation_attribution_match("PERPUSTAKAAN AWAM", "TELEKOM TANAH PUTIH") is False
    assert is_substation_attribution_match("PERPUSTAKAAN AWAM", "PE 5 TALAPIA") is False
    assert is_substation_attribution_match("TALAPIA", "CENDERAWASIH NO.1") is False


def test_verify_cbm_defect_attribution():
    """Verify CBM defect slice metadata is checked against target substation."""
    meta_matching = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p01",
        equipment_id="VCB1",
        defect_area="CABLE_BOX",
        substation="PE 5 TALAPIA",
    )
    assert verify_cbm_defect_attribution(meta_matching, "TALAPIA") is True

    meta_blank = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p01",
        equipment_id="VCB1",
        defect_area="CABLE_BOX",
        substation="",
    )
    # Blank allowed with warning
    assert verify_cbm_defect_attribution(meta_blank, "TALAPIA") is True

    meta_foreign = CbmDefectSliceMetadata(
        equipment_category="swg",
        equipment_instance="swg1",
        sequence="p01",
        equipment_id="VCB1",
        defect_area="CABLE_BOX",
        substation="TELEKOM TANAH PUTIH",
    )
    assert verify_cbm_defect_attribution(meta_foreign, "TALAPIA") is False


def test_verify_front_page_attribution(tmp_path: Path):
    """Verify Table 1 in front_page.docx is checked for both ERMS and SITE names."""
    doc = docx.Document()
    doc.add_table(rows=1, cols=3)  # Table 0
    t1 = doc.add_table(rows=5, cols=3)  # Table 1
    t1.rows[0].cells[0].text = "FUNCTIONAL LOCATION (ERMS)"
    t1.rows[1].cells[0].text = "FUNCTIONAL LOCATION (SITE)"
    t1.rows[2].cells[0].text = "SUBSTATION NAME (ERMS)"
    t1.rows[2].cells[2].text = "PE 12 PERPUSTAKAAN AWAM"
    t1.rows[3].cells[0].text = "SUBSTATION NAME (SITE)"
    t1.rows[3].cells[2].text = "PERPUSTAKAAN AWAM"

    front_valid = tmp_path / "front_valid.docx"
    doc.save(front_valid)

    valid, reason = verify_front_page_attribution(front_valid, "PERPUSTAKAAN AWAM")
    assert valid is True
    assert reason == ""

    # Mutate to foreign substation
    t1.rows[2].cells[2].text = "PE 144 TELEKOM TANAH PUTIH"
    t1.rows[3].cells[2].text = "TELEKOM TANAH PUTIH"
    front_foreign = tmp_path / "front_foreign.docx"
    doc.save(front_foreign)

    valid_f, reason_f = verify_front_page_attribution(front_foreign, "PERPUSTAKAAN AWAM")
    assert valid_f is False
    assert "TELEKOM TANAH PUTIH" in reason_f


def test_verify_structural_guards(tmp_path: Path):
    """Verify structural guards for condition_pages, sticker_page, vi_summary, and vi_defect_pages."""
    # 1. Condition pages: requires >= 1 table and >= 1 image
    doc_cond = docx.Document()
    doc_cond.add_table(rows=2, cols=2)
    # Add a mock drawing element to satisfy image check
    p = doc_cond.add_paragraph()
    run = p.add_run()
    drawing_elm = parse_xml(r'<w:drawing %s><w:inline><a:graphic %s><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic %s><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:inline></w:drawing>' % (nsdecls('w'), nsdecls('a'), nsdecls('pic', 'r')))
    run._r.append(drawing_elm)
    cond_path = tmp_path / "condition_pages.docx"
    doc_cond.save(cond_path)

    valid, reason = verify_condition_pages_structure(cond_path)
    assert valid is True

    # 2. Sticker page: requires NORMAL STICKER or DEFECT STICKER
    doc_stk = docx.Document()
    doc_stk.add_paragraph("SUBSTATION NORMAL STICKER ATTACHED")
    stk_path = tmp_path / "sticker_page.docx"
    doc_stk.save(stk_path)

    valid_stk, _ = verify_sticker_page_structure(stk_path)
    assert valid_stk is True

    doc_bad_stk = docx.Document()
    doc_bad_stk.add_paragraph("JUST SOME RANDOM TEXT")
    bad_stk_path = tmp_path / "bad_sticker.docx"
    doc_bad_stk.save(bad_stk_path)
    valid_bad_stk, reason = verify_sticker_page_structure(bad_stk_path)
    assert valid_bad_stk is False

    # 3. VI summary: table rows match expected count
    doc_visum = docx.Document()
    t_visum = doc_visum.add_table(rows=3, cols=4)  # 1 header + 2 data rows
    visum_path = tmp_path / "vi_summary.docx"
    doc_visum.save(visum_path)

    valid_vi, _ = verify_vi_summary_structure(visum_path, expected_count=2)
    assert valid_vi is True

    valid_vi_bad, reason = verify_vi_summary_structure(visum_path, expected_count=5)
    assert valid_vi_bad is False

    # 4. VI defect pages: requires images
    doc_videf = docx.Document()
    p_vi = doc_videf.add_paragraph()
    r_vi = p_vi.add_run()
    r_vi._r.append(parse_xml(r'<w:drawing %s><w:inline><a:graphic %s><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic %s><pic:blipFill><a:blip r:embed="rId2"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:inline></w:drawing>' % (nsdecls('w'), nsdecls('a'), nsdecls('pic', 'r'))))
    videf_path = tmp_path / "vi_defect_pages.docx"
    doc_videf.save(videf_path)

    valid_videf, _ = verify_vi_defect_pages_structure(videf_path)
    assert valid_videf is True


def test_inspect_deliverable_attribution_and_quarantine(tmp_path: Path):
    """Verify post-compilation headless OpenXML inspection detects foreign headers and quarantines file."""
    from src.full_report.attribution import inspect_deliverable_attribution, quarantine_deliverable

    # 1. Clean deliverable matching target
    doc_clean = docx.Document()
    t_clean = doc_clean.add_table(rows=2, cols=3)
    t_clean.rows[0].cells[0].text = "SUBSTATION NAME"
    t_clean.rows[0].cells[2].text = "PE 12 PERPUSTAKAAN AWAM"
    t_clean.rows[1].cells[0].text = "FEEDER NAME"
    t_clean.rows[1].cells[2].text = "FEEDER TO PE TALAPIA"  # Feeder line ignored!

    clean_path = tmp_path / "012. PERPUSTAKAAN AWAM.docx"
    doc_clean.save(clean_path)

    valid, reason = inspect_deliverable_attribution(clean_path, "PERPUSTAKAAN AWAM")
    assert valid is True
    assert reason == ""

    # 2. Compromised deliverable with foreign header
    doc_foreign = docx.Document()
    t_front = doc_foreign.add_table(rows=1, cols=3)
    t_front.rows[0].cells[0].text = "SUBSTATION"
    t_front.rows[0].cells[2].text = "PERPUSTAKAAN AWAM"
    # Leaked foreign defect page table!
    t_leak = doc_foreign.add_table(rows=2, cols=2)
    t_leak.rows[0].cells[0].text = "Substation"
    t_leak.rows[0].cells[1].text = "TELEKOM TANAH PUTIH"

    compromised_path = tmp_path / "compromised_report.docx"
    doc_foreign.save(compromised_path)

    valid_f, reason_f = inspect_deliverable_attribution(compromised_path, "PERPUSTAKAAN AWAM")
    assert valid_f is False
    assert "TELEKOM TANAH PUTIH" in reason_f

    # 3. Quarantine
    quarantine_dir = tmp_path / ".quarantine"
    quarantined_path = quarantine_deliverable(compromised_path, quarantine_dir)

    assert not compromised_path.exists()
    assert quarantined_path.exists()
    assert quarantined_path.parent == quarantine_dir
    assert quarantined_path.name == "compromised_report.docx"

