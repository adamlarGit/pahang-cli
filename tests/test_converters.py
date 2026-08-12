"""Unit tests for document converters and COM PageSetup configuration."""

from unittest.mock import MagicMock

from src.postprocessing.converters import ComDocumentConverter, FakeDocumentConverter


def test_configure_target_page_setup_enforces_paper_size_and_orientation() -> None:
    """Test that _configure_target_page_setup sets A4 (9), Landscape (2), Zoom (False), FitToPagesWide (1), FitToPagesTall (1)."""
    converter = ComDocumentConverter(optimize_page_setup=True)

    mock_ws1 = MagicMock()
    mock_ws2 = MagicMock()
    mock_wb = MagicMock()
    mock_wb.Worksheets = [mock_ws1, mock_ws2]
    # Remove hasattr(mock_wb, "PageSetup") so it iterates over Worksheets
    del mock_wb.PageSetup

    converter._configure_target_page_setup(mock_wb)

    for ws in [mock_ws1, mock_ws2]:
        assert ws.PageSetup.PaperSize == 9
        assert ws.PageSetup.Orientation == 2
        assert ws.PageSetup.Zoom is False
        assert ws.PageSetup.FitToPagesWide == 1
        assert ws.PageSetup.FitToPagesTall == 1


def test_configure_target_page_setup_disabled() -> None:
    """Test that PageSetup is not modified when optimize_page_setup=False."""
    converter = ComDocumentConverter(optimize_page_setup=False)

    mock_ws = MagicMock()
    mock_wb = MagicMock()
    mock_wb.Worksheets = [mock_ws]
    del mock_wb.PageSetup

    converter._configure_target_page_setup(mock_wb)

    assert not mock_ws.PageSetup.method_calls


def test_fake_document_converter(tmp_path) -> None:
    """Test FakeDocumentConverter basic interface compliance."""
    converter = FakeDocumentConverter()
    xlsx_path = tmp_path / "test.xlsx"
    pdf_path = tmp_path / "test.pdf"

    xlsx_path.write_bytes(b"dummy")
    result = converter.convert_testsheet_to_pdf(xlsx_path, pdf_path, target_sheets=["PCE Testsheet", "PCE VI"])

    assert result.exists()
    assert len(converter.convert_testsheet_calls) == 1
