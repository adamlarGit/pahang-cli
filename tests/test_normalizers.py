"""Unit tests for domain normalizers in src/core/normalizers.py."""

from __future__ import annotations

from datetime import date, datetime

from decimal import Decimal

from src.core.normalizers import (
    extract_background_temperature,
    format_busbar_position,
    format_cbm_reading,
    format_date_cbm,
    format_date_front_page,
    format_db_int,
    format_heater_amp,
    format_humidity_str,
    format_iso8601,
    format_month_folder,
    format_temperature_float,
    format_testsheet_time,
    normalize_date_str,
    normalize_fl_erms,
    normalize_for_csv,
    normalize_for_excel,
    normalize_for_report,
    normalize_us_characteristic,
    parse_background_temp,
)


def test_format_date_front_page() -> None:
    # Hyphenated strings (DD-MM-YYYY)
    assert format_date_front_page("12-08-2026") == "12 AUG 2026"
    assert format_date_front_page("5-7-2026") == "05 JUL 2026"
    # Slashed strings (DD/MM/YYYY)
    assert format_date_front_page("12/08/2026") == "12 AUG 2026"
    assert format_date_front_page("5/7/2026") == "05 JUL 2026"
    # ISO strings (YYYY-MM-DD and YYYY/MM/DD)
    assert format_date_front_page("2026-08-12") == "12 AUG 2026"
    assert format_date_front_page("2026/08/12") == "12 AUG 2026"
    # Named month strings
    assert format_date_front_page("12 AUG 2026") == "12 AUG 2026"
    assert format_date_front_page("12-Aug-2026") == "12 AUG 2026"
    # date and datetime objects
    assert format_date_front_page(date(2026, 8, 12)) == "12 AUG 2026"
    assert format_date_front_page(datetime(2026, 8, 12, 14, 30)) == "12 AUG 2026"
    # Fallback for None, empty string, or invalid text
    assert format_date_front_page(None) == "-"
    assert format_date_front_page("") == "-"
    assert format_date_front_page("invalid_date") == "-"
    assert format_date_front_page("N/A") == "-"


def test_format_date_cbm() -> None:
    # Hyphenated strings (DD-MM-YYYY)
    assert format_date_cbm("12-08-2026") == "12/08/2026"
    assert format_date_cbm("5-7-2026") == "05/07/2026"
    # Slashed strings (DD/MM/YYYY)
    assert format_date_cbm("12/08/2026") == "12/08/2026"
    assert format_date_cbm("5/7/2026") == "05/07/2026"
    # ISO strings (YYYY-MM-DD and YYYY/MM/DD)
    assert format_date_cbm("2026-08-12") == "12/08/2026"
    assert format_date_cbm("2026/08/12") == "12/08/2026"
    # Named month strings
    assert format_date_cbm("12 AUG 2026") == "12/08/2026"
    assert format_date_cbm("12-Aug-2026") == "12/08/2026"
    # date and datetime objects
    assert format_date_cbm(date(2026, 8, 12)) == "12/08/2026"
    assert format_date_cbm(datetime(2026, 8, 12, 14, 30)) == "12/08/2026"
    # Fallback for None, empty string, or invalid text
    assert format_date_cbm(None) == "-"
    assert format_date_cbm("") == "-"
    assert format_date_cbm("invalid_date") == "-"
    assert format_date_cbm("N/A") == "-"


def test_normalize_date_str_empty() -> None:
    assert normalize_date_str(None) == ""
    assert normalize_date_str("") == ""


def test_normalize_date_str_date_and_datetime() -> None:
    assert normalize_date_str(date(2026, 7, 30)) == "30-07-2026"
    assert normalize_date_str(datetime(2026, 7, 30, 14, 30)) == "30-07-2026"


def test_normalize_date_str_iso_format() -> None:
    assert normalize_date_str("2026-07-30") == "30-07-2026"
    assert normalize_date_str("2026-7-5") == "05-07-2026"


def test_normalize_date_str_slashes_and_dashes() -> None:
    assert normalize_date_str("30/07/2026") == "30-07-2026"
    assert normalize_date_str("30-07-2026") == "30-07-2026"
    assert normalize_date_str("5-7-2026") == "05-07-2026"


def test_normalize_date_str_passthrough() -> None:
    assert normalize_date_str("invalid_date") == "invalid_date"


def test_format_month_folder_empty() -> None:
    assert format_month_folder(None) == ""
    assert format_month_folder("") == ""
    assert format_month_folder("-") == ""
    assert format_month_folder("None") == ""
    assert format_month_folder("N/A") == ""


