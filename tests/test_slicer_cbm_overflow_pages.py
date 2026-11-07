"""Regression (#175): summary overflow pages must not be sliced as CBM defect detail pages.

REX THEATRE (CKTN/PCE/J00105): the VISUAL DEFECT SUMMARY ran onto page 3, which held
only rows 20-21. The CBM defect page scan skipped only the summary heading page, the
header parser accepted page 3 as "SWG1 OVERVIEW", and it replaced the real switchgear
overview page in the Full Report.

Two layers are tested separately:
- the real header parser rejects overflow pages (end-to-end through slice_sections);
- the scan skips every page a summary table covers, even with a parser that would
  accept anything.

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

from src.full_report.defect_parser import CbmDefectHeaderParser, CbmDefectSliceMetadata  # noqa: E402
from src.full_report.slicer import WordComDocumentSlicer  # noqa: E402

pytestmark = pytest.mark.word

STATION = "TEST STATION"
OVERFLOW_ROWS = 60  # spills each summary table across several pages


def _page_break(d) -> None:
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _png_bytes() -> io.BytesIO:
    buf = io.BytesIO()
    PIL_Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    buf.seek(0)
    return buf


def _summary_table(d, header: list[str], rows: int) -> None:
    t = d.add_table(rows=rows + 1, cols=len(header))
    for c, h in enumerate(header):
        t.rows[0].cells[c].text = h
    for i in range(1, rows + 1):
        t.rows[i].cells[0].text = str(i)
        for c in range(1, len(header)):
            t.rows[i].cells[c].text = f"R{i}C{c}"


def _cbm_defect_page(d) -> None:
    grid = [
        ["Substation", STATION, "Date: 12/08/2026"],
        ["Equipment", "FEEDER PILLAR", "Manufacturer", "-", "Time: 12:31 PM"],
        ["Model", "J-SLOTTED", "Rating", "-", "Humidity: 65%"],
        ["Area", "OUTGOING FUSE CONNECTION", "Feeder No.", "F03"],
        ["Feeder Name", "OUTGOING F3"],
    ]
    t = d.add_table(rows=len(grid), cols=5)
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            t.rows[r].cells[c].text = val


def _build_quick_report(path: Path, cbm_rows: int, vi_rows: int) -> None:
    """Quick Report with a CBM summary, a VI summary, one real CBM defect page, condition and sticker."""
    d = docx.Document()
    d.add_paragraph("QUICK SCANNING REPORT")
    d.add_table(rows=1, cols=2).rows[0].cells[0].text = "FRONT PAGE"
    _page_break(d)

    d.add_paragraph("CBM DEFECT SUMMARY")
    _summary_table(d, ["NO.", "EQUIPMENT", "DEFECT AREA", "SEVERITY"], cbm_rows)
    _page_break(d)

    d.add_paragraph("VISUAL DEFECT SUMMARY")
    _summary_table(d, ["NO.", "EQUIPMENT", "DEFECT DESCRIPTION", "ADDITIONAL REMARKS"], vi_rows)
    _page_break(d)

    _cbm_defect_page(d)
    _page_break(d)

    d.add_paragraph("SUBSTATION CONDITION")
    d.add_table(rows=1, cols=1).rows[0].cells[0].text = "CONDITION"
    d.add_picture(_png_bytes(), width=Inches(0.5))
    _page_break(d)

    d.add_paragraph("NORMAL/DEFECT STICKER")
    d.add_paragraph("NORMAL STICKER")
    d.save(path)


class _AcceptEverythingParser(CbmDefectHeaderParser):
    """Accepts any page and records the first non-empty cell of its first table."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    def parse(self, target, sequence_hint="", index=1, slice_path=None):
        grid = self._extract_grid(target)
        first = next((c for row in grid for c in row if c), "")
        self.seen.append(first)
        n = len(self.seen)
        return CbmDefectSliceMetadata(
            equipment_category="swg",
            equipment_instance="swg1",
            sequence=f"p{n:02d}",
            equipment_id=f"STUB{n}",
            defect_area="OVERVIEW",
            filename=f"stub_{n:02d}.docx",
            slice_path=slice_path,
        )


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


def _first_cell(path: Path) -> str:
    t = docx.Document(path).tables[0]
    return next((c.text.strip() for r in t.rows for c in r.cells if c.text.strip()), "")


def test_overflowing_summaries_yield_only_the_real_cbm_defect_page(tmp_path, word_app):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, cbm_rows=OVERFLOW_ROWS, vi_rows=OVERFLOW_ROWS)
    sections = WordComDocumentSlicer(word_app=word_app).slice_sections(
        src, tmp_path / "out", station=STATION, expected_vi_defect_count=OVERFLOW_ROWS
    )
    assert [_first_cell(p) for p in sections.cbm_defect_pages] == ["Substation"]


@pytest.mark.parametrize(
    ("cbm_rows", "vi_rows"),
    [(OVERFLOW_ROWS, 3), (3, OVERFLOW_ROWS)],
    ids=["cbm-summary-overflows", "vi-summary-overflows"],
)
def test_scan_skips_every_page_a_summary_table_covers(tmp_path, word_app, cbm_rows, vi_rows):
    src = tmp_path / "qr.docx"
    _build_quick_report(src, cbm_rows=cbm_rows, vi_rows=vi_rows)
    parser = _AcceptEverythingParser()
    WordComDocumentSlicer(word_app=word_app, header_parser=parser).slice_sections(
        src, tmp_path / "out", station=STATION, expected_vi_defect_count=vi_rows
    )
    assert parser.seen == ["Substation"], f"scan offered non-CBM pages to the parser: {parser.seen}"
