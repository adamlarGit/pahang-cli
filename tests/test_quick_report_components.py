"""Unit tests for Quick Report components."""

from pathlib import Path
from src.quick_report.cbm_summary import prepare_tech_summary_rows

def test_prepare_tech_summary_rows():
    defects = [
        {"equipment": "TX", "technology": "IR", "defect_area": "Body", "reading": "50"},
        {"equipment": "TX", "technology": "US", "defect_area": "Body", "reading": "20"},
    ]
    rows = prepare_tech_summary_rows(defects)
    assert len(rows) == 1
    assert rows[0].equipment == "TX"
    assert rows[0].ir_reading == "50 °C"
    assert rows[0].us_reading == "20dB"

def test_prepare_tech_summary_rows_empty():
    rows = prepare_tech_summary_rows([])
    assert len(rows) == 0

def test_prepare_tech_summary_rows_different_areas():
    defects = [
        {"equipment": "TX", "technology": "IR", "defect_area": "Body", "reading": "50"},
        {"equipment": "TX", "technology": "US", "defect_area": "Bush", "reading": "20"},
    ]
    rows = prepare_tech_summary_rows(defects)
    assert len(rows) == 2


def test_environment_front_page_template_resolution():
    from unittest.mock import MagicMock
    from src.project.environment import ProjectEnvironment
    from src.project.models import ProjectMetadata
    from src.project.storage import WorkspaceStorage

    def make_env(techs):
        meta = ProjectMetadata("k", "n", "po", "st", "11kV", "2026", "c1", techs, "p")
        storage = MagicMock(spec=WorkspaceStorage)
        storage.get_template.side_effect = lambda k: Path(f"/templates/{k}.docx")
        return ProjectEnvironment(meta, storage)

    env_ir = make_env(("IR",))
    assert env_ir.get_vi_front_page_template() == Path("/templates/vi_front_page_ir.docx")

    env_us = make_env(("IR", "US"))
    assert env_us.get_vi_front_page_template() == Path("/templates/vi_front_page_ir_us.docx")

    env_tev = make_env(("IR", "US", "TEV"))
    assert env_tev.get_vi_front_page_template() == Path("/templates/vi_front_page_ir_us_tev.docx")


def test_environment_cbm_summary_template_resolution():
    from unittest.mock import MagicMock
    from src.project.environment import ProjectEnvironment
    from src.project.models import ProjectMetadata
    from src.project.storage import WorkspaceStorage

    def make_env(techs):
        meta = ProjectMetadata("k", "n", "po", "st", "11kV", "2026", "c1", techs, "p")
        storage = MagicMock(spec=WorkspaceStorage)
        storage.get_template.side_effect = lambda k: Path(f"/templates/{k}.docx")
        return ProjectEnvironment(meta, storage)

    env_ir = make_env(("IR",))
    assert env_ir.get_cbm_summary_template() == Path("/templates/cbm_summary_ir.docx")

    env_us = make_env(("IR", "US"))
    assert env_us.get_cbm_summary_template() == Path("/templates/cbm_summary_ir_us.docx")

    env_tev = make_env(("IR", "US", "TEV"))
    assert env_tev.get_cbm_summary_template() == Path("/templates/cbm_summary_ir_us_tev.docx")


def test_generate_vi_summary_programmatic(tmp_path: Path):
    import docx
    from src.quick_report.vi_summary import generate_vi_summary

    template_p = Path("templates/QUICK REPORT/2. VI SUMMARY TEMPLATE Jinja2 DYNAMIC.docx")
    if not template_p.exists():
        # Create a dummy template docx with 4 columns and 4 rows
        template_p = tmp_path / "vi_template.docx"
        doc = docx.Document()
        table = doc.add_table(rows=4, cols=4)
        for j, h in enumerate(["NO.", "EQUIPMENT", "DEFECT DESCRIPTION", "REMARKS"]):
            table.rows[0].cells[j].text = h
        doc.save(template_p)

    pe_info = {"substation": {"name_erms": "TEST SUB"}}
    defects = [
        {"equipment": "SWITCHGEAR", "defect_area": "Indicator Fault", "remarks": "Replace lamp"},
        {"equipment": "TRANSFORMER", "defect_area": "Oil Leakage", "remarks": "Top up oil"},
    ]

    out_path = generate_vi_summary(pe_info, defects, template_p, tmp_path, 1)
    assert out_path.exists()

    rendered_doc = docx.Document(out_path)
    assert len(rendered_doc.tables) == 1
    t = rendered_doc.tables[0]
    assert len(t.rows) == 3  # 1 header + 2 data rows

    # Header verification
    header_texts = [c.text.strip() for c in t.rows[0].cells]
    assert header_texts == ["NO.", "EQUIPMENT", "DEFECT DESCRIPTION", "REMARKS"]

    # Data rows verification
    r1_texts = [c.text.strip() for c in t.rows[1].cells]
    assert r1_texts == ["1", "SWITCHGEAR", "Indicator Fault", "Replace lamp"]

    r2_texts = [c.text.strip() for c in t.rows[2].cells]
    assert r2_texts == ["2", "TRANSFORMER", "Oil Leakage", "Top up oil"]

    # Check cell XML formatting
    tcPr = t.rows[1].cells[0]._tc.get_or_add_tcPr()
    assert tcPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}vAlign") is not None
    pPr = t.rows[1].cells[0].paragraphs[0]._p.get_or_add_pPr()
    assert pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}jc") is not None
    assert pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}spacing") is not None


def test_generate_cbm_tech_summary_programmatic(tmp_path: Path):
    import docx
    from src.quick_report.cbm_summary import generate_cbm_tech_summary

    template_p = Path("templates/QUICK REPORT/CBM DEFECT IR SUMMARY.docx")
    if not template_p.exists():
        template_p = tmp_path / "cbm_template.docx"
        doc = docx.Document()
        table = doc.add_table(rows=4, cols=6)
        for j, h in enumerate(["NO.", "EQUIPMENT", "DEFECT AREA", "IR (Abs T/ΔT)", "IR (ΔT)", "DEFECT"]):
            table.rows[0].cells[j].text = h
        doc.save(template_p)

    pe_info = {"substation": {"name_erms": "TEST SUB"}}
    defects = [
        {"equipment": "TRANSFORMER", "technology": "IR", "defect_area": "HV Bushing", "reading": "65", "status": "PENDING"},
    ]

    out_path = generate_cbm_tech_summary(pe_info, defects, template_p, tmp_path, 1)
    assert out_path.exists()

    rendered_doc = docx.Document(out_path)
    assert len(rendered_doc.tables) == 1
    t = rendered_doc.tables[0]
    assert len(t.rows) == 2  # 1 header + 1 data row

    r1_texts = [c.text.strip() for c in t.rows[1].cells]
    assert r1_texts[0] == "1"
    assert r1_texts[1] == "TRANSFORMER"
    assert r1_texts[2] == "HV Bushing"
    assert r1_texts[3] == "65 °C"

    # Check cell XML formatting
    tcPr = t.rows[1].cells[0]._tc.get_or_add_tcPr()
    assert tcPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}vAlign") is not None
    pPr = t.rows[1].cells[0].paragraphs[0]._p.get_or_add_pPr()
    assert pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}jc") is not None
    assert pPr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}spacing") is not None




