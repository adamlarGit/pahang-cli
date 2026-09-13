"""Unit test suite for Core Scan Page Renderer & Dynamic Shading Engine (Ticket #30 / T4.2a).

Verifies:
- FullReportScanPageRendererCore wrapping docxtpl.DocxTemplate.
- Dynamic shading of technology severity cells (IR, US, TEV) Green 00B050 (healthy) or Red EE0000 (defective), clearing text.
- Dynamic shading of Analysis & Recommendation banner Green 00B050 ('No Anomaly.') or Red EE0000 (defect forwarding).
- XML cell shading attributes (w:fill="00B050" and w:fill="EE0000") on mock and generated documents.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
import zipfile

import docx
from docx.oxml.ns import qn
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from PIL import Image
import pytest

from src.full_report.scan_render import (
    BANNER_DEFECT_FORWARDING,
    BANNER_HEALTHY_ANALYSIS,
    BANNER_HEALTHY_RECOMMENDATION,
    COLOR_DEFECT,
    COLOR_HEALTHY,
    COLOR_NORMAL,
    FullReportScanPageRendererCore,
    SEVERITY_MARKER_IR,
    SEVERITY_MARKER_TEV,
    SEVERITY_MARKER_US,
    apply_banner_shading,
    apply_technology_severity_shading,
    detect_cell_technology,
    is_defect_forwarding_text,
    is_healthy_banner_text,
    render_scan_page,
)

TEMPLATES_DIR = Path("templates/FULL REPORT/NORMAL IR US TEV")


def _get_cell_fill(cell: Any) -> str | None:
    """Read w:fill attribute from a table cell's tcPr/w:shd XML element."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.attrib.get(qn("w:fill"))


def _read_document_xml(docx_path: Path) -> str:
    """Read word/document.xml content directly from .docx zip archive."""
    with zipfile.ZipFile(docx_path, "r") as z:
        return z.read("word/document.xml").decode("utf-8")


@pytest.fixture(scope="module")
def dummy_image_file() -> Path:
    """Create a temporary test image file for image binding."""
    tmp = Path(tempfile.gettempdir()) / "test_scan_render_dummy.png"
    img = Image.new("RGB", (60, 45), color=(0, 176, 80))
    img.save(tmp)
    return tmp


# ==============================================================================
# 1. Technology Detection & Text Matching Unit Tests
# ==============================================================================

def test_detect_cell_technology_markers():
    """Detect technology severity cells from Jinja sentinels and placeholders."""
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=6)

    t.cell(0, 0).text = SEVERITY_MARKER_IR
    t.cell(0, 1).text = "{{ ir.severity }}"
    t.cell(0, 2).text = SEVERITY_MARKER_US
    t.cell(0, 3).text = "{{ us.severity }}"
    t.cell(0, 4).text = SEVERITY_MARKER_TEV
    t.cell(0, 5).text = "{{ tev.severity }}"

    assert detect_cell_technology(t.cell(0, 0)) == "IR"
    assert detect_cell_technology(t.cell(0, 1)) == "IR"
    assert detect_cell_technology(t.cell(0, 2)) == "US"
    assert detect_cell_technology(t.cell(0, 3)) == "US"
    assert detect_cell_technology(t.cell(0, 4)) == "TEV"
    assert detect_cell_technology(t.cell(0, 5)) == "TEV"


def test_detect_cell_technology_tokens_and_none():
    """Detect technology from standard token names and return None for normal cells."""
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=5)

    t.cell(0, 0).text = "IR_SEVERITY"
    t.cell(0, 1).text = "U/S"
    t.cell(0, 2).text = "TEV"
    t.cell(0, 3).text = "PE SUBSTATION"
    t.cell(0, 4).text = ""

    assert detect_cell_technology(t.cell(0, 0)) == "IR"
    assert detect_cell_technology(t.cell(0, 1)) == "US"
    assert detect_cell_technology(t.cell(0, 2)) == "TEV"
    assert detect_cell_technology(t.cell(0, 3)) is None
    assert detect_cell_technology(t.cell(0, 4)) is None


