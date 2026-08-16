"""Unit tests for interactive station, month, and inspection date selectors (Ticket 089)."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.cli_selectors import (
    SelectOption,
    prompt_target_inspection_dates,
    select_or_create_testsheet_month,
    select_or_create_testsheet_station,
)


def _make_mock_env(testsheet_dir: Path) -> SimpleNamespace:
    """Create a mock ProjectEnvironment with storage returning testsheet_dir."""
    storage = MagicMock()
    storage.get_testsheet_dir.return_value = testsheet_dir
    return SimpleNamespace(storage=storage)


# ==============================================================================
# Tests for select_or_create_testsheet_station
# ==============================================================================


def test_select_existing_station(tmp_path: Path) -> None:
    """Verify selecting an existing station returns the station name in uppercase."""
    ts_dir = tmp_path / "TESTSHEET"
    ts_dir.mkdir()
    (ts_dir / "KUANTAN").mkdir()
    (ts_dir / "TEMERLOH").mkdir()
    (ts_dir / "PEKAN").mkdir()
    (ts_dir / "notes.txt").touch()  # Non-directory should be ignored

    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="TEMERLOH") as mock_select:
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result == "TEMERLOH"

        # Verify options passed to select_one: alphabetical stations + Add New + Cancel
        options = mock_select.call_args[0][1]
        option_values = [opt.value for opt in options]
        assert option_values == ["KUANTAN", "PEKAN", "TEMERLOH", "__new_station__", "__cancel__"]


def test_select_station_add_new(tmp_path: Path) -> None:
    """Verify adding a new station prompts operator and returns uppercase name."""
    ts_dir = tmp_path / "TESTSHEET"
    ts_dir.mkdir()
    (ts_dir / "KUANTAN").mkdir()

    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__new_station__"), \
         patch("builtins.input", return_value="  rompin  "):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result == "ROMPIN"


def test_select_station_add_new_empty_aborts(tmp_path: Path) -> None:
    """Verify empty station input returns None."""
    ts_dir = tmp_path / "TESTSHEET"
    ts_dir.mkdir()
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__new_station__"), \
         patch("builtins.input", return_value="   "):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result is None


def test_select_station_add_new_keyboard_interrupt(tmp_path: Path) -> None:
    """Verify KeyboardInterrupt during new station input returns None."""
    ts_dir = tmp_path / "TESTSHEET"
    ts_dir.mkdir()
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__new_station__"), \
         patch("builtins.input", side_effect=KeyboardInterrupt):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result is None


def test_select_station_cancel(tmp_path: Path) -> None:
    """Verify cancelling at station menu returns None."""
    ts_dir = tmp_path / "TESTSHEET"
    ts_dir.mkdir()
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__cancel__"):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result is None

    with patch("src.cli_selectors.select_one", return_value=None):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result is None


def test_select_station_nonexistent_testsheet_dir(tmp_path: Path) -> None:
    """Verify nonexistent testsheet directory handles gracefully with only Add New and Cancel."""
    ts_dir = tmp_path / "NONEXISTENT_TESTSHEET"
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__new_station__"), \
         patch("builtins.input", return_value="BERA"):
        result = select_or_create_testsheet_station(env)  # type: ignore[arg-type]
        assert result == "BERA"


# ==============================================================================
# Tests for select_or_create_testsheet_month
# ==============================================================================


def test_select_existing_month(tmp_path: Path) -> None:
    """Verify selecting an existing month folder returns the exact folder name."""
    ts_dir = tmp_path / "TESTSHEET"
    station_dir = ts_dir / "KUANTAN"
    station_dir.mkdir(parents=True)
    (station_dir / "01. AUGUST").mkdir()
    (station_dir / "02. SEPTEMBER").mkdir()
    (station_dir / "desktop.ini").touch()  # Non-directory should be ignored

    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="01. AUGUST") as mock_select:
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result == "01. AUGUST"

        options = mock_select.call_args[0][1]
        option_values = [opt.value for opt in options]
        assert option_values == ["01. AUGUST", "02. SEPTEMBER", "__new_month__", "__cancel__"]


def test_select_month_add_new_first_month(tmp_path: Path) -> None:
    """Verify adding the first month assigns sequential index '01.'."""
    ts_dir = tmp_path / "TESTSHEET"
    station_dir = ts_dir / "KUANTAN"
    station_dir.mkdir(parents=True)

    env = _make_mock_env(ts_dir)

    # First select_one chooses __new_month__, second select_one chooses MARCH
    with patch("src.cli_selectors.select_one", side_effect=["__new_month__", "MARCH"]) as mock_select:
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result == "01. MARCH"

        # Check second call had the 12 standard months + cancel
        assert mock_select.call_count == 2
        month_options = mock_select.call_args_list[1][0][1]
        assert len(month_options) == 13  # 12 months + cancel
        assert month_options[0].value == "JANUARY"
        assert month_options[11].value == "DECEMBER"
        assert month_options[12].value == "__cancel__"


def test_select_month_add_new_sequential_index(tmp_path: Path) -> None:
    """Verify adding month when 2 existing months are present assigns '03.'."""
    ts_dir = tmp_path / "TESTSHEET"
    station_dir = ts_dir / "KUANTAN"
    station_dir.mkdir(parents=True)
    (station_dir / "01. AUGUST").mkdir()
    (station_dir / "02. SEPTEMBER").mkdir()

    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", side_effect=["__new_month__", "OCTOBER"]):
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result == "03. OCTOBER"


def test_select_month_cancel_at_main_menu(tmp_path: Path) -> None:
    """Verify cancelling at month main menu returns None."""
    ts_dir = tmp_path / "TESTSHEET"
    station_dir = ts_dir / "KUANTAN"
    station_dir.mkdir(parents=True)
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", return_value="__cancel__"):
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result is None

    with patch("src.cli_selectors.select_one", return_value=None):
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result is None


def test_select_month_cancel_at_month_picker(tmp_path: Path) -> None:
    """Verify cancelling inside 12-month picker returns None."""
    ts_dir = tmp_path / "TESTSHEET"
    station_dir = ts_dir / "KUANTAN"
    station_dir.mkdir(parents=True)
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", side_effect=["__new_month__", "__cancel__"]):
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result is None

    with patch("src.cli_selectors.select_one", side_effect=["__new_month__", None]):
        result = select_or_create_testsheet_month(env, "KUANTAN")  # type: ignore[arg-type]
        assert result is None


def test_select_month_nonexistent_station_dir(tmp_path: Path) -> None:
    """Verify nonexistent station directory creates index '01.' gracefully."""
    ts_dir = tmp_path / "TESTSHEET"
    env = _make_mock_env(ts_dir)

    with patch("src.cli_selectors.select_one", side_effect=["__new_month__", "JANUARY"]):
        result = select_or_create_testsheet_month(env, "NEW_STATION")  # type: ignore[arg-type]
        assert result == "01. JANUARY"


# ==============================================================================
# Tests for prompt_target_inspection_dates
# ==============================================================================


def test_prompt_dates_default_explicit():
    """Verify pressing Enter with explicit default_date returns tuple of default date."""
    with patch("builtins.input", return_value=""):
        result = prompt_target_inspection_dates(default_date="15-08-2026")
        assert result == ("15-08-2026",)


def test_prompt_dates_default_today():
    """Verify pressing Enter with no default_date returns today's date formatted DD-MM-YYYY."""
    today_str = datetime.now().strftime("%d-%m-%Y")
    with patch("builtins.input", return_value=""):
        result = prompt_target_inspection_dates()
        assert result == (today_str,)