def test_format_month_folder_date_objects() -> None:
    assert format_month_folder(date(2026, 3, 15)) == "03. MARCH"
    assert format_month_folder(datetime(2026, 12, 1, 10, 0)) == "12. DECEMBER"


def test_format_month_folder_strings() -> None:
    assert format_month_folder("01. JAN") == "01. JANUARY"
    assert format_month_folder("01. JANUARY") == "01. JANUARY"
    assert format_month_folder("2026-01 (Jan)") == "01. JANUARY"
    assert format_month_folder("01-01-2026") == "01. JANUARY"
    assert format_month_folder("JANUARY") == "01. JANUARY"
    assert format_month_folder("january") == "01. JANUARY"
    assert format_month_folder("02. FEB") == "02. FEBRUARY"
    assert format_month_folder("03. MARCH") == "03. MARCH"
    assert format_month_folder("04. APRIL") == "04. APRIL"
    assert format_month_folder("05. MAY") == "05. MAY"
    assert format_month_folder("06. JUNE") == "06. JUNE"
    assert format_month_folder("07. JULY") == "07. JULY"
    assert format_month_folder("08. AUGUST") == "08. AUGUST"
    assert format_month_folder("09. SEPTEMBER") == "09. SEPTEMBER"
    assert format_month_folder("10. OCTOBER") == "10. OCTOBER"
    assert format_month_folder("11. NOVEMBER") == "11. NOVEMBER"
    assert format_month_folder("12. DECEMBER") == "12. DECEMBER"


def test_format_month_folder_keyword_args() -> None:
    assert format_month_folder(month_input="05. MAY") == "05. MAY"
    assert format_month_folder(val="06. JUNE") == "06. JUNE"


def test_format_testsheet_time() -> None:
    from datetime import time, date, datetime
    from decimal import Decimal

    # datetime objects (including openpyxl epoch 1899-12-30)
    assert format_testsheet_time(datetime(1899, 12, 30, 10, 35)) == "10:35 AM"
    assert format_testsheet_time(datetime(2026, 9, 2, 14, 30)) == "02:30 PM"
    assert format_testsheet_time(datetime(2026, 9, 2, 0, 0)) == "12:00 AM"
    assert format_testsheet_time(datetime(2026, 9, 2, 12, 0)) == "12:00 PM"

    # time objects
    assert format_testsheet_time(time(10, 35)) == "10:35 AM"
    assert format_testsheet_time(time(14, 30)) == "02:30 PM"
    assert format_testsheet_time(time(9, 15)) == "09:15 AM"
    assert format_testsheet_time(time(0, 0)) == "12:00 AM"
    assert format_testsheet_time(time(12, 0)) == "12:00 PM"

    # date objects (without time component) -> fallback to "-"
    assert format_testsheet_time(date(2026, 9, 2)) == "-"

    # Excel day fraction numbers (0.0 <= val < 1.0)
    assert format_testsheet_time(0.4409722222222222) == "10:35 AM"
    assert format_testsheet_time(0.6041666666666666) == "02:30 PM"
    assert format_testsheet_time(Decimal("0.4409722222222222")) == "10:35 AM"
    assert format_testsheet_time(0.0) == "12:00 AM"
    assert format_testsheet_time("0.4409722222222222") == "10:35 AM"

    # Integers and float-integers (3-4 digits, e.g. 1035, 1035.0, 930, 930.0)
    assert format_testsheet_time(1035) == "10:35 AM"
    assert format_testsheet_time(1035.0) == "10:35 AM"
    assert format_testsheet_time(930) == "09:30 AM"
    assert format_testsheet_time(930.0) == "09:30 AM"
    assert format_testsheet_time(1430) == "02:30 PM"
    assert format_testsheet_time(1430.0) == "02:30 PM"
    assert format_testsheet_time(915) == "09:15 AM"
    assert format_testsheet_time("1035") == "10:35 AM"
    assert format_testsheet_time("1035.0") == "10:35 AM"
    assert format_testsheet_time("930") == "09:30 AM"
    assert format_testsheet_time("930.0") == "09:30 AM"
    assert format_testsheet_time("0915") == "09:15 AM"
    assert format_testsheet_time("915") == "09:15 AM"
    assert format_testsheet_time("1430") == "02:30 PM"

    # Colon and dot separated strings with or without AM/PM
    assert format_testsheet_time("10:35 AM") == "10:35 AM"
    assert format_testsheet_time("10.35 AM") == "10:35 AM"
    assert format_testsheet_time("10:35:00") == "10:35 AM"
    assert format_testsheet_time("10.35.00") == "10:35 AM"
    assert format_testsheet_time("10:35:00 AM") == "10:35 AM"
    assert format_testsheet_time("10.35.00 AM") == "10:35 AM"
    assert format_testsheet_time("10.35") == "10:35 AM"
    assert format_testsheet_time("10:35") == "10:35 AM"
    assert format_testsheet_time("14:30") == "02:30 PM"
    assert format_testsheet_time("14.30") == "02:30 PM"
    assert format_testsheet_time("14:30:00") == "02:30 PM"
    assert format_testsheet_time("2:30 PM") == "02:30 PM"
    assert format_testsheet_time("2.30 PM") == "02:30 PM"
    assert format_testsheet_time("2.30pm") == "02:30 PM"
    assert format_testsheet_time("2:30pm") == "02:30 PM"
    assert format_testsheet_time("02:30 PM") == "02:30 PM"
    assert format_testsheet_time("9.30") == "09:30 AM"
    assert format_testsheet_time("9:30") == "09:30 AM"
    assert format_testsheet_time("9:30 PM") == "09:30 PM"
    assert format_testsheet_time("9.30 PM") == "09:30 PM"
    assert format_testsheet_time("12:00 PM") == "12:00 PM"
    assert format_testsheet_time("12:00 AM") == "12:00 AM"
    assert format_testsheet_time("00:00") == "12:00 AM"
    assert format_testsheet_time("0:00") == "12:00 AM"

    # Null, empty, sentinels, booleans, and invalid inputs
    assert format_testsheet_time(None) == "-"
    assert format_testsheet_time("") == "-"
    assert format_testsheet_time("   ") == "-"
    assert format_testsheet_time("-") == "-"
    assert format_testsheet_time("--") == "-"
    assert format_testsheet_time("N/A") == "-"
    assert format_testsheet_time("n/a") == "-"
    assert format_testsheet_time("None") == "-"
    assert format_testsheet_time("none") == "-"
    assert format_testsheet_time("nan") == "-"
    assert format_testsheet_time(float("nan")) == "-"
    assert format_testsheet_time(float("inf")) == "-"
    assert format_testsheet_time(True) == "-"
    assert format_testsheet_time(False) == "-"
    assert format_testsheet_time("invalid") == "-"
    assert format_testsheet_time("25:00") == "-"
    assert format_testsheet_time("10:65") == "-"
    assert format_testsheet_time("99:99") == "-"
    assert format_testsheet_time("14:30 AM") == "-"