def test_banner_text_helpers():
    """Verify healthy and defect forwarding text detection helpers."""
    assert is_healthy_banner_text("Analysis: No Anomaly.")
    assert is_healthy_banner_text("No Anomaly.")
    assert is_healthy_banner_text("TIADA ANOMALI")
    assert not is_healthy_banner_text("Analysis: Please refer to the following page for details defect.")

    assert is_defect_forwarding_text("Analysis: Please refer to the following page for details defect.")
    assert is_defect_forwarding_text("Recommendation: Please refer to the following page for details defect.")
    assert is_defect_forwarding_text("Please refer to the following page for detail defect.")
    assert not is_defect_forwarding_text("No Anomaly.")


# ==============================================================================
# 2. DOM Post-Processor Unit Tests (Mock Documents & Tables)
# ==============================================================================

def test_apply_technology_severity_shading_single_cells():
    """Verify shading and text clearing on single cells for IR, US, and TEV."""
    doc = docx.Document()
    t = doc.add_table(rows=2, cols=3)

    cell_ir = t.cell(0, 0)
    cell_ir.text = "{{ ir.severity }}"
    cell_us = t.cell(0, 1)
    cell_us.text = "{{ us.severity }}"
    cell_tev = t.cell(0, 2)
    cell_tev.text = "{{ tev.severity }}"

    # Apply healthy shading
    apply_technology_severity_shading(cell_ir, is_defective=False)
    apply_technology_severity_shading(cell_us, is_defective=False)
    apply_technology_severity_shading(cell_tev, is_defective=False)

    assert cell_ir.text == ""
    assert _get_cell_fill(cell_ir) == COLOR_HEALTHY
    assert "00B050" in cell_ir._tc.xml

    assert cell_us.text == ""
    assert _get_cell_fill(cell_us) == COLOR_HEALTHY
    assert "00B050" in cell_us._tc.xml

    assert cell_tev.text == ""
    assert _get_cell_fill(cell_tev) == COLOR_HEALTHY
    assert "00B050" in cell_tev._tc.xml

    # Apply defective shading
    cell_ir_def = t.cell(1, 0)
    cell_ir_def.text = SEVERITY_MARKER_IR
    cell_us_def = t.cell(1, 1)
    cell_us_def.text = SEVERITY_MARKER_US
    cell_tev_def = t.cell(1, 2)
    cell_tev_def.text = SEVERITY_MARKER_TEV

    apply_technology_severity_shading(cell_ir_def, is_defective=True)
    apply_technology_severity_shading(cell_us_def, is_defective=True)
    apply_technology_severity_shading(cell_tev_def, is_defective=True)

    assert cell_ir_def.text == ""
    assert _get_cell_fill(cell_ir_def) == COLOR_DEFECT
    assert "EE0000" in cell_ir_def._tc.xml

    assert cell_us_def.text == ""
    assert _get_cell_fill(cell_us_def) == COLOR_DEFECT
    assert "EE0000" in cell_us_def._tc.xml

    assert cell_tev_def.text == ""
    assert _get_cell_fill(cell_tev_def) == COLOR_DEFECT
    assert "EE0000" in cell_tev_def._tc.xml


def test_apply_technology_severity_shading_mock_table_healthy():
    """Verify table-level shading when all technologies are healthy."""
    doc = docx.Document()
    t = doc.add_table(rows=2, cols=3)
    t.cell(0, 0).text = "{{ ir.severity }}"
    t.cell(0, 1).text = "{{ us.severity }}"
    t.cell(0, 2).text = "{{ tev.severity }}"

    apply_technology_severity_shading(t, defective_technologies=None)

    for c_idx in range(3):
        cell = t.cell(0, c_idx)
        assert cell.text == ""
        assert _get_cell_fill(cell) == "00B050"
        assert 'w:fill="00B050"' in cell._tc.xml


