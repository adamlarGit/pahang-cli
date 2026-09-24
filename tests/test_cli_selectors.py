"""Tests for CLI selector shortcut assignment and multi-digit option formatting."""

import unittest

import pytest
from pathlib import Path
from unittest.mock import patch
from src.cli_selectors import (
    SelectOption,
    _iter_directory_children,
    _with_shortcuts,
    is_pahang_date_folder,
    prompt_directory_path,
    select_substations_interactive,
)


class TestCliSelectors(unittest.TestCase):
    def test_with_shortcuts_sequential_numbering(self) -> None:
        options = [SelectOption(f"Option {i}", i) for i in range(1, 12)]
        with_sc = _with_shortcuts(options)

        self.assertEqual(len(with_sc), 11)
        self.assertEqual(with_sc[0].shortcut_key, "1")
        self.assertEqual(with_sc[0].title, "1) Option 1")
        self.assertEqual(with_sc[8].shortcut_key, "9")
        self.assertEqual(with_sc[8].title, "9) Option 9")
        self.assertEqual(with_sc[9].shortcut_key, "10")
        self.assertEqual(with_sc[9].title, "10) Option 10")
        self.assertEqual(with_sc[10].shortcut_key, "11")
        self.assertEqual(with_sc[10].title, "11) Option 11")

    def test_with_shortcuts_preserves_explicit_cancel(self) -> None:
        options = [SelectOption(f"Option {i}", i) for i in range(1, 11)]
        options.append(SelectOption("Cancel", "__cancel__", shortcut_key="c"))

        with_sc = _with_shortcuts(options)
        self.assertEqual(with_sc[9].shortcut_key, "10")
        self.assertEqual(with_sc[9].title, "10) Option 10")
        self.assertEqual(with_sc[10].shortcut_key, "c")
        self.assertEqual(with_sc[10].title, "[C] Cancel")


def test_is_pahang_date_folder(tmp_path: Path) -> None:
    valid_date_dir = tmp_path / "01-05-2026"
    valid_date_dir.mkdir()
    assert is_pahang_date_folder(valid_date_dir) is True

    invalid_dir = tmp_path / "RAUB"
    invalid_dir.mkdir()
    assert is_pahang_date_folder(invalid_dir) is False

    file_path = tmp_path / "01-05-2026.txt"
    file_path.touch()
    assert is_pahang_date_folder(file_path) is False


def test_iter_directory_children_sorts_dates_descending(tmp_path: Path) -> None:
    d1 = tmp_path / "01-05-2026"
    d2 = tmp_path / "15-05-2026"
    d3 = tmp_path / "09-05-2026"
    for d in (d1, d2, d3):
        d.mkdir()

    children = _iter_directory_children(tmp_path)
    names = [c.name for c in children]
    assert names == ["15-05-2026", "09-05-2026", "01-05-2026"]


def test_prompt_directory_path_valid(tmp_path: Path) -> None:
    target = tmp_path / "my_dir"
    target.mkdir()

    with patch("builtins.input", return_value=str(target)):
        result = prompt_directory_path("Enter dir")
        assert result == target


def test_prompt_directory_path_default(tmp_path: Path) -> None:
    with patch("builtins.input", return_value=""):
        result = prompt_directory_path("Enter dir", default=tmp_path)
        assert result == tmp_path


def test_select_substations_interactive_empty() -> None:
    assert select_substations_interactive([]) == []


