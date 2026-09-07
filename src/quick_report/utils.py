"""Shared quick-report utility functions."""

from __future__ import annotations

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


def clear_cell_text(cell: Any) -> None:
    """Clear paragraph text and run text in a python-docx table cell."""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.text = ""
        paragraph.text = ""


def set_cell_no_borders(cell: Any) -> None:
    """Set all borders on a python-docx table cell to nil (invisible)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)

    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tcBorders.find(qn(f"w:{border_name}"))
        if border is None:
            border = OxmlElement(f"w:{border_name}")
            tcBorders.append(border)
        border.set(qn("w:val"), "nil")


def set_cell_shading(cell: Any, hex_color: str) -> None:
    """Set background fill color on a python-docx table cell (e.g. 'EE0000' or '00B050')."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color.lstrip("#").upper())


__all__ = [
    "clear_cell_text",
    "normalize_functional_location_input",
    "sanitize_filename",
    "set_cell_no_borders",
    "set_cell_shading",
]