def test_apply_technology_severity_shading_mock_table_selective_defects():
    """Verify table-level selective shading when specific technologies are defective."""
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=3)
    t.cell(0, 0).text = SEVERITY_MARKER_IR
    t.cell(0, 1).text = SEVERITY_MARKER_US
    t.cell(0, 2).text = SEVERITY_MARKER_TEV

    # IR and TEV defective, US healthy
    apply_technology_severity_shading(t, defective_technologies={"IR", "TEV"})

    assert t.cell(0, 0).text == ""
    assert _get_cell_fill(t.cell(0, 0)) == "EE0000"

    assert t.cell(0, 1).text == ""
    assert _get_cell_fill(t.cell(0, 1)) == "00B050"

    assert t.cell(0, 2).text == ""
    assert _get_cell_fill(t.cell(0, 2)) == "EE0000"


def test_apply_technology_severity_shading_string_syntax():
    """Verify defective_technologies supports string format 'IR, US' and 'IR+TEV'."""
    doc = docx.Document()
    t = doc.add_table(rows=1, cols=3)
    t.cell(0, 0).text = "{{ ir.severity }}"
    t.cell(0, 1).text = "{{ us.severity }}"
    t.cell(0, 2).text = "{{ tev.severity }}"

    apply_technology_severity_shading(t, defective_technologies="US+TEV")

    assert _get_cell_fill(t.cell(0, 0)) == "00B050"
    assert _get_cell_fill(t.cell(0, 1)) == "EE0000"
    assert _get_cell_fill(t.cell(0, 2)) == "EE0000"


def test_apply_banner_shading_single_cells():
    """Verify banner shading on individual cells for healthy and defective prose."""
    doc = docx.Document()
    t = doc.add_table(rows=2, cols=2)

    healthy_cell = t.cell(0, 0)
    healthy_cell.text = "Analysis: No Anomaly."
    defective_cell = t.cell(0, 1)
    defective_cell.text = "Analysis: Please refer to the following page for details defect."

    apply_banner_shading(healthy_cell)
    apply_banner_shading(defective_cell)

    assert _get_cell_fill(healthy_cell) == "00B050"
    assert 'w:fill="00B050"' in healthy_cell._tc.xml

    assert _get_cell_fill(defective_cell) == "EE0000"
    assert 'w:fill="EE0000"' in defective_cell._tc.xml


def test_apply_banner_shading_mock_table_healthy_and_defective():
    """Verify table-level banner shading matching standard scan page banner rows."""
    # Healthy Table
    doc_healthy = docx.Document()
    t_h = doc_healthy.add_table(rows=3, cols=1)
    t_h.cell(0, 0).text = "Analysis & Recommendations:"
    t_h.cell(1, 0).text = "Analysis:  No Anomaly."
    t_h.cell(2, 0).text = "Recommendation:  -"

    apply_banner_shading(t_h)

    assert _get_cell_fill(t_h.cell(0, 0)) is None  # Heading unaffected
    assert _get_cell_fill(t_h.cell(1, 0)) == "00B050"  # Analysis Green
    assert 'w:fill="00B050"' in t_h.cell(1, 0)._tc.xml

    # Defective Table
    doc_def = docx.Document()
    t_d = doc_def.add_table(rows=3, cols=1)
    t_d.cell(0, 0).text = "Analysis & Recommendations:"
    t_d.cell(1, 0).text = "Analysis:  Please refer to the following page for details defect."
    t_d.cell(2, 0).text = "Recommendation:  Please refer to the following page for details defect."

    apply_banner_shading(t_d)

    assert _get_cell_fill(t_d.cell(0, 0)) is None  # Heading unaffected
    assert _get_cell_fill(t_d.cell(1, 0)) == "EE0000"  # Analysis Red
    assert _get_cell_fill(t_d.cell(2, 0)) == "EE0000"  # Recommendation Red
    assert 'w:fill="EE0000"' in t_d.cell(1, 0)._tc.xml
    assert 'w:fill="EE0000"' in t_d.cell(2, 0)._tc.xml


def test_apply_banner_shading_explicit_is_defective_flag():
    """Verify apply_banner_shading with explicit is_defective flag."""
    doc = docx.Document()
    t = doc.add_table(rows=2, cols=1)
    t.cell(0, 0).text = "Analysis: Custom defect analysis text."
    t.cell(1, 0).text = "Recommendation: Custom action."

    apply_banner_shading(t, is_defective=True)
    assert _get_cell_fill(t.cell(0, 0)) == "EE0000"
    assert _get_cell_fill(t.cell(1, 0)) == "EE0000"