def test_select_substations_interactive_prechecks_ready_telemetry() -> None:
    from types import SimpleNamespace

    item1 = SimpleNamespace(substation_name="TALAPIA", is_ready=True)
    item2 = SimpleNamespace(substation_name="BAD_STATION", is_ready=False)

    with patch("src.cli_selectors.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = [item1]
        result = select_substations_interactive([item1, item2])
        assert result == [item1]

        mock_select_multiple.assert_called_once()
        title, options = mock_select_multiple.call_args[0]
        assert "Select substations" in title
        assert len(options) == 2
        assert options[0].title == "TALAPIA [READY]"
        assert options[0].checked is True
        assert options[0].value == item1

        assert options[1].title == "BAD_STATION [NOT READY]"
        assert options[1].checked is False
        assert options[1].value == item2


def test_select_substations_interactive_strings_prechecked() -> None:
    with patch("src.cli_selectors.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = ["STATION_A", "STATION_B"]
        result = select_substations_interactive(["STATION_A", "STATION_B"])
        assert result == ["STATION_A", "STATION_B"]

        _, options = mock_select_multiple.call_args[0]
        assert len(options) == 2
        assert options[0].title == "STATION_A"
        assert options[0].checked is True
        assert options[1].title == "STATION_B"
        assert options[1].checked is True


def test_select_substations_interactive_custom_callbacks() -> None:
    data = [{"id": 1, "name": "Item 1", "ok": True}, {"id": 2, "name": "Item 2", "ok": False}]
    with patch("src.cli_selectors.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = [1]
        result = select_substations_interactive(
            data,
            title="Custom Title",
            get_title=lambda x: f"Custom: {x['name']}",
            get_value=lambda x: x["id"],
            is_checked=lambda x: x["ok"],
        )
        assert result == [1]

        title, options = mock_select_multiple.call_args[0]
        assert title == "Custom Title"
        assert options[0].title == "Custom: Item 1"
        assert options[0].value == 1
        assert options[0].checked is True
        assert options[1].title == "Custom: Item 2"
        assert options[1].value == 2
        assert options[1].checked is False


if __name__ == "__main__":
    unittest.main()


from src.cli_selectors import (
    expand_date_range_syntax,
    select_pahang_inspection_dates_interactive,
    prompt_target_inspection_dates_with_ranges,
)
from src.project.environment import ProjectEnvironment
from unittest.mock import MagicMock

def test_expand_date_range_syntax_single():
    assert expand_date_range_syntax("01-05-2026") == ("01-05-2026",)

def test_expand_date_range_syntax_comma_separated():
    assert expand_date_range_syntax("01-05-2026, 03-05-2026, 02-05-2026") == ("01-05-2026", "02-05-2026", "03-05-2026")

def test_expand_date_range_syntax_range_dotdot():
    assert expand_date_range_syntax("01-05-2026..04-05-2026") == ("01-05-2026", "02-05-2026", "03-05-2026", "04-05-2026")

def test_expand_date_range_syntax_range_to():
    assert expand_date_range_syntax("01-05-2026 to 03-05-2026") == ("01-05-2026", "02-05-2026", "03-05-2026")

def test_expand_date_range_syntax_whitespace_tolerance():
    assert expand_date_range_syntax("  01-05-2026   TO    02-05-2026  , 04-05-2026 ") == ("01-05-2026", "02-05-2026", "04-05-2026")

def test_expand_date_range_syntax_inverted():
    with pytest.raises(ValueError):
        expand_date_range_syntax("05-05-2026..01-05-2026")

def test_select_pahang_inspection_dates_interactive_loop_back(tmp_path):
    env = MagicMock(spec=ProjectEnvironment)
    storage = MagicMock()
    env.storage = storage
    storage.get_testsheet_dir.return_value = tmp_path
    
    # Mock sequence: 
    # 1. select station -> "RAUB"
    # 2. select month -> "01. JANUARY"
    # 3. select_multiple -> None (simulating zero selection or cancel)
    # 4. select month -> None (simulating back)
    # 5. select station -> None (simulating cancel)
    with patch("src.cli_selectors.select_or_create_testsheet_station", side_effect=["RAUB", None]), \
         patch("src.cli_selectors.select_or_create_testsheet_month", side_effect=["01. JANUARY", None]), \
         patch("src.cli_selectors.select_multiple", return_value=None):
         
         month_dir = tmp_path / "RAUB" / "01. JANUARY"
         month_dir.mkdir(parents=True)
         (month_dir / "01-01-2026").mkdir()
         
         result = select_pahang_inspection_dates_interactive(env)
         assert result is None

def test_prompt_target_inspection_dates_with_ranges_partial(tmp_path):
    env = MagicMock(spec=ProjectEnvironment)
    storage = MagicMock()
    env.storage = storage
    storage.get_testsheet_dir.return_value = tmp_path
    
    # Create matching folder
    st_dir = tmp_path / "RAUB" / "01. JANUARY"
    st_dir.mkdir(parents=True)
    d1 = st_dir / "01-01-2026"
    d1.mkdir()
    
    with patch("builtins.input", side_effect=["01-01-2026, 02-01-2026"]), \
         patch("src.cli_selectors.confirm", return_value=True):
         
         result = prompt_target_inspection_dates_with_ranges(env)
         assert result == (d1,)


def test_expand_date_range_syntax_case_insensitive_to():
    assert expand_date_range_syntax("01-05-2026 To 03-05-2026") == ("01-05-2026", "02-05-2026", "03-05-2026")
    assert expand_date_range_syntax("01-05-2026 tO 02-05-2026") == ("01-05-2026", "02-05-2026")


def test_expand_date_range_syntax_malformed_endpoint():
    with pytest.raises(ValueError, match="Invalid date in range"):
        expand_date_range_syntax("01-05-2026..invalid")
    with pytest.raises(ValueError, match="Invalid date in range"):
        expand_date_range_syntax("invalid to 05-05-2026")


def test_prompt_target_inspection_dates_with_ranges_sorted_and_enumerates(tmp_path, capsys):
    env = MagicMock(spec=ProjectEnvironment)
    storage = MagicMock()
    env.storage = storage
    storage.get_testsheet_dir.return_value = tmp_path

    # Create matching folders in non-chronological order
    st_dir = tmp_path / "RAUB" / "05. MAY"
    st_dir.mkdir(parents=True)
    d2 = st_dir / "05-05-2026"
    d1 = st_dir / "02-05-2026"
    d2.mkdir()
    d1.mkdir()

    with patch("builtins.input", side_effect=["05-05-2026, 02-05-2026, 09-05-2026"]),          patch("src.cli_selectors.confirm", return_value=True):

        result = prompt_target_inspection_dates_with_ranges(env)
        # Verify chronological sorting
        assert result == (d1, d2)

    captured = capsys.readouterr().out
    assert "✓ Found 2 date folder(s): 02-05-2026, 05-05-2026" in captured
    assert "⚠️ Missing 1 date folder(s): 09-05-2026" in captured