def test_format_humidity_str() -> None:
    assert format_humidity_str(None) == "-"
    assert format_humidity_str("") == "-"
    assert format_humidity_str("-") == "-"
    assert format_humidity_str("65") == "65%"
    assert format_humidity_str(65) == "65%"
    assert format_humidity_str(65.0) == "65%"
    assert format_humidity_str("65.0") == "65%"
    assert format_humidity_str("65%") == "65%"
    assert format_humidity_str("invalid") == "-"


def test_parse_background_temp() -> None:
    assert parse_background_temp(None) == "-"
    assert parse_background_temp("") == "-"
    assert parse_background_temp("-") == "-"
    assert parse_background_temp("BACKGROUND TEMP : 23.2 °C") == "23.2 °C"
    assert parse_background_temp("BACKGROUND TEMP : 30.4 °C") == "30.4 °C"
    assert parse_background_temp("23.2") == "23.2 °C"
    assert parse_background_temp(23.2) == "23.2 °C"
    assert parse_background_temp(23) == "23.0 °C"
    assert parse_background_temp("invalid") == "-"
    assert parse_background_temp(float("nan")) == "-"
    assert parse_background_temp(True) == "-"
    assert parse_background_temp(False) == "-"


def test_normalize_for_csv_null_and_empty() -> None:
    assert normalize_for_csv(None) == ""
    assert normalize_for_csv("") == ""
    assert normalize_for_csv("   ") == ""
    assert normalize_for_csv("-") == ""
    assert normalize_for_csv("--") == ""
    assert normalize_for_csv("None") == ""
    assert normalize_for_csv("NONE") == ""
    assert normalize_for_csv("NaN") == ""
    assert normalize_for_csv("nan") == ""
    assert normalize_for_csv("NAN") == ""
    assert normalize_for_csv("N/A") == ""
    assert normalize_for_csv("n/a") == ""
    assert normalize_for_csv("NaT") == ""
    assert normalize_for_csv("null") == ""
    assert normalize_for_csv("#REF!") == ""
    assert normalize_for_csv(float("nan")) == ""
    assert normalize_for_csv(float("inf")) == ""


