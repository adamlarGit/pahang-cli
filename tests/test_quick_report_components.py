"""Unit tests for Quick Report components."""

from pathlib import Path
import pytest
from src.quick_report.cbm_summary import (
    format_db_reading,
    format_temperature_reading,
    prepare_tech_summary_rows,
)
from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
from src.quick_report.models import ViDefectPagePlan, ViSummaryRow
from src.quick_report.vi_defect_pages import ViDefectPageBuilder, build_vi_defect_page_context
from src.quick_report.vi_summary import build_vi_summary_context, prepare_vi_summary_rows


def test_format_temperature_reading():
    assert format_temperature_reading("") == "-"
    assert format_temperature_reading(None) == "-"
    assert format_temperature_reading("-") == "-"
    assert format_temperature_reading("50") == "50 °C"
    assert format_temperature_reading("50.5") == "50.5 °C"
    assert format_temperature_reading("50 °C") == "50 °C"
    assert format_temperature_reading("50°C") == "50 °C"


def test_quick_report_transformer_date_formatting():
    """Verify QuickReportTransformer formats datefrontpage as DD MMM YYYY and date as DD/MM/YYYY."""
    from unittest.mock import MagicMock
    from src.quick_report.transformer import QuickReportTransformer

    transformer = QuickReportTransformer()

    pkg = MagicMock()
    pkg.station = "KUANTAN"
    pkg.month = "08. AUGUST"
    pkg.substation_number = 1
    pkg.data = MagicMock()
    pkg.data.date_str = "12-08-2026"
    pkg.data.substation_name_erms = "TEST SUBSTATION"
    pkg.data.substation_name_site = "TEST SUBSTATION"
    pkg.data.fl_erms = "FL123"
    pkg.data.fl_site = "FL123"
    pkg.data.gps_coordinate = ""
    pkg.data.substation_type = ""
    pkg.data.building_type = ""
    pkg.data.ambient = ""
    pkg.data.humidity = ""
    pkg.data.time = ""

    env = MagicMock()
    env.po_number = "12345"
    env.state = "PAHANG"
    env.get_vi_front_page_template.return_value = Path("dummy.docx")
    env.get_template.return_value = Path("dummy.docx")

    plan = transformer.transform(pkg, [], [], env)

    substation_info = plan.pe_info["substation"]
    assert substation_info["datefrontpage"] == "12 AUG 2026"
    assert substation_info["date"] == "12/08/2026"

    # Test with ISO date string format
    pkg.data.date_str = "2026-08-12"
    plan_iso = transformer.transform(pkg, [], [], env)
    assert plan_iso.pe_info["substation"]["datefrontpage"] == "12 AUG 2026"
    assert plan_iso.pe_info["substation"]["date"] == "12/08/2026"

    # Test fallback for None / empty date_str
    pkg.data.date_str = None
    plan_none = transformer.transform(pkg, [], [], env)
    assert plan_none.pe_info["substation"]["datefrontpage"] == "-"
    assert plan_none.pe_info["substation"]["date"] == "-"


def test_format_db_reading():
    assert format_db_reading("") == "-"
    assert format_db_reading(None) == "-"
    assert format_db_reading("-") == "-"
    assert format_db_reading("12") == "12dB"
    assert format_db_reading("12.0") == "12dB"
    assert format_db_reading("12.5") == "12.5dB"
    assert format_db_reading("12dB") == "12dB"


def test_prepare_tech_summary_rows():
    defects = [
        CbmDefectRecord(equipment="TX", technology="IR", defect_area="Body", raw_measurement="50", ir_reading="50"),
        CbmDefectRecord(equipment="TX", technology="US", defect_area="Body", raw_measurement="20", us_reading="20"),
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
        CbmDefectRecord(equipment="TX", technology="IR", defect_area="Body", raw_measurement="50", ir_reading="50"),
        CbmDefectRecord(equipment="TX", technology="US", defect_area="Bush", raw_measurement="20", us_reading="20"),
    ]
    rows = prepare_tech_summary_rows(defects)
    assert len(rows) == 2