# ==============================================================================
# 3. Core Scan Page Renderer Tests (FullReportScanPageRendererCore)
# ==============================================================================

def _build_test_context(dt: DocxTemplate, image_file: Path) -> dict[str, Any]:
    """Build mock context satisfying scanning template variables."""
    img = InlineImage(dt, str(image_file), width=Mm(40))
    return {
        "substation": {
            "name_erms": "PE TEST 11KV",
            "date": "10-08-2026",
            "time": "11:00 AM",
            "ambient": "31.0 °C",
            "humidity": "65%",
        },
        "swg": {
            "type": "RMU SF6",
            "manufacturer": "TAMCO",
            "model": "AIR",
            "rating": "12kV",
            "area": "OVERVIEW",
            "serialnumber": "SN-SWG-001",
        },
        "panel": {
            "name": "FEEDER 1",
            "linknumber": "1",
            "area": "CABLE COMPARTMENT",
            "serialnumber": "SN-PANEL-01",
            "heateramp": "0.5A",
            "breakerstatus": "CLOSE",
            "busbarposition": "TOP",
            "cabletype": "3C 300mm2 XLPE",
            "loadamp": "200A",
        },
        "tx": {
            "manufacturer": "SGB",
            "model": "HERMETICALLY SEAL",
            "rating": "1000kVA",
            "number": "TX1",
            "location": "HV SIDE",
            "area": "HV BUSHING",
            "serialnumber": "TX-100",
            "cabletype": "3C 300mm2 XLPE",
        },
        "fp": {
            "labelsource": "LVDB TX1",
            "manufacturer": "ALGEBRA",
            "model": "J-SLOTTED",
            "rating": "1600A",
            "area": "OVERVIEW",
            "serialnumber": "FP-01",
            "cabletype": "4C 300mm2 PVC",
            "feederno": "F01",
            "loadamp": "120A",
        },
        "battery": {
            "manufacturer": "SUNPOWER",
            "model": "SP-100",
            "number": "1",
            "serialnumber": "BATT-01",
            "rating": "240V/50Hz",
            "area": "OVERVIEW",
        },
        "batt": {
            "manufacturer": "SUNPOWER",
            "model": "SP-100",
            "number": "1",
            "serialnumber": "BATT-01",
            "rating": "240V/50Hz",
            "area": "OVERVIEW",
        },
        "ir": {
            "image": img,
            "sp1": "32.0 °C",
            "sp2": "31.5 °C",
            "ar1": "31.8 °C",
            "reading": "32.0 °C",
            "delta_t": "0.5 °C",
        },
        "us": {
            "reading": "10",
            "char": "NORMAL",
            "prpd": img,
        },
        "tev": {
            "bg": "3",
            "reading": "5",
            "ppc": "0.0",
            "prpd": img,
        },
        "visual": {
            "image": img,
        },
    }


