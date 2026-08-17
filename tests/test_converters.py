from pathlib import Path
from unittest.mock import MagicMock, patch

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

    docx_path = tmp_path / "test.docx"
    docx_pdf_path = tmp_path / "test_docx.pdf"
    docx_path.write_bytes(b"dummy_docx")
    docx_result = converter.convert_docx_to_pdf(docx_path, docx_pdf_path)

    assert docx_result.exists()
    assert len(converter.convert_docx_calls) == 1


def test_convert_docx_to_pdf_with_provided_word_app(tmp_path) -> None:
    """Test that ComDocumentConverter reuses provided word_app without quitting it."""
    converter = ComDocumentConverter()
    docx_path = tmp_path / "sample.docx"
    pdf_path = tmp_path / "sample.pdf"
    docx_path.write_bytes(b"docx_content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_save_as(path, FileFormat):
        Path(path).write_bytes(b"%PDF-mock")

    mock_doc.SaveAs2.side_effect = fake_save_as

    result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

    assert result == pdf_path
    assert pdf_path.exists()
    mock_word.Documents.Open.assert_called_once_with(str(docx_path.resolve()))
    mock_doc.SaveAs2.assert_called_once_with(str(pdf_path.resolve()), FileFormat=17)
    mock_doc.Close.assert_called_once_with(SaveChanges=False)
    # word_app must NOT be quit when passed in
    mock_word.Quit.assert_not_called()


@patch("pythoncom.CoUninitialize")
@patch("pythoncom.CoInitialize")
@patch("win32com.client.DispatchEx")
def test_convert_docx_to_pdf_standalone_lifecycle(
    mock_dispatch_ex: MagicMock,
    mock_co_init: MagicMock,
    mock_co_uninit: MagicMock,
    tmp_path: Path,
) -> None:
    """Test that ComDocumentConverter initializes and quits Word when word_app is None."""
    converter = ComDocumentConverter()
    docx_path = tmp_path / "standalone.docx"
    pdf_path = tmp_path / "standalone.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_dispatch_ex.return_value = mock_word
    mock_word.Documents.Open.return_value = mock_doc

    def fake_save_as(path, FileFormat):
        Path(path).write_bytes(b"%PDF-standalone")

    mock_doc.SaveAs2.side_effect = fake_save_as

    result = converter.convert_docx_to_pdf(docx_path, pdf_path)

    assert result == pdf_path
    assert pdf_path.exists()
    mock_co_init.assert_called_once()
    mock_dispatch_ex.assert_called_once_with("Word.Application")
    mock_word.Quit.assert_called_once()
    mock_co_uninit.assert_called_once()