def test_normalize_for_csv_numbers_and_types() -> None:
    assert normalize_for_csv(23.2) == "23.2"
    assert normalize_for_csv(41.05) == "41.1"
    assert normalize_for_csv(32.55) == "32.6"
    assert normalize_for_csv(35.33) == "35.3"
    assert normalize_for_csv(36.55) == "36.6"
    assert normalize_for_csv(0.10000000000000142) == "0.1"
    assert normalize_for_csv(3.1000000000000014) == "3.1"
    assert normalize_for_csv(28.0) == "28.0"
    assert normalize_for_csv(0.0) == "0.0"
    assert normalize_for_csv(0) == "0"
    assert normalize_for_csv(42) == "42"
    assert normalize_for_csv(True) == "True"
    assert normalize_for_csv(False) == "False"
    assert normalize_for_csv("  INDKOM  ") == "INDKOM"
    assert normalize_for_csv(date(2026, 8, 12)) == "2026-08-12"
    assert normalize_for_csv(datetime(2026, 8, 12, 14, 30)) == "2026-08-12T14:30:00+08:00"


def test_normalize_for_excel_null_and_empty() -> None:
    assert normalize_for_excel(None) is None
    assert normalize_for_excel("") is None
    assert normalize_for_excel("   ") is None
    assert normalize_for_excel("-") is None
    assert normalize_for_excel("--") is None
    assert normalize_for_excel("None") is None
    assert normalize_for_excel("NONE") is None
    assert normalize_for_excel("NaN") is None
    assert normalize_for_excel("nan") is None
    assert normalize_for_excel("N/A") is None
    assert normalize_for_excel("#REF!") is None
    assert normalize_for_excel(float("nan")) is None
    assert normalize_for_excel(float("inf")) is None


def test_normalize_for_excel_native_types() -> None:
    assert normalize_for_excel(42) == 42
    assert isinstance(normalize_for_excel(42), int)
    assert normalize_for_excel(23.5) == 23.5
    assert isinstance(normalize_for_excel(23.5), float)
    assert normalize_for_excel("42") == 42
    assert normalize_for_excel("23.5") == 23.5
    assert normalize_for_excel("064") == "064"
    assert normalize_for_excel("TAMCO VHIH") == "TAMCO VHIH"
    d = date(2026, 8, 12)
    assert normalize_for_excel(d) == d
    dt = datetime(2026, 8, 12, 10, 30)
    assert normalize_for_excel(dt) == dt
    assert normalize_for_excel(True) is True
    assert normalize_for_excel(False) is False


def test_normalize_for_report_null_and_placeholders() -> None:
    assert normalize_for_report(None) == "-"
    assert normalize_for_report("") == "-"
    assert normalize_for_report("   ") == "-"
    assert normalize_for_report("-") == "-"
    assert normalize_for_report("--") == "-"
    assert normalize_for_report("None") == "-"
    assert normalize_for_report("NONE") == "-"
    assert normalize_for_report("NaN") == "-"
    assert normalize_for_report("nan") == "-"
    assert normalize_for_report("N/A") == "-"
    assert normalize_for_report("#REF!") == "-"
    assert normalize_for_report(float("nan")) == "-"


def test_normalize_for_report_formatted_values() -> None:
    assert normalize_for_report(42) == "42"
    assert normalize_for_report(42.0) == "42"
    assert normalize_for_report("42.0") == "42"
    assert normalize_for_report(23.5) == "23.5"
    assert normalize_for_report("23.5") == "23.5"
    assert normalize_for_report("TAMCO") == "TAMCO"
    assert normalize_for_report(date(2026, 8, 12)) == "12/08/2026"
    assert normalize_for_report(datetime(2026, 8, 12, 10, 30)) == "12/08/2026"



def test_format_iso8601() -> None:
    # datetime objects
    dt = datetime(2026, 6, 9, 14, 17, 6)
    assert format_iso8601(dt) == "2026-06-09T14:17:06+08:00"
    assert format_iso8601(dt, tz_offset="+00:00") == "2026-06-09T14:17:06+00:00"
    
    # date objects
    d = date(2026, 6, 9)
    assert format_iso8601(d) == "2026-06-09"

    # date strings
    assert format_iso8601("2026-06-09") == "2026-06-09"
    assert format_iso8601("09-06-2026") == "2026-06-09"
    assert format_iso8601("09/06/2026") == "2026-06-09"
    assert format_iso8601("2026-06-09 14:17:06") == "2026-06-09T14:17:06+08:00"
    assert format_iso8601("2026-06-09T14:17:06") == "2026-06-09T14:17:06+08:00"

    # null/empty
    assert format_iso8601(None) == ""
    assert format_iso8601("") == ""
    assert format_iso8601("-") == ""
    assert format_iso8601("invalid") == ""


