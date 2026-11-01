"""Multi-date selection for Full Report generation (13) and post-processing (14).

Covers the MultiDateSelectionPolicy: shared selection menu, per-station Browse
mapping, typed dates across stations, Manual FL lookup, superseded exclusion,
date tags and empty-date warnings.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.project.environment import ProjectEnvironment
from src.project_workflow_actions import (
    generate_full_reports_action,
    postprocess_full_reports_action,
)
from src.testsheet.models import SubstationTestsheetPackage
from src.workflows.full_report import FullReportWorkflow
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingTelemetry,
    FullReportPostProcessingWorkflow,
)

MONTH = "05. MAY"


@pytest.fixture
def env(tmp_path: Path) -> MagicMock:
    e = MagicMock(spec=ProjectEnvironment)
    e.base_path = tmp_path
    e.get_full_report_dir.return_value = tmp_path / "FULL REPORT"
    e.get_testsheet_dir.return_value = tmp_path / "TESTSHEET"
    return e


def _fr_docx(env: MagicMock, station: str, date: str, name: str) -> Path:
    folder = env.get_full_report_dir() / station / MONTH / date
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_bytes(b"x")
    return p


def _ts_folder(env: MagicMock, station: str, date: str) -> Path:
    folder = env.get_testsheet_dir() / station / MONTH / date
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _run_14(env, selection_mode, selector_patch, workflow=None):
    """Drive action 14 up to the checklist; return (targets shown, get_title, printed)."""
    shown = {}

    def _capture(targets, **kwargs):
        shown["targets"] = list(targets)
        shown["get_title"] = kwargs["get_title"]
        return []

    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value=selection_mode), \
         patch(selector_patch[0], return_value=selector_patch[1]), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", side_effect=_capture):
        postprocess_full_reports_action(env, workflow=workflow)
    return shown


# --- 1. Shared selection menu ------------------------------------------------

def test_13_and_14_offer_the_same_selection_modes(env: MagicMock) -> None:
    menus = []

    def _spy(title, options, *a, **k):
        menus.append([(o.title, o.value) for o in options])
        return "__cancel__"

    with patch("src.project_workflow_actions.cli_selectors.select_one", side_effect=_spy):
        generate_full_reports_action(env)
        postprocess_full_reports_action(env)

    assert len(menus) == 2
    assert menus[0] == menus[1]
    assert [v for _, v in menus[0]] == ["manual", "browse_dates", "enter_dates", "__cancel__"]


# --- 2. Browse: only the ticked station's Full Reports -----------------------

def test_14_browse_processes_only_ticked_station_and_dates(env: MagicMock) -> None:
    _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    _fr_docx(env, "BENTONG", "02-05-2026", "002. BRAVO.docx")
    _fr_docx(env, "BENTONG", "03-05-2026", "003. NOT TICKED.docx")
    _fr_docx(env, "RAUB", "01-05-2026", "004. OTHER STATION.docx")
    ticked = (_ts_folder(env, "BENTONG", "01-05-2026"), _ts_folder(env, "BENTONG", "02-05-2026"))

    shown = _run_14(
        env, "browse_dates",
        ("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", ticked),
        workflow=FullReportPostProcessingWorkflow(converter=MagicMock()),
    )

    stems = sorted(t.stem for t in shown["targets"])
    assert stems == ["001. ALPHA", "002. BRAVO"]


# --- 3. Typed dates: every station that has the date -------------------------

def test_14_typed_dates_match_every_station(env: MagicMock) -> None:
    _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    _fr_docx(env, "RAUB", "01-05-2026", "004. OTHER STATION.docx")
    _fr_docx(env, "RAUB", "09-05-2026", "005. NOT TYPED.docx")
    typed = (_ts_folder(env, "BENTONG", "01-05-2026"), _ts_folder(env, "RAUB", "01-05-2026"))

    shown = _run_14(
        env, "enter_dates",
        ("src.project_workflow_actions.cli_selectors.prompt_target_inspection_dates_with_ranges", typed),
        workflow=FullReportPostProcessingWorkflow(converter=MagicMock()),
    )

    assert sorted(t.stem for t in shown["targets"]) == ["001. ALPHA", "004. OTHER STATION"]


# --- 4. Manual FL ------------------------------------------------------------

def _pkg(station: str, date: str, number: int) -> SubstationTestsheetPackage:
    return SubstationTestsheetPackage(
        testsheet_path=Path("x.xlsx"),
        unsorted_raw_data_dir=Path("raw"),
        station=station,
        month=MONTH,
        date_str=date,
        substation_number=number,
    )


def test_14_manual_fl_finds_all_parts_for_every_matching_date(env: MagicMock, capsys) -> None:
    parts = [
        _fr_docx(env, "BENTONG", "01-05-2026", f"157. PERPUSTAKAAN AWAM - Part {i:02d} - X.docx")
        for i in (1, 2, 3)
    ]
    again = _fr_docx(env, "BENTONG", "07-05-2026", "157. PERPUSTAKAAN AWAM.docx")
    _fr_docx(env, "BENTONG", "01-05-2026", "158. SOMEONE ELSE.docx")
    packages = [_pkg("BENTONG", "01-05-2026", 157), _pkg("BENTONG", "07-05-2026", 157)]

    shown = {}

    def _capture(targets, **kwargs):
        shown["targets"] = list(targets)
        return []

    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value="manual"), \
         patch("builtins.input", return_value="FL-157"), \
         patch.object(FullReportWorkflow, "_discover_packages", return_value=(packages, [], [])), \
         patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", side_effect=_capture):
        postprocess_full_reports_action(
            env, workflow=FullReportPostProcessingWorkflow(converter=MagicMock())
        )

    by_date = {t.date_str: t for t in shown["targets"]}
    assert set(by_date) == {"01-05-2026", "07-05-2026"}
    assert by_date["01-05-2026"].is_multipart
    assert set(by_date["01-05-2026"].part_docx_paths) == {p.resolve() for p in parts}
    assert by_date["07-05-2026"].docx_path == again.resolve()


# --- 5. Superseded parts never discovered ------------------------------------

def test_superseded_docx_is_never_discovered(env: MagicMock) -> None:
    live = _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    stale_dir = live.parent / "_superseded" / "20260501-101010"
    stale_dir.mkdir(parents=True)
    (stale_dir / "001. ALPHA.docx").write_bytes(b"old")
    wf = FullReportPostProcessingWorkflow(converter=MagicMock())

    for target in ([live.parent], live.parent, [live.parent.parent.parent.parent]):
        files, _, _ = wf._discover_docx_files(target, env)
        assert files == [live.resolve()], target


# --- 6. Date tags ------------------------------------------------------------

def test_14_checklist_titles_carry_date_tag(env: MagicMock) -> None:
    for i in (1, 2, 3):
        _fr_docx(env, "BENTONG", "01-05-2026", f"157. PERPUSTAKAAN AWAM - Part {i:02d} - X.docx")
    ticked = (_ts_folder(env, "BENTONG", "01-05-2026"),)

    shown = _run_14(
        env, "browse_dates",
        ("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", ticked),
        workflow=FullReportPostProcessingWorkflow(converter=MagicMock()),
    )

    title = shown["get_title"](shown["targets"][0])
    assert title.startswith("[01-05-2026] 157. PERPUSTAKAAN AWAM [3 docx parts -> 1 pdf deliverable] [")


def test_14_inspect_progress_lines_carry_date_tag(env: MagicMock) -> None:
    _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    lines: list[str] = []
    FullReportPostProcessingWorkflow(converter=MagicMock()).inspect(
        [env.get_full_report_dir() / "BENTONG" / MONTH / "01-05-2026"],
        env,
        progress_sink=lines.append,
    )
    assert any(l.startswith("[1/1] [01-05-2026] Inspecting testsheet PDF for 001. ALPHA") for l in lines)


def test_14_convert_progress_lines_carry_date_tag(env: MagicMock) -> None:
    docx = _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    ts_pdf = env.base_path / "ts.pdf"
    ts_pdf.write_bytes(b"%PDF")
    wf = FullReportPostProcessingWorkflow(converter=MagicMock())
    lines: list[str] = []
    ready = SimpleNamespace(
        is_ready=True, docx_path=docx.resolve(), testsheet_pdf_path=ts_pdf,
        target_pdf_path=docx.with_suffix(".pdf"), stem="001. ALPHA", date_str="01-05-2026",
        is_multipart=False, part_docx_paths=(), errors=(),
    )
    with patch.object(wf, "_inspect_single_report", return_value=ready), \
         patch.object(wf, "_compile_deliverable", return_value=()), \
         patch.object(wf, "_establish_batch_session") as sess:
        sess.return_value.__enter__.return_value = None
        sess.return_value.__exit__.return_value = False
        wf.process([docx], env, progress_sink=lines.append)
    assert any(l.startswith("[1/1] [01-05-2026] Converting and merging Full Report for 001. ALPHA") for l in lines)


# --- 7. Empty-date warnings --------------------------------------------------

def test_14_empty_date_warns_and_run_continues(env: MagicMock) -> None:
    ok = _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")
    empty = env.get_full_report_dir() / "BENTONG" / MONTH / "03-05-2026"  # never generated
    superseded_only = env.get_full_report_dir() / "BENTONG" / MONTH / "04-05-2026"
    (superseded_only / "_superseded" / "t").mkdir(parents=True)
    (superseded_only / "_superseded" / "t" / "009. OLD.docx").write_bytes(b"x")

    files, warnings, errors = FullReportPostProcessingWorkflow(converter=MagicMock())._discover_docx_files(
        [ok.parent, empty, superseded_only], env
    )

    assert files == [ok.resolve()]
    assert warnings == [
        "⚠️ 03-05-2026 (BENTONG): no Full Report documents — run Generate Full Reports first",
        "⚠️ 04-05-2026 (BENTONG): no Full Report documents — run Generate Full Reports first",
    ]


def test_14_preflight_prints_warning_line_with_icon(env: MagicMock, capsys) -> None:
    empty = _ts_folder(env, "BENTONG", "03-05-2026")
    _run_14(
        env, "browse_dates",
        ("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", (empty,)),
        workflow=FullReportPostProcessingWorkflow(converter=MagicMock()),
    )
    out = capsys.readouterr().out
    assert "03-05-2026 (BENTONG): no Full Report documents — run Generate Full Reports first" in out
    assert "No Full Report documents discovered for post-processing." in out


def test_13_empty_date_gets_its_own_warning(env: MagicMock) -> None:
    has = _ts_folder(env, "BENTONG", "01-05-2026")
    none = _ts_folder(env, "BENTONG", "03-05-2026")
    extractor = MagicMock()
    extractor.extract.return_value = [
        SubstationTestsheetPackage(
            testsheet_path=Path("x.xlsx"), unsorted_raw_data_dir=Path("raw"),
            station="BENTONG", month=MONTH, date_str="01-05-2026", substation_number=1,
            data=MagicMock(),
        )
    ]
    wf = FullReportWorkflow(compiler=MagicMock(), extractor=extractor)

    pkgs, warnings, errors = wf._discover_packages((has, none), env)

    assert len(pkgs) == 1
    assert warnings == ["⚠️ 03-05-2026 (BENTONG): no testsheet packages found"]


def test_13_all_dates_empty_keeps_nothing_discovered_message(env: MagicMock, capsys) -> None:
    none = _ts_folder(env, "BENTONG", "03-05-2026")
    extractor = MagicMock()
    extractor.extract.return_value = []
    wf = FullReportWorkflow(compiler=MagicMock(), extractor=extractor)
    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value="browse_dates"), \
         patch("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", return_value=(none,)):
        generate_full_reports_action(env, workflow=wf)
    out = capsys.readouterr().out
    assert "03-05-2026 (BENTONG): no testsheet packages found" in out
    assert "No substations discovered to process." in out


# --- Review fixes -------------------------------------------------------------

def test_14_browse_maps_noncanonical_testsheet_month_to_canonical_full_report_month(env: MagicMock) -> None:
    _fr_docx(env, "BENTONG", "01-05-2026", "001. ALPHA.docx")  # FULL REPORT/BENTONG/05. MAY/...
    ts = env.get_testsheet_dir() / "BENTONG" / "5. MAY" / "01-05-2026"
    ts.mkdir(parents=True)
    empty_ts = env.get_testsheet_dir() / "BENTONG" / "MAY" / "03-05-2026"
    empty_ts.mkdir(parents=True)

    shown = _run_14(
        env, "browse_dates",
        ("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", (ts, empty_ts)),
        workflow=FullReportPostProcessingWorkflow(converter=MagicMock()),
    )
    assert [t.stem for t in shown["targets"]] == ["001. ALPHA"]


def test_14_manual_fl_matches_substation_name_not_just_pe_number(env: MagicMock) -> None:
    mine = _fr_docx(env, "BENTONG", "01-05-2026", "157. PERPUSTAKAAN AWAM.docx")
    _fr_docx(env, "BENTONG", "01-05-2026", "157. SOMEWHERE ELSE.docx")
    pkg = _pkg("BENTONG", "01-05-2026", 157)
    pkg = SubstationTestsheetPackage(
        testsheet_path=pkg.testsheet_path, unsorted_raw_data_dir=pkg.unsorted_raw_data_dir,
        station=pkg.station, month=pkg.month, date_str=pkg.date_str, substation_number=157,
        data=SimpleNamespace(substation_name_site="PERPUSTAKAAN AWAM", substation_name_erms="",
                             station_name="BENTONG"),
    )
    with patch.object(FullReportWorkflow, "_discover_packages", return_value=([pkg], [], [])):
        files, warnings = FullReportPostProcessingWorkflow(converter=MagicMock()).locate_full_reports_for_fls(
            ["FL-157"], env
        )
    assert files == [mine.resolve()]


def test_14_manual_fl_warns_when_matches_span_distinct_stems(env: MagicMock) -> None:
    _fr_docx(env, "BENTONG", "01-05-2026", "157. PERPUSTAKAAN AWAM.docx")
    _fr_docx(env, "BENTONG", "01-05-2026", "157. SOMEWHERE ELSE.docx")
    with patch.object(FullReportWorkflow, "_discover_packages",
                      return_value=([_pkg("BENTONG", "01-05-2026", 157)], [], [])):
        files, warnings = FullReportPostProcessingWorkflow(converter=MagicMock()).locate_full_reports_for_fls(
            ["FL-157"], env
        )
    assert len(files) == 2
    assert any("01-05-2026 (BENTONG)" in w and "more than one" in w for w in warnings)


def test_empty_date_warnings_carry_warning_icon(env: MagicMock) -> None:
    empty = env.get_full_report_dir() / "BENTONG" / MONTH / "03-05-2026"
    _, warnings, _ = FullReportPostProcessingWorkflow(converter=MagicMock())._discover_docx_files([empty], env)
    assert warnings[0].startswith("⚠️ 03-05-2026 (BENTONG): no Full Report documents")

    none = _ts_folder(env, "BENTONG", "03-05-2026")
    extractor = MagicMock()
    extractor.extract.return_value = []
    _, w13, _ = FullReportWorkflow(compiler=MagicMock(), extractor=extractor)._discover_packages((none,), env)
    assert w13 == ["⚠️ 03-05-2026 (BENTONG): no testsheet packages found"]


def test_13_empty_date_station_is_read_from_testsheet_layout_not_path_depth(env: MagicMock) -> None:
    """A date folder outside the TESTSHEET/<ST>/<MONTH>/<DATE> layout gets no station guess."""
    odd = env.base_path / "elsewhere" / "03-05-2026"
    odd.mkdir(parents=True)
    extractor = MagicMock()
    extractor.extract.return_value = [
        SubstationTestsheetPackage(
            testsheet_path=Path("x.xlsx"), unsorted_raw_data_dir=Path("raw"),
            station="BENTONG", month=MONTH, date_str="01-05-2026", substation_number=1, data=MagicMock(),
        )
    ]
    _, warnings, _ = FullReportWorkflow(compiler=MagicMock(), extractor=extractor)._discover_packages((odd,), env)
    assert warnings == ["⚠️ 03-05-2026: no testsheet packages found"]
