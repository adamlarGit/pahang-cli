"""Paragraph search against real Word: which paragraph wins, not how it was found (#181)."""
from __future__ import annotations

from pathlib import Path

import docx
import pytest
from docx.enum.text import WD_BREAK

win32com_client = pytest.importorskip("win32com.client")
pythoncom = pytest.importorskip("pythoncom")

from src.full_report.slicer import _find_paragraph  # noqa: E402

pytestmark = pytest.mark.word


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


@pytest.fixture(scope="module")
def report(word_app, tmp_path_factory):
    d = docx.Document()
    d.add_paragraph("Executive Summary")
    d.add_paragraph("VISUAL DEFECT SUMMARY")
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    d.add_paragraph("VISUAL DEFECT")
    d.add_paragraph("VISUAL DEFECT")
    d.add_paragraph("EXECUTIVE SUMMARY")
    d.add_table(rows=1, cols=1).rows[0].cells[0].text = "CELL HEADING"
    d.add_paragraph("TAIL")
    path: Path = tmp_path_factory.mktemp("search") / "report.docx"
    d.save(path)
    doc = word_app.Documents.Open(str(path), False, True)
    yield doc
    doc.Close(False)


def test_absent_heading_is_not_found(report):
    assert _find_paragraph(report, "CBM DEFECT SUMMARY") is None


def test_case_variant_is_passed_over_for_the_exact_heading_on_a_later_page(report):
    found = _find_paragraph(report, "EXECUTIVE SUMMARY")

    assert found is not None
    assert found.text == "EXECUTIVE SUMMARY\r"
    assert found.page_number == 2


def test_case_variant_alone_is_not_a_match(report):
    assert _find_paragraph(report, "Executive SUMMARY") is None


def test_excluded_match_is_passed_over_and_first_duplicate_wins(report):
    found = _find_paragraph(report, "VISUAL DEFECT", must_not_contain="SUMMARY")

    assert found is not None
    assert found.text == "VISUAL DEFECT\r"
    assert found.page_number == 2


def test_start_bound_selects_the_second_duplicate(report):
    first = _find_paragraph(report, "VISUAL DEFECT", must_not_contain="SUMMARY")

    second = _find_paragraph(report, "VISUAL DEFECT", start_pos=first.end)

    assert second is not None
    assert second.start == first.end


def test_end_bound_hides_a_heading_beyond_it(report):
    first = _find_paragraph(report, "VISUAL DEFECT", must_not_contain="SUMMARY")

    assert _find_paragraph(report, "EXECUTIVE SUMMARY", start_pos=0, end_pos=first.start) is None


def test_heading_inside_a_table_cell_is_found(report):
    found = _find_paragraph(report, "CELL HEADING")

    assert found is not None
    assert found.page_number == 2


def test_start_bound_hides_a_heading_before_it(report):
    first = _find_paragraph(report, "VISUAL DEFECT", must_not_contain="SUMMARY")

    assert _find_paragraph(report, "VISUAL DEFECT SUMMARY", start_pos=first.start) is None
