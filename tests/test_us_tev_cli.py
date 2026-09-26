"""CLI integration unit tests for US+TEV survey graph utility action (Ticket #74)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.utility_actions import UTILITY_ACTIONS, _load_generate_us_tev_graphs_runner
from src.workflows.us_tev_graphs import (
    BrowserPrerequisiteError,
    UsTevCandidate,
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
    candidate = candidates[0]
    assert isinstance(candidate, UsTevCandidate)
    assert candidate.package.data.substation_name_erms == "PE TEST 1"
    assert candidate.raw_data_dir == raw_dir_1
    assert candidate.survey_dir == survey_1
    assert candidate.output_dir == raw_dir_1 / "US+TEV" / "graphs"


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
    candidate = UsTevCandidate(
        package=pkg,
        raw_data_dir=raw_dir,
        survey_dir=survey_dir,
        output_dir=raw_dir / "US+TEV" / "graphs",
    )
    candidates = [candidate]

    with patch("src.workflows.us_tev_graphs.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = candidates

        selected = select_us_tev_substations_interactive(candidates)

        assert selected == candidates
        options_arg = mock_select_multiple.call_args[0][1]
        assert len(options_arg) == 1
        assert options_arg[0].title == "[20-09-2026] 316-PE-GALI"
        assert options_arg[0].value == candidate
        assert options_arg[0].checked is True


def test_run_generate_us_tev_graphs_action_browser_missing():
    """Verify action handles BrowserPrerequisiteError gracefully without crashing."""
    env = MagicMock()
    prpd_cfg = MagicMock()
    prpd_cfg.mode = "option_c"
    env.get_prpd_config.return_value = prpd_cfg

    cand = UsTevCandidate(
        package=MagicMock(),
        raw_data_dir=Path("raw"),
        survey_dir=Path("survey"),
        output_dir=Path("raw/US+TEV/graphs"),
    )

    with patch("src.workflows.us_tev_graphs.select_one", return_value="browse_dates"), \
         patch("src.workflows.us_tev_graphs.select_pahang_inspection_dates_interactive", return_value=(Path("10-08-2026"),)), \
         patch("src.workflows.us_tev_graphs.discover_us_tev_candidate_substations", return_value=[cand]), \
         patch("src.workflows.us_tev_graphs.select_us_tev_substations_interactive", return_value=[cand]), \
         patch("src.workflows.us_tev_graphs.find_chrome_executable", side_effect=FileNotFoundError("No Chrome")):

        res = run_generate_us_tev_graphs_action(env)
        assert res is None


def test_run_generate_us_tev_graphs_action_date_selection_loop_back():
    """Verify loop-back resilience when date browsing or range input is cancelled."""
    env = MagicMock()

    # Sequence of mode selections:
    # 1. First selects "browse_dates" -> returns empty tuple () (cancels date browser)
    # 2. Loop backs to mode prompt, selects "enter_dates" -> returns empty list [] (cancels range input)
    # 3. Loop backs to mode prompt, selects "__cancel__" -> cleanly exits
    with patch("src.workflows.us_tev_graphs.select_one", side_effect=["browse_dates", "enter_dates", "__cancel__"]) as mock_mode, \
         patch("src.workflows.us_tev_graphs.select_pahang_inspection_dates_interactive", return_value=()), \
         patch("src.workflows.us_tev_graphs.prompt_target_inspection_dates_with_ranges", return_value=[]):

        res = run_generate_us_tev_graphs_action(env)
        assert res is None
        assert mock_mode.call_count == 3


def test_run_generate_us_tev_graphs_action_date_selection_loop_back_then_succeeds():
    """Verify cancellation in date browser loops back to date mode, then user enters valid dates and completes."""
    env = MagicMock()
    prpd_cfg = MagicMock()
    prpd_cfg.mode = "option_b"
    env.get_prpd_config.return_value = prpd_cfg

    cand = UsTevCandidate(
        package=MagicMock(),
        raw_data_dir=Path("raw"),
        survey_dir=Path("survey"),
        output_dir=Path("raw/US+TEV/graphs"),
    )

    # 1. First selects "browse_dates" -> cancelled ()
    # 2. Loop backs, selects "enter_dates" -> provides ["10-08-2026"]
    with patch("src.workflows.us_tev_graphs.select_one", side_effect=["browse_dates", "enter_dates"]), \
         patch("src.workflows.us_tev_graphs.select_pahang_inspection_dates_interactive", return_value=()), \
         patch("src.workflows.us_tev_graphs.prompt_target_inspection_dates_with_ranges", return_value=["10-08-2026"]), \
         patch("src.workflows.us_tev_graphs.discover_us_tev_candidate_substations", return_value=[cand]), \
         patch("src.workflows.us_tev_graphs.select_us_tev_substations_interactive", return_value=[cand]), \
         patch("src.workflows.us_tev_graphs.UsTevGraphWorkflow.run_batch") as mock_run_batch:

        mock_run_batch.return_value = MagicMock(total_substations=1, total_graphs=2, elapsed_time=1.0, errors=[])
        res = run_generate_us_tev_graphs_action(env)

        assert res is not None
        assert mock_run_batch.called
        passed_batch = mock_run_batch.call_args[0][0]
        assert len(passed_batch) == 1
        assert passed_batch[0] == (cand.package, cand.survey_dir, cand.output_dir)