def test_prompt_dates_single_custom():
    """Verify single date input normalization."""
    with patch("builtins.input", return_value="12/08/2026"):
        result = prompt_target_inspection_dates()
        assert result == ("12-08-2026",)


def test_prompt_dates_multiple_comma_separated():
    """Verify comma-separated date inputs normalization with mixed formats and whitespace."""
    with patch("builtins.input", return_value=" 10-08-2026 , 11/08/2026, 2026-08-12 "):
        result = prompt_target_inspection_dates()
        assert result == ("10-08-2026", "11-08-2026", "12-08-2026")


def test_prompt_dates_cancel_letter_c():
    """Verify 'c' or 'C' cancels prompt returning None."""
    with patch("builtins.input", return_value="c"):
        assert prompt_target_inspection_dates() is None

    with patch("builtins.input", return_value="  C  "):
        assert prompt_target_inspection_dates() is None


def test_prompt_dates_cancel_word():
    """Verify 'cancel' or 'CANCEL' cancels prompt returning None."""
    with patch("builtins.input", return_value="cancel"):
        assert prompt_target_inspection_dates() is None

    with patch("builtins.input", return_value="CANCEL"):
        assert prompt_target_inspection_dates() is None


def test_prompt_dates_keyboard_interrupt():
    """Verify KeyboardInterrupt returns None."""
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        assert prompt_target_inspection_dates() is None