def test_extract_background_temperature() -> None:
    assert extract_background_temperature("BACKGROUND TEMP : 23.2 °C") == 23.2
    assert extract_background_temperature("BACKGROUND TEMP:30.4°C") == 30.4
    assert extract_background_temperature("BACKGROUND  TEMP  :  28.0 C") == 28.0
    assert extract_background_temperature("BACKGROUND TEMP: 25.0 ° C") == 25.0
    assert extract_background_temperature("23.2") == 23.2
    assert extract_background_temperature(23.2) == 23.2
    assert extract_background_temperature(25) == 25.0
    assert extract_background_temperature(None) is None
    assert extract_background_temperature("") is None
    assert extract_background_temperature("-") is None
    assert extract_background_temperature("N/A") is None
    assert extract_background_temperature("invalid text") is None
    assert extract_background_temperature(float("nan")) is None
    assert extract_background_temperature(True) is None
    assert extract_background_temperature(False) is None


def test_normalize_fl_erms() -> None:
    # Inserts slash at position 8
    assert normalize_fl_erms("CKTN0001AAAA") == "CKTN0001/AAAA"
    assert normalize_fl_erms("CKTN/PCEJ01565") == "CKTN/PCE/J01565"

    # Already has slash at position 8
    assert normalize_fl_erms("CKTN/PCE/J01565") == "CKTN/PCE/J01565"
    assert normalize_fl_erms("CKTN0003/CCCC") == "CKTN0003/CCCC"

    # Short string (length <= 8)
    assert normalize_fl_erms("CKTN0001") == "CKTN0001"
    assert normalize_fl_erms("SHORT") == "SHORT"

    # Empty, None, or sentinel values
    assert normalize_fl_erms(None) == ""
    assert normalize_fl_erms("") == ""
    assert normalize_fl_erms("None") == ""
    assert normalize_fl_erms("nan") == ""
    assert normalize_fl_erms("location") == ""


