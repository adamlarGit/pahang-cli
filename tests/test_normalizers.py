"""Unit tests for domain normalizers in src/core/normalizers.py."""

from __future__ import annotations

from datetime import date, datetime
import pytest

from src.core.normalizers import (
    extract_background_temperature,
    format_date_cbm,
    format_date_front_page,
    format_humidity_str,
    format_iso8601,
    format_month_folder, 
    format_testsheet_time,
    normalize_date_str,
    normalize_fl_erms,
    normalize_for_csv,
    normalize_for_excel,
    normalize_for_report,
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
    from datetime import time
    assert format_testsheet_time(None) == "-"
    assert format_testsheet_time("") == "-"
    assert format_testsheet_time("-") == "-"
    assert format_testsheet_time("1430") == "02:30 PM"
    assert format_testsheet_time(1430) == "02:30 PM"
    assert format_testsheet_time("0915") == "09:15 AM"
    assert format_testsheet_time(915) == "09:15 AM"
    assert format_testsheet_time("14:30") == "02:30 PM"
    assert format_testsheet_time("9:15") == "09:15 AM"
    assert format_testsheet_time(time(14, 30)) == "02:30 PM"
    assert format_testsheet_time("invalid") == "-"


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
    assert parse_background_temp(23) == "23 °C"
    assert parse_background_temp("invalid") == "-"
    assert parse_background_temp(float("nan")) == "-"


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
