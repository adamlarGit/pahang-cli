"""Unit tests for domain normalizers in src/core/normalizers.py."""

from __future__ import annotations

from datetime import date, datetime
import pytest

from src.core.normalizers import (
    format_month_folder, 
    normalize_date_str,
    format_testsheet_time,
    format_humidity_str,
    parse_background_temp
)


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
