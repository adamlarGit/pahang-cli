"""End-to-End Verification with Real Substation Inspection Datasets (Ticket 106)."""

from __future__ import annotations

from pathlib import Path
import docx
from docx.oxml.ns import qn
import pytest

from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
from src.quick_report.defects import CbmDefectRecord
from src.quick_report.models import (
    CbmDefectDetailGroup,
    CbmDefectFamilyPlan,
    CbmDefectGroup,
)
from src.testsheet.extractor import TestsheetExtractor


REAL_DATASET_ROOT = Path(r"\\?\C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD")


@pytest.mark.skipif(
    not REAL_DATASET_ROOT.exists(),
    reason="Real inspection datasets not available on current environment",
)
def test_e2e_real_substation_tras_swg_and_prpd(tmp_path: Path):
    """End-to-end verification of Substation 020 TRAS with real testsheet and raw survey data."""
    ts_path = (
        REAL_DATASET_ROOT
        / "TESTSHEET"
        / "RAUB"
        / "01. AUGUST"
        / "05-08-2026"
        / "020 IR.xlsx"
    )
    raw_material_dir = (
        REAL_DATASET_ROOT
        / "RAW MATERIAL"
        / "RAUB"
        / "01. AUGUST"
        / "05-08-2026"
        / "020. TRAS (IR+VI)"
    )

    if not ts_path.exists() or not raw_material_dir.exists():
        pytest.skip("Dataset for 020 TRAS not found.")

    # 1. Ingest testsheet
    extractor = TestsheetExtractor()
    ts_data = extractor.extract_testsheet_data(ts_path)

    assert ts_data.substation_name_erms == "TRAS"
    assert ts_data.tev_background == "2"
    assert len(ts_data.equipment.switchgear.panels) == 4
    assert ts_data.equipment.switchgear.panels[0].name == "DURIAN TRAS"

    # 2. Setup render plan
    pe_info = {
        "substation": {
            "name_erms": ts_data.substation_name_erms,
            "tev_bg": ts_data.tev_background,
        },
        "tev_bg": ts_data.tev_background,
        "raw_data_dir": raw_material_dir,
        "testsheet_data": ts_data,
        "equipment": ts_data.equipment,
    }

    swg_spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]
    overview_tpl = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-overview.docx")
    detail_tpl = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-panel.docx")

    defect_rec = CbmDefectRecord(
        equipment="FEEDER 1",
        technology="US",
        defect_area="Spout",
        us_reading="15.0",
        us_char="TRACKING",
    )
    detail_group = CbmDefectDetailGroup(role_id="panel_area", defects=(defect_rec,))
    group = CbmDefectGroup(
        item_key="FEEDER 1",
        item_suffix="",
        defects=(defect_rec,),
        overview=defect_rec,
        detail_groups=(detail_group,),
    )
    family_plan = CbmDefectFamilyPlan(
        spec=swg_spec,
        overview_template=overview_tpl,
        detail_templates=(("panel_area", detail_tpl),),
        groups=(group,),
    )

    # 3. Generate pages
    out_dir = tmp_path / "out_e2e_tras"
    generated = generate_cbm_defect_pages(
        plan=family_plan,
        output_dir=out_dir,
        substation_number=20,
        pe_info=pe_info,
    )

    assert len(generated) == 2

    # 4. Verify detail page DOCX table cell shading & PRPD images
    detail_doc = docx.Document(generated[1])
    t = detail_doc.tables[0]

    # IR severity cell -> Green #00B050
    shd_ir = t.rows[18].cells[3]._tc.get_or_add_tcPr().find(qn("w:shd"))
    assert shd_ir is not None and shd_ir.get(qn("w:fill")) == "00B050"
    assert t.rows[18].cells[3].text.strip() == ""

    # US severity cell -> Red #EE0000
    shd_us = t.rows[30].cells[4]._tc.get_or_add_tcPr().find(qn("w:shd"))
    assert shd_us is not None and shd_us.get(qn("w:fill")) == "EE0000"
    assert t.rows[30].cells[4].text.strip() == ""

    # TEV severity cell -> Green #00B050
    shd_tev = t.rows[30].cells[18]._tc.get_or_add_tcPr().find(qn("w:shd"))
    assert shd_tev is not None and shd_tev.get(qn("w:fill")) == "00B050"
    assert t.rows[30].cells[18].text.strip() == ""

    # Check PRPD images embedded
    assert len(detail_doc.inline_shapes) >= 2
