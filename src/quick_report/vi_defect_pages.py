from __future__ import annotations

import logging
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate

from src.quick_report.cbm_render import _build_jinja_env, _preserve_blank_render_values

# Constants
DEFECTS_PER_PAGE = 6

EMPTY_DEFECT_CELL_MAP = {
    0: ([0, 1, 2], [0], None),
    1: ([0, 1, 2], [1, 2], None),
    2: ([4, 5, 6], [0], 3),
    3: ([4, 5, 6], [1, 2], 3),
    4: ([8, 9, 10], [0], 7),
    5: ([8, 9, 10], [1, 2], 7),
}


def _clear_cell_text(cell) -> None:
    """Clear paragraph text and run text in cell."""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.text = ""
        paragraph.text = ""


def _set_cell_no_borders(cell) -> None:
    """Construct/update <w:tcBorders> XML element on cell tcPr with w:val='nil'."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn('w:tcBorders'))
    if tcBorders is None:
        tcBorders = OxmlElement('w:tcBorders')
        tcPr.append(tcBorders)

    for border_name in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        border = tcBorders.find(qn(f'w:{border_name}'))
        if border is None:
            border = OxmlElement(f'w:{border_name}')
            tcBorders.append(border)
        border.set(qn('w:val'), 'nil')


def _remove_empty_cell_borders(docx_path: Path, active_count: int) -> None:
    """Clear borders and text for unused VI defect card cells safely using python-docx oxml."""
    if active_count >= DEFECTS_PER_PAGE:
        return

    try:
        doc = Document(docx_path)
        if not doc.tables:
            return

        table = doc.tables[0]
        for idx in range(active_count, DEFECTS_PER_PAGE):
            row_indices, col_indices, spacer_row = EMPTY_DEFECT_CELL_MAP[idx]
            for r in row_indices:
                for c in col_indices:
                    if r < len(table.rows) and c < len(table.rows[r].cells):
                        cell = table.cell(r, c)
                        _clear_cell_text(cell)
                        _set_cell_no_borders(cell)
            if spacer_row is not None and spacer_row < len(table.rows):
                for c in col_indices:
                    if c < len(table.rows[spacer_row].cells):
                        cell = table.cell(spacer_row, c)
                        _clear_cell_text(cell)
                        _set_cell_no_borders(cell)

        doc.save(docx_path)
    except Exception as exc:
        logging.warning(f"Failed to remove empty cell borders for {docx_path}: {exc}")


def build_vi_defect_page_context(pe_info: dict, chunk: list[dict]) -> dict:
    """Build context for a single VI defect page."""
    context = pe_info.copy()
    context["defects"] = chunk
    for idx_slot, item in enumerate(chunk, start=1):
        context[f"equipment{idx_slot}"] = item.get("equipment", "")
        context[f"description{idx_slot}"] = item.get("defect_area", "")
        context[f"remark{idx_slot}"] = item.get("remarks", "")
    return context


def generate_vi_defect_pages(defects: list[dict], template_path: str | Path, output_dir: str | Path, substation_number: int, pe_info: dict) -> list[Path]:
    """Generate VI defect pages dynamically with automatic pagination."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    if not defects:
        return []

    chunks = [defects[i:i + DEFECTS_PER_PAGE] for i in range(0, len(defects), DEFECTS_PER_PAGE)]
    output_paths = []

    for part_number, chunk in enumerate(chunks, start=1):
        doc = DocxTemplate(template_p)
        
        padded_chunk = list(chunk)
        while len(padded_chunk) < DEFECTS_PER_PAGE:
            padded_chunk.append({})
            
        context = build_vi_defect_page_context(pe_info, padded_chunk)
        
        doc.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env(), autoescape=True)

        output_path = Path(output_dir) / f"{substation_number:03d}_6 VI DEFECT part{part_number}.docx"
        doc.save(output_path)
        
        _remove_empty_cell_borders(output_path, len(chunk))
        output_paths.append(output_path)

    return output_paths

# Alias for backwards compatibility
generate_vi_defect_page = generate_vi_defect_pages
