"""Regression: vi_summary slice must keep every summary row, however many pages the table spans.

REX THEATRE (CKTN/PCE/J00105): 21-row VISUAL DEFECT SUMMARY table, rows 20-21 on
page 3. The slice ended at the heading page + 1, so only 19 rows survived and the
guard failed against the master count of 21.

SSU BANDAR INDERA MAHKOTA (CKTN/PCE/J01647): same truncation (23 of 32 rows), but
the master QR03 VI sheet held 23 rows, so the guard passed by coincidence. The guard
now also compares the slice against the Quick Report's own summary row count.

Needs real Word: pagination is computed by Word's layout engine, not mockable.
"""
from __future__ import annotations

import io
from pathlib import Path

import docx
import pytest
from docx.enum.text import WD_BREAK
from docx.shared import Inches

win32com_client = pytest.importorskip("win32com.client")
pythoncom = pytest.importorskip("pythoncom")
PIL_Image = pytest.importorskip("PIL.Image")

from src.full_report import slicer as slicer_mod  # noqa: E402
from src.full_report.slicer import (  # noqa: E402
    SlicingError,
    WordComDocumentSlicer,
    _count_vi_summary_source_rows,
    _find_paragraph,
    _resolve_vi_summary_end,
    _slice_range_to_doc,
)

STATION = "TEST STATION"


def _page_break(d: docx.document.Document) -> None:
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _png_bytes() -> io.BytesIO:
    buf = io.BytesIO()
    PIL_Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    buf.seek(0)
    return buf


def _build_quick_report(path: Path, rows: int, trailing_blank_rows: int = 0) -> None:
    """Minimal Quick Report satisfying every slice_sections guard, with an N-row VI summary."""
    d = docx.Document()
    d.add_paragraph("QUICK SCANNING REPORT")
    d.add_table(rows=1, cols=2).rows[0].cells[0].text = "FRONT PAGE"
    _page_break(d)

    d.add_paragraph("VISUAL DEFECT SUMMARY")
    t = d.add_table(rows=rows + 1 + trailing_blank_rows, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "NO.", "DEFECT DESCRIPTION"
    for i in range(1, rows + 1):
        t.rows[i].cells[0].text, t.rows[i].cells[1].text = str(i), f"DEFECT {i}"
    _page_break(d)

    d.add_paragraph("CBM DEFECT DETAIL PAGE")
    d.add_table(rows=2, cols=2).rows[1].cells[0].text = "CBM ROW"
    _page_break(d)

    d.add_paragraph("SUBSTATION CONDITION")
    d.add_table(rows=1, cols=1).rows[0].cells[0].text = "CONDITION"
    d.add_picture(_png_bytes(), width=Inches(0.5))
    _page_break(d)

    d.add_paragraph("NORMAL/DEFECT STICKER")
    d.add_paragraph("NORMAL STICKER")
    d.save(path)


def _data_rows(path: Path) -> int:
    t = docx.Document(path).tables[0]
    return len([r for r in t.rows[1:] if any(c.text.strip() for c in r.cells)])


@pytest.fixture(scope="module")
def word_app():
    pythoncom.CoInitialize()
    try:
        app = win32com_client.DispatchEx("Word.Application")
    except Exception:
        pytest.skip("Microsoft Word not available")
    app.Visible = False
    app.DisplayAlerts = 0
    yield app
    app.Quit()
    pythoncom.CoUninitialize()


def _open(word_app, path: Path):
    return word_app.Documents.Open(str(path), False, True)


def _summary_bounds(doc):
    p_visum = _find_paragraph(doc, "VISUAL DEFECT SUMMARY")
    p_cond = _find_paragraph(doc, "SUBSTATION CONDITION")
    return p_visum, p_cond


@pytest.mark.parametrize(
    ("rows", "min_pages_spanned"),
    [(30, 2), (60, 3), (220, 5)],
    ids=["2-pages", "3-pages", "5-plus-pages"],
)
def test_vi_summary_slice_keeps_every_row_across_pages_and_excludes_cbm_page(
    tmp_path, word_app, rows, min_pages_spanned
):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, rows)
    doc = _open(word_app, src)
    try:
        p_visum, p_cond = _summary_bounds(doc)
        tbl = doc.Tables(2)
        last_row_page = tbl.Rows(rows + 1).Range.Information(3)
        assert last_row_page - p_visum.page_number + 1 >= min_pages_spanned, (
            f"fixture must span >= {min_pages_spanned} pages, spans "
            f"p{p_visum.page_number}-p{last_row_page}"
        )

        end = _resolve_vi_summary_end(doc, p_visum, p_cond.start)
        out = _slice_range_to_doc(word_app, doc, p_visum.start, end, tmp_path / "vi_summary.docx")
    finally:
        doc.Close(False)

    assert _data_rows(out) == rows
    assert len(docx.Document(out).tables) == 1, "CBM page after the summary must not be pulled in"


def test_count_vi_summary_source_rows_ignores_header_and_blank_rows(tmp_path, word_app):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, rows=130, trailing_blank_rows=5)
    doc = _open(word_app, src)
    try:
        p_visum, p_cond = _summary_bounds(doc)
        assert _count_vi_summary_source_rows(doc, p_visum, p_cond.start) == 130
    finally:
        doc.Close(False)


def test_slice_sections_passes_when_slice_quick_report_and_master_agree(tmp_path, word_app):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, rows=130)
    sections = WordComDocumentSlicer(word_app=word_app).slice_sections(
        src, tmp_path / "out", station=STATION, expected_vi_defect_count=130
    )
    assert sections.vi_summary is not None
    assert _data_rows(sections.vi_summary) == 130


def test_slice_sections_rejects_truncated_slice_even_when_it_matches_master_count(
    tmp_path, word_app, monkeypatch
):
    """J01647: truncated slice row count happened to equal the master count, so it slipped through."""
    src = tmp_path / "qr.docx"
    _build_quick_report(src, rows=60)

    def old_heading_page_end(source_doc, p_visum, cond_start):
        nxt = source_doc.GoTo(1, 1, p_visum.page_number + 1)
        return min(nxt.Start, cond_start)

    doc = _open(word_app, src)
    try:
        p_visum, p_cond = _summary_bounds(doc)
        old_end = old_heading_page_end(doc, p_visum, p_cond.start)
        tbl = doc.Tables(2)
        truncated = sum(1 for i in range(2, tbl.Rows.Count + 1) if tbl.Rows(i).Range.Start < old_end)
    finally:
        doc.Close(False)
    assert 0 < truncated < 60, "fixture must put the page break inside the summary table"

    monkeypatch.setattr(slicer_mod, "_resolve_vi_summary_end", old_heading_page_end)
    with pytest.raises(SlicingError) as exc:
        WordComDocumentSlicer(word_app=word_app).slice_sections(
            src, tmp_path / "out", station=STATION, expected_vi_defect_count=truncated
        )
    msg = str(exc.value)
    assert f"({truncated} data rows)" in msg
    assert "Quick Report summary table has 60" in msg


def test_slice_sections_rejects_quick_report_that_disagrees_with_master(tmp_path, word_app):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, rows=60)
    with pytest.raises(SlicingError) as exc:
        WordComDocumentSlicer(word_app=word_app).slice_sections(
            src, tmp_path / "out", station=STATION, expected_vi_defect_count=51
        )
    msg = str(exc.value)
    assert "does not match expected defect count 51" in msg
    assert "Quick Report summary table has 60" in msg
