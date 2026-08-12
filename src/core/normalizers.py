"""Domain normalization utilities for Pahang CLI."""

from __future__ import annotations

from datetime import date, datetime, time
import re


MONTH_NAME_MAP = {
    1: "01. JANUARY",
    2: "02. FEBRUARY",
    3: "03. MARCH",
    4: "04. APRIL",
    5: "05. MAY",
    6: "06. JUNE",
    7: "07. JULY",
    8: "08. AUGUST",
    9: "09. SEPTEMBER",
    10: "10. OCTOBER",
    11: "11. NOVEMBER",
    12: "12. DECEMBER",
}

MONTH_STEM_TO_NUM = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}

MONTH_ABBR_MAP = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}


def _parse_date_object(date_input: str | date | datetime | None) -> date | None:
    """Parse date input into a datetime.date instance, returning None if unparseable."""
    if date_input is None:
        return None
    if isinstance(date_input, datetime):
        return date_input.date()
    if isinstance(date_input, date):
        return date_input

    s = str(date_input).strip()
    if not s or s in ("-", "None", "N/A"):
        return None

    # Try ISO format YYYY-MM-DD or YYYY/MM/DD
    match_iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if match_iso:
        try:
            return date(int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3)))
        except ValueError:
            return None

    # Try DD-MM-YYYY or DD/MM/YYYY format
    match_ddmmyyyy = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if match_ddmmyyyy:
        try:
            return date(int(match_ddmmyyyy.group(3)), int(match_ddmmyyyy.group(2)), int(match_ddmmyyyy.group(1)))
        except ValueError:
            return None

    # Try DD MMM YYYY (e.g., "12 AUG 2026", "12-Aug-2026")
    match_named = re.match(r"^(\d{1,2})[\s\-\/]+([A-Za-z]+)[\s\-\/]+(\d{4})$", s)
    if match_named:
        day_str, month_str, year_str = match_named.groups()
        month_upper = month_str.upper()
        if month_upper in MONTH_STEM_TO_NUM:
            try:
                return date(int(year_str), MONTH_STEM_TO_NUM[month_upper], int(day_str))
            except ValueError:
                return None

    return None


def format_date_front_page(date_input: str | date | datetime | None) -> str:
    """Format date input for Quick Report Front Page ('datefrontpage') as 'DD MMM YYYY' with uppercase month.

    Parses hyphenated strings ('12-08-2026'), slashed strings ('12/08/2026'), ISO strings ('2026-08-12'),
    and date/datetime objects. Falls back to '-' for None, empty strings, or unparseable input.

    Args:
        date_input: Date input as a string, date, datetime object, or None.

    Returns:
        Formatted date string in 'DD MMM YYYY' format with uppercase month (e.g. '12 AUG 2026'),
        or '-' if input is None, empty, or unparseable.
    """
    d = _parse_date_object(date_input)
    if d is None:
        return "-"
    return f"{d.day:02d} {MONTH_ABBR_MAP[d.month]} {d.year:04d}"


def format_date_cbm(date_input: str | date | datetime | None) -> str:
    """Format date input for Quick Report CBM Defect Pages ('date') as 'DD/MM/YYYY' with forward slashes.

    Parses hyphenated strings ('12-08-2026'), slashed strings ('12/08/2026'), ISO strings ('2026-08-12'),
    and date/datetime objects. Falls back to '-' for None, empty strings, or unparseable input.

    Args:
        date_input: Date input as a string, date, datetime object, or None.

    Returns:
        Formatted date string in 'DD/MM/YYYY' format with forward slashes (e.g. '12/08/2026'),
        or '-' if input is None, empty, or unparseable.
    """
    d = _parse_date_object(date_input)
    if d is None:
        return "-"
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


def normalize_date_str(date_input: object) -> str:
    """Normalize date inputs (date, datetime, or strings) to DD-MM-YYYY format."""
    if not date_input:
        return ""
    if isinstance(date_input, (datetime, date)):
        return date_input.strftime("%d-%m-%Y")
    s = str(date_input).strip().replace("/", "-")
    match_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if match_iso:
        year, month, day = int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3))
        return f"{day:02d}-{month:02d}-{year:04d}"
    match = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{day:02d}-{month:02d}-{year:04d}"
    return s


