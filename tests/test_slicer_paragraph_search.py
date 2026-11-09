"""Paragraph search in the slicer: when the slow paragraph walk runs, and what gets logged (#181).

The fake models the Word behaviour the search depends on: Find ignores case and collapses its
range onto the hit, and reading a paragraph out of doc.Paragraphs costs one COM round trip.
"""
from __future__ import annotations

import logging

from src.full_report.slicer import _find_paragraph

SLICER_LOGGER = "src.full_report.slicer"


class _FakeFind:
    def __init__(self, rng: "_FakeRange") -> None:
        self._rng = rng

    def ClearFormatting(self) -> None:
        pass

    def Execute(self, text: str, *_args, **_kwargs) -> bool:
        doc = self._rng.doc
        if doc.find_error is not None:
            raise doc.find_error
        at = doc.text[self._rng.Start : self._rng.End].lower().find(text.lower())
        if at < 0:
            return False
        self._rng.Start += at
        self._rng.End = self._rng.Start + len(text)
        return True


class _FakeRange:
    def __init__(self, doc: "_FakeDocument", start: int, end: int) -> None:
        self.doc = doc
        self.Start = start
        self.End = end
        self.Find = _FakeFind(self)

    @property
    def Text(self) -> str:
        if self.doc.text_error is not None:
            raise self.doc.text_error
        return self.doc.text[self.Start : self.End]

    def Paragraphs(self, index: int) -> "_FakeParagraph":
        for start, end in self.doc.spans:
            if start <= self.Start < end:
                return _FakeParagraph(self.doc, start, end)
        raise IndexError(index)

    def Information(self, _kind: int) -> int:
        if self.doc.page_error is not None:
            raise self.doc.page_error
        return 1 + self.doc.text[: self.Start].count("\x0c")


class _FakeParagraph:
    def __init__(self, doc: "_FakeDocument", start: int, end: int) -> None:
        self.doc = doc
        self._start = start
        self._end = end

    @property
    def Range(self) -> _FakeRange:
        return _ParagraphRange(self.doc, self._start, self._end)


class _ParagraphRange(_FakeRange):
    """Stays readable when only the wide range read is failing."""

    @property
    def Text(self) -> str:
        return self.doc.text[self.Start : self.End]


class _FakeParagraphs:
    def __init__(self, doc: "_FakeDocument") -> None:
        self._doc = doc
        self.Count = len(doc.spans)

    def __call__(self, index: int) -> _FakeParagraph:
        if self._doc.walk_error is not None:
            raise self._doc.walk_error
        self._doc.walked += 1
        start, end = self._doc.spans[index - 1]
        return _FakeParagraph(self._doc, start, end)


class _FakeDocument:
    def __init__(self, *paragraphs: str) -> None:
        self.text = "".join(f"{p}\r" for p in paragraphs)
        self.spans: list[tuple[int, int]] = []
        at = 0
        for p in paragraphs:
            self.spans.append((at, at + len(p) + 1))
            at += len(p) + 1
        self.walked = 0
        self.find_error: Exception | None = None
        self.text_error: Exception | None = None
        self.page_error: Exception | None = None
        self.walk_error: Exception | None = None
        self.Paragraphs = _FakeParagraphs(self)

    @property
    def Content(self) -> _FakeRange:
        return _FakeRange(self, 0, len(self.text))

    def Range(self, start: int, end: int) -> _FakeRange:
        return _FakeRange(self, start, end)


def test_absent_heading_returns_none_without_walking_paragraphs():
    doc = _FakeDocument("FRONT PAGE", "VISUAL DEFECT SUMMARY", "SUBSTATION CONDITION")

    assert _find_paragraph(doc, "CBM DEFECT SUMMARY") is None
    assert doc.walked == 0


def test_walk_finds_exact_heading_after_case_variant_hit_and_logs_it(caplog):
    doc = _FakeDocument("Executive summary", "NOTES", "EXECUTIVE SUMMARY", "EXECUTIVE SUMMARY AGAIN")

    with caplog.at_level(logging.WARNING, logger=SLICER_LOGGER):
        result = _find_paragraph(doc, "EXECUTIVE SUMMARY")

    assert result is not None
    assert result.text == "EXECUTIVE SUMMARY\r"
    assert result.start == 24
    assert "paragraph walk" in caplog.text
    assert "'EXECUTIVE SUMMARY'" in caplog.text


def test_unreadable_range_text_still_walks_and_logs_the_read_failure(caplog):
    doc = _FakeDocument("FRONT PAGE", "SUBSTATION CONDITION")
    doc.find_error = RuntimeError("find broke")
    doc.text_error = RuntimeError("text read broke")

    with caplog.at_level(logging.WARNING, logger=SLICER_LOGGER):
        result = _find_paragraph(doc, "SUBSTATION CONDITION")

    assert result is not None
    assert result.start == 11
    assert "text read broke" in caplog.text


def test_find_failure_is_logged_and_search_still_finds_the_heading(caplog):
    doc = _FakeDocument("FRONT PAGE", "SUBSTATION CONDITION")
    doc.find_error = RuntimeError("find broke")

    with caplog.at_level(logging.WARNING, logger=SLICER_LOGGER):
        result = _find_paragraph(doc, "SUBSTATION CONDITION")

    assert result is not None
    assert result.start == 11
    assert "find broke" in caplog.text
    assert "'SUBSTATION CONDITION'" in caplog.text


def test_walk_failure_is_logged_and_reports_no_match(caplog):
    doc = _FakeDocument("Substation condition", "SUBSTATION CONDITION")
    doc.walk_error = RuntimeError("walk broke")

    with caplog.at_level(logging.WARNING, logger=SLICER_LOGGER):
        assert _find_paragraph(doc, "SUBSTATION CONDITION") is None

    assert "walk broke" in caplog.text


def test_unreadable_page_number_defaults_to_one_and_is_logged(caplog):
    doc = _FakeDocument("FRONT PAGE", "SUBSTATION CONDITION")
    doc.page_error = RuntimeError("page broke")

    with caplog.at_level(logging.WARNING, logger=SLICER_LOGGER):
        result = _find_paragraph(doc, "SUBSTATION CONDITION")

    assert result is not None
    assert result.page_number == 1
    assert "page broke" in caplog.text