def test_cbm_defect_record_normalization():
    # 1. Technology upper-casing and string whitespace stripping
    rec = CbmDefectRecord(
        equipment="  TX 1  ",
        technology="  ir  ",
        brand="  ABB  ",
        model="  XYZ  ",
        rating="  11kV  ",
        defect_area="  Body  ",
        additional_remarks="  Hotspot  ",
        raw_measurement="  55.4  ",
    )
    assert rec.technology == "IR"
    assert rec.equipment == "TX 1"
    assert rec.brand == "ABB"
    assert rec.model == "XYZ"
    assert rec.rating == "11kV"
    assert rec.defect_area == "Body"
    assert rec.additional_remarks == "Hotspot"
    # Invariant: IR reading populated from raw_measurement
    assert rec.raw_measurement == "55.4"
    assert rec.ir_reading == "55.4"

    # 2. Invariant: IR reading populates raw_measurement if raw_measurement empty
    rec_ir2 = CbmDefectRecord(technology="IR", ir_reading="  60.1  ")
    assert rec_ir2.ir_reading == "60.1"
    assert rec_ir2.raw_measurement == "60.1"

    # 3. Invariant: US technology
    rec_us = CbmDefectRecord(technology="us", raw_measurement="  15.0  ")
    assert rec_us.technology == "US"
    assert rec_us.us_reading == "15.0"
    assert rec_us.raw_measurement == "15.0"

    rec_us2 = CbmDefectRecord(technology="US", us_reading="22.5")
    assert rec_us2.raw_measurement == "22.5"

    # 4. Invariant: TEV technology
    rec_tev = CbmDefectRecord(technology="tev", raw_measurement="  25.0  ")
    assert rec_tev.technology == "TEV"
    assert rec_tev.tev_reading == "25.0"
    assert rec_tev.raw_measurement == "25.0"

    rec_tev2 = CbmDefectRecord(technology="TEV", tev_reading="30.0")
    assert rec_tev2.raw_measurement == "30.0"



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
        ViDefectRecord(equipment="SWITCHGEAR", defect_area="Indicator Fault", additional_remarks="Replace lamp"),
        ViDefectRecord(equipment="TRANSFORMER", defect_area="Oil Leakage", additional_remarks="Top up oil"),
    ]

    out_path = generate_vi_summary(pe_info, defects, template_p, tmp_path, 1)
    assert out_path.exists()

    rendered_doc = docx.Document(out_path)
    assert len(rendered_doc.tables) == 1
    t = rendered_doc.tables[0]
    assert len(t.rows) == 3  # 1 header + 2 data rows

    # Header verification
    header_texts = [c.text.strip() for c in t.rows[0].cells]
    assert header_texts == ["NO.", "EQUIPMENT", "DEFECT DESCRIPTION", "ADDITIONAL REMARKS"]

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


def test_prepare_vi_summary_rows():
    defects = [
        ViDefectRecord(equipment="SWG", defect_area="Door", additional_remarks="Broken latch"),
        ViDefectRecord(equipment="TX", defect_area="Body", additional_remarks="Rust"),
    ]
    rows = prepare_vi_summary_rows(defects)
    assert len(rows) == 2
    assert rows[0] == ViSummaryRow(equipment="SWG", defect_area="Door", remarks="Broken latch")
    assert rows[1] == ViSummaryRow(equipment="TX", defect_area="Body", remarks="Rust")


def test_build_vi_summary_context_accepts_only_vi_defect_record():
    pe_info = {"substation": {"name_erms": "TEST"}}
    defects = [
        ViDefectRecord(equipment="SWG 1", defect_area="Indicator", additional_remarks="Faulty"),
    ]
    context = build_vi_summary_context(pe_info, defects)
    assert context["substation"] == {"name_erms": "TEST"}
    assert len(context["defects"]) == 1
    assert context["defects"][0]["equipment"] == "SWG 1"
    assert context["defects"][0]["defect_area"] == "Indicator"
    assert context["defects"][0]["remarks"] == "Faulty"

    with pytest.raises(AttributeError):
        build_vi_summary_context(pe_info, [{"equipment": "SWG 1"}])  # type: ignore