def test_normalize_us_characteristic() -> None:
    """Verify normalize_us_characteristic maps shorthand codes to full descriptive terms."""
    # 1. Null, empty, and sentinel values -> '-'
    assert normalize_us_characteristic(None) == "-"
    assert normalize_us_characteristic("") == "-"
    assert normalize_us_characteristic("   ") == "-"
    assert normalize_us_characteristic("-") == "-"
    assert normalize_us_characteristic("--") == "-"
    assert normalize_us_characteristic("---") == "-"
    assert normalize_us_characteristic("N/A") == "-"
    assert normalize_us_characteristic("n/a") == "-"
    assert normalize_us_characteristic("NAN") == "-"
    assert normalize_us_characteristic("nan") == "-"
    assert normalize_us_characteristic(float("nan")) == "-"
    assert normalize_us_characteristic("None") == "-"
    assert normalize_us_characteristic("null") == "-"
    assert normalize_us_characteristic("#REF!") == "-"

    # 2. Corona Discharge mappings (C, CORONA, CORONA DISCHARGE)
    assert normalize_us_characteristic("C") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("c") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("  c  ") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("CORONA") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("corona") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("CORONA DISCHARGE") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("corona discharge") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("  CORONA  ") == "CORONA DISCHARGE"

    # 3. Arcing mappings (A, ARCING)
    assert normalize_us_characteristic("A") == "ARCING"
    assert normalize_us_characteristic("a") == "ARCING"
    assert normalize_us_characteristic("  a  ") == "ARCING"
    assert normalize_us_characteristic("ARCING") == "ARCING"
    assert normalize_us_characteristic("arcing") == "ARCING"
    assert normalize_us_characteristic("  ARCING  ") == "ARCING"

    # 4. Tracking mappings (T, TRACKING, SURFACE TRACKING)
    assert normalize_us_characteristic("T") == "TRACKING"
    assert normalize_us_characteristic("t") == "TRACKING"
    assert normalize_us_characteristic("  t  ") == "TRACKING"
    assert normalize_us_characteristic("TRACKING") == "TRACKING"
    assert normalize_us_characteristic("tracking") == "TRACKING"
    assert normalize_us_characteristic("SURFACE TRACKING") == "TRACKING"
    assert normalize_us_characteristic("surface tracking") == "TRACKING"
    assert normalize_us_characteristic("  SURFACE TRACKING  ") == "TRACKING"

    # 5. Mechanical Vibration mappings (MV, MECHANICAL VIBRATION)
    assert normalize_us_characteristic("MV") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("mv") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("  mv  ") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("MECHANICAL VIBRATION") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("mechanical vibration") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("  MECHANICAL VIBRATION  ") == "MECHANICAL VIBRATION"

    # 6. Other / non-mapped strings -> return cleaned string representation
    assert normalize_us_characteristic("NORMAL") == "NORMAL"
    assert normalize_us_characteristic("normal") == "NORMAL"
    assert normalize_us_characteristic("PARTIAL DISCHARGE") == "PARTIAL DISCHARGE"
    assert normalize_us_characteristic("  Custom Sound Pattern  ") == "Custom Sound Pattern"

    # 7. Unspecified with default="NORMAL" (detail pages)
    assert normalize_us_characteristic(None, default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("   ", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("-", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("--", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("N/A", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("nan", default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic(float("nan"), default="NORMAL") == "NORMAL"
    assert normalize_us_characteristic("C", default="NORMAL") == "CORONA DISCHARGE"
    assert normalize_us_characteristic("T", default="NORMAL") == "TRACKING"
    assert normalize_us_characteristic("A", default="NORMAL") == "ARCING"
    assert normalize_us_characteristic("MV", default="NORMAL") == "MECHANICAL VIBRATION"
    assert normalize_us_characteristic("NORMAL", default="NORMAL") == "NORMAL"



def test_format_db_int() -> None:
    """Verify format_db_int formats US and TEV dB readings as 0-decimal integer strings."""
    # Integers
    assert format_db_int(20) == "20"
    assert format_db_int(0) == "0"
    assert format_db_int(-5) == "-5"

    # Floats (rounding to nearest integer)
    assert format_db_int(20.0) == "20"
    assert format_db_int(0.0) == "0"
    assert format_db_int(14.8) == "15"
    assert format_db_int(14.2) == "14"
    assert format_db_int(14.5) == "15"
    assert format_db_int(-5.6) == "-6"
    assert format_db_int(-5.2) == "-5"

    # Decimal instances
    assert format_db_int(Decimal("20.0")) == "20"
    assert format_db_int(Decimal("14.8")) == "15"
    assert format_db_int(Decimal("0.0")) == "0"

    # Strings with units and variations
    assert format_db_int("20") == "20"
    assert format_db_int("20.0") == "20"
    assert format_db_int("20 dB") == "20"
    assert format_db_int("20dB") == "20"
    assert format_db_int("20.0 dB") == "20"
    assert format_db_int("14.8 dB") == "15"
    assert format_db_int("14.2dB") == "14"
    assert format_db_int("  18.5 dB  ") == "19"
    assert format_db_int("-5 dB") == "-5"
    assert format_db_int("0") == "0"
    assert format_db_int("0.0") == "0"
    assert format_db_int("0 dB") == "0"

    # Null, empty, sentinel, boolean, and invalid inputs -> "-"
    assert format_db_int(None) == "-"
    assert format_db_int("") == "-"
    assert format_db_int("   ") == "-"
    assert format_db_int("-") == "-"
    assert format_db_int("--") == "-"
    assert format_db_int("---") == "-"
    assert format_db_int("None") == "-"
    assert format_db_int("none") == "-"
    assert format_db_int("NaN") == "-"
    assert format_db_int("nan") == "-"
    assert format_db_int("N/A") == "-"
    assert format_db_int("n/a") == "-"
    assert format_db_int("null") == "-"
    assert format_db_int("#REF!") == "-"
    assert format_db_int(float("nan")) == "-"
    assert format_db_int(float("inf")) == "-"
    assert format_db_int(-float("inf")) == "-"
    assert format_db_int(True) == "-"
    assert format_db_int(False) == "-"
    assert format_db_int("invalid text") == "-"


def test_format_temperature_float() -> None:
    """Verify format_temperature_float formats IR temperature readings as 1-decimal float strings."""
    # Integers
    assert format_temperature_float(32) == "32.0"
    assert format_temperature_float(0) == "0.0"
    assert format_temperature_float(-5) == "-5.0"

    # Floats
    assert format_temperature_float(32.0) == "32.0"
    assert format_temperature_float(32.34) == "32.3"
    assert format_temperature_float(32.36) == "32.4"
    assert format_temperature_float(32.35) == "32.4"
    assert format_temperature_float(0.0) == "0.0"
    assert format_temperature_float(-5.65) == "-5.7"
    assert format_temperature_float(-5.64) == "-5.6"

    # Decimal instances
    assert format_temperature_float(Decimal("32")) == "32.0"
    assert format_temperature_float(Decimal("32.0")) == "32.0"
    assert format_temperature_float(Decimal("32.34")) == "32.3"
    assert format_temperature_float(Decimal("32.35")) == "32.4"

    # Strings with units and variations
    assert format_temperature_float("32") == "32.0"
    assert format_temperature_float("32.0") == "32.0"
    assert format_temperature_float("32.34") == "32.3"
    assert format_temperature_float("33.3 °C") == "33.3"
    assert format_temperature_float("33.3°C") == "33.3"
    assert format_temperature_float("33 °C") == "33.0"
    assert format_temperature_float("33C") == "33.0"
    assert format_temperature_float("  35.5 °C  ") == "35.5"
    assert format_temperature_float("ΔT 5.4") == "5.4"
    assert format_temperature_float("ΔT 5.4 °C") == "5.4"
    assert format_temperature_float("0") == "0.0"
    assert format_temperature_float("0.0") == "0.0"

    # Null, empty, sentinel, boolean, and invalid inputs -> "-"
    assert format_temperature_float(None) == "-"
    assert format_temperature_float("") == "-"
    assert format_temperature_float("   ") == "-"
    assert format_temperature_float("-") == "-"
    assert format_temperature_float("--") == "-"
    assert format_temperature_float("---") == "-"
    assert format_temperature_float("None") == "-"
    assert format_temperature_float("none") == "-"
    assert format_temperature_float("NaN") == "-"
    assert format_temperature_float("nan") == "-"
    assert format_temperature_float("N/A") == "-"
    assert format_temperature_float("n/a") == "-"
    assert format_temperature_float("null") == "-"
    assert format_temperature_float("#REF!") == "-"
    assert format_temperature_float(float("nan")) == "-"
    assert format_temperature_float(float("inf")) == "-"
    assert format_temperature_float(-float("inf")) == "-"
    assert format_temperature_float(True) == "-"
    assert format_temperature_float(False) == "-"
    assert format_temperature_float("invalid text") == "-"


def test_format_cbm_reading() -> None:
    """Verify format_cbm_reading dispatches to format_db_int for US/TEV and format_temperature_float for IR."""
    # US readings -> format_db_int
    assert format_cbm_reading(14.8, "US") == "15"
    assert format_cbm_reading("14.2 dB", "US") == "14"
    assert format_cbm_reading("20.0 dB", "ULTRASOUND") == "20"
    assert format_cbm_reading(None, "US") == "-"

    # TEV readings -> format_db_int
    assert format_cbm_reading(20.0, "TEV") == "20"
    assert format_cbm_reading("28.5 dB", "TEV") == "29"
    assert format_cbm_reading("12", "TRANSIENT EARTH VOLTAGE") == "12"
    assert format_cbm_reading(None, "TEV") == "-"

    # IR readings -> format_temperature_float
    assert format_cbm_reading(32, "IR") == "32.0"
    assert format_cbm_reading(32.34, "IR") == "32.3"
    assert format_cbm_reading("33.3 °C", "INFRARED") == "33.3"
    assert format_cbm_reading("55", "THERMAL") == "55.0"
    assert format_cbm_reading(None, "IR") == "-"

    # Other / None / VI -> normalize_for_report
    assert format_cbm_reading("Corrosion", "VI") == "Corrosion"
    assert format_cbm_reading("Oil Leakage", "VISUAL") == "Oil Leakage"
    assert format_cbm_reading(None, None) == "-"
    assert format_cbm_reading("", "") == "-"


def test_format_heater_amp() -> None:
    """Verify format_heater_amp formats anti-condensation heater current per domain rules."""
    # 1. Numeric and string formatting with explicit is_vcb=True or VCB switchgear
    assert format_heater_amp("0.5A", is_vcb=True) == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp("0.5a", is_vcb=True) == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp("0.5 A", is_vcb=True) == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp("0.55", is_vcb=True) == "ON:0.6A/OFF:0.0A"
    assert format_heater_amp("0.54", is_vcb=True) == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp(0.5, is_vcb=True) == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp(0.55, is_vcb=True) == "ON:0.6A/OFF:0.0A"
    assert format_heater_amp(1, is_vcb=True) == "ON:1.0A/OFF:0.0A"
    assert format_heater_amp("1", is_vcb=True) == "ON:1.0A/OFF:0.0A"
    assert format_heater_amp(0, is_vcb=True) == "ON:0.0A/OFF:0.0A"
    assert format_heater_amp("0", is_vcb=True) == "ON:0.0A/OFF:0.0A"
    assert format_heater_amp("0.0A", is_vcb=True) == "ON:0.0A/OFF:0.0A"
    assert format_heater_amp(Decimal("0.55"), is_vcb=True) == "ON:0.6A/OFF:0.0A"

    # Explicit VCB switchgear_type
    assert format_heater_amp("0.5A", switchgear_type="VCB") == "ON:0.5A/OFF:0.0A"
    assert format_heater_amp("0.55", switchgear_type="VCB") == "ON:0.6A/OFF:0.0A"
    assert format_heater_amp("1", switchgear_type="AIS VCB") == "ON:1.0A/OFF:0.0A"
    assert format_heater_amp("0", switchgear_type="vcb") == "ON:0.0A/OFF:0.0A"

    # 2. Non-VCB switchgear or unknown/omitted switchgear type always outputs '-'
    assert format_heater_amp("0.5A", switchgear_type="RMU SF6") == "-"
    assert format_heater_amp("0.5A", switchgear_type="RMU OIL") == "-"
    assert format_heater_amp("0.5A", switchgear_type="MRMU") == "-"
    assert format_heater_amp("0.5A", switchgear_type="OCB") == "-"
    assert format_heater_amp("0.5A", switchgear_type="OTHER") == "-"
    assert format_heater_amp(1.0, switchgear_type="RMU SF6") == "-"
    assert format_heater_amp("0.5A", is_vcb=False) == "-"
    assert format_heater_amp("0.5A", switchgear_type=None) == "-"
    assert format_heater_amp("0.5A") == "-"

    # 3. Empty, blank, '-', 'N/A', or non-numeric outputs '-' even on VCB
    assert format_heater_amp(None, is_vcb=True) == "-"
    assert format_heater_amp("", is_vcb=True) == "-"
    assert format_heater_amp("   ", is_vcb=True) == "-"
    assert format_heater_amp("-", is_vcb=True) == "-"
    assert format_heater_amp("--", is_vcb=True) == "-"
    assert format_heater_amp("N/A", is_vcb=True) == "-"
    assert format_heater_amp("n/a", is_vcb=True) == "-"
    assert format_heater_amp("None", is_vcb=True) == "-"
    assert format_heater_amp("null", is_vcb=True) == "-"
    assert format_heater_amp("NOT WORKING", is_vcb=True) == "-"
    assert format_heater_amp("DAMAGED", is_vcb=True) == "-"
    assert format_heater_amp(float("nan"), is_vcb=True) == "-"
    assert format_heater_amp(True, is_vcb=True) == "-"
    assert format_heater_amp(False, is_vcb=True) == "-"


def test_format_busbar_position() -> None:
    """Verify format_busbar_position presents busbar position per domain rules."""
    # 1. Transition panels -> '-' regardless of switchgear type
    assert format_busbar_position("TRANSITION PANEL", is_vcb=True) == "-"
    assert format_busbar_position("TRANSITION", is_vcb=True) == "-"
    assert format_busbar_position("transition panel", is_vcb=True) == "-"
    assert format_busbar_position("Panel Transition", is_vcb=True) == "-"
    assert format_busbar_position("TRANSITION PANEL", switchgear_type="VCB") == "-"
    assert format_busbar_position("TRANSITION PANEL", switchgear_type="RMU SF6") == "-"
    assert format_busbar_position("TRANSITION PANEL", is_vcb=False) == "-"
    assert format_busbar_position("TRANSITION PANEL") == "-"

    # 2. VCB switchgear (non-transition) -> 'MAIN'
    assert format_busbar_position("INCOMING 1", is_vcb=True) == "MAIN"
    assert format_busbar_position("PANEL 1", is_vcb=True) == "MAIN"
    assert format_busbar_position("INCOMING 1", switchgear_type="VCB") == "MAIN"
    assert format_busbar_position("PANEL 1", switchgear_type="VCB") == "MAIN"
    assert format_busbar_position("TX 1", switchgear_type="AIS VCB") == "MAIN"
    assert format_busbar_position("BUS COUPLER", switchgear_type="vcb") == "MAIN"
    assert format_busbar_position("", is_vcb=True) == "MAIN"
    assert format_busbar_position(None, is_vcb=True) == "MAIN"

    # 3. Non-VCB switchgear (RMU, MRMU, OIL, OCB, etc.) -> '-'
    assert format_busbar_position("PANEL 1", switchgear_type="RMU SF6") == "-"
    assert format_busbar_position("PANEL 1", switchgear_type="RMU OIL") == "-"
    assert format_busbar_position("PANEL 1", switchgear_type="MRMU") == "-"
    assert format_busbar_position("PANEL 1", switchgear_type="OCB") == "-"
    assert format_busbar_position("PANEL 1", switchgear_type="OTHER") == "-"
    assert format_busbar_position("PANEL 1", is_vcb=False) == "-"
    assert format_busbar_position("PANEL 1", switchgear_type="") == "-"
    assert format_busbar_position("PANEL 1", switchgear_type=None) == "-"
    assert format_busbar_position("PANEL 1") == "-"




