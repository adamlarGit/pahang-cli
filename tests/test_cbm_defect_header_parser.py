"""Unit tests for CBM Defect Header Parsing & D37 Naming (Ticket 004 / T1.3b)."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.full_report.defect_parser import (
    CbmDefectHeaderParser,
    CbmDefectSliceMetadata,
    build_d37_defect_filename,
)


def test_parse_swg_defect_table_d37_benchmark():
    """Verify parsing of Switchgear defect Table 1 matching D37 benchmark example."""
    table_grid = [
        ["Substation", "CENDERAWASIH NO.1", "Date: 28-Aug-2026"],
        ["Equipment", "RMU SF6", "Manufacturer", "INDKOM", "Time: 10:00 AM"],
        ["Model", "INS24", "Rating", "630A", "Humidity: 65%"],
        ["Area", "FUSE COMPARTMENT", "Panel No.", "p04"],
        ["Panel Name", "CKN01309"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert isinstance(meta, CbmDefectSliceMetadata)
    assert meta.equipment_category == "swg"
    assert meta.equipment_instance == "swg1"
    assert meta.sequence == "p04"
    assert meta.equipment_id == "CKN01309"
    assert meta.defect_area == "FUSE_COMPARTMENT"
    assert meta.index == 1
    assert meta.filename == "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"
    assert build_d37_defect_filename(meta) == "swg1_p04_CKN01309_FUSE_COMPARTMENT_01.docx"


def test_parse_swg_overview_table():
    """Verify parsing of Switchgear Overview Table 1 maps to sequence p00."""
    table_grid = [
        ["Substation", "PE TEST", "Date: 04-Aug-2026"],
        ["Equipment", "VCB", "Manufacturer", "TAMCO", "Time: 10:00 AM"],
        ["Model", "-", "Rating", "-", "Humidity: -"],
        ["Area", "OVERVIEW", "Panel No.", "-"],
        ["Panel Name", "-"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert meta.equipment_category == "swg"
    assert meta.equipment_instance == "swg1"
    assert meta.sequence == "p00"
    assert meta.defect_area == "OVERVIEW"
    assert meta.equipment_id == "SWG1"
    assert meta.filename == "swg1_p00_SWG1_OVERVIEW_01.docx"


def test_parse_transformer_defect_table():
    """Verify parsing of Transformer defect Table 1."""
    table_grid = [
        ["Substation", "TALAPIA", "Date: 04-Aug-2026"],
        ["Equipment", "TRANSFORMER", "Manufacturer", "MTM", "Time: 10:00 AM"],
        ["Model", "750kVA", "Rating", "11kV/415V", "Humidity: 60%"],
        ["Area", "HV BUSHING", "Tx No.", "1"],
        ["Location", "TX ROOM"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert meta.equipment_category == "tx"
    assert meta.equipment_instance == "tx1"
    assert meta.sequence == "s02"
    assert meta.defect_area == "HV_BUSHING"
    assert meta.equipment_id == "TX1"
    assert meta.filename == "tx1_s02_TX1_HV_BUSHING_01.docx"


def test_parse_transformer_2_lv_bushing_defect():
    """Verify parsing of Transformer 2 LV Bushing defect table."""
    table_grid = [
        ["Substation", "BUKIT SETONGKOL MEWAH", "Date: 28-Aug-2026"],
        ["Equipment", "TRANSFORMER", "Manufacturer", "MTM", "Time: 11:00 AM"],
        ["Model", "500kVA", "Rating", "11kV/415V", "Humidity: 65%"],
        ["Area", "LV Bushing", "Tx No.", "2"],
        ["Location", "TX ROOM"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid, index=2)

    assert meta.equipment_category == "tx"
    assert meta.equipment_instance == "tx2"
    assert meta.sequence == "s05"
    assert meta.defect_area == "LV_BUSHING"
    assert meta.equipment_id == "TX2"
    assert meta.index == 2
    assert meta.filename == "tx2_s05_TX2_LV_BUSHING_02.docx"


def test_parse_feeder_pillar_defect_table():
    """Verify parsing of Feeder Pillar defect Table 1."""
    table_grid = [
        ["Substation", "TALAPIA", "Date: 04-Aug-2026"],
        ["Equipment", "FEEDER PILLAR", "Manufacturer", "TAMCO", "Time: 11:30 AM"],
        ["Model", "10 WAY", "Rating", "1600A", "Humidity: 60%"],
        ["Area", "Fuse Base", "Feeder No.", "F02"],
        ["Feeder Name", "OUTGOING F2"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert meta.equipment_category == "fp"
    assert meta.equipment_instance == "fp1"
    assert meta.sequence == "f02"
    assert meta.defect_area == "FUSE_BASE"
    assert meta.equipment_id == "OUTGOING_F2"
    assert meta.filename == "fp1_f02_OUTGOING_F2_FUSE_BASE_01.docx"


def test_parse_feeder_pillar_overview_table():
    """Verify parsing of Feeder Pillar overview Table 1."""
    table_grid = [
        ["Substation", "TALAPIA", "Date: 04-Aug-2026"],
        ["Equipment", "FEEDER PILLAR (OUTDOOR)", "Manufacturer", "TAMCO", "Time: 11:30 AM"],
        ["Model", "10 WAY", "Rating", "1600A", "Humidity: 60%"],
        ["Area", "OVERVIEW", "Feeder No.", "-"],
        ["Feeder Name", "-"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert meta.equipment_category == "fp"
    assert meta.equipment_instance == "fp1"
    assert meta.sequence == "f00"
    assert meta.defect_area == "OVERVIEW"
    assert meta.filename == "fp1_f00_FP1_OVERVIEW_01.docx"


def test_parse_battery_overview_table():
    """Verify parsing of Battery Bank overview Table 1."""
    table_grid = [
        ["Substation", "TALAPIA", "Date: 04-Aug-2026"],
        ["Equipment", "BATTERY BANK", "Manufacturer", "SUNPOWER", "Time: 11:30 AM"],
        ["Model", "24V", "Rating", "240V/50Hz", "Humidity: 60%"],
        ["Area", "OVERVIEW", "Battery No.", "1"],
        ["Location", "-"],
    ]

    parser = CbmDefectHeaderParser()
    meta = parser.parse(table_grid)

    assert meta.equipment_category == "battery"
    assert meta.equipment_instance == "battery1"
    assert meta.sequence == "b00"
    assert meta.defect_area == "OVERVIEW"
    assert meta.filename == "battery1_b00_BATTERY1_OVERVIEW_01.docx"


def test_parse_docx_file_path(tmp_path):
    """Verify parsing Table 1 directly from a saved .docx file."""
    import docx

    doc_path = tmp_path / "mock_swg_defect.docx"
    doc = docx.Document()
    table = doc.add_table(rows=5, cols=3)
    table.rows[0].cells[0].text = "Substation"
    table.rows[0].cells[1].text = "CENDERAWASIH NO.1"
    table.rows[1].cells[0].text = "Equipment"
    table.rows[1].cells[1].text = "RMU SF6"
    table.rows[2].cells[0].text = "Model"
    table.rows[2].cells[1].text = "INS24"
    table.rows[3].cells[0].text = "Area"
    table.rows[3].cells[1].text = "Cable Compartment"
    table.rows[3].cells[2].text = "Panel No. 2"
    table.rows[4].cells[0].text = "Panel Name"
    table.rows[4].cells[1].text = "INCOMING 2"
    doc.save(str(doc_path))

    parser = CbmDefectHeaderParser()
    meta = parser.parse(doc_path)

    assert meta.equipment_category == "swg"
    assert meta.equipment_instance == "swg1"
    assert meta.sequence == "p02"
    assert meta.defect_area == "CABLE_COMPARTMENT"
    assert meta.equipment_id == "INCOMING_2"
    assert meta.filename == "swg1_p02_INCOMING_2_CABLE_COMPARTMENT_01.docx"


def test_parse_real_rendered_quick_report_defect_pages(tmp_path):
    """Verify CbmDefectHeaderParser on real docx generated by QuickReport generator."""
    from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
    from src.quick_report.defects import CbmDefectRecord
    from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup
    from src.testsheet.models import SubstationEquipmentPackage, SwitchgearPanelSpec, SwitchgearSpec, TestsheetData

    overview_tpl = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-overview.docx")
    detail_tpl = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-panel.docx")
    if not overview_tpl.exists() or not detail_tpl.exists():
        pytest.skip("Quick report templates not available.")

    panel1 = SwitchgearPanelSpec(panel_no=1, panel_feeder_no="F01", name="INCOMING 1")
    swg_equipment = SwitchgearSpec(switchgear_type="VCB", manufacturer="TAMCO", panels=(panel1,))
    equipment_pkg = SubstationEquipmentPackage(switchgears=(swg_equipment,))
    ts_data = TestsheetData(substation_number=1, substation_name_erms="PE TEST", equipment=equipment_pkg)
    pe_info = {"substation": {"name_erms": "PE TEST"}, "testsheet_data": ts_data, "equipment": equipment_pkg}
    defect_rec = CbmDefectRecord(equipment="INCOMING 1", technology="US", defect_area="Cable Box")
    detail_group = CbmDefectDetailGroup(role_id="panel_area", defects=(defect_rec,))
    group = CbmDefectGroup(item_key="INCOMING 1", item_suffix="", defects=(defect_rec,), overview=defect_rec, detail_groups=(detail_group,))
    family_plan = CbmDefectFamilyPlan(
        spec=QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"],
        overview_template=overview_tpl,
        detail_templates=(("panel_area", detail_tpl),),
        groups=(group,),
    )

    out_dir = tmp_path / "rendered"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = generate_cbm_defect_pages(plan=family_plan, output_dir=out_dir, substation_number=1, pe_info=pe_info)

    assert len(generated) == 2
    parser = CbmDefectHeaderParser()

    # Overview page
    overview_meta = parser.parse(generated[0])
    assert overview_meta.equipment_category == "swg"
    assert overview_meta.sequence == "p00"
    assert overview_meta.defect_area == "OVERVIEW"
    assert overview_meta.filename == "swg1_p00_SWG1_OVERVIEW_01.docx"

    # Detail page
    detail_meta = parser.parse(generated[1])
    assert detail_meta.equipment_category == "swg"
    assert detail_meta.sequence == "p01"
    assert detail_meta.defect_area == "CABLE_BOX"
    assert detail_meta.equipment_id == "INCOMING_1"
    assert detail_meta.filename == "swg1_p01_INCOMING_1_CABLE_BOX_01.docx"


def test_parse_batch_increments_duplicate_indices():
    """Verify parse_batch automatically increments the D37 index for duplicate equipment/areas."""
    table1 = [
        ["Substation", "PE TEST"],
        ["Equipment", "RMU SF6"],
        ["Area", "CABLE COMPARTMENT", "Panel No.", "1"],
        ["Panel Name", "INCOMING 1"],
    ]
    table2 = [
        ["Substation", "PE TEST"],
        ["Equipment", "RMU SF6"],
        ["Area", "CABLE COMPARTMENT", "Panel No.", "1"],
        ["Panel Name", "INCOMING 1"],
    ]

    parser = CbmDefectHeaderParser()
    results = parser.parse_batch([table1, table2])

    assert len(results) == 2
    assert results[0].index == 1
    assert results[0].filename == "swg1_p01_INCOMING_1_CABLE_COMPARTMENT_01.docx"
    assert results[1].index == 2
    assert results[1].filename == "swg1_p01_INCOMING_1_CABLE_COMPARTMENT_02.docx"



