"""VI quick-report rendering engine and context builders."""

from __future__ import annotations

import gc
from pathlib import Path

from docxtpl import DocxTemplate

from src.quick_report.cbm_render import _build_jinja_env, _preserve_blank_render_values

# Constants
DEFECTS_PER_PAGE = 6


def _remove_empty_cell_borders(docx_path: Path, active_count: int) -> None:
    """Clear borders for unused VI defect card cells to clean up the page."""
    import zipfile
    import xml.etree.ElementTree as ET

    if active_count >= DEFECTS_PER_PAGE:
        return

    temp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin:
        with zipfile.ZipFile(temp_path, "w") as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    xml_content = zin.read(item.filename)
                    root = ET.fromstring(xml_content)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    
                    tables = root.findall(".//w:tbl", ns)
                    for i, table in enumerate(tables):
                        if i >= active_count:
                            for tc in table.findall(".//w:tc", ns):
                                tcPr = tc.find("w:tcPr", ns)
                                if tcPr is not None:
                                    tcBorders = tcPr.find("w:tcBorders", ns)
                                    if tcBorders is not None:
                                        for border in tcBorders:
                                            border.set(f"{{{ns['w']}}}val", "nil")

                    zout.writestr(item, ET.tostring(root))
                else:
                    zout.writestr(item, zin.read(item.filename))
    
    temp_path.replace(docx_path)


def generate_vi_summary(pe_info: dict, defects: list[dict], template_path: str, output_dir: str, pe_number: int) -> Path:
    """Generate VI defect summary page."""
    context = pe_info.copy()
    context["defects"] = defects
    
    doc = DocxTemplate(template_path)
    doc.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env(), autoescape=True)
    
    out_path = Path(output_dir) / f"{pe_number:03d}_2 VI SUMMARY.docx"
    doc.save(out_path)
    del doc
    gc.collect()
    return out_path


def generate_vi_defect_page(defects: list[dict], template_path: str, output_dir: str, pe_number: int, pe_info: dict) -> list[Path]:
    """Generate VI defect pages dynamically with automatic pagination."""
    if not defects:
        return []

    chunks = [defects[i:i + DEFECTS_PER_PAGE] for i in range(0, len(defects), DEFECTS_PER_PAGE)]
    output_paths = []

    for part_number, chunk in enumerate(chunks, start=1):
        doc = DocxTemplate(template_path)
        
        padded_chunk = list(chunk)
        while len(padded_chunk) < DEFECTS_PER_PAGE:
            padded_chunk.append({})
            
        context = pe_info.copy()
        context["defects"] = padded_chunk
        
        doc.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env(), autoescape=True)

        output_path = Path(output_dir) / f"{pe_number:03d}_6 VI DEFECT PAGE part{part_number}.docx"
        doc.save(output_path)
        del doc
        gc.collect()
        
        _remove_empty_cell_borders(output_path, len(chunk))
        output_paths.append(output_path)

    return output_paths
