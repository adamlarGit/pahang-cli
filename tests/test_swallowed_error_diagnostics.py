"""Word-path errors that are handled and carried past still reach the Run Record (#191).

Each test injects a failure through a fake Word and checks three things: the diagnostic and its
traceback are in a temporary Run Record, the fallback still happened, and the console stayed quiet.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from src.full_report.slicer import (
    ParagraphBoundary,
    SlicingError,
    WordComDocumentSlicer,
    _count_vi_summary_source_rows,
    _resolve_vi_summary_end,
    _slice_cbm_defects_from_doc,
    _slice_range_to_doc,
    _summary_table_last_page,
)
from src.postprocessing.converters import (
    ComDocumentConverter,
    _quit_word,
    convert_docx_native_restored,
    safe_replace_with_retry,
    safe_unlink_with_retry,
)
from src.quick_report.compiler import (
    WordComDocumentCompiler,
    _paste_with_retry,
    _terminate_word_process,
    clear_windows_clipboard,
)
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, open_run

BOOM = "injected COM failure"


@pytest.fixture
def recorded(tmp_path, monkeypatch, capsys):
    """Run an action inside a Run and hand back its result, entries and console text."""
    folder = tmp_path / "records"
    monkeypatch.setenv(RECORD_DIR_OVERRIDE_VARIABLE, str(folder))

    def run_action(action):
        with open_run("Diagnostics") as run:
            result = run.call(action)
        files = list(folder.glob("*.jsonl"))
        assert len(files) == 1
        entries = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
        captured = capsys.readouterr()
        return result, entries, captured.out + captured.err

    return run_action


def assert_diagnosed(entries: list[dict], console: str, *context: str) -> None:
    """One DEBUG entry names the context and carries the injected traceback; the Run still completed."""
    matching = [
        entry
        for entry in entries
        if entry["type"] == "log"
        and entry["level"] == "DEBUG"
        and all(text in entry["message"] for text in context)
        and BOOM in entry.get("traceback", "")
    ]
    assert matching, f"no DEBUG diagnostic naming {context}: {[e for e in entries if e['type'] == 'log']}"
    assert "Traceback" not in console
    assert all(entry["message"] not in console for entry in matching)
    assert entries[-1]["type"] == "run_finish"
    assert entries[-1]["status"] == "completed"


def _word_with(part: MagicMock | None = None) -> tuple[MagicMock, MagicMock]:
    word, main = MagicMock(), MagicMock()
    word.Documents.Add.return_value = main
    main.Content.Information.return_value = False  # the insertion point is not inside a table
    word.Documents.Open.return_value = part or MagicMock()
    return word, main


def test_compiler_part_close_failure_is_diagnosed_and_compile_still_saves(recorded, tmp_path) -> None:
    part = MagicMock()
    part.Close.side_effect = RuntimeError(BOOM)
    word, main = _word_with(part)
    output = tmp_path / "out.docx"

    result, entries, console = recorded(
        lambda: WordComDocumentCompiler(word_app=word).compile([tmp_path / "part.docx"], output)
    )

    assert result == output.resolve()
    main.SaveAs2.assert_called_once_with(str(output.resolve()))
    assert_diagnosed(entries, console, "part.docx", "close")


def test_paste_retry_is_diagnosed_and_the_retry_still_pastes(recorded) -> None:
    rng = MagicMock()
    rng.PasteAndFormat.side_effect = [RuntimeError(BOOM), None]

    _, entries, console = recorded(lambda: _paste_with_retry(rng, delay=0))

    assert rng.PasteAndFormat.call_count == 2
    assert_diagnosed(entries, console, "attempt 1/5")


def test_paste_format_fallback_is_diagnosed_and_plain_paste_still_runs(recorded) -> None:
    rng = MagicMock()
    rng.PasteAndFormat.side_effect = TypeError(BOOM)

    _, entries, console = recorded(lambda: _paste_with_retry(rng, delay=0))

    rng.Paste.assert_called_once_with()
    assert_diagnosed(entries, console, "plain Paste")


def test_clipboard_failure_is_diagnosed_and_all_three_attempts_run(recorded) -> None:
    with patch("src.quick_report.compiler.ctypes") as fake_ctypes:
        fake_ctypes.windll.user32.OpenClipboard.side_effect = RuntimeError(BOOM)
        _, entries, console = recorded(clear_windows_clipboard)

    assert fake_ctypes.windll.user32.OpenClipboard.call_count == 3
    assert_diagnosed(entries, console, "clipboard", "attempt 3/3")


def test_failure_to_end_a_word_process_is_diagnosed_and_not_raised(recorded) -> None:
    with patch("src.quick_report.compiler.ctypes") as fake_ctypes:
        fake_ctypes.windll.kernel32.OpenProcess.side_effect = RuntimeError(BOOM)
        _, entries, console = recorded(lambda: _terminate_word_process(4242))

    assert_diagnosed(entries, console, "4242")


@pytest.mark.parametrize(
    ("module", "adapter", "use"),
    [
        ("src.quick_report.compiler", WordComDocumentCompiler, "compiler's Word"),
        ("src.full_report.slicer", WordComDocumentSlicer, "slicer's Word"),
    ],
)
def test_word_quit_failure_is_diagnosed_and_com_is_still_released(recorded, module, adapter, use) -> None:
    word = MagicMock()
    word.Quit.side_effect = RuntimeError(BOOM)
    win32process = MagicMock()
    win32process.GetWindowThreadProcessId.side_effect = RuntimeError(BOOM)

    def open_and_close_session() -> None:
        with patch(f"{module}.pythoncom") as pythoncom, patch(f"{module}.win32com") as win32com:
            win32com.client.Dispatch.return_value = word
            pythoncom.CoUninitialize.side_effect = RuntimeError(BOOM)
            with patch.dict("sys.modules", {"win32process": win32process}):
                with adapter().session():
                    pass
        pythoncom.CoUninitialize.assert_called_once_with()

    _, entries, console = recorded(open_and_close_session)

    word.Quit.assert_called_once_with()
    assert_diagnosed(entries, console, "quit", use)
    assert_diagnosed(entries, console, "uninitialize COM", use)
    assert_diagnosed(entries, console, "process id", use)


@pytest.mark.parametrize(
    ("module", "adapter", "use"),
    [
        ("src.quick_report.compiler", WordComDocumentCompiler, "compiler's Word"),
        ("src.full_report.slicer", WordComDocumentSlicer, "slicer's Word"),
    ],
)
@pytest.mark.parametrize(
    ("options", "what"),
    [
        ({"is_enabled": {"side_effect": RuntimeError(BOOM)}}, "pause faulthandler"),
        (
            {"is_enabled": {"return_value": True}, "disable": {}, "enable": {"side_effect": RuntimeError(BOOM)}},
            "re-enable faulthandler",
        ),
    ],
)
def test_session_faulthandler_failure_is_diagnosed_and_word_is_still_quit(
    recorded, module, adapter, use, options, what
) -> None:
    word = MagicMock()
    patchers = [patch(f"faulthandler.{name}", **kwargs) for name, kwargs in options.items()]

    def open_and_close_session() -> None:
        with patch(f"{module}.pythoncom"), patch(f"{module}.win32com") as win32com:
            win32com.client.Dispatch.return_value = word
            with patch.dict("sys.modules", {"win32process": None}):  # no process id, so nothing is terminated
                with adapter().session():
                    pass

    for patcher in patchers:
        patcher.start()
    try:
        _, entries, console = recorded(open_and_close_session)
    finally:
        for patcher in patchers:
            patcher.stop()

    word.Quit.assert_called_once_with()
    assert_diagnosed(entries, console, what, use)


class _Exploding:
    """A COM object whose every member fails."""

    def __getattr__(self, name: str):
        raise RuntimeError(BOOM)


def _slicing(tmp_path, break_it, *, is_front_page: bool = False):
    """Slice with fake Word after break_it(source, new); returns the action, the new doc and the output path."""
    word, source, new = MagicMock(), MagicMock(), MagicMock()
    word.Documents.Add.return_value = new
    source.Range.return_value.Text = "x"
    new.Paragraphs.Count = 1
    break_it(source, new)
    output = tmp_path / "slice.docx"

    def action() -> Path:
        return _slice_range_to_doc(word, source, 0, 10, output, is_front_page=is_front_page)

    return action, new, output


def _break_page_setup(source, new) -> None:
    source.PageSetup = _Exploding()


def _break_trim(source, new) -> None:
    new.Paragraphs = _Exploding()


def _break_close(source, new) -> None:
    new.Close.side_effect = RuntimeError(BOOM)


def _break_slice_end(source, new) -> None:
    good = source.Range.return_value
    source.Range.side_effect = [RuntimeError(BOOM), good]


@pytest.mark.parametrize(
    ("break_it", "what"),
    [
        (_break_page_setup, "page setup"),
        (_break_trim, "trim"),
        (_break_close, "close"),
        (_break_slice_end, "slice end"),
    ],
)
def test_slice_step_failure_is_diagnosed_and_the_slice_is_still_saved(recorded, tmp_path, break_it, what) -> None:
    action, new, output = _slicing(tmp_path, break_it)

    result, entries, console = recorded(action)

    assert result == output.resolve()
    new.SaveAs2.assert_called_once_with(str(output.resolve()))
    new.Close.assert_called_once_with(False)
    assert_diagnosed(entries, console, "slice.docx", what)


def test_title_replace_retry_is_diagnosed_and_the_keyword_retry_still_runs(recorded, tmp_path) -> None:
    def break_find(source, new) -> None:
        new.Content.Find.Execute.side_effect = [RuntimeError(BOOM), True]

    action, new, _ = _slicing(tmp_path, break_find, is_front_page=True)

    _, entries, console = recorded(action)

    assert new.Content.Find.Execute.call_count == 2
    assert_diagnosed(entries, console, "title", "retrying by keyword")


HEADING = ParagraphBoundary(start=5, end=9, text="VISUAL DEFECT SUMMARY", page_number=2)


def _summary_doc(table: MagicMock) -> MagicMock:
    source = MagicMock()
    tables = source.Range.return_value.Tables
    tables.Count = 1
    tables.return_value = table
    table.Cell.return_value.Range.Text = "NO."
    return source


def test_unreadable_summary_table_is_diagnosed_and_the_slice_ends_at_condition(recorded) -> None:
    source = MagicMock()
    source.Range.side_effect = RuntimeError(BOOM)
    source.GoTo.side_effect = RuntimeError(BOOM)

    result, entries, console = recorded(lambda: _resolve_vi_summary_end(source, HEADING, 100))

    assert result == 100
    assert_diagnosed(entries, console, "summary table", HEADING.text)
    assert_diagnosed(entries, console, "page 3", "VI summary")


def test_unreadable_summary_last_page_is_diagnosed_and_the_heading_page_is_used(recorded) -> None:
    table = MagicMock()
    table.Range = _Exploding()

    result, entries, console = recorded(lambda: _summary_table_last_page(_summary_doc(table), HEADING, 100))

    assert result == HEADING.page_number
    assert_diagnosed(entries, console, "last page", HEADING.text)


def test_unreadable_summary_rows_are_diagnosed_and_the_count_is_unknown(recorded) -> None:
    table = MagicMock()
    table.Rows = _Exploding()

    result, entries, console = recorded(lambda: _count_vi_summary_source_rows(_summary_doc(table), HEADING, 100))

    assert result is None
    assert_diagnosed(entries, console, "rows", HEADING.text)


def _cbm_source() -> MagicMock:
    source = MagicMock()
    source.Content.Text = ""  # no summary headings to find
    source.GoTo.side_effect = lambda _what, _which, page: SimpleNamespace(Start=page * 10)
    return source


def _slice_cbm(source: MagicMock, target: Path, parser: MagicMock, cond_page: int = 3):
    return _slice_cbm_defects_from_doc(
        MagicMock(),
        source,
        target,
        total_pages=5,
        cond_start=100,
        p_cond=ParagraphBoundary(start=100, end=110, text="SUBSTATION CONDITION", page_number=cond_page),
        header_parser=parser,
        station="STATION",
    )


def test_unlocatable_cbm_page_is_diagnosed_and_the_next_page_is_still_tried(recorded, tmp_path) -> None:
    source = _cbm_source()
    pages_tried: list[int] = []

    def go_to(_what, _which, page):
        pages_tried.append(page)
        if page == 2:
            raise RuntimeError(BOOM)
        return SimpleNamespace(Start=page * 10)

    source.GoTo.side_effect = go_to
    parser = MagicMock()
    parser.parse.side_effect = ValueError("not a defect page")

    with patch("src.full_report.slicer._slice_range_to_doc"):
        result, entries, console = recorded(lambda: _slice_cbm(source, tmp_path, parser, cond_page=4))

    assert result == ()
    assert 3 in pages_tried
    assert_diagnosed(entries, console, "candidate CBM defect page 2")


@pytest.mark.parametrize(
    ("attributed", "parse_error", "what"),
    [(True, ValueError("not a defect page"), "non-defect"), (False, None, "rejected")],
)
def test_temp_slice_removal_failure_is_diagnosed_and_not_raised(recorded, tmp_path, attributed, parse_error, what) -> None:
    parser = MagicMock()
    parser.parse.side_effect = parse_error

    with (
        patch("src.full_report.slicer._slice_range_to_doc"),
        patch("src.full_report.slicer.verify_cbm_defect_attribution", return_value=attributed),
        patch("pathlib.Path.unlink", side_effect=RuntimeError(BOOM)),
    ):
        result, entries, console = recorded(lambda: _slice_cbm(_cbm_source(), tmp_path, parser))

    assert result == ()
    assert_diagnosed(entries, console, what, "_temp_defect_p2.docx")
    assert_diagnosed(entries, console, "temporary CBM slice", "_temp_defect_p2.docx")


def test_source_close_failure_is_diagnosed_and_the_result_still_returned(recorded, tmp_path) -> None:
    source_path = tmp_path / "quick.docx"
    source_path.write_bytes(b"x")
    source = MagicMock()
    source.Content.Text = ""
    source.ComputeStatistics.return_value = 1
    source.Close.side_effect = RuntimeError(BOOM)
    word = MagicMock()
    word.Documents.Open.return_value = source

    result, entries, console = recorded(
        lambda: WordComDocumentSlicer(word_app=word).slice_cbm_defects(source_path, tmp_path / "parts", "STATION")
    )

    assert result == ()
    assert_diagnosed(entries, console, "quick.docx", "close")


def test_unknown_page_two_is_diagnosed_before_the_slice_carries_on(recorded, tmp_path) -> None:
    source_path = tmp_path / "quick.docx"
    source = MagicMock()
    source.Content.Text = ""
    source.ComputeStatistics.side_effect = RuntimeError(BOOM)
    word = MagicMock()
    word.Documents.Open.return_value = source

    def action() -> str:
        with pytest.raises(SlicingError, match="SUBSTATION CONDITION"):
            WordComDocumentSlicer(word_app=word).slice_sections(source_path, tmp_path / "parts", "STATION")
        return "carried on to the boundary search"

    result, entries, console = recorded(action)

    assert result == "carried on to the boundary search"
    assert_diagnosed(entries, console, "page 2", "quick.docx")


CONVERTERS = "src.postprocessing.converters"


def _write_pdf(path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def test_unlink_retry_is_diagnosed_and_the_retry_still_removes(recorded, tmp_path) -> None:
    target = tmp_path / "locked.pdf"
    target.write_bytes(b"x")

    with patch("pathlib.Path.unlink", side_effect=[OSError(BOOM), None]) as unlink:
        result, entries, console = recorded(lambda: safe_unlink_with_retry(target, total_wait=0))

    assert result is True
    assert unlink.call_count == 2
    assert_diagnosed(entries, console, "locked.pdf", "attempt 1/5")


def test_replace_retry_is_diagnosed_and_the_retry_still_replaces(recorded, tmp_path) -> None:
    source = tmp_path / "new.pdf"
    source.write_bytes(b"x")

    with patch(f"{CONVERTERS}.os.replace", side_effect=[OSError(BOOM), None]) as replace:
        result, entries, console = recorded(
            lambda: safe_replace_with_retry(source, tmp_path / "published.pdf", total_wait=0)
        )

    assert result is True
    assert replace.call_count == 2
    assert_diagnosed(entries, console, "published.pdf", "attempt 1/5")


def test_export_failure_keeps_its_traceback_and_word_is_still_recycled_and_retried(recorded, tmp_path) -> None:
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"x")
    pdf = tmp_path / "report.pdf"
    attempts: list[Path] = []
    recycle = MagicMock()

    def export(_docx: Path, out: Path) -> None:
        attempts.append(out)
        if len(attempts) == 1:
            raise RuntimeError(BOOM)
        _write_pdf(out)

    _, entries, console = recorded(
        lambda: convert_docx_native_restored(
            docx, pdf, export, recycle=recycle, retry_delays=(), restore_images=False
        )
    )

    assert len(attempts) == 2
    recycle.assert_called_once_with()
    assert pdf.exists()
    assert_diagnosed(entries, console, "report.docx", "attempt 1/2")


def test_unopenable_export_is_diagnosed_and_validation_still_tries_again(recorded, tmp_path) -> None:
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"x")
    pdf = tmp_path / "report.pdf"
    recycle = MagicMock()
    real_open = fitz.open
    failures = [RuntimeError(BOOM)]

    def flaky_open(*args, **kwargs):
        if args and failures:
            raise failures.pop()
        return real_open(*args, **kwargs)

    with patch(f"{CONVERTERS}.fitz.open", side_effect=flaky_open):
        _, entries, console = recorded(
            lambda: convert_docx_native_restored(
                docx, pdf, lambda _d, out: _write_pdf(out), recycle=recycle, retry_delays=(0,), restore_images=False
            )
        )

    recycle.assert_not_called()
    assert pdf.exists()
    assert_diagnosed(entries, console, "open", ".tmp_native_")


def _excel_with(sheet_names: list[str]) -> tuple[MagicMock, MagicMock, list[MagicMock]]:
    excel, workbook = MagicMock(), MagicMock()
    sheets = []
    for name in sheet_names:
        sheet = MagicMock()
        sheet.Name = name
        sheet.ExportAsFixedFormat.side_effect = lambda _kind, path, *_rest: _write_pdf(path)
        sheets.append(sheet)
    workbook.Worksheets = sheets
    excel.Workbooks.Open.return_value = workbook
    return excel, workbook, sheets


def test_unreadable_extra_sheet_is_kept_and_a_failed_workbook_close_is_diagnosed(recorded, tmp_path) -> None:
    excel, workbook, sheets = _excel_with(["33kV (Extra)"])
    sheets[0].Range.side_effect = RuntimeError(BOOM)
    workbook.Close.side_effect = RuntimeError(BOOM)
    pdf = tmp_path / "sheet.pdf"
    converter = ComDocumentConverter(optimize_page_setup=False)

    result, entries, console = recorded(
        lambda: converter.convert_testsheet_to_pdf(tmp_path / "book.xlsx", pdf, excel_app=excel)
    )

    assert result == pdf
    sheets[0].ExportAsFixedFormat.assert_called_once()
    assert_diagnosed(entries, console, "33kv (extra)", "book.xlsx")
    assert_diagnosed(entries, console, "close workbook", "book.xlsx")


def test_temp_sheet_pdf_removal_failure_is_diagnosed_and_the_merge_still_stands(recorded, tmp_path) -> None:
    excel, _, _ = _excel_with(["33kV (Main)", "33kV (Extra)"])
    pdf = tmp_path / "sheet.pdf"
    converter = ComDocumentConverter(optimize_page_setup=False)
    converter._merge_temp_pdfs = lambda _temps, out: _write_pdf(out)

    with patch("pathlib.Path.unlink", side_effect=RuntimeError(BOOM)):
        result, entries, console = recorded(
            lambda: converter.convert_testsheet_to_pdf(tmp_path / "book.xlsx", pdf, excel_app=excel)
        )

    assert result == pdf
    assert_diagnosed(entries, console, "temporary sheet PDF", ".tmp_sheet_sheet_0.pdf")


def test_owned_excel_quit_and_com_release_failures_are_diagnosed(recorded, tmp_path) -> None:
    excel, _, _ = _excel_with(["33kV (Main)"])
    excel.Quit.side_effect = RuntimeError(BOOM)
    pdf = tmp_path / "sheet.pdf"
    converter = ComDocumentConverter(optimize_page_setup=False)

    with (
        patch("win32com.client.DispatchEx", return_value=excel),
        patch("pythoncom.CoInitialize"),
        patch("pythoncom.CoUninitialize", side_effect=RuntimeError(BOOM)) as uninitialize,
    ):
        result, entries, console = recorded(
            lambda: converter.convert_testsheet_to_pdf(tmp_path / "book.xlsx", pdf)
        )

    assert result == pdf
    uninitialize.assert_called_once_with()
    assert_diagnosed(entries, console, "quit Excel", "book.xlsx")
    assert_diagnosed(entries, console, "uninitialize COM", "book.xlsx")


def test_word_document_close_and_com_release_failures_are_diagnosed(recorded, tmp_path) -> None:
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"x")
    pdf = tmp_path / "report.pdf"
    word, document = MagicMock(), MagicMock()
    word.Documents.Open.return_value = document
    document.ExportAsFixedFormat.side_effect = lambda OutputFileName, **_kw: _write_pdf(OutputFileName)
    document.Close.side_effect = RuntimeError(BOOM)

    with (
        patch(f"{CONVERTERS}._start_word", return_value=word),
        patch("pythoncom.CoInitialize"),
        patch("pythoncom.CoUninitialize", side_effect=RuntimeError(BOOM)),
    ):
        result, entries, console = recorded(
            lambda: ComDocumentConverter().convert_docx_to_pdf(docx, pdf, restore_images=False)
        )

    assert result == pdf
    word.Quit.assert_called_once_with()
    assert_diagnosed(entries, console, "close Word document", "report.docx")
    assert_diagnosed(entries, console, "uninitialize COM", "report.docx")


@pytest.mark.parametrize(
    ("patches", "what"),
    [
        ({"is_enabled": {"side_effect": RuntimeError(BOOM)}}, "pause faulthandler"),
        (
            {"is_enabled": {"return_value": True}, "disable": {}, "enable": {"side_effect": RuntimeError(BOOM)}},
            "re-enable faulthandler",
        ),
    ],
)
def test_faulthandler_failure_is_diagnosed_and_word_is_still_quit(recorded, patches, what) -> None:
    word = MagicMock()
    patchers = [patch(f"faulthandler.{name}", **options) for name, options in patches.items()]
    for patcher in patchers:
        patcher.start()
    try:
        _, entries, console = recorded(lambda: _quit_word(word))
    finally:
        for patcher in patchers:
            patcher.stop()

    word.Quit.assert_called_once_with()
    assert_diagnosed(entries, console, what)


def test_batch_continues_to_the_next_report_after_a_failed_document_close(recorded, tmp_path) -> None:
    first, second = tmp_path / "first.docx", tmp_path / "second.docx"
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    word, failing, healthy = MagicMock(), MagicMock(), MagicMock()
    word.Documents.Open.side_effect = [failing, healthy]
    for document in (failing, healthy):
        document.ExportAsFixedFormat.side_effect = lambda OutputFileName, **_kw: _write_pdf(OutputFileName)
    failing.Close.side_effect = RuntimeError(BOOM)
    converter = ComDocumentConverter()

    def convert_both() -> list[Path]:
        return [
            converter.convert_docx_to_pdf(docx, docx.with_suffix(".pdf"), word_app=word, restore_images=False)
            for docx in (first, second)
        ]

    result, entries, console = recorded(convert_both)

    assert [path.name for path in result] == ["first.pdf", "second.pdf"]
    assert all(path.exists() for path in result)
    healthy.Close.assert_called_once_with(SaveChanges=False)
    word.Quit.assert_not_called()
    assert_diagnosed(entries, console, "close Word document", "first.docx")


def test_merge_cleanup_failure_is_diagnosed_and_the_save_error_still_raises(recorded, tmp_path) -> None:
    out_doc = MagicMock()
    out_doc.save.side_effect = ValueError("save failed")

    def action() -> str:
        with pytest.raises(ValueError, match="save failed"):
            ComDocumentConverter().merge_pdfs_batch([], tmp_path / "merged.pdf")
        return "raised"

    with (
        patch(f"{CONVERTERS}.fitz.open", return_value=out_doc),
        patch("pathlib.Path.unlink", side_effect=RuntimeError(BOOM)),
    ):
        result, entries, console = recorded(action)

    assert result == "raised"
    assert_diagnosed(entries, console, "temporary merge output", "merged.pdf")
