"""Shared quick-report utility functions."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from src.project.storage import sanitize_filename

PAHANG_DATE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")

NON_PAHANG_DATE_PATTERNS = (
    # YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$"),
    # DD/MM/YYYY, MM/DD/YYYY, DD.MM.YYYY, MM.DD.YYYY
    re.compile(r"^\d{1,2}[/.]\d{1,2}[/.]\d{2,4}$"),
    # DD-MM-YY (2 digit year)
    re.compile(r"^\d{1,2}-\d{1,2}-\d{2}$"),
    # D-M-YYYY, D-MM-YYYY, DD-M-YYYY (where day or month has 1 digit)
    re.compile(r"^\d{1}-\d{1,2}-\d{4}$"),
    re.compile(r"^\d{2}-\d{1}-\d{4}$"),
    # YYYYMMDD
    re.compile(r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$"),
)


def validate_date_string(value: object) -> None:
    """Validate date string against strict Pahang DD-MM-YYYY format.

    Raises ValueError if a non-Pahang date format is detected or if
    the date is an invalid calendar date.
    """
    s = str(value).strip()
    for pattern in NON_PAHANG_DATE_PATTERNS:
        if pattern.match(s):
            raise ValueError(
                f"Invalid date format: '{value}'. Pahang date format must strictly follow DD-MM-YYYY (e.g. '01-09-2026')."
            )
    if PAHANG_DATE_PATTERN.match(s):
        try:
            datetime.strptime(s, "%d-%m-%Y")
        except ValueError as exc:
            raise ValueError(
                f"Invalid calendar date '{value}': {exc}. Expected valid DD-MM-YYYY date."
            ) from exc


def is_pahang_date_str(value: object) -> bool:
    """Return True if value is a valid DD-MM-YYYY date string."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not PAHANG_DATE_PATTERN.match(s):
        return False
    try:
        datetime.strptime(s, "%d-%m-%Y")
        return True
    except ValueError:
        return False


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
    "NON_PAHANG_DATE_PATTERNS",
    "PAHANG_DATE_PATTERN",
    "clear_cell_text",
    "is_pahang_date_str",
    "normalize_functional_location_input",
    "sanitize_filename",
    "set_cell_no_borders",
    "set_cell_shading",
    "validate_date_string",
]