def test_vi_defect_page_builder_pagination_and_plans(tmp_path: Path):
    template_p = tmp_path / "vi_defect_template.docx"
    template_p.touch()

    builder = ViDefectPageBuilder()
    pe_info = {"substation": {"name_erms": "SUB 1"}}

    # 1. No VI defects returns no page plans (empty list)
    empty_plans = builder.build([], template_p, pe_info, 1)
    assert empty_plans == []

    # 2. 7 VI defects produce 2 ViDefectPagePlan objects
    defects = [
        ViDefectRecord(
            equipment=f"equipment{i}",
            defect_area=f"area{i}",
            additional_remarks=f"remark{i}",
        )
        for i in range(1, 8)
    ]
    plans = builder.build(defects, template_p, pe_info, 1)
    assert len(plans) == 2

    # 3. First page plan contains equipment1 through equipment6
    plan1 = plans[0]
    assert isinstance(plan1, ViDefectPagePlan)
    assert plan1.template_path == template_p
    assert plan1.output_filename == "001_6 VI DEFECT part1.docx"
    assert plan1.active_defect_count == 6
    for i in range(1, 7):
        assert plan1.context[f"equipment{i}"] == f"equipment{i}"
        assert plan1.context[f"description{i}"] == f"area{i}"
        assert plan1.context[f"remark{i}"] == f"remark{i}"

    # 4. Second page plan has active_defect_count == 1
    plan2 = plans[1]
    assert isinstance(plan2, ViDefectPagePlan)
    assert plan2.template_path == template_p
    assert plan2.output_filename == "001_6 VI DEFECT part2.docx"
    assert plan2.active_defect_count == 1
    assert plan2.context["equipment1"] == "equipment7"
    assert plan2.context["description1"] == "area7"
    assert plan2.context["remark1"] == "remark7"
    assert len(plan2.context["defects"]) == 6
    for i in range(2, 7):
        assert plan2.context[f"equipment{i}"] == ""
        assert plan2.context[f"description{i}"] == ""
        assert plan2.context[f"remark{i}"] == ""


def test_vi_defect_record_to_dict_uses_remarks_key():
    rec = ViDefectRecord(
        equipment="SWITCHGEAR",
        defect_area="Rust",
        additional_remarks="Corroded hinges",
    )
    assert rec.additional_remarks == "Corroded hinges"
    d = rec.to_dict()
    assert d == {
        "equipment": "SWITCHGEAR",
        "defect_area": "Rust",
        "remarks": "Corroded hinges",
    }
    assert "additional_remarks" not in d


def test_build_vi_defect_page_context_padding():
    pe_info = {"substation": {"name_erms": "SUB A"}}
    defects = [
        ViDefectRecord(
            equipment="SWG 1",
            defect_area="Oil leak",
            additional_remarks="Minor",
        ),
    ]

    context = build_vi_defect_page_context(pe_info, defects)

    assert len(context["defects"]) == 6
    assert context["defects"][0] == {
        "equipment": "SWG 1",
        "defect_area": "Oil leak",
        "remarks": "Minor",
    }
    for i in range(1, 6):
        assert context["defects"][i] == {
            "equipment": "",
            "defect_area": "",
            "remarks": "",
        }

    assert context["equipment1"] == "SWG 1"
    assert context["description1"] == "Oil leak"
    assert context["remark1"] == "Minor"

    for slot in range(2, 7):
        assert context[f"equipment{slot}"] == ""
        assert context[f"description{slot}"] == ""
        assert context[f"remark{slot}"] == ""


def test_generate_vi_defect_pages_direct_rendering(tmp_path: Path):
    import docx
    from src.quick_report.vi_defect_pages import generate_vi_defect_pages

    template_p = tmp_path / "vi_defect_template.docx"
    doc = docx.Document()
    doc.save(template_p)

    defects = [
        ViDefectRecord(
            equipment="SWG 1",
            defect_area="Door defect",
            additional_remarks="Loose latch",
        ),
    ]
    pe_info = {"substation": {"name_erms": "TEST SUB"}}

    out_paths = generate_vi_defect_pages(
        defects=defects,
        template_path=template_p,
        output_dir=tmp_path,
        substation_number=1,
        pe_info=pe_info,
    )

    assert len(out_paths) == 1
    assert out_paths[0].exists()
    assert out_paths[0].name == "001_6 VI DEFECT part1.docx"


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
        CbmDefectRecord(equipment="TRANSFORMER", technology="IR", defect_area="HV Bushing", raw_measurement="65"),
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


