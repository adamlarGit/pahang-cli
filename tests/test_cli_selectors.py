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

