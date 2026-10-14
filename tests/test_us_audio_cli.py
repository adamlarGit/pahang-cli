"""CLI integration unit tests for ultrasound audio workflow and menu action (Ticket #087)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.utility_actions import UTILITY_ACTIONS, _load_generate_us_audio_runner
from src.workflows.us_audio import (
    UsAudioCandidate,
    discover_us_audio_candidate_substations,
    run_generate_us_audio_action,
    select_us_audio_substations_interactive,
)


def test_utility_action_menu_registration():
    """Verify 'Generate US 16-bit audio & embed sounds into PDFs' is registered at Position 10 (index 9)."""
    assert len(UTILITY_ACTIONS) >= 10
    action_idx_9 = UTILITY_ACTIONS[9]
    assert action_idx_9.label == "Generate US 16-bit audio & embed sounds into PDFs"

    # Immediately follows "Generate US+TEV survey graphs" at index 8
    assert UTILITY_ACTIONS[8].label == "Generate US+TEV survey graphs"


def test_runner_factory_contract():
    """Verify _load_generate_us_audio_runner adheres to zero-arg callable contract and dispatches to action."""
    runner = _load_generate_us_audio_runner()
    assert callable(runner)

    with patch("src.workflows.us_audio.run_generate_us_audio_action") as mock_action, \
         patch("src.project.environment.get_or_create_utility_environment") as mock_env:
        mock_env.return_value = MagicMock()
        mock_action.return_value = MagicMock()
        res = runner()
        assert res == mock_action.return_value
        mock_action.assert_called_once_with(mock_env.return_value)


def test_discover_us_audio_candidate_substations(tmp_path: Path):
    """Verify discovery filters strictly to substations with US+TEV surveys and resolves deliverable PDFs."""
    env = MagicMock()
    storage = MagicMock()
    env.storage = storage

    full_report_dir = tmp_path / "FULL REPORT"
    quick_report_dir = tmp_path / "QUICK REPORT"
    env.get_full_report_dir.return_value = full_report_dir
    env.get_quick_report_dir.return_value = quick_report_dir

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

    # Substation 1: has valid US+TEV survey folder AND deliverable PDFs
    raw_dir_1 = tmp_path / "RAW_1"
    survey_1 = raw_dir_1 / "RAW DATA" / "US+TEV"
    survey_1.mkdir(parents=True, exist_ok=True)
    (survey_1 / "survey_summary.js").write_text("var survey_summary = {};", encoding="utf-8")

    full_pdf_1 = full_report_dir / "KUANTAN" / "01. JANUARY" / "01-01-2026" / "001. PE TEST 1.pdf"
    full_pdf_1.parent.mkdir(parents=True, exist_ok=True)
    full_pdf_1.write_bytes(b"%PDF-1.4 mock full")

    quick_pdf_1 = quick_report_dir / "KUANTAN" / "01. JANUARY" / "01-01-2026" / "001. PE TEST 1.pdf"
    quick_pdf_1.parent.mkdir(parents=True, exist_ok=True)
    quick_pdf_1.write_bytes(b"%PDF-1.4 mock quick")

    # Substation 2: no US+TEV survey folder
    raw_dir_2 = tmp_path / "RAW_2"
    raw_dir_2.mkdir(parents=True, exist_ok=True)

    def mock_get_raw(station, month, date_str, sub_no):
        if sub_no == 1:
            return raw_dir_1
        return raw_dir_2

    storage.get_substation_raw_data_dir.side_effect = mock_get_raw

    with patch("src.workflows.us_audio.QuickReportExtractor") as mock_extractor_cls:
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [pkg1, pkg2]
        mock_extractor_cls.return_value = mock_extractor

        candidates = discover_us_audio_candidate_substations(env, ["01-01-2026"])

    assert len(candidates) == 1
    cand = candidates[0]
    assert isinstance(cand, UsAudioCandidate)
    assert cand.package == pkg1
    assert cand.raw_data_dir == raw_dir_1
    assert cand.survey_dir == survey_1
    assert cand.sounds_output_dir == raw_dir_1 / "RAW DATA" / "US+TEV" / "sounds"
    assert cand.full_report_pdf == full_pdf_1
    assert cand.quick_report_pdf == quick_pdf_1


def test_select_us_audio_substations_interactive(tmp_path: Path):
    """Verify checklist label formatting with date prefix and [PDF READY] / [NO PDF] tags."""
    fake_pdf = tmp_path / "report.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock")

    pkg1 = SubstationTestsheetPackage(
        testsheet_path=Path("fake1.xlsx"),
        unsorted_raw_data_dir=Path("fake1"),
        station="KUANTAN",
        month="01. JANUARY",
        date_str="20-09-2026",
        substation_number=316,
        data=TestsheetData(
            substation_number=316,
            substation_name_erms="316-PE-GALI",
        ),
    )
    cand_pdf_ready = UsAudioCandidate(
        package=pkg1,
        raw_data_dir=Path("/raw/1"),
        survey_dir=Path("/raw/1/survey"),
        full_report_pdf=fake_pdf,
        quick_report_pdf=None,
    )

    pkg2 = SubstationTestsheetPackage(
        testsheet_path=Path("fake2.xlsx"),
        unsorted_raw_data_dir=Path("fake2"),
        station="KUANTAN",
        month="01. JANUARY",
        date_str="21-09-2026",
        substation_number=317,
        data=TestsheetData(
            substation_number=317,
            substation_name_erms="317-PE-SUNGAI",
        ),
    )
    cand_no_pdf = UsAudioCandidate(
        package=pkg2,
        raw_data_dir=Path("/raw/2"),
        survey_dir=Path("/raw/2/survey"),
        full_report_pdf=None,
        quick_report_pdf=None,
    )

    candidates = [cand_pdf_ready, cand_no_pdf]

    with patch("src.workflows.us_audio.select_multiple") as mock_select_multiple:
        mock_select_multiple.return_value = candidates

        selected = select_us_audio_substations_interactive(candidates)

        assert selected == candidates
        options_arg = mock_select_multiple.call_args[0][1]
        assert len(options_arg) == 2

        assert options_arg[0].title == "[20-09-2026] 316-PE-GALI [PDF READY]"
        assert options_arg[0].value == cand_pdf_ready
        assert options_arg[0].checked is True

        assert options_arg[1].title == "[21-09-2026] 317-PE-SUNGAI [NO PDF]"
        assert options_arg[1].value == cand_no_pdf
        assert options_arg[1].checked is True


def test_select_us_audio_substations_interactive_zero_selection_loop_back():
    """Verify zero-selection loops back safely until selection made or cancelled."""
    cand = UsAudioCandidate(
        package=MagicMock(date_str="01-01-2026", substation_name="PE TEST"),
        full_report_pdf=None,
    )

    # First call returns empty list [] (zero selection), second call returns [cand]
    with patch("src.workflows.us_audio.select_multiple", side_effect=[[], [cand]]) as mock_select:
        selected = select_us_audio_substations_interactive([cand])
        assert selected == [cand]
        assert mock_select.call_count == 2


def test_run_generate_us_audio_action_missing_pdf_notice_fallback_to_export():
    """Verify Mode 1 displays notice when zero deliverable PDFs exist and allows switching to Mode 2."""
    env = MagicMock()

    cand_no_pdf = UsAudioCandidate(
        package=MagicMock(date_str="01-01-2026", substation_name="PE TEST"),
        survey_dir=Path("survey"),
        full_report_pdf=None,
        quick_report_pdf=None,
    )

    # User picks Mode 1 ("embed_pdf"), selects browse_dates, then gets missing PDF notice and switches to export_wav
    with patch("src.workflows.us_audio.select_one", side_effect=["embed_pdf", "browse_dates", "export_wav"]), \
         patch("src.workflows.us_audio.select_pahang_inspection_dates_interactive", return_value=(Path("01-01-2026"),)), \
         patch("src.workflows.us_audio.discover_us_audio_candidate_substations", return_value=[cand_no_pdf]), \
         patch("src.workflows.us_audio.select_us_audio_substations_interactive", return_value=[cand_no_pdf]), \
         patch("src.workflows.us_audio.UsAudioWorkflow.run_batch") as mock_run_batch:

        mock_run_batch.return_value = MagicMock(
            total_substations=1,
            total_wavs_exported=2,
            total_sounds_embedded=0,
            elapsed_time=1.2,
            errors=[],
        )

        res = run_generate_us_audio_action(env)

        assert res is not None
        assert mock_run_batch.called


def test_run_generate_us_audio_action_missing_pdf_notice_cancelled():
    """Verify Mode 1 displays notice when zero deliverable PDFs exist and exits cleanly on cancel."""
    env = MagicMock()

    cand_no_pdf = UsAudioCandidate(
        package=MagicMock(date_str="01-01-2026", substation_name="PE TEST"),
        survey_dir=Path("survey"),
        full_report_pdf=None,
        quick_report_pdf=None,
    )

    # User picks Mode 1 ("embed_pdf"), selects browse_dates, then cancels at the fallback prompt
    with patch("src.workflows.us_audio.select_one", side_effect=["embed_pdf", "browse_dates", "__cancel__"]), \
         patch("src.workflows.us_audio.select_pahang_inspection_dates_interactive", return_value=(Path("01-01-2026"),)), \
         patch("src.workflows.us_audio.discover_us_audio_candidate_substations", return_value=[cand_no_pdf]), \
         patch("src.workflows.us_audio.UsAudioWorkflow.run_batch") as mock_run_batch:

        res = run_generate_us_audio_action(env)

        assert res is None
        assert not mock_run_batch.called


def test_run_generate_us_audio_action_both_mode_success(tmp_path: Path):
    """Verify 'both' mode execution runs batch with progress telemetry and returns summary."""
    env = MagicMock()

    full_pdf = tmp_path / "full.pdf"
    full_pdf.write_bytes(b"%PDF mock full")
    quick_pdf = tmp_path / "quick.pdf"
    quick_pdf.write_bytes(b"%PDF mock quick")

    cand = UsAudioCandidate(
        package=MagicMock(date_str="01-01-2026", substation_name="PE TEST"),
        survey_dir=Path("survey"),
        full_report_pdf=full_pdf,
        quick_report_pdf=quick_pdf,
    )

    with patch("src.workflows.us_audio.select_one", side_effect=["both", "enter_dates"]), \
         patch("src.workflows.us_audio.prompt_target_inspection_dates_with_ranges", return_value=["01-01-2026"]), \
         patch("src.workflows.us_audio.discover_us_audio_candidate_substations", return_value=[cand]), \
         patch("src.workflows.us_audio.select_us_audio_substations_interactive", return_value=[cand]), \
         patch("src.workflows.us_audio.UsAudioWorkflow.run_batch") as mock_run_batch:

        mock_run_batch.return_value = MagicMock(
            total_substations=1,
            total_wavs_exported=3,
            total_sounds_embedded=3,
            elapsed_time=2.5,
            errors=[],
        )

        res = run_generate_us_audio_action(env)

        assert res is not None
        assert mock_run_batch.called
        assert res.total_wavs_exported == 3
        assert res.total_sounds_embedded == 3


def test_run_generate_us_audio_action_mode_cancel():
    """Verify selecting Cancel at mode prompt exits cleanly."""
    env = MagicMock()
    with patch("src.workflows.us_audio.select_one", return_value="__cancel__"):
        res = run_generate_us_audio_action(env)
        assert res is None


def test_run_generate_us_audio_action_date_mode_cancel():
    """Verify selecting Cancel at date prompt exits cleanly."""
    env = MagicMock()
    with patch("src.workflows.us_audio.select_one", side_effect=["export_wav", "__cancel__"]):
        res = run_generate_us_audio_action(env)
        assert res is None


def test_run_generate_us_audio_action_no_candidates():
    """Verify action handles zero candidates found without crashing."""
    env = MagicMock()
    with patch("src.workflows.us_audio.select_one", side_effect=["export_wav", "enter_dates"]), \
         patch("src.workflows.us_audio.prompt_target_inspection_dates_with_ranges", return_value=["01-01-2026"]), \
         patch("src.workflows.us_audio.discover_us_audio_candidate_substations", return_value=[]):

        res = run_generate_us_audio_action(env)
        assert res is None


def test_run_generate_us_audio_action_substations_cancelled():
    """Verify action handles substation checklist cancellation gracefully."""
    env = MagicMock()
    cand = UsAudioCandidate(package=MagicMock())

    with patch("src.workflows.us_audio.select_one", side_effect=["export_wav", "enter_dates"]), \
         patch("src.workflows.us_audio.prompt_target_inspection_dates_with_ranges", return_value=["01-01-2026"]), \
         patch("src.workflows.us_audio.discover_us_audio_candidate_substations", return_value=[cand]), \
         patch("src.workflows.us_audio.select_us_audio_substations_interactive", return_value=[]):

        res = run_generate_us_audio_action(env)
        assert res is None


def test_select_us_audio_substations_interactive_cancel_returns_empty():
    """Verify select_multiple returning None results in empty list."""
    cand = UsAudioCandidate(package=MagicMock(date_str="01-01-2026", substation_name="PE TEST"))
    with patch("src.workflows.us_audio.select_multiple", return_value=None):
        selected = select_us_audio_substations_interactive([cand])
        assert selected == []


def test_select_us_audio_substations_interactive_empty_input():
    """Verify empty candidates input returns empty list immediately."""
    assert select_us_audio_substations_interactive([]) == []