def test_cbm_defect_planner(tmp_path: Path):
    from unittest.mock import MagicMock
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner
    from src.quick_report.defects import CbmDefectRecord

    tmpl = tmp_path / "swg_overview.docx"
    panel_tmpl = tmp_path / "swg_panel.docx"
    tmpl.touch()
    panel_tmpl.touch()

    env = MagicMock()
    templates = {"swg_overview": tmpl, "swg_panel": panel_tmpl}
    env.get_template.side_effect = lambda k: templates.get(k)

    planner = CbmDefectPlanner()
    defects = [
        CbmDefectRecord(equipment="RMU SF6", technology="IR"),
    ]
    plans = planner.plan(defects, env)

    assert len(plans) == 1
    assert plans[0].spec.id == "swg"
    assert plans[0].overview_template == tmpl
    assert len(plans[0].groups) == 1
    assert plans[0].groups[0].item_key == "RMU SF6"
    assert plans[0].groups[0].overview.technology == "IR"
    assert len(plans[0].groups[0].detail_groups) == 1
    assert plans[0].groups[0].detail_groups[0].role_id == "panel_area"
    assert plans[0].groups[0].detail_groups[0].defects == (defects[0],)


def test_cbm_defect_planner_missing_overview_template_raises_error(tmp_path: Path):
    """Verify missing overview template raises FileNotFoundError."""
    from unittest.mock import MagicMock
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner
    from src.quick_report.defects import CbmDefectRecord

    panel_tmpl = tmp_path / "swg_panel.docx"
    panel_tmpl.touch()

    env = MagicMock()
    env.get_template.side_effect = lambda k: panel_tmpl if k == "swg_panel" else None

    planner = CbmDefectPlanner()
    defects = [CbmDefectRecord(equipment="RMU SF6", technology="IR")]

    with pytest.raises(FileNotFoundError, match="Missing CBM template 'swg_overview' for family 'swg'"):
        planner.plan(defects, env)


def test_cbm_defect_planner_missing_detail_template_raises_error(tmp_path: Path):
    """Verify missing detail role template raises FileNotFoundError."""
    from unittest.mock import MagicMock
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner
    from src.quick_report.defects import CbmDefectRecord

    overview_tmpl = tmp_path / "swg_overview.docx"
    overview_tmpl.touch()

    env = MagicMock()
    env.get_template.side_effect = lambda k: overview_tmpl if k == "swg_overview" else None

    planner = CbmDefectPlanner()
    defects = [CbmDefectRecord(equipment="RMU SF6", technology="IR")]

    with pytest.raises(FileNotFoundError, match="Missing CBM template 'swg_panel' for family 'swg'"):
        planner.plan(defects, env)


def test_cbm_defect_planner_tx_defects_split_hv_lv_roles(tmp_path: Path):
    """Verify TX defects are correctly split into HV and LV detail roles in detail_groups."""
    from unittest.mock import MagicMock
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner
    from src.quick_report.defects import CbmDefectRecord

    overview_tmpl = tmp_path / "tx_overview.docx"
    hv_tmpl = tmp_path / "tx_hv_sides.docx"
    lv_tmpl = tmp_path / "tx_lv_sides.docx"
    overview_tmpl.touch()
    hv_tmpl.touch()
    lv_tmpl.touch()

    env = MagicMock()
    templates = {
        "tx_overview": overview_tmpl,
        "tx_hv_sides": hv_tmpl,
        "tx_lv_sides": lv_tmpl,
    }
    env.get_template.side_effect = lambda k: templates.get(k)

    planner = CbmDefectPlanner()
    d_hv = CbmDefectRecord(equipment="CABLE LTX/DTX", technology="IR")
    d_lv = CbmDefectRecord(equipment="LTX/DTX", technology="IR")

    plans = planner.plan([d_hv, d_lv], env)

    assert len(plans) == 1
    tx_plan = plans[0]
    assert tx_plan.spec.id == "tx"
    assert len(tx_plan.groups) == 2

    # Group 1: CABLE LTX/DTX
    g_hv = [g for g in tx_plan.groups if g.item_key == "CABLE LTX/DTX"][0]
    hv_role = [dg for dg in g_hv.detail_groups if dg.role_id == "tx_hv_side"][0]
    lv_role_in_hv_grp = [dg for dg in g_hv.detail_groups if dg.role_id == "tx_lv_side"][0]
    assert hv_role.defects == (d_hv,)
    assert lv_role_in_hv_grp.defects == ()

    # Group 2: LTX/DTX
    g_lv = [g for g in tx_plan.groups if g.item_key == "LTX/DTX"][0]
    hv_role_in_lv_grp = [dg for dg in g_lv.detail_groups if dg.role_id == "tx_hv_side"][0]
    lv_role = [dg for dg in g_lv.detail_groups if dg.role_id == "tx_lv_side"][0]
    assert hv_role_in_lv_grp.defects == ()
    assert lv_role.defects == (d_lv,)


