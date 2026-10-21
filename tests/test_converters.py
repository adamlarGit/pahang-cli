from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import pymupdf as fitz
except ImportError:
    import fitz

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


def test_com_document_converter_merge_pdfs_batch_pymupdf(tmp_path: Path) -> None:
    """Test that merge_pdfs_batch uses PyMuPDF, writes via temp file with garbage=3 and deflate=True, and replaces atomically."""
    doc1 = fitz.open()
    doc1.new_page(width=595, height=842)
    pdf1 = tmp_path / "input1.pdf"
    doc1.save(pdf1)
    doc1.close()

    doc2 = fitz.open()
    doc2.new_page(width=595, height=842)
    pdf2 = tmp_path / "input2.pdf"
    doc2.save(pdf2)
    doc2.close()

    converter = ComDocumentConverter()

    # Track save calls to verify garbage=3, deflate=True
    real_save = fitz.Document.save
    save_calls = []

    def tracking_save(self, *args, **kwargs):
        save_calls.append((args, kwargs))
        return real_save(self, *args, **kwargs)

    with patch.object(fitz.Document, "save", autospec=True, side_effect=tracking_save):
        out_pdf = tmp_path / "merged.pdf"
        res = converter.merge_pdfs_batch([pdf1, pdf2], out_pdf)

    assert res == out_pdf
    assert out_pdf.exists()
    assert len(save_calls) == 1
    # Check save kwargs: garbage=3, deflate=True
    kwargs = save_calls[0][1]
    assert kwargs.get("garbage") == 3
    assert kwargs.get("deflate") is True

    # Test in-place merge where output_pdf == pdf1
    res_inplace = converter.merge_pdfs_batch([pdf1, pdf2], pdf1)
    assert res_inplace == pdf1
    with fitz.open(pdf1) as merged_doc:
        assert len(merged_doc) == 2


def test_com_document_converter_merge_pdfs_combines_documents(tmp_path: Path) -> None:
    """Test that merge_pdfs and _merge_temp_pdfs correctly combine documents into output_pdf."""
    doc1 = fitz.open()
    doc1.new_page(width=400, height=400)
    p1 = tmp_path / "a.pdf"
    doc1.save(p1)
    doc1.close()

    doc2 = fitz.open()
    doc2.new_page(width=400, height=400)
    p2 = tmp_path / "b.pdf"
    doc2.save(p2)
    doc2.close()

    doc3 = fitz.open()
    doc3.new_page(width=400, height=400)
    p3 = tmp_path / "c.pdf"
    doc3.save(p3)
    doc3.close()

    converter = ComDocumentConverter()
    out1 = tmp_path / "out1.pdf"
    res1 = converter.merge_pdfs(p1, p2, out1)
    assert res1 == out1
    with fitz.open(out1) as res_doc:
        assert len(res_doc) == 2

    out2 = tmp_path / "out2.pdf"
    res2 = converter._merge_temp_pdfs([p1, p2, p3], out2)
    assert res2 == out2
    with fitz.open(out2) as res_doc:
        assert len(res_doc) == 3


def test_fake_document_converter_pymupdf_parity_and_telemetry(tmp_path: Path) -> None:
    """Test FakeDocumentConverter merges using PyMuPDF without PyPDF2, maintaining telemetry."""
    fake = FakeDocumentConverter()
    doc1 = fitz.open()
    doc1.new_page(width=595, height=842)
    p1 = tmp_path / "part1.pdf"
    doc1.save(p1)
    doc1.close()

    doc2 = fitz.open()
    doc2.new_page(width=595, height=842)
    p2 = tmp_path / "part2.pdf"
    doc2.save(p2)
    doc2.close()

    out_batch = tmp_path / "out_batch.pdf"

    with patch("PyPDF2.PdfReader", side_effect=AssertionError("PyPDF2 must not be used")):
        # 1. merge_pdfs_batch with existing files
        fake.merge_pdfs_batch([p1, p2], out_batch)
        assert len(fake.merge_pdfs_batch_calls) == 1
        assert len(fake.merge_pdfs_calls) == 0
        with fitz.open(out_batch) as doc:
            assert len(doc) == 2

        # 2. merge_pdfs with existing files
        out_merge = tmp_path / "out_merge.pdf"
        fake.merge_pdfs(p1, p2, out_merge)
        assert len(fake.merge_pdfs_calls) == 1
        assert len(fake.merge_pdfs_batch_calls) == 1
        with fitz.open(out_merge) as doc:
            assert len(doc) == 2

        # 3. Non-existent files fallback
        missing1 = tmp_path / "nonexistent1.pdf"
        missing2 = tmp_path / "nonexistent2.pdf"
        out_missing_batch = tmp_path / "out_missing_batch.pdf"
        fake.merge_pdfs_batch([missing1, missing2], out_missing_batch)
        with fitz.open(out_missing_batch) as doc:
            assert len(doc) == 2

        out_missing_merge = tmp_path / "out_missing_merge.pdf"
        fake.merge_pdfs(missing1, missing2, out_missing_merge)
        with fitz.open(out_missing_merge) as doc:
            assert len(doc) == 2


def _create_synthetic_pdf_with_xobject(path: Path, xobject_name: str, color_val: int) -> None:
    """Create a synthetic PDF containing an explicit named XObject in its resources and content stream."""
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0)
    pix.clear_with(color_val)
    page.insert_image(fitz.Rect(10, 10, 50, 50), stream=pix.tobytes("png"))

    tmp_path = path.with_suffix(".tmp.pdf")
    doc.save(tmp_path)
    doc.close()

    doc = fitz.open(tmp_path)
    for xref in range(1, doc.xref_length()):
        txt = doc.xref_object(xref)
        if "/fzImg0" in txt:
            doc.update_object(xref, txt.replace("/fzImg0", f"/{xobject_name}"))
        if doc.xref_is_stream(xref):
            st = doc.xref_stream(xref)
            if b"/fzImg0" in st:
                doc.update_stream(xref, st.replace(b"/fzImg0", f"/{xobject_name}".encode("ascii")))
    doc.save(path)
    doc.close()
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass


def test_com_document_converter_xobject_collision_regression(tmp_path: Path) -> None:
    """Regression test: verify that merging PDFs with colliding /XObject identifiers (e.g. /Image41)

    preserves 100% distinct indirect XObject resources and produces zero
    'cannot find XObject resource' syntax errors during PyMuPDF rendering.
    """
    p1 = tmp_path / "part_01.pdf"
    p2 = tmp_path / "part_02.pdf"
    p3 = tmp_path / "part_03.pdf"

    _create_synthetic_pdf_with_xobject(p1, "Image41", 50)
    _create_synthetic_pdf_with_xobject(p2, "Image41", 120)
    _create_synthetic_pdf_with_xobject(p3, "Image41", 200)

    converter = ComDocumentConverter()
    out_pdf = tmp_path / "merged_deliverable.pdf"
    converter.merge_pdfs_batch([p1, p2, p3], out_pdf)

    assert out_pdf.exists()

    fitz.TOOLS.reset_mupdf_warnings()
    with fitz.open(out_pdf) as merged_doc:
        assert len(merged_doc) == 3
        for idx in range(len(merged_doc)):
            page = merged_doc[idx]
            pix = page.get_pixmap()
            assert pix.width == 300 and pix.height == 300
            images = page.get_images()
            assert len(images) == 1
            assert images[0][7] == "Image41"

    warnings = fitz.TOOLS.mupdf_warnings()
    assert "cannot find XObject resource" not in warnings
    assert "syntax error" not in warnings