def format_month_folder(month_input: object = None, val: object = None) -> str:
    """
    Format any month string, date object, or folder name to canonical Pahang format:
    'XX. MONTH' (e.g., '01. JANUARY', '02. FEBRUARY', '03. MARCH').
    """
    target = month_input if month_input is not None else val
    if target is None:
        return ""
    if isinstance(target, (datetime, date)):
        return MONTH_NAME_MAP.get(target.month, f"{target.month:02d}. UNKNOWN")

    s = str(target).strip()
    if not s or s in ("-", "None", "N/A"):
        return ""

    s_upper = s.upper()

    match_exact = re.match(r"^(\d{2})\.\s+([A-Z]+)$", s_upper)
    if match_exact:
        prefix_num = match_exact.group(1)
        month_word = match_exact.group(2)
        if month_word in MONTH_STEM_TO_NUM:
            target_num = MONTH_STEM_TO_NUM[month_word]
            full_word = MONTH_NAME_MAP[target_num].split(". ")[1]
            return f"{prefix_num}. {full_word}"
        return s_upper

    match_leading = re.match(r"^(\d{1,2})[\.\s_-]+([A-Za-z]+)", s_upper)
    if match_leading:
        idx = int(match_leading.group(1))
        month_str = match_leading.group(2)
        if month_str in MONTH_STEM_TO_NUM:
            target_num = MONTH_STEM_TO_NUM[month_str]
            full_word = MONTH_NAME_MAP[target_num].split(". ")[1]
            return f"{idx:02d}. {full_word}"
        if 1 <= idx <= 12:
            return MONTH_NAME_MAP[idx]

    for stem, m_num in MONTH_STEM_TO_NUM.items():
        if len(stem) >= 3 and stem in s_upper:
            return MONTH_NAME_MAP[m_num]

    match_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", s)
    if match_date:
        m_num = int(match_date.group(2))
        if 1 <= m_num <= 12:
            return MONTH_NAME_MAP[m_num]

    digits = re.findall(r"\d+", s)
    if digits:
        for d in digits:
            num = int(d)
            if 1 <= num <= 12 and len(d) <= 2:
                return MONTH_NAME_MAP[num]

    return s_upper


def format_testsheet_time(val: object) -> str:
    """
    Parse 24-hour time values in various formats and convert to 12-hour hh:mm AM/PM.
    Returns '-' if unparseable or empty.
    """
    if val is None:
        return "-"
    if isinstance(val, time):
        return val.strftime("%I:%M %p")
    
    s = str(val).strip()
    if not s or s == "-":
        return "-"

    s_clean = re.sub(r"[^\d:]", "", s)
    if ":" in s_clean:
        parts = s_clean.split(":")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            hour, minute = int(parts[0]), int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute).strftime("%I:%M %p")
    else:
        if s_clean.isdigit():
            if len(s_clean) == 3:
                s_clean = "0" + s_clean
            if len(s_clean) == 4:
                hour, minute = int(s_clean[:2]), int(s_clean[2:])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute).strftime("%I:%M %p")
    return "-"


def format_humidity_str(val: object) -> str:
    """
    Extract numeric humidity value and append '%'. Returns '-' if empty or invalid.
    """
    if val is None:
        return "-"
    s = str(val).strip()
    if not s or s == "-":
        return "-"
    match = re.search(r"(\d+(?:\.\d+)?)", s)
    if match:
        num = match.group(1)
        if num.endswith(".0"):
            num = num[:-2]
        return f"{num}%"
    return "-"


def parse_background_temp(val: object) -> str:
    """
    Extract numeric temperature value and append ' °C'. Returns '-' if empty or invalid.
    """
    if val is None:
        return "-"
    s = str(val).strip()
    if not s or s == "-":
        return "-"
    match = re.search(r"(\d+(?:\.\d+)?)", s)
    if match:
        return f"{match.group(1)} °C"
    return "-"