def test_core_renderer_swg_panel_healthy(tmp_path: Path, dummy_image_file: Path):
    """Render swg-panel.docx when healthy: IR/US/TEV are 00B050 and banner is 00B050."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "rendered_swg_panel_healthy.docx"

    dt = DocxTemplate(str(template_path))
    ctx = _build_test_context(dt, dummy_image_file)

    renderer = FullReportScanPageRendererCore()
    out = renderer.render(
        template_path,
        output_path,
        ctx,
        defective_technologies=None,
    )

    assert out.is_file()
    xml_str = _read_document_xml(out)

    # Document XML must contain healthy green fill
    assert 'w:fill="00B050"' in xml_str
    # Healthy scan page must NOT contain defect red fill
    assert 'w:fill="EE0000"' not in xml_str

    # Inspect generated python-docx elements
    doc = docx.Document(out)
    table = doc.tables[0]

    # Row 18: IR Severity (Cell 3)
    ir_cell = table.rows[18].cells[3]
    assert ir_cell.text.strip() == ""
    assert _get_cell_fill(ir_cell) == "00B050"

    # Row 30: US Severity (Cell 4) & TEV Severity (Cell 18)
    us_cell = table.rows[30].cells[4]
    assert us_cell.text.strip() == ""
    assert _get_cell_fill(us_cell) == "00B050"

    tev_cell = table.rows[30].cells[18]
    assert tev_cell.text.strip() == ""
    assert _get_cell_fill(tev_cell) == "00B050"

    # Banner analysis row
    analysis_cell = table.rows[35].cells[0]
    assert "No Anomaly." in analysis_cell.text
    assert _get_cell_fill(analysis_cell) == "00B050"


def test_core_renderer_swg_panel_ir_defect(tmp_path: Path, dummy_image_file: Path):
    """Render swg-panel.docx with IR defect: IR is EE0000, US/TEV are 00B050, banner is EE0000."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "rendered_swg_panel_ir_defect.docx"

    dt = DocxTemplate(str(template_path))
    ctx = _build_test_context(dt, dummy_image_file)

    renderer = FullReportScanPageRendererCore(template_path)
    out = renderer.render(
        output_path,
        ctx,
        defective_technologies={"IR"},
    )

    assert out.is_file()
    xml_str = _read_document_xml(out)

    assert 'w:fill="EE0000"' in xml_str
    assert 'w:fill="00B050"' in xml_str

    doc = docx.Document(out)
    table = doc.tables[0]

    # Row 18: IR Severity is Red EE0000 with text cleared
    ir_cell = table.rows[18].cells[3]
    assert ir_cell.text.strip() == ""
    assert _get_cell_fill(ir_cell) == "EE0000"

    # Row 30: US & TEV Severity are Green 00B050 with text cleared
    us_cell = table.rows[30].cells[4]
    assert us_cell.text.strip() == ""
    assert _get_cell_fill(us_cell) == "00B050"

    tev_cell = table.rows[30].cells[18]
    assert tev_cell.text.strip() == ""
    assert _get_cell_fill(tev_cell) == "00B050"

    # Banner analysis & recommendation rows are Red EE0000
    analysis_cell = table.rows[35].cells[0]
    assert "Please refer to the following page" in analysis_cell.text
    assert _get_cell_fill(analysis_cell) == "EE0000"

    rec_cell = table.rows[36].cells[0]
    assert "Please refer to the following page" in rec_cell.text
    assert _get_cell_fill(rec_cell) == "EE0000"


def test_core_renderer_swg_panel_tev_defect(tmp_path: Path, dummy_image_file: Path):
    """Render swg-panel.docx with TEV defect: TEV is EE0000, IR/US are 00B050, banner is EE0000."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "rendered_swg_panel_tev_defect.docx"

    dt = DocxTemplate(str(template_path))
    ctx = _build_test_context(dt, dummy_image_file)

    out = FullReportScanPageRendererCore.render_page(
        template_path,
        output_path,
        ctx,
        defective_technologies="TEV",
    )

    assert out.is_file()
    doc = docx.Document(out)
    table = doc.tables[0]

    # IR is healthy Green
    ir_cell = table.rows[18].cells[3]
    assert ir_cell.text.strip() == ""
    assert _get_cell_fill(ir_cell) == "00B050"

    # US is healthy Green
    us_cell = table.rows[30].cells[4]
    assert us_cell.text.strip() == ""
    assert _get_cell_fill(us_cell) == "00B050"

    # TEV is defective Red
    tev_cell = table.rows[30].cells[18]
    assert tev_cell.text.strip() == ""
    assert _get_cell_fill(tev_cell) == "EE0000"

    # Banner is Red
    assert _get_cell_fill(table.rows[35].cells[0]) == "EE0000"


def test_core_renderer_all_templates_smoke(tmp_path: Path, dummy_image_file: Path):
    """Verify FullReportScanPageRendererCore renders all 7 scanning templates cleanly."""
    templates = [
        "swg-overview.docx",
        "swg-panel.docx",
        "tx-overview.docx",
        "tx-hv-sides.docx",
        "tx-lv-sides.docx",
        "fp-overview.docx",
        "battery-overview.docx",
    ]

    for tpl_name in templates:
        tpl_file = TEMPLATES_DIR / tpl_name
        assert tpl_file.is_file()

        out_file = tmp_path / f"rendered_{tpl_name}"
        dt = DocxTemplate(str(tpl_file))
        ctx = _build_test_context(dt, dummy_image_file)

        render_scan_page(tpl_file, out_file, ctx)
        assert out_file.is_file()

        xml = _read_document_xml(out_file)
        assert 'w:fill="00B050"' in xml
        assert "{{" not in xml
        assert "}}" not in xml


def test_core_renderer_error_handling(tmp_path: Path):
    """Verify error handling on non-existent template or invalid paths."""
    renderer = FullReportScanPageRendererCore()
    with pytest.raises(FileNotFoundError):
        renderer.render("non_existent_template.docx", tmp_path / "out.docx", {})

    renderer_with_bad_tpl = FullReportScanPageRendererCore("missing.docx")
    with pytest.raises(FileNotFoundError):
        renderer_with_bad_tpl.render(tmp_path / "out.docx", {})


def test_core_renderer_missing_images_graceful_fallback(tmp_path: Path):
    """Verify missing images in context safely render as '' without crashing."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "missing_images.docx"

    ctx = {
        "substation": {"name_erms": "PE EMPTY IMAGES", "date": "10-08-2026"},
        "swg": {"area": "OVERVIEW"},
        "panel": {"name": "BAY 1", "area": "CABLE COMPARTMENT"},
        "ir": {"image": "non_existent_path.jpg", "reading": "30.0"},
        "visual": {"image": ""},
        "us": {"reading": "10", "prpd": "-"},
        "tev": {"reading": "5", "prpd": None},
    }

    renderer = FullReportScanPageRendererCore()
    out = renderer.render(template_path, output_path, ctx)

    assert out.is_file()
    xml = _read_document_xml(out)
    assert 'w:fill="00B050"' in xml
    assert "{{" not in xml