def test_cbm_defect_planner_no_defects_returns_empty_tuple():
    """Verify empty cbm_defects returns empty tuple."""
    from unittest.mock import MagicMock
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner

    env = MagicMock()
    planner = CbmDefectPlanner()
    plans = planner.plan([], env)
    assert plans == ()


def test_generate_cbm_defect_pages_typed_plan_processing(tmp_path: Path):
    """Verify renderer receives and processes a typed CbmDefectFamilyPlan."""
    from unittest.mock import patch
    from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
    from src.quick_report.defects import CbmDefectRecord
    from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]

    overview_t = tmp_path / "swg_overview.docx"
    panel_t = tmp_path / "swg_panel.docx"
    overview_t.touch()
    panel_t.touch()

    defect = CbmDefectRecord(equipment="RMU SF6", technology="IR")
    group = CbmDefectGroup(
        item_key="RMU SF6",
        item_suffix="",
        defects=(defect,),
        overview=defect,
        detail_groups=(
            CbmDefectDetailGroup(role_id="panel_area", defects=(defect,)),
        ),
    )

    family_plan = CbmDefectFamilyPlan(
        spec=spec,
        overview_template=overview_t,
        detail_templates=(("panel_area", panel_t),),
        groups=(group,),
    )

    with patch("src.quick_report.cbm_defect_pages._render_docx_template") as mock_render:
        paths = generate_cbm_defect_pages(
            family_plan, tmp_path, 101, {"substation": {"name_erms": "SUB A"}}
        )

    assert len(paths) == 2
    assert mock_render.call_count == 2
    assert "101_3 SWG OVERVIEW.docx" in paths[0].name
    assert "101_3 SWG RMU SF6.docx" in paths[1].name


def test_cbm_defect_page_builder_single_group(tmp_path: Path):
    """Verify CbmDefectPageBuilder builds overview and detail page plans for a single group in memory."""
    from src.quick_report.cbm_defect_pages import CbmDefectPageBuilder
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
    from src.quick_report.defects import CbmDefectRecord
    from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]

    overview_t = tmp_path / "swg_overview.docx"
    panel_t = tmp_path / "swg_panel.docx"
    overview_t.touch()
    panel_t.touch()

    defect = CbmDefectRecord(
        equipment="RMU SF6",
        technology="IR",
        brand="ABB",
        model="SafePlus",
        rating="11kV",
        defect_area="Cable Compartment",
        additional_remarks="Hotspot",
        ir_reading="55.0",
    )
    group = CbmDefectGroup(
        item_key="RMU SF6",
        item_suffix="PANEL 1",
        defects=(defect,),
        overview=defect,
        detail_groups=(
            CbmDefectDetailGroup(role_id="panel_area", defects=(defect,)),
        ),
    )
    family_plan = CbmDefectFamilyPlan(
        spec=spec,
        overview_template=overview_t,
        detail_templates=(("panel_area", panel_t),),
        groups=(group,),
    )

    pe_info = {"substation": {"name_erms": "PE TEST"}}
    builder = CbmDefectPageBuilder()
    page_plans = builder.build(
        family_plan=family_plan,
        pe_info=pe_info,
        substation_number=1,
    )

    assert len(page_plans) == 2

    # Overview Page Plan
    overview_plan = page_plans[0]
    assert overview_plan.template_path == overview_t
    assert overview_plan.output_filename == "001_3 SWG OVERVIEW.docx"
    assert overview_plan.context["substation"] == {"name_erms": "PE TEST"}
    assert overview_plan.context["swg"]["area"] == "OVERVIEW"
    assert overview_plan.context["swg"]["type"] == "RMU SF6"
    assert overview_plan.context["panel"]["name"] == "PANEL 1"

    # Detail Page Plan
    detail_plan = page_plans[1]
    assert detail_plan.template_path == panel_t
    assert detail_plan.output_filename == "001_3 SWG RMU SF6.docx"
    assert detail_plan.context["swg"]["area"] == "Cable Compartment/ Hotspot"
    assert detail_plan.context["panel"]["ir"]["reading"] == "55.0"


