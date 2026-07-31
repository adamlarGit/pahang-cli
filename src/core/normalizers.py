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