def test_core_renderer_all_technologies_defective(tmp_path: Path, dummy_image_file: Path):
    """Verify all 3 technology severity cells shaded Red EE0000 when all are defective."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "all_defective.docx"

    dt = DocxTemplate(str(template_path))
    ctx = _build_test_context(dt, dummy_image_file)

    renderer = FullReportScanPageRendererCore()
    out = renderer.render(
        template_path,
        output_path,
        ctx,
        defective_technologies={"IR", "US", "TEV"},
    )

    doc = docx.Document(out)
    t = doc.tables[0]

    assert _get_cell_fill(t.rows[18].cells[3]) == "EE0000"
    assert _get_cell_fill(t.rows[30].cells[4]) == "EE0000"
    assert _get_cell_fill(t.rows[30].cells[18]) == "EE0000"
    assert _get_cell_fill(t.rows[35].cells[0]) == "EE0000"


def test_core_renderer_raw_filepath_images(tmp_path: Path, dummy_image_file: Path):
    """Verify passing string file paths for images works seamlessly without prior InlineImage wrapping."""
    template_path = TEMPLATES_DIR / "swg-panel.docx"
    output_path = tmp_path / "raw_path_images.docx"

    ctx = {
        "substation": {"name_erms": "PE PATH IMAGES", "date": "10-08-2026"},
        "swg": {"area": "OVERVIEW"},
        "panel": {"name": "BAY 1", "area": "CABLE COMPARTMENT"},
        "ir": {"image": str(dummy_image_file), "reading": "30.0"},
        "visual": {"image": dummy_image_file},
        "us": {"reading": "10", "prpd": str(dummy_image_file)},
        "tev": {"reading": "5", "prpd": dummy_image_file},
    }

    out = render_scan_page(template_path, output_path, ctx)
    assert out.is_file()

    doc = docx.Document(out)
    drawings = doc._body._element.xpath(".//w:drawing")
    assert len(drawings) >= 4


def test_apply_shading_document_level():
    """Verify apply_technology_severity_shading and apply_banner_shading accept docx.Document."""
    doc = docx.Document()
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "{{ ir.severity }}"
    t.cell(0, 1).text = "Analysis: No Anomaly."

    apply_technology_severity_shading(doc, defective_technologies=None)
    apply_banner_shading(doc)

    assert _get_cell_fill(t.cell(0, 0)) == "00B050"
    assert t.cell(0, 0).text == ""
    assert _get_cell_fill(t.cell(0, 1)) == "00B050"
