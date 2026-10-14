"""Shared cell parsing utilities and normalizers for testsheet workbooks."""

from __future__ import annotations

from datetime import date, datetime
import math
import re


def normalize_fl_erms(val: object) -> str:
    """Strip whitespace, handle .0 float suffix from FL ERMS values."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace("\t", "").strip()


def clean_val(val: object) -> str | None:
    """Strip tabs/spaces, return None if empty/dash/NONE."""
    if val is None:
        return None
    s = str(val).replace("\t", "").strip()
    if not s or s in ("-", "None", "NONE", "N/A", "#REF!", "nan"):
        return None
    return s


def is_marked(val: object) -> bool:
    """Checkbox detection — True if cell has a non-negative marker."""
    if val is None:
        return False
    s = str(val).strip().upper()
    return s not in ("", "NONE", "NO", "N/A", "0", "FALSE", "-", "NAN")


def normalize_building_type(val: object) -> str | None:
    """Normalize building type strings to ATTACH, INDOOR, or OUTDOOR."""
    if val is None:
        return None
    s = str(val).strip().upper()
    if not s or s in ("-", "NONE", "N/A"):
        return None
    if "ATTACH" in s:
        return "ATTACH"
    if "INDOOR" in s or "DALAMAN" in s:
        return "INDOOR"
    if "OUTDOOR" in s or "LUARAN" in s:
        return "OUTDOOR"
    return s


def to_excel_date(val: object) -> datetime | None:
    """Parse date from cell value — handles datetime, date, and string formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    s = str(val).strip()
    if not s or s in ("-", "None", "N/A"):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_photo_numbers(val: object) -> tuple[int, ...]:
    """Parse inline photo numbers from a cell value into a tuple of integers."""
    if val is None or isinstance(val, bool):
        return ()
    if isinstance(val, int):
        if 100000 <= val <= 999999:
            first, second = divmod(val, 1000)
            if first > 0 and second > 0:
                return (first, second)
        return (val,)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return ()
        ival = int(val)
        if 100000 <= ival <= 999999:
            first, second = divmod(ival, 1000)
            if first > 0 and second > 0:
                return (first, second)
        return (ival,)
    s = str(val).strip()
    if not s or s.upper() in ("-", "NONE", "N/A", "#REF!", "NAN"):
        return ()
    s = re.sub(r"\.\d+\b", "", s)
    matches = re.findall(r"\d+", s)
    res: list[int] = []
    for m in matches:
        num = int(m)
        if 100000 <= num <= 999999:
            first, second = divmod(num, 1000)
            if first > 0 and second > 0:
                res.extend([first, second])
                continue
        res.append(num)
    return tuple(res)


def parse_secondary_photo(val: object) -> int | None:
    """Parse secondary panel IR photo number from Col P (row r+1).

    Matches 'S.PANEL IR <num>', 'S PANEL IR <num>', 'IR <num>', etc.
    Falls back to bare integer parsing.
    """
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if val > 0 else None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        ival = int(val)
        return ival if ival > 0 else None

    s = str(val).strip()
    if not s or s.upper() in ("-", "NONE", "N/A", "#REF!", "NAN"):
        return None

    m = re.search(r"(?:S\.?\s*PANEL\s*IR|IR)[\s\:\-]*(\d+)", s, re.IGNORECASE)
    if m:
        return int(m.group(1))

    bare_m = re.search(r"^\s*(\d+)(?:\.0+)?\s*$", s)
    if bare_m:
        return int(bare_m.group(1))

    return None
