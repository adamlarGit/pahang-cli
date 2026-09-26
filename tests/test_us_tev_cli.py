"""CLI integration unit tests for US+TEV survey graph utility action (Ticket #74)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.utility_actions import UTILITY_ACTIONS, _load_generate_us_tev_graphs_runner
from src.workflows.us_tev_graphs import (
    BrowserPrerequisiteError,
    discover_us_tev_candidate_substations,
    run_generate_us_tev_graphs_action,
    select_us_tev_substations_interactive,
)


def test_utility_action_menu_registration():
    """Verify 'Generate US+TEV survey graphs' is registered at Position 9 (index 8)."""
    assert len(UTILITY_ACTIONS) >= 9
    action_idx_8 = UTILITY_ACTIONS[8]
    assert action_idx_8.label == "Generate US+TEV survey graphs"

    # Immediately follows "Rename FLIR raw files numbering" at index 7
    assert UTILITY_ACTIONS[7].label == "Rename FLIR raw files numbering"


def test_runner_factory_contract():
    """Verify _load_generate_us_tev_graphs_runner adheres to zero-arg callable contract."""
    runner = _load_generate_us_tev_graphs_runner()
    assert callable(runner)


def test_discover_us_tev_candidate_substations(tmp_path: Path):
    """Verify only packages with valid RAW DATA/US+TEV survey dirs are discovered."""
    env = MagicMock()
    storage = MagicMock()
    env.storage = storage

    pkg1 = SubstationTestsheetPackage(
        testsheet_path=Path("fake1.xlsx"),
        unsorted_raw_data_dir=Path("fake1"),
        station="KUANTAN",
        month="01. JANUARY",
        date_str="01-01-2026",
        substation_number=1,
        data=TestsheetData(
            substation_number=1,
            substation_name_erms="PE TEST 1",
        ),
    )
    pkg2 = SubstationTestsheetPackage(
        testsheet_path=Path("fake2.xlsx"),
        unsorted_raw_data_dir=Path("fake2"),
        station="KUANTAN",
        month="01. JANUARY",
        date_str="01-01-2026",
        substation_number=2,
        data=TestsheetData(
            substation_number=2,
            substation_name_erms="PE TEST 2",
        ),
    )

    raw_dir_1 = tmp_path / "RAW_1"
    survey_1 = raw_dir_1 / "RAW DATA" / "US+TEV"
    survey_1.mkdir(parents=True, exist_ok=True)
    # Put a survey indicator
    (survey_1 / "survey_summary.js").write_text("var survey_summary = {};", encoding="utf-8")

    raw_dir_2 = tmp_path / "RAW_2"
    raw_dir_2.mkdir(parents=True, exist_ok=True)  # No US+TEV directory!

    def mock_get_raw(station, month, date_str, sub_no):
        if sub_no == 1:
            return raw_dir_1
        return raw_dir_2

    storage.get_substation_raw_data_dir.side_effect = mock_get_raw

    with patch("src.workflows.us_tev_graphs.QuickReportExtractor") as mock_extractor_cls:
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [pkg1, pkg2]
        mock_extractor_cls.return_value = mock_extractor

        candidates = discover_us_tev_candidate_substations(env, ["01-01-2026"])

    assert len(candidates) == 1
    found_pkg, found_raw, found_survey = candidates[0]
    assert found_pkg.data.substation_name_erms == "PE TEST 1"
    assert found_raw == raw_dir_1
    assert found_survey == survey_1


def test_select_us_tev_substations_interactive():
    """Verify single merged checklist prefixes date tag and pre-checks candidates."""
    pkg = SubstationTestsheetPackage(
        testsheet_path=Path("fake316.xlsx"),
        unsorted_raw_data_dir=Path("fake316"),
        station="KUANTAN",
        month="01. JANUARY",
        date_str="20-09-2026",
        substation_number=316,
        data=TestsheetData(
            substation_number=316,
            substation_name_erms="316-PE-GALI",
        ),
    )
    raw_dir = Path("/fake/raw")
    survey_dir = Path("/fake/survey")
    candidates = [(pkg, raw_dir, survey_dir)]

    with patch("src.workflows.us_tev_graphs.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = candidates

        selected = select_us_tev_substations_interactive(candidates)

        assert selected == candidates
        options_arg = mock_select_multiple.call_args[0][1]
        assert len(options_arg) == 1
        assert options_arg[0].title == "[20-09-26] 316-PE-GALI" or options_arg[0].title == "[20-09-2026] 316-PE-GALI"
        assert options_arg[0].checked is True


def test_run_generate_us_tev_graphs_action_browser_missing():
    """Verify action handles BrowserPrerequisiteError gracefully without crashing."""
    env = MagicMock()
    prpd_cfg = MagicMock()
    prpd_cfg.mode = "option_c"
    env.get_prpd_config.return_value = prpd_cfg

    with patch("src.workflows.us_tev_graphs.select_one", return_value="browse_dates"), \
         patch("src.workflows.us_tev_graphs.select_pahang_inspection_dates_interactive", return_value=(Path("10-08-2026"),)), \
         patch("src.workflows.us_tev_graphs.discover_us_tev_candidate_substations", return_value=[(MagicMock(), Path("raw"), Path("survey"))]), \
         patch("src.workflows.us_tev_graphs.select_us_tev_substations_interactive", return_value=[(MagicMock(), Path("raw"), Path("survey"))]), \
         patch("src.workflows.us_tev_graphs.find_chrome_executable", side_effect=FileNotFoundError("No Chrome")):

        res = run_generate_us_tev_graphs_action(env)
        assert res is None
