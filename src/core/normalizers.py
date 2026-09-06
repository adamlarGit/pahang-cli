"""Domain normalization utilities for Pahang CLI."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import math
import re
from typing import Any


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
    """Parse 24-hour time values or time serials in various formats and convert to 12-hour hh:mm AM/PM.

    Handles:
    - datetime.datetime objects (e.g. datetime(1899, 12, 30, 10, 35)) -> '10:35 AM'
    - datetime.time objects (e.g. time(10, 35)) -> '10:35 AM'
    - Float / int numbers representing Excel day fractions (0.0 <= val < 1.0) -> '10:35 AM'
    - 3-4 digit integers / floats (e.g. 1035, 1035.0 -> '10:35 AM', 930, 930.0 -> '09:30 AM')
    - Strings with colon or dot separators, with or without AM/PM:
      '10:35 AM', '10.35 AM', '10:35:00', '10.35', '10:35', '14:30', '14.30', '2:30 PM' -> 12-hour AM/PM string
    - Empty / None / '-' / 'N/A' / 'None' / NaN -> returns '-'

    Args:
        val: Time representation as datetime, time, int, float, string, or None.

    Returns:
        Formatted 12-hour time string '%I:%M %p' (e.g. '10:35 AM'), or '-' if unparseable or empty.
    """
    if val is None or isinstance(val, bool):
        return "-"
    if isinstance(val, (datetime, time)):
        return val.strftime("%I:%M %p")
    if isinstance(val, date):
        return "-"
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return "-"

    if isinstance(val, (int, float, Decimal)):
        f_val = float(val)
        if 0.0 <= f_val < 1.0 and (isinstance(val, (float, Decimal)) or f_val == 0.0):
            total_minutes = int(round(f_val * 1440)) % 1440
            hour = total_minutes // 60
            minute = total_minutes % 60
            return time(hour, minute).strftime("%I:%M %p")
        if f_val.is_integer():
            int_val = int(round(f_val))
            s_num = str(int_val)
            if len(s_num) == 3:
                s_num = "0" + s_num
            if len(s_num) == 4:
                hour, minute = int(s_num[:2]), int(s_num[2:])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute).strftime("%I:%M %p")

    s = str(val).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return "-"

    try:
        f = float(s)
        if 0.0 <= f < 1.0 and not (math.isnan(f) or math.isinf(f)):
            total_minutes = int(round(f * 1440)) % 1440
            hour = total_minutes // 60
            minute = total_minutes % 60
            return time(hour, minute).strftime("%I:%M %p")
    except ValueError:
        pass

    if re.match(r"^\d{3,4}\.0+$", s):
        s = s.split(".")[0]

    is_pm: bool | None = None
    if re.search(r"\bPM\b|(?<=\d)PM\b|\bP\.M\.\b", s, re.IGNORECASE):
        is_pm = True
    elif re.search(r"\bAM\b|(?<=\d)AM\b|\bA\.M\.\b", s, re.IGNORECASE):
        is_pm = False

    m = re.search(r"(?:^|[^\d])(\d{1,2})[:.](\d{1,2})(?:[:.](\d{1,2}))?(?:[^\d]|$)", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m2 = re.search(r"(?:^|[^\d])(\d{3,4})(?:[^\d]|$)", s)
        if m2:
            digits = m2.group(1)
            if len(digits) == 3:
                digits = "0" + digits
            hour, minute = int(digits[:2]), int(digits[2:])
        else:
            return "-"

    if not (0 <= minute <= 59):
        return "-"

    if is_pm is True:
        if 1 <= hour <= 11:
            hour += 12
        elif hour == 12:
            pass
        elif hour == 0:
            hour = 12
        elif 13 <= hour <= 23:
            pass
        else:
            return "-"
    elif is_pm is False:
        if hour == 12:
            hour = 0
        elif 0 <= hour <= 11:
            pass
        elif 13 <= hour <= 23:
            return "-"
        else:
            return "-"
    else:
        if not (0 <= hour <= 23):
            return "-"

    return time(hour, minute).strftime("%I:%M %p")


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
    """Extract numeric temperature value, format as 1-decimal float, and append ' °C'.

    Returns '-' if empty or invalid.

    Examples:
        32         → "32.0 °C"
        32.0       → "32.0 °C"
        23.2       → "23.2 °C"
        "BACKGROUND TEMP : 23.2 °C" → "23.2 °C"
        None / "" / "-"  → "-"
    """
    temp = extract_background_temperature(val)
    if temp is None:
        return "-"
    formatted = format_temperature_float(temp)
    if formatted == "-":
        return "-"
    return f"{formatted} °C"


_NULL_SENTINELS = frozenset({
    "",
    "-",
    "--",
    "---",
    "none",
    "null",
    "nan",
    "nat",
    "n/a",
    "na",
    "#ref!",
    "#value!",
    "#n/a",
    "#name?",
    "#num!",
    "#div/0!",
})


def _is_null_or_empty(val: Any) -> bool:
    """Check if value represents an empty/null/missing/NaN entry."""
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    if isinstance(val, str):
        return val.strip().lower() in _NULL_SENTINELS
    return False


def normalize_for_csv(val: Any) -> str:
    """Sanitize and normalize value for CSV ingestion target.
    
    Returns clean string representation or empty string "" for missing/empty/NaN values.
    Never returns "-" or "NaN" or "None".
    """
    if _is_null_or_empty(val):
        return ""
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        d = Decimal(str(round(val, 6)))
        return str(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    if isinstance(val, (datetime, date)):
        return format_iso8601(val)
    s = str(val).strip()
    if s.lower() in _NULL_SENTINELS:
        return ""
    return s


def normalize_for_excel(val: Any) -> Any:
    """Convert value to native Python type (float, int, datetime.date, datetime.datetime, str, bool) or None for openpyxl cells."""
    if _is_null_or_empty(val):
        return None
    if isinstance(val, (bool, int, date, datetime)):
        return val
    if isinstance(val, float):
        return val
    s = str(val).strip()
    if s.lower() in _NULL_SENTINELS:
        return None
    # Check for integer string
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        if len(s) > 1 and s.startswith("0"):
            return s  # preserve strings with leading zeros like "064"
        return int(s)
    # Check for float string
    try:
        f_val = float(s)
        if not (math.isnan(f_val) or math.isinf(f_val)):
            if len(s) > 1 and s.startswith("0") and not s.startswith("0."):
                return s
            return f_val
    except ValueError:
        pass
    return s


def normalize_for_report(val: Any) -> str:
    """Format value for Word/PDF report tables with '-' placeholders for missing/empty values."""
    if _is_null_or_empty(val):
        return "-"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val)
    if isinstance(val, (datetime, date)):
        return format_date_cbm(val)
    s = str(val).strip()
    if s.lower() in _NULL_SENTINELS:
        return "-"
    if s.endswith(".0"):
        prefix = s[:-2]
        if prefix.isdigit() or (prefix.startswith("-") and prefix[1:].isdigit()):
            return prefix
    return s



def format_iso8601(dt: Any, tz_offset: str = "+08:00") -> str:
    """Convert datetime/date/string into standard ISO-8601 format (e.g. YYYY-MM-DDTHH:MM:SS+08:00 or YYYY-MM-DD)."""
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.isoformat()
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}{tz_offset}"
    if isinstance(dt, date):
        return dt.strftime("%Y-%m-%d")
    
    s = str(dt).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return ""
    
    # Try parsing combined datetime strings: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS
    match_dt = re.match(
        r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?(?:\.\d+)?(.*)$",
        s,
    )
    if match_dt:
        y, m, d_part, hh, mm, ss, extra = match_dt.groups()
        ss_val = int(ss) if ss else 0
        try:
            parsed = datetime(int(y), int(m), int(d_part), int(hh), int(mm), ss_val)
            if extra and re.match(r"^[+-]\d{2}:\d{2}$", extra.strip()):
                return f"{parsed.strftime('%Y-%m-%dT%H:%M:%S')}{extra.strip()}"
            return f"{parsed.strftime('%Y-%m-%dT%H:%M:%S')}{tz_offset}"
        except ValueError:
            return ""

    # Try parsing date only strings
    d_obj = _parse_date_object(s)
    if d_obj is not None:
        return d_obj.strftime("%Y-%m-%d")
    
    return ""


def extract_background_temperature(text: Any) -> float | None:
    """Extract background temperature numeric float from testsheet cell value."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        if isinstance(text, float) and (math.isnan(text) or math.isinf(text)):
            return None
        return float(text)
    s = str(text).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return None
    match = re.search(r"BACKGROUND\s*TEMP\s*:\s*(\d+(?:\.\d+)?)\s*°?\s*C?", s, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    match_num = re.search(r"^(\d+(?:\.\d+)?)\s*°?\s*C?$", s, re.IGNORECASE)
    if match_num:
        try:
            return float(match_num.group(1))
        except ValueError:
            pass
    return None


US_CHARACTERISTIC_MAP: dict[str, str] = {
    "C": "CORONA DISCHARGE",
    "CORONA": "CORONA DISCHARGE",
    "CORONA DISCHARGE": "CORONA DISCHARGE",
    "A": "ARCING",
    "ARCING": "ARCING",
    "T": "TRACKING",
    "TRACKING": "TRACKING",
    "SURFACE TRACKING": "TRACKING",
    "MV": "MECHANICAL VIBRATION",
    "MECHANICAL VIBRATION": "MECHANICAL VIBRATION",
}


def normalize_us_characteristic(val: Any, default: str = "-") -> str:
    """Normalize ultrasound defect characteristic shorthand codes to standard full terms.

    Mapping:
    - C, CORONA, CORONA DISCHARGE -> CORONA DISCHARGE
    - A, ARCING -> ARCING
    - T, TRACKING, SURFACE TRACKING -> TRACKING
    - MV, MECHANICAL VIBRATION -> MECHANICAL VIBRATION
    - None, empty, '-', 'N/A', 'NAN', etc. -> default (defaults to '-')
    - Other strings -> cleaned string representation

    Args:
        val: Ultrasound defect characteristic code or string.
        default: Fallback string when value is unspecified/null/empty/sentinel (defaults to '-').

    Returns:
        Standardized ultrasound defect characteristic string or default if empty/invalid.
    """
    if _is_null_or_empty(val):
        return default
    s = str(val).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return default
    s_upper = s.upper()
    if s_upper in US_CHARACTERISTIC_MAP:
        return US_CHARACTERISTIC_MAP[s_upper]
    return s


def normalize_fl_erms(location: object) -> str:
    """Normalize location string to FL ERMS by inserting a slash after character 8 if length >= 8.

    Examples:
        'CKTN0001AAAA' -> 'CKTN0001/AAAA'
        'CKTN/PCEJ01565' -> 'CKTN/PCE/J01565'
        'CKTN/PCE/J01565' -> 'CKTN/PCE/J01565'
        'CKTN0003/CCCC' -> 'CKTN0003/CCCC'
    """
    if location is None:
        return ""
    s = str(location).strip()
    if not s or s.lower() in ("none", "nan", "location"):
        return ""
    if len(s) > 8:
        if s[8] == "/":
            return s
        return s[:8] + "/" + s[8:]
    return s


def format_db_int(val: Any) -> str:
    """Format ultrasound (US) and TEV measurement or background dB values as integer strings (0 decimal places).

    Rounds floating-point numbers to the nearest integer using standard half-up rounding.
    Strips 'dB' or other unit text. Falls back to '-' for null, empty, boolean, NaN, or sentinel values.

    Examples:
        20.0 -> "20"
        0.0 -> "0"
        14.8 -> "15"
        "20 dB" -> "20"
        "20dB" -> "20"
        "14.8 dB" -> "15"
        None / "" / "-" -> "-"
    """
    if val is None or isinstance(val, bool):
        return "-"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return "-"
        d = Decimal(str(round(val, 6))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return str(int(d))
    if isinstance(val, Decimal):
        d = val.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return str(int(d))

    s = str(val).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return "-"

    match = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not match:
        return "-"

    try:
        f_val = float(match.group(0))
        if math.isnan(f_val) or math.isinf(f_val):
            return "-"
        d = Decimal(str(round(f_val, 6))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return str(int(d))
    except (ValueError, InvalidOperation):
        return "-"


def format_temperature_float(val: Any) -> str:
    """Format infrared (IR) temperature measurement values (°C / ΔT) as 1-decimal float strings.

    Rounds floating-point numbers to 1 decimal place using standard half-up rounding.
    Strips '°C' or other unit text. Falls back to '-' for null, empty, boolean, NaN, or sentinel values.

    Examples:
        32 -> "32.0"
        32.0 -> "32.0"
        32.34 -> "32.3"
        32.36 -> "32.4"
        "33.3 °C" -> "33.3"
        "33 °C" -> "33.0"
        None / "" / "-" -> "-"
    """
    if val is None or isinstance(val, bool):
        return "-"
    if isinstance(val, int):
        return f"{float(val):.1f}"
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return "-"
        d = Decimal(str(round(val, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{d:.1f}"
    if isinstance(val, Decimal):
        d = val.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{d:.1f}"

    s = str(val).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return "-"

    match = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not match:
        return "-"

    try:
        f_val = float(match.group(0))
        if math.isnan(f_val) or math.isinf(f_val):
            return "-"
        d = Decimal(str(round(f_val, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{d:.1f}"
    except (ValueError, InvalidOperation):
        return "-"


def format_cbm_reading(val: Any, technology: str | None) -> str:
    """Format a CBM measurement reading according to inspection technology rules.

    - US (Ultrasound) and TEV: Formatted as integer dB (0 decimal places) via format_db_int.
    - IR (Infrared): Formatted as 1-decimal float temperature (°C) via format_temperature_float.
    - Other / Unknown / VI: Falls back to normalize_for_report(val).

    Args:
        val: Measurement reading value (int, float, Decimal, str, etc.).
        technology: Inspection technology identifier (e.g. 'US', 'TEV', 'IR', 'VI').

    Returns:
        Technology-specific formatted string representation, or '-' for missing/invalid.
    """
    if not technology:
        return normalize_for_report(val)
    tech_upper = str(technology).strip().upper()
    if any(k in tech_upper for k in ("US", "ULTRASOUND", "TEV", "TRANSIENT")):
        return format_db_int(val)
    if any(k in tech_upper for k in ("IR", "INFRARED", "THERMAL", "THERMOGRAPHY")):
        return format_temperature_float(val)
    return normalize_for_report(val)


def format_heater_amp(val: Any, switchgear_type: str | None = None) -> str:
    """Format anti-condensation heater current for switchgear panels.

    - For VCB switchgear (or when switchgear_type is None / contains 'VCB'):
      Parses valid numeric current into 1-decimal float using half-up rounding (stripping trailing 'A'/'a' and whitespace).
      Renders as 'ON:<amp>A/OFF:0.0A' (e.g. '0.5A' -> 'ON:0.5A/OFF:0.0A', '0.55' -> 'ON:0.6A/OFF:0.0A', '1' -> 'ON:1.0A/OFF:0.0A', '0' -> 'ON:0.0A/OFF:0.0A').
      Returns '-' if empty, blank, '-', 'N/A', or non-numeric.
    - For Non-VCB switchgear (RMU SF6, RMU OIL, MRMU, OCB, etc.):
      Always returns '-'.

    Args:
        val: Heater current reading (str, int, float, Decimal, etc.).
        switchgear_type: Switchgear type string (e.g. 'VCB', 'RMU SF6', 'MRMU', etc.).

    Returns:
        Formatted heater current string or '-' if invalid or non-VCB.
    """
    if switchgear_type is not None and "VCB" not in str(switchgear_type).upper():
        return "-"

    if _is_null_or_empty(val) or isinstance(val, bool):
        return "-"

    if isinstance(val, (int, float, Decimal)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return "-"
        d = Decimal(str(round(float(val), 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"ON:{d:.1f}A/OFF:0.0A"

    s = str(val).strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return "-"

    m_on = re.match(r"^ON:\s*(\d+(?:\.\d+)?)\s*A\s*/\s*OFF:\s*0(?:\.0)?\s*A$", s, re.IGNORECASE)
    if m_on:
        clean = m_on.group(1)
    else:
        clean = re.sub(r"[Aa]\s*$", "", s).strip()

    if not clean or clean.lower() in _NULL_SENTINELS:
        return "-"

    try:
        f_val = float(clean)
        if math.isnan(f_val) or math.isinf(f_val):
            return "-"
        d = Decimal(str(round(f_val, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"ON:{d:.1f}A/OFF:0.0A"
    except (ValueError, InvalidOperation):
        return "-"


def format_busbar_position(panel_name: Any, switchgear_type: str | None = None) -> str:
    """Format busbar position for switchgear panels.

    - If panel name contains 'TRANSITION' (case-insensitive, e.g. 'TRANSITION PANEL', 'TRANSITION'): output '-'.
    - Otherwise, if switchgear is VCB: output 'MAIN'.
    - Otherwise (Non-VCB like RMU, MRMU, OIL, OCB, etc.): output '-'.

    Args:
        panel_name: Name or label of the switchgear panel.
        switchgear_type: Switchgear type string (e.g. 'VCB', 'RMU SF6', 'MRMU', etc.).

    Returns:
        'MAIN' for non-transition panels on VCB switchgear, or '-' otherwise.
    """
    p_name = str(panel_name or "").strip().upper()
    if "TRANSITION" in p_name:
        return "-"
    if switchgear_type and "VCB" in str(switchgear_type).upper():
        return "MAIN"
    return "-"


__all__ = [
    "FL_PREFIX_TO_STATION",
    "STATION_NAME_TO_CODE",
    "extract_background_temperature",
    "format_busbar_position",
    "format_cbm_reading",
    "format_date_cbm",
    "format_date_front_page",
    "format_db_int",
    "format_heater_amp",
    "format_humidity_str",
    "format_iso8601",
    "format_month_folder",
    "format_temperature_float",
    "format_testsheet_time",
    "normalize_date_str",
    "normalize_fl_erms",
    "normalize_for_csv",
    "normalize_for_excel",
    "normalize_for_report",
    "normalize_us_characteristic",
    "parse_background_temp",
    "resolve_station_code",
    "resolve_station_from_fl",
]


FL_PREFIX_TO_STATION: dict[str, str] = {
    "CRAU": "RAUB",
    "CKTN": "KUANTAN",
    "CCHL": "CAMERON HIGHLAND",
    "CBTO": "BENTONG",
    "CBTG": "BENTONG",
    "CTMH": "TEMERLOH",
    "CTML": "TEMERLOH",
    "CPKN": "PEKAN",
    "CPEK": "PEKAN",
    "CMRN": "MARAN",
    "CJEN": "JENGKA",
    "CBMS": "MUADZAM SHAH",
    "CBGB": "GEBENG",
    "CROM": "ROMPIN",
    "CTRI": "TRIANG",
    "CKLS": "KUALA LIPIS",
    "CJRT": "JERANTUT",
}

STATION_NAME_TO_CODE: dict[str, str] = {
    "RAUB": "RAU",
    "RAU": "RAU",
    "KUANTAN": "KTN",
    "KTN": "KTN",
    "CAMERON HIGHLAND": "CHL",
    "CAMERON HIGHLANDS": "CHL",
    "CAMERON": "CHL",
    "CHL": "CHL",
    "BENTONG": "BTG",
    "BTO": "BTG",
    "BTG": "BTG",
    "TEMERLOH": "TMH",
    "TMH": "TMH",
    "TML": "TMH",
    "PEKAN": "PKN",
    "PKN": "PKN",
    "PEK": "PKN",
    "MARAN": "MRN",
    "MRN": "MRN",
    "JENGKA": "JEN",
    "JEN": "JEN",
    "MUADZAM SHAH": "BMS",
    "BMS": "BMS",
    "GEBENG": "GBG",
    "GBG": "GBG",
    "ROMPIN": "ROM",
    "ROM": "ROM",
    "TRIANG": "TRI",
    "TRI": "TRI",
    "KUALA LIPIS": "KLS",
    "KLS": "KLS",
    "JERANTUT": "JRT",
    "JRT": "JRT",
}


def resolve_station_code(station: str | None) -> str | None:
    """Resolve a station name or abbreviation to canonical 3-letter ENGR station code.

    Maps:
        RAUB -> RAU
        KUANTAN -> KTN
        CAMERON HIGHLAND -> CHL
        BENTONG -> BTG
        TEMERLOH -> TMH
        PEKAN -> PKN
    """
    if not station or not str(station).strip():
        return None
    s = str(station).strip().upper()
    if s in STATION_NAME_TO_CODE:
        return STATION_NAME_TO_CODE[s]
    for name, code in STATION_NAME_TO_CODE.items():
        if len(name) > 3 and (name in s or s in name):
            return code
    return None


def resolve_station_from_fl(fl: str | None) -> str | None:
    """Infer station name from standard 4-character functional location prefix.

    Maps:
        CRAU -> RAUB
        CKTN -> KUANTAN
        CCHL -> CAMERON HIGHLAND
        CBTO / CBTG -> BENTONG
        CTMH / CTML -> TEMERLOH
        CPKN / CPEK -> PEKAN
    """
    if not fl or not str(fl).strip():
        return None
    s = str(fl).strip().upper().replace("/", "").replace("-", "")
    prefix = s[:4]
    return FL_PREFIX_TO_STATION.get(prefix, None)

