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
    """Test that ComDocumentConverter reuses provided word_app without quitting it and exports high fidelity PDF."""
    converter = ComDocumentConverter()
    docx_path = tmp_path / "sample.docx"
    pdf_path = tmp_path / "sample.pdf"
    docx_path.write_bytes(b"docx_content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        Path(OutputFileName).write_bytes(b"%PDF-mock")

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

    assert result == pdf_path
    assert pdf_path.exists()
    mock_word.Documents.Open.assert_called_once_with(str(docx_path.resolve()))
    mock_doc.ExportAsFixedFormat.assert_called_once_with(
        OutputFileName=str(pdf_path.resolve()),
        ExportFormat=17,
        OpenAfterExport=False,
        OptimizeFor=0,
        Range=0,
        Item=0,
        IncludeDocProps=True,
        KeepIRM=True,
        CreateBookmarks=0,
        DocStructureTags=True,
        BitmapMissingFonts=True,
        UseISO19005_1=False,
    )
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

    def fake_export(OutputFileName, **kwargs):
        Path(OutputFileName).write_bytes(b"%PDF-standalone")

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    result = converter.convert_docx_to_pdf(docx_path, pdf_path)

    assert result == pdf_path
    assert pdf_path.exists()
    mock_co_init.assert_called_once()
    mock_dispatch_ex.assert_called_once_with("Word.Application")
    mock_doc.ExportAsFixedFormat.assert_called_once()
    mock_word.Quit.assert_called_once()
    mock_co_uninit.assert_called_once()


def test_merge_temp_pdfs_combines_pages(tmp_path: Path) -> None:
    """Test that _merge_temp_pdfs cleanly combines multiple PDF pages into one output file."""
    from PyPDF2 import PdfReader, PdfWriter

    pdf1 = tmp_path / "sheet_1.pdf"
    pdf2 = tmp_path / "sheet_2.pdf"
    out_pdf = tmp_path / "merged.pdf"

    w1 = PdfWriter()
    w1.add_blank_page(width=792.0, height=612.0)
    with open(pdf1, "wb") as f:
        w1.write(f)

    w2 = PdfWriter()
    w2.add_blank_page(width=792.0, height=612.0)
    with open(pdf2, "wb") as f:
        w2.write(f)

    converter = ComDocumentConverter()
    converter._merge_temp_pdfs([pdf1, pdf2], out_pdf)

    reader = PdfReader(str(out_pdf))
    assert len(reader.pages) == 2
    for page in reader.pages:
        assert round(float(page.mediabox.width), 2) == 792.0
        assert round(float(page.mediabox.height), 2) == 612.0


def test_configure_uniform_printer_prefers_adobe_pdf() -> None:
    """Test that configure_uniform_printer assigns Adobe PDF if available."""
    converter = ComDocumentConverter()
    mock_app = MagicMock()
    mock_app.ActivePrinter = "Brother Printer on USB01:"

    with patch("winreg.OpenKey"), patch(
        "winreg.EnumValue",
        side_effect=[
            ("Adobe PDF", "winspool,Ne07:", None),
            ("Microsoft Print to PDF", "winspool,Ne02:", None),
            OSError("No more data"),
        ],
    ):
        converter._configure_uniform_printer(mock_app)

    assert mock_app.ActivePrinter == "Adobe PDF on Ne07:"


def test_configure_uniform_printer_falls_back_to_microsoft_print_to_pdf() -> None:
    """Test that configure_uniform_printer falls back to Microsoft Print to PDF if Adobe PDF is absent."""
    converter = ComDocumentConverter()
    mock_app = MagicMock()
    mock_app.ActivePrinter = "Brother Printer on USB01:"

    with patch("winreg.OpenKey"), patch(
        "winreg.EnumValue",
        side_effect=[
            ("Brother Printer", "winspool,USB01:", None),
            ("Microsoft Print to PDF", "winspool,Ne02:", None),
            OSError("No more data"),
        ],
    ):
        converter._configure_uniform_printer(mock_app)

    assert mock_app.ActivePrinter == "Microsoft Print to PDF on Ne02:"
