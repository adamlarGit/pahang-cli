"""Shared quick-report utility functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from src.project.storage import sanitize_filename

def normalize_functional_location_input(value: object) -> str:
    """Normalize a user-entered functional-location string or cell value."""
    if value is None:
        return ""
    normalized = str(value).strip()
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    if normalized.upper().startswith("F/L "):
        normalized = normalized[4:].strip()
    return normalized


def sort_quick_report_detail_jobs(jobs: list[dict]) -> list[dict]:
    """Sort quick-report detail jobs in source-Excel order."""
    return sorted(
        jobs,
        key=lambda job: (
            int(job.get("source_order", 0) or 0),
            int(job.get("family_order", 0) or 0),
            str(job.get("item_key", "")),
        ),
    )

def _find_dg_photo(raw_data_dir: Path, stem: str) -> str:
    """Find DG photo by stem matching. TODO: Implement stem-based discovery."""
    return ""  # Fallback: empty string per ticket #028

def _find_ir_photo(raw_data_dir: Path, stem: str) -> str:
    """Find IR photo by stem matching. TODO: Implement for future map."""
    return ""

def _find_us_photo(raw_data_dir: Path, stem: str) -> str:
    """Find US photo by stem matching. TODO: Implement for future map."""
    return ""

def _find_tev_photo(raw_data_dir: Path, stem: str) -> str:
    """Find TEV photo by stem matching. TODO: Implement for future map."""
    return ""

def format_table_cell(
    cell,
    text: str,
    font_size_pt: int = 10,
    font_name: str = "Tahoma",
    bold: bool = False,
    fill: str | None = None,
) -> None:
    """Format table cell text, vertical alignment, centering, spacing, and font attributes."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from docx.shared import Pt

    cell.text = text

    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith("vAlign"):
            tcPr.remove(child)
    tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))

    if fill:
        for child in list(tcPr):
            if child.tag.endswith("shd"):
                tcPr.remove(child)
        tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill}"/>'))

    for p in cell.paragraphs:
        pPr = p._p.get_or_add_pPr()
        for child in list(pPr):
            if child.tag.endswith("jc"):
                pPr.remove(child)
        pPr.append(parse_xml(f'<w:jc {nsdecls("w")} w:val="center"/>'))

        for child in list(pPr):
            if child.tag.endswith("spacing"):
                pPr.remove(child)
        pPr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'))

        runs = p.runs
        if not runs:
            runs = [p.add_run(text)]
        for r in runs:
            r.font.name = font_name
            r.font.size = Pt(font_size_pt)
            r.bold = bold


def clear_cell_text(cell: Any) -> None:
    """Clear paragraph text and run text in a python-docx table cell."""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.text = ""
        paragraph.text = ""


def set_cell_no_borders(cell: Any) -> None:
    """Set all borders on a python-docx table cell to nil (invisible)."""
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


__all__ = [
    "normalize_functional_location_input",
    "sort_quick_report_detail_jobs",
    "sanitize_filename",
    "format_table_cell",
    "clear_cell_text",
    "set_cell_no_borders",
    "_find_dg_photo",
    "_find_ir_photo",
    "_find_us_photo",
    "_find_tev_photo",
]