def test_cbm_defect_page_builder_multi_group_and_part_suffixes(tmp_path: Path):
    """Verify CbmDefectPageBuilder formats group and part suffixes correctly for multi-group and multi-defect plans."""
    from src.quick_report.cbm_defect_pages import CbmDefectPageBuilder
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
    from src.quick_report.defects import CbmDefectRecord
    from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]

    overview_t = tmp_path / "swg_overview.docx"
    panel_t = tmp_path / "swg_panel.docx"
    overview_t.touch()
    panel_t.touch()

    d1 = CbmDefectRecord(equipment="RMU SF6", technology="IR", defect_area="Area 1")
    d2 = CbmDefectRecord(equipment="RMU SF6", technology="US", defect_area="Area 2")
    d3 = CbmDefectRecord(equipment="RMU SF6", technology="TEV", defect_area="Area 3")

    group1 = CbmDefectGroup(
        item_key="RMU SF6",
        item_suffix="",
        defects=(d1, d2),
        overview=d1,
        detail_groups=(
            CbmDefectDetailGroup(role_id="panel_area", defects=(d1, d2)),
        ),
    )
    group2 = CbmDefectGroup(
        item_key="RMU SF6",
        item_suffix="",
        defects=(d3,),
        overview=d3,
        detail_groups=(
            CbmDefectDetailGroup(role_id="panel_area", defects=(d3,)),
        ),
    )

    family_plan = CbmDefectFamilyPlan(
        spec=spec,
        overview_template=overview_t,
        detail_templates=(("panel_area", panel_t),),
        groups=(group1, group2),
    )

    builder = CbmDefectPageBuilder()
    page_plans = builder.build(
        family_plan=family_plan,
        pe_info={"substation": {"name_erms": "PE TEST"}},
        substation_number=5,
    )

    # Page count check: 2 overview pages + 3 detail pages = 5
    assert len(page_plans) == 5

    filenames = [p.output_filename for p in page_plans]
    expected_filenames = [
        "005_3 SWG OVERVIEW_grp1.docx",
        "005_3 SWG RMU SF6_grp1_part1.docx",
        "005_3 SWG RMU SF6_grp1_part2.docx",
        "005_3 SWG OVERVIEW_grp2.docx",
        "005_3 SWG RMU SF6_grp2.docx",
    ]
    assert filenames == expected_filenames

    # Check ordering: Overview grp1 -> Detail grp1 part1 -> Detail grp1 part2 -> Overview grp2 -> Detail grp2
    assert page_plans[0].template_path == overview_t
    assert page_plans[1].template_path == panel_t
    assert page_plans[2].template_path == panel_t
    assert page_plans[3].template_path == overview_t
    assert page_plans[4].template_path == panel_t


def test_cbm_defect_page_builder_empty_or_missing_templates(tmp_path: Path):
    """Verify CbmDefectPageBuilder returns empty list when plan has no groups or missing overview template."""
    from src.quick_report.cbm_defect_pages import CbmDefectPageBuilder
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
    from src.quick_report.models import CbmDefectFamilyPlan

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]
    missing_template = tmp_path / "nonexistent.docx"

    family_plan = CbmDefectFamilyPlan(
        spec=spec,
        overview_template=missing_template,
        detail_templates=(),
        groups=(),
    )

    builder = CbmDefectPageBuilder()
    plans = builder.build(
        family_plan=family_plan,
        pe_info={},
        substation_number=1,
    )
    assert plans == []


