import os
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from src.postprocessing.converters import ComDocumentConverter, FakeDocumentConverter


class _NativeTmpPath:
    """Matches the unique temp file native export writes to: <folder>/.tmp_native_<token>.pdf."""

    def __eq__(self, other: object) -> bool:
        name = Path(str(other)).name
        return name.startswith(".tmp_native_") and name.endswith(".pdf")

    def __repr__(self) -> str:
        return "<.tmp_native_*.pdf>"


def _write_real_pdf(path) -> None:
    """Write a valid one-page PDF (native export validation opens the file)."""
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()



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
    converter = ComDocumentConverter(try_adobe_printer=False)
    docx_path = tmp_path / "sample.docx"
    pdf_path = tmp_path / "sample.pdf"
    docx_path.write_bytes(b"docx_content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

    assert result == pdf_path
    assert pdf_path.exists()
    mock_word.Documents.Open.assert_called_once_with(str(docx_path.resolve()))
    mock_doc.ExportAsFixedFormat.assert_called_once_with(
        OutputFileName=_NativeTmpPath(),
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
    converter = ComDocumentConverter(try_adobe_printer=False)
    docx_path = tmp_path / "standalone.docx"
    pdf_path = tmp_path / "standalone.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_dispatch_ex.return_value = mock_word
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

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


def test_convert_docx_to_pdf_fallback_when_adobe_printer_missing(tmp_path: Path) -> None:
    """Test fallback to ExportAsFixedFormat(OptimizeFor=0) when Adobe PDF printer is not available on host."""
    converter = ComDocumentConverter(try_adobe_printer=True)
    docx_path = tmp_path / "no_adobe.docx"
    pdf_path = tmp_path / "no_adobe.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    with patch.object(converter, "_find_adobe_pdf_printer", return_value=None):
        result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

        assert result == pdf_path
        assert pdf_path.exists()
        mock_doc.PrintOut.assert_not_called()
        mock_doc.ExportAsFixedFormat.assert_called_once_with(
            OutputFileName=_NativeTmpPath(),
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


def test_convert_docx_to_pdf_fallback_when_distiller_missing(tmp_path: Path) -> None:
    """Test fallback to ExportAsFixedFormat when Adobe PDF printer exists but Acrobat Distiller registry keys are missing."""
    converter = ComDocumentConverter(try_adobe_printer=True)
    docx_path = tmp_path / "no_distiller.docx"
    pdf_path = tmp_path / "no_distiller.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    with (
        patch.object(converter, "_find_adobe_pdf_printer", return_value="Adobe PDF on Ne07:"),
        patch.object(converter, "_is_distiller_available", return_value=False),
    ):
        result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

        assert result == pdf_path
        mock_doc.PrintOut.assert_not_called()
        mock_doc.ExportAsFixedFormat.assert_called_once()


def test_convert_docx_to_pdf_fallback_when_try_adobe_printer_false(tmp_path: Path) -> None:
    """Test that try_adobe_printer=False directly routes to native ExportAsFixedFormat without printer checks."""
    converter = ComDocumentConverter(try_adobe_printer=False)
    docx_path = tmp_path / "disabled_adobe.docx"
    pdf_path = tmp_path / "disabled_adobe.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    with patch.object(converter, "_find_adobe_pdf_printer") as mock_find:
        result = converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)

        assert result == pdf_path
        mock_find.assert_not_called()
        mock_doc.PrintOut.assert_not_called()
        mock_doc.ExportAsFixedFormat.assert_called_once()


def test_printer_job_control_registration_and_cleanup_deterministic(tmp_path: Path) -> None:
    """Verify registry automation for PrinterJobControl registers entries for WINWORD.EXE and splwow64.exe and deletes them."""
    import winreg

    converter = ComDocumentConverter()
    pdf_path = tmp_path / "sample_out.pdf"

    mock_word = MagicMock()
    mock_word.Path = r"C:\Office"

    set_calls = []
    delete_calls = []

    mock_key = MagicMock()

    def fake_set_value(key, name, reserved, type_, val):
        set_calls.append((name, val))

    def fake_delete_value(key, name):
        delete_calls.append(name)

    with (
        patch("winreg.CreateKey", return_value=mock_key),
        patch("winreg.OpenKey", return_value=mock_key),
        patch("winreg.SetValueEx", side_effect=fake_set_value),
        patch("winreg.DeleteValue", side_effect=fake_delete_value),
    ):
        entries = converter._register_printer_job_control(mock_word, pdf_path)

        assert "WINWORD.EXE" in entries
        assert "splwow64.exe" in entries
        assert any("splwow64.exe" in e and "\\" in e for e in entries)
        assert any(r"C:\Office\WINWORD.EXE" in e for e in entries)

        # Check all registered names received the absolute PDF path
        target_str = str(pdf_path.resolve())
        for name, val in set_calls:
            assert val == target_str

        # Now clean up
        converter._cleanup_printer_job_control(entries)
        for e in entries:
            assert e in delete_calls


def test_detect_distiller_joboptions_preset_registry_selection() -> None:
    """Test joboptions preset detection prioritizes High Quality Print(1), then High Quality Print."""
    converter = ComDocumentConverter()

    # Case 1: High Quality Print(1) is available
    with (
        patch("winreg.OpenKey"),
        patch(
            "winreg.EnumValue",
            side_effect=[
                ("Standard", "desc", None),
                ("High Quality Print(1)", "desc", None),
                ("High Quality Print", "desc", None),
                OSError("No more data"),
            ],
        ),
    ):
        assert converter._detect_distiller_joboptions_preset() == "High Quality Print(1)"

    # Case 2: Only High Quality Print is available
    with (
        patch("winreg.OpenKey"),
        patch(
            "winreg.EnumValue",
            side_effect=[
                ("Standard", "desc", None),
                ("High Quality Print", "desc", None),
                OSError("No more data"),
            ],
        ),
    ):
        assert converter._detect_distiller_joboptions_preset() == "High Quality Print"

    # Case 3: Neither found in registry -> default to High Quality Print(1)
    with (
        patch("winreg.OpenKey", side_effect=OSError("Key not found")),
        patch("pathlib.Path.exists", return_value=False),
    ):
        assert converter._detect_distiller_joboptions_preset() == "High Quality Print(1)"


def test_transient_distiller_joboptions_set_and_restore() -> None:
    """Test that _set_transient_distiller_joboptions captures original JobOptions and restores them faithfully."""
    import winreg

    converter = ComDocumentConverter()
    mock_root = MagicMock()
    mock_root.__enter__.return_value = mock_root
    mock_sub = MagicMock()
    mock_sub.__enter__.return_value = mock_sub

    with (
        patch("winreg.OpenKey", side_effect=[mock_root, mock_sub, mock_sub]),
        patch("winreg.EnumKey", side_effect=["DC", OSError("No more keys")]),
        patch("winreg.QueryValueEx", return_value=("Standard", winreg.REG_SZ)),
        patch("winreg.SetValueEx") as mock_set,
    ):
        backup = converter._set_transient_distiller_joboptions("High Quality Print(1)")
        assert backup == {"": "Standard", "DC": "Standard"}
        mock_set.assert_called_with(mock_sub, "JobOptions", 0, winreg.REG_SZ, "High Quality Print(1)")

    # Test restoration
    with (
        patch("winreg.OpenKey", return_value=mock_sub),
        patch("winreg.SetValueEx") as mock_restore_set,
    ):
        converter._restore_distiller_joboptions(backup)
        assert mock_restore_set.call_count == 2
        mock_restore_set.assert_called_with(mock_sub, "JobOptions", 0, winreg.REG_SZ, "Standard")


def test_get_installed_printers_enumeration() -> None:
    """Test get_installed_printers enumerates Devices and maps lowercase printer names to full specs."""
    from src.postprocessing.converters import get_installed_printers

    with (
        patch("winreg.OpenKey"),
        patch(
            "winreg.EnumValue",
            side_effect=[
                ("Adobe PDF", "winspool,Ne07:", None),
                ("Microsoft Print to PDF", "winspool,Ne02:", None),
                ("DirectPrinter", "winspool", None),
                OSError("No more items"),
            ],
        ),
    ):
        printers = get_installed_printers()
        assert printers["adobe pdf"] == "Adobe PDF on Ne07:"
        assert printers["microsoft print to pdf"] == "Microsoft Print to PDF on Ne02:"
        assert printers["directprinter"] == "DirectPrinter"


def test_wait_for_pdf_success_with_eof(tmp_path: Path) -> None:
    """Test _wait_for_pdf returns True immediately when file exists, is unlocked, and contains %%EOF."""
    converter = ComDocumentConverter()
    pdf_path = tmp_path / "valid.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    assert converter._wait_for_pdf(pdf_path, timeout=1.0) is True


def test_wait_for_pdf_failure_on_incomplete_file_or_timeout(tmp_path: Path) -> None:
    """Test _wait_for_pdf returns False when file is incomplete/missing %%EOF or never appears."""
    converter = ComDocumentConverter()
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.write_bytes(b"%PDF-incomplete-without-eof")

    # When file lacks %%EOF and size doesn't stabilize twice before timeout
    assert converter._wait_for_pdf(pdf_path, timeout=0.05, poll_interval=0.01) is False

    # When file does not exist at all
    missing_path = tmp_path / "does_not_exist.pdf"
    assert converter._wait_for_pdf(missing_path, timeout=0.05, poll_interval=0.01) is False


def test_compute_dynamic_conversion_timeout(tmp_path: Path) -> None:
    """Test dynamic timeout scaling based on .docx file size: min 90s, +2s/MB, capped at 180s."""
    from src.postprocessing.converters import compute_dynamic_conversion_timeout

    # 1. Non-existent or 0MB file -> 90.0s
    missing_file = tmp_path / "missing.docx"
    assert compute_dynamic_conversion_timeout(missing_file) == 90.0

    # 2. 10MB file -> 60 + 10*2 = 80 -> clamped to 90.0s min
    file_10mb = tmp_path / "doc_10mb.docx"
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = 10 * 1024 * 1024
        assert compute_dynamic_conversion_timeout(file_10mb) == 90.0

    # 3. 20MB file -> 60 + 20*2 = 100.0s
    file_20mb = tmp_path / "doc_20mb.docx"
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = 20 * 1024 * 1024
        assert compute_dynamic_conversion_timeout(file_20mb) == 100.0

    # 4. 35MB file -> 60 + 35*2 = 130.0s
    file_35mb = tmp_path / "doc_35mb.docx"
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = 35 * 1024 * 1024
        assert compute_dynamic_conversion_timeout(file_35mb) == 130.0

    # 5. 70MB file -> 60 + 70*2 = 200 -> clamped to 180.0s max
    file_70mb = tmp_path / "doc_70mb.docx"
    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value.st_size = 70 * 1024 * 1024
        assert compute_dynamic_conversion_timeout(file_70mb) == 180.0


def test_two_tier_pdf_completion_probe(tmp_path: Path) -> None:
    """Test two-tier probe: structural marker check and exclusive write-lock check."""
    from src.postprocessing.converters import probe_two_tier_pdf_completion

    pdf_file = tmp_path / "probe_test.pdf"

    # Non-existent
    assert probe_two_tier_pdf_completion(pdf_file) == (False, False)

    # Empty
    pdf_file.write_bytes(b"")
    assert probe_two_tier_pdf_completion(pdf_file) == (False, False)

    # Missing %%EOF
    pdf_file.write_bytes(b"%PDF-1.7 corrupt incomplete content")
    assert probe_two_tier_pdf_completion(pdf_file) == (False, False)

    # Valid structural content
    valid_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    pdf_file.write_bytes(valid_bytes)

    # When unlocked -> (True, True)
    assert probe_two_tier_pdf_completion(pdf_file) == (True, True)

    # When locked exclusively by an open file handle
    # On Windows, opening with "r+b" or holding an exclusive handle simulates lock
    with patch("builtins.open") as mock_open:
        # First call: rb reads header, second seeks to tail -> succeeds. Third call: r+b raises PermissionError
        from io import BytesIO

        mock_stream = BytesIO(valid_bytes)

        def fake_open(p, mode="r", *args, **kwargs):
            if "r+b" in mode or "rb+" in mode:
                raise PermissionError("File locked by Acrobat Distiller")
            mock_stream.seek(0)
            return mock_stream

        mock_open.side_effect = fake_open
        structural, exclusive = probe_two_tier_pdf_completion(pdf_file)
        assert structural is True
        assert exclusive is False


def test_conversion_feedback_monitor_phased_transitions(tmp_path: Path) -> None:
    """Test ConversionFeedbackMonitor transitions QUEUED -> SPOOLING -> DISTILLING -> LOCK_RELEASE -> VERIFIED."""
    from src.postprocessing.converters import (
        ConversionFeedbackMonitor,
        ConversionFeedbackState,
    )

    pdf_path = tmp_path / "phased.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    mock_word = MagicMock()
    # 1st poll: BackgroundPrintingStatus=1 (SPOOLING)
    # 2nd poll: BackgroundPrintingStatus=0 (DISTILLING/LOCK_RELEASE/VERIFIED)
    mock_word.BackgroundPrintingStatus = 1

    monitor = ConversionFeedbackMonitor(
        target_pdf=pdf_path,
        timeout=1.0,
        poll_interval=0.01,
        word_app=mock_word,
    )

    def fake_spool_drain(*args):
        mock_word.BackgroundPrintingStatus = 0

    with patch("time.sleep", side_effect=fake_spool_drain):
        success = monitor.wait_for_completion()

    assert success is True
    assert monitor.state == ConversionFeedbackState.VERIFIED
    assert ConversionFeedbackState.QUEUED in monitor.history
    assert ConversionFeedbackState.SPOOLING in monitor.history
    assert ConversionFeedbackState.LOCK_RELEASE in monitor.history
    assert ConversionFeedbackState.VERIFIED in monitor.history


def test_conversion_feedback_monitor_failure_on_timeout(tmp_path: Path) -> None:
    """Test ConversionFeedbackMonitor transitions to FAILED when file never appears before timeout."""
    from src.postprocessing.converters import (
        ConversionFeedbackMonitor,
        ConversionFeedbackState,
    )

    pdf_path = tmp_path / "never_created.pdf"
    monitor = ConversionFeedbackMonitor(
        target_pdf=pdf_path,
        timeout=0.02,
        poll_interval=0.005,
    )
    success = monitor.wait_for_completion()

    assert success is False
    assert monitor.state == ConversionFeedbackState.FAILED
    assert monitor.history[-1] == ConversionFeedbackState.FAILED


def test_drain_word_spooler_waits_for_completion() -> None:
    """Test drain_word_spooler polls until BackgroundPrintingStatus drains to 0."""
    from src.postprocessing.converters import drain_word_spooler

    mock_word = MagicMock()
    statuses = [2, 1, 0]

    def get_status(*args, **kwargs):
        if statuses:
            return statuses.pop(0)
        return 0

    type(mock_word).BackgroundPrintingStatus = property(get_status)

    drain_word_spooler(mock_word, max_wait=1.0, poll_interval=0.001)
    assert len(statuses) == 0


def test_drain_word_spooler_safe_with_unconfigured_mock() -> None:
    """Test drain_word_spooler handles unconfigured MagicMock without throwing TypeError."""
    from src.postprocessing.converters import drain_word_spooler

    mock_word = MagicMock()
    # BackgroundPrintingStatus is a MagicMock, not int/float
    drain_word_spooler(mock_word, max_wait=0.05, poll_interval=0.001)


def test_convert_docx_to_pdf_spooler_drain_guard_called(tmp_path: Path) -> None:
    """Verify convert_docx_to_pdf calls drain_word_spooler before closing the document."""
    converter = ComDocumentConverter(try_adobe_printer=False)
    docx_path = tmp_path / "drain_test.docx"
    pdf_path = tmp_path / "drain_test.pdf"
    docx_path.write_bytes(b"content")

    mock_word = MagicMock()
    mock_doc = MagicMock()
    mock_word.Documents.Open.return_value = mock_doc

    def fake_export(OutputFileName, **kwargs):
        _write_real_pdf(OutputFileName)

    mock_doc.ExportAsFixedFormat.side_effect = fake_export

    with patch("src.postprocessing.converters.drain_word_spooler") as mock_drain:
        converter.convert_docx_to_pdf(docx_path, pdf_path, word_app=mock_word)
        mock_drain.assert_called()


def test_get_active_printer_job_ids_and_purge() -> None:
    """Test get_active_printer_job_ids queries win32print and purge_printer_jobs deletes stalled jobs."""
    from src.postprocessing.converters import get_active_printer_job_ids, purge_printer_jobs

    mock_handle = MagicMock()
    mock_jobs = ({"JobId": 101, "pDocument": "Doc1"}, {"JobId": 102, "pDocument": "Doc2"})

    with (
        patch("win32print.OpenPrinter", return_value=mock_handle),
        patch("win32print.ClosePrinter"),
        patch("win32print.EnumJobs", return_value=mock_jobs),
        patch("win32print.SetJob") as mock_set_job,
    ):
        active_ids = get_active_printer_job_ids("Adobe PDF on Ne07:")
        assert active_ids == {101, 102}

        # Purge only job 101
        purged = purge_printer_jobs("Adobe PDF", job_ids={101})
        assert purged == 1
        mock_set_job.assert_called_once_with(mock_handle, 101, 0, None, 5)

        # Purge all jobs
        mock_set_job.reset_mock()
        purged_all = purge_printer_jobs("Adobe PDF")
        assert purged_all == 2
        assert mock_set_job.call_count == 2


def test_suppress_view_print_output_registry_dword() -> None:
    """Test _suppress_view_print_output writes ViewPrintOutput = 0 (DWORD) under PrinterJobControl and subkeys."""
    converter = ComDocumentConverter()
    mock_word = MagicMock()
    mock_word.Path = r"C:\Program Files\Microsoft Office\Office16"

    mock_key = MagicMock()
    created_paths: list[str] = []
    set_values: list[tuple[str, str, int, int]] = []

    def fake_create_key(root, subpath):
        created_paths.append(subpath)
        return mock_key

    def fake_set_value(key, name, reserved, type_, val):
        set_values.append((name, val, type_))

    with (
        patch("winreg.CreateKey", side_effect=fake_create_key),
        patch("winreg.SetValueEx", side_effect=fake_set_value),
        patch.dict("os.environ", {"USERNAME": "TESTUSER"}),
    ):
        ret = converter._suppress_view_print_output(mock_word)
        assert ret is None

        assert any("WINWORD.EXE" in p for p in created_paths)
        assert any("splwow64.exe" in p for p in created_paths)
        assert any("WINWORD.EXE:TESTUSER" in p for p in created_paths)
        assert any("splwow64.exe:TESTUSER" in p for p in created_paths)

        # Check that ViewPrintOutput was written as REG_DWORD (4) with value 0
        import winreg

        for name, val, val_type in set_values:
            assert name == "ViewPrintOutput"
            assert val == 0
            assert val_type == winreg.REG_DWORD


def test_terminate_stray_acrobat_processes_surgical() -> None:
    """Test terminate_stray_acrobat_processes terminates only Acrobat.exe instances referencing .tmp_conv_."""
    from src.postprocessing.converters import terminate_stray_acrobat_processes

    proc_stray = MagicMock()
    proc_stray.ProcessId = 1234
    proc_stray.CommandLine = r'"C:\Acrobat\Acrobat.exe" "C:\Work\.tmp_conv_report.pdf"'

    proc_unrelated = MagicMock()
    proc_unrelated.ProcessId = 5678
    proc_unrelated.CommandLine = r'"C:\Acrobat\Acrobat.exe" "C:\User\Manual.pdf"'

    mock_wmi = MagicMock()
    mock_wmi.ExecQuery.return_value = [proc_stray, proc_unrelated]

    with patch("win32com.client.GetObject", return_value=mock_wmi):
        killed = terminate_stray_acrobat_processes()
        assert killed == 1
        proc_stray.Terminate.assert_called_once()
        proc_unrelated.Terminate.assert_not_called()


def test_terminate_hung_distiller_processes() -> None:
    """Test terminate_hung_distiller_processes terminates acrodist.exe -Embedding."""
    from src.postprocessing.converters import terminate_hung_distiller_processes

    distiller_hung = MagicMock()
    distiller_hung.ProcessId = 9999
    distiller_hung.CommandLine = r'"C:\Acrobat\acrodist.exe" -Embedding'

    distiller_other = MagicMock()
    distiller_other.ProcessId = 8888
    distiller_other.CommandLine = r'"C:\Acrobat\acrodist.exe" /other'

    mock_wmi = MagicMock()
    mock_wmi.ExecQuery.return_value = [distiller_hung, distiller_other]

    with patch("win32com.client.GetObject", return_value=mock_wmi):
        killed = terminate_hung_distiller_processes()
        assert killed == 1
        distiller_hung.Terminate.assert_called_once()
        distiller_other.Terminate.assert_not_called()


def test_safe_unlink_with_retry(tmp_path: Path) -> None:
    """Test safe_unlink_with_retry succeeds immediately, retries on lock, and fails gracefully."""
    from src.postprocessing.converters import safe_unlink_with_retry

    # 1. Non-existent file returns True
    missing = tmp_path / "missing.tmp"
    assert safe_unlink_with_retry(missing) is True

    # 2. Existing unlocked file unlinked immediately
    f = tmp_path / "unlocked.tmp"
    f.write_text("temp")
    assert safe_unlink_with_retry(f) is True
    assert not f.exists()

    # 3. Retries on PermissionError and succeeds once lock released
    locked_f = tmp_path / "locked.tmp"
    locked_f.write_text("locked")

    call_count = 0

    def fake_unlink():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise PermissionError("Locked by another process")
        # Second call removes file
        os.remove(locked_f)

    with patch.object(Path, "unlink", side_effect=fake_unlink), patch("time.sleep"):
        success = safe_unlink_with_retry(locked_f, max_attempts=3)
        assert success is True
        assert call_count == 2


def test_safe_replace_with_retry(tmp_path: Path) -> None:
    """Test safe_replace_with_retry replaces destination, retries on transient lock, and handles missing source."""
    from src.postprocessing.converters import safe_replace_with_retry

    # 1. Missing source returns False
    missing_src = tmp_path / "missing.tmp"
    dst = tmp_path / "dst.tmp"
    assert safe_replace_with_retry(missing_src, dst) is False

    # 2. Immediate successful replacement
    src = tmp_path / "src.tmp"
    src.write_text("source content")
    assert safe_replace_with_retry(src, dst) is True
    assert dst.read_text() == "source content"
    assert not src.exists()

    # 3. Retries on PermissionError and succeeds once lock released
    src2 = tmp_path / "src2.tmp"
    src2.write_text("retry content")
    dst2 = tmp_path / "dst2.tmp"

    call_count = 0

    def fake_replace(s, d):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise PermissionError("Destination locked")
        Path(d).write_text(Path(s).read_text())
        Path(s).unlink()

    with patch("os.replace", side_effect=fake_replace), patch("time.sleep"):
        success = safe_replace_with_retry(src2, dst2, max_attempts=3)
        assert success is True
        assert call_count == 2


def test_cleanup_printer_job_control_preserves_persistent_view_print_output() -> None:
    """Verify _cleanup_printer_job_control never deletes ViewPrintOutput to keep suppression persistent."""
    converter = ComDocumentConverter()
    entries = ["WINWORD.EXE", "splwow64.exe", r"C:\Windows\splwow64.exe"]
    deleted_values: list[str] = []

    def fake_delete(key, val_name):
        deleted_values.append(val_name)

    mock_key = MagicMock()
    with (
        patch("winreg.OpenKey", return_value=mock_key),
        patch("winreg.DeleteValue", side_effect=fake_delete),
    ):
        converter._cleanup_printer_job_control(entries)

        assert "WINWORD.EXE" in deleted_values
        assert "splwow64.exe" in deleted_values
        assert "ViewPrintOutput" not in deleted_values


def test_calculate_exponential_delays() -> None:
    """Verify calculate_exponential_delays distributes total_wait across geometric weights."""
    import pytest
    from src.postprocessing.converters import calculate_exponential_delays

    assert calculate_exponential_delays(1, 5.0) == []
    delays = calculate_exponential_delays(5, 5.0)
    assert len(delays) == 4
    assert sum(delays) == pytest.approx(5.0)


def test_safe_unlink_with_retry_sentinel_invocation_and_defaults(tmp_path: Path) -> None:
    """Verify safe_unlink_with_retry defaults to 5 attempts, 5.0s, and invokes terminate_stray_acrobat_processes."""
    import inspect
    from src.postprocessing.converters import safe_unlink_with_retry

    sig = inspect.signature(safe_unlink_with_retry)
    assert sig.parameters["max_attempts"].default == 5
    assert sig.parameters["total_wait"].default == 5.0
    assert "logger_func" not in sig.parameters

    test_file = tmp_path / "test_file.tmp"
    test_file.write_text("data")

    # Case 1: normal unlink invokes terminate_stray_acrobat_processes before attempting unlink
    with patch("src.postprocessing.converters.terminate_stray_acrobat_processes") as mock_sentinel:
        assert safe_unlink_with_retry(test_file) is True
        assert mock_sentinel.call_count == 1
        assert not test_file.exists()

    # Case 2: retry on lock invokes sentinel on retry as well
    locked_file = tmp_path / "locked_file.tmp"
    locked_file.write_text("locked")
    attempts = 0

    def fake_unlink():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("Process holding handle")
        os.remove(locked_file)

    with (
        patch.object(Path, "unlink", side_effect=fake_unlink),
        patch("src.postprocessing.converters.terminate_stray_acrobat_processes") as mock_sentinel,
        patch("time.sleep"),
    ):
        success = safe_unlink_with_retry(locked_file, max_attempts=5, total_wait=5.0)
        assert success is True
        assert attempts == 3
        # Sentinel called once before first unlink, and twice on retries before success
        assert mock_sentinel.call_count == 3


def test_convert_docx_via_adobe_pdf_eliminates_activeprinter_thrashing(tmp_path: Path) -> None:
    """Verify _convert_docx_via_adobe_pdf avoids ActivePrinter reassignments when already Adobe PDF,
    and preserves ActivePrinter inside batch COM sessions.
    """
    from src.postprocessing.converters import BatchComSession

    converter = ComDocumentConverter()
    pdf_path = tmp_path / "output.pdf"

    def fake_print(*args, **kwargs):
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    mock_doc = MagicMock()
    mock_doc.PrintOut.side_effect = fake_print

    # Case A: Already Adobe PDF -> ActivePrinter assignment skipped, no revert
    setter_called_a = False

    class MockWordA:
        def __init__(self):
            self._printer = "Adobe PDF on Ne07:"

        @property
        def ActivePrinter(self):
            return self._printer

        @ActivePrinter.setter
        def ActivePrinter(self, val):
            nonlocal setter_called_a
            setter_called_a = True
            self._printer = val

    mock_word_a = MockWordA()

    with (
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        converter._convert_docx_via_adobe_pdf(mock_word_a, mock_doc, pdf_path, "Adobe PDF on Ne07:")
        # Setting ActivePrinter should have been skipped completely
        assert setter_called_a is False

    # Case B: Different printer and session is None -> switches to Adobe PDF, then restores original
    mock_word_b = MagicMock()
    mock_word_b.ActivePrinter = "Microsoft Print to PDF on Ne01:"
    with (
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        converter._convert_docx_via_adobe_pdf(mock_word_b, mock_doc, pdf_path, "Adobe PDF on Ne07:", session=None)
        assert mock_word_b.ActivePrinter == "Microsoft Print to PDF on Ne01:"

    # Case C: Different printer and session is NOT None (BatchComSession) -> switches to Adobe PDF, NEVER restores original
    mock_word_c = MagicMock()
    mock_word_c.ActivePrinter = "Microsoft Print to PDF on Ne01:"
    mock_session = MagicMock(spec=BatchComSession)

    with (
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        converter._convert_docx_via_adobe_pdf(mock_word_c, mock_doc, pdf_path, "Adobe PDF on Ne07:", session=mock_session)
        assert mock_word_c.ActivePrinter == "Adobe PDF on Ne07:"


def test_post_print_spooler_port_drain_guard() -> None:
    """Verify wait_for_printer_job_drain polls until tracked jobs leave JOB_STATUS_PRINTING or retire."""
    from src.postprocessing.converters import wait_for_printer_job_drain

    # Case 1: Job is in JOB_STATUS_PRINTING (0x10) then retires (queue becomes empty)
    queue_states = [
        [{"JobId": 42, "Status": 0x10}],
        [{"JobId": 42, "Status": 0x10}],
        [],  # retired
    ]

    with (
        patch("src.postprocessing.converters.get_printer_jobs_info", side_effect=queue_states),
        patch("time.sleep"),
    ):
        drained = wait_for_printer_job_drain("Adobe PDF", job_ids={42}, max_wait=5.0, poll_interval=0.01)
        assert drained is True

    # Case 2: Job transitions out of JOB_STATUS_PRINTING (e.g. status 0)
    queue_states_2 = [
        [{"JobId": 42, "Status": 0x10}],
        [{"JobId": 42, "Status": 0x0}],  # left printing
    ]

    with (
        patch("src.postprocessing.converters.get_printer_jobs_info", side_effect=queue_states_2),
        patch("time.sleep"),
    ):
        drained = wait_for_printer_job_drain("Adobe PDF", job_ids={42}, max_wait=5.0, poll_interval=0.01)
        assert drained is True

    # Case 3: Job remains hung in JOB_STATUS_PRINTING until timeout
    with (
        patch("src.postprocessing.converters.get_printer_jobs_info", return_value=[{"JobId": 42, "Status": 0x10}]),
        patch("time.sleep"),
    ):
        drained = wait_for_printer_job_drain("Adobe PDF", job_ids={42}, max_wait=0.05, poll_interval=0.01)
        assert drained is False


def test_conversion_feedback_monitor_large_spool_no_premature_stagnation_abort(tmp_path: Path) -> None:
    """Verify ConversionFeedbackMonitor does not abort large print jobs early while output file is still 0 bytes,
    allowing large PostScript spooling (e.g. 50MB-88MB) to complete under the full dynamic timeout.
    """
    from src.postprocessing.converters import (
        ConversionFeedbackMonitor,
        ConversionFeedbackState,
    )

    spooling_pdf = tmp_path / "large_spool.pdf"
    mock_word = MagicMock()
    mock_word.BackgroundPrintingStatus = 1

    monitor = ConversionFeedbackMonitor(
        target_pdf=spooling_pdf,
        timeout=1.0,
        poll_interval=0.01,
        word_app=mock_word,
        job_ids={55},
        printer_name="Adobe PDF",
    )

    # Ensure stagnation_timeout attribute is removed
    assert not hasattr(monitor, "stagnation_timeout")

    poll_count = 0

    def mock_probe(pdf_path: Path):
        nonlocal poll_count
        poll_count += 1
        # During the first 6 polls, document is still spooling 0 bytes through GDI / spooler
        if poll_count < 6:
            return False, False
        # Spooling finishes, Word BackgroundPrintingStatus drops to 0, Distiller completes output
        mock_word.BackgroundPrintingStatus = 0
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")
        return True, True

    with (
        patch("src.postprocessing.converters.probe_two_tier_pdf_completion", side_effect=mock_probe),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        success = monitor.wait_for_completion()

    assert success is True
    assert monitor.state == ConversionFeedbackState.VERIFIED
    assert ConversionFeedbackState.SPOOLING in monitor.history
    assert poll_count >= 6


def test_ensure_session_distiller_warmed_success() -> None:
    """Verify ensure_session_distiller_warmed dispatches PdfDistiller COM server in Session 1."""
    from src.postprocessing.converters import (
        _ensure_session_distiller_warmed,
        ensure_session_distiller_warmed,
    )

    mock_distiller = MagicMock(name="PdfDistillerCOM")
    with patch("win32com.client.Dispatch", return_value=mock_distiller) as mock_dispatch:
        res = ensure_session_distiller_warmed()
        assert res is mock_distiller
        mock_dispatch.assert_called_once_with("PdfDistiller.PdfDistiller")

    # Verify alias parity
    with patch("win32com.client.Dispatch", return_value=mock_distiller):
        assert _ensure_session_distiller_warmed() is mock_distiller


def test_ensure_session_distiller_warmed_failure_logs_debug(caplog) -> None:
    """Verify ensure_session_distiller_warmed degrades gracefully returning None on COM failure."""
    import logging
    from src.postprocessing.converters import ensure_session_distiller_warmed

    with (
        patch("win32com.client.Dispatch", side_effect=RuntimeError("COM class not registered")),
        caplog.at_level(logging.DEBUG),
    ):
        res = ensure_session_distiller_warmed()
        assert res is None
        assert "Could not pre-warm Acrobat Distiller COM server" in caplog.text


def test_batch_com_session_distiller_lifecycle() -> None:
    """Verify BatchComSession pre-warms Distiller in __enter__ and cleans up on __exit__."""
    from src.postprocessing.converters import BatchComSession

    mock_word = MagicMock()
    mock_excel = MagicMock()
    mock_distiller = MagicMock(name="DistillerApp")

    session = BatchComSession(word_app=mock_word, excel_app=mock_excel)
    assert session.distiller_app is None

    with patch("src.postprocessing.converters.ensure_session_distiller_warmed", return_value=mock_distiller) as mock_warm:
        with session:
            mock_warm.assert_called_once()
            assert session.distiller_app is mock_distiller

    assert session.distiller_app is None


def test_convert_docx_via_adobe_pdf_pre_warms_distiller_when_standalone(tmp_path: Path) -> None:
    """Verify _convert_docx_via_adobe_pdf pre-warms Distiller before doc.PrintOut when session is None."""
    converter = ComDocumentConverter()
    pdf_path = tmp_path / "standalone_distiller.pdf"

    mock_doc = MagicMock()
    called_sequence = []

    def fake_warm():
        called_sequence.append("warm")
        return MagicMock(name="DistillerMock")

    def fake_print(*args, **kwargs):
        called_sequence.append("print")
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    mock_doc.PrintOut.side_effect = fake_print
    mock_word = MagicMock()
    mock_word.ActivePrinter = "Adobe PDF on Ne07:"

    with (
        patch("src.postprocessing.converters.ensure_session_distiller_warmed", side_effect=fake_warm) as mock_warm,
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        success = converter._convert_docx_via_adobe_pdf(
            mock_word,
            mock_doc,
            pdf_path,
            "Adobe PDF on Ne07:",
            session=None,
        )

        assert success is True
        assert mock_warm.call_count == 1
        assert called_sequence == ["warm", "print"]


def test_convert_docx_via_adobe_pdf_reuses_distiller_from_session(tmp_path: Path) -> None:
    """Verify _convert_docx_via_adobe_pdf reuses active Distiller from BatchComSession without redundant pre-warming."""
    from src.postprocessing.converters import BatchComSession

    converter = ComDocumentConverter()
    pdf_path = tmp_path / "session_distiller.pdf"

    def fake_print(*args, **kwargs):
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    mock_doc = MagicMock()
    mock_doc.PrintOut.side_effect = fake_print
    mock_word = MagicMock()
    mock_word.ActivePrinter = "Adobe PDF on Ne07:"

    mock_session = MagicMock(spec=BatchComSession)
    mock_session.distiller_app = MagicMock(name="ActiveSessionDistiller")

    with (
        patch("src.postprocessing.converters.ensure_session_distiller_warmed") as mock_warm,
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        success = converter._convert_docx_via_adobe_pdf(
            mock_word,
            mock_doc,
            pdf_path,
            "Adobe PDF on Ne07:",
            session=mock_session,
        )

        assert success is True
        mock_warm.assert_not_called()


def test_convert_docx_via_adobe_pdf_pre_warms_if_session_distiller_is_none(tmp_path: Path) -> None:
    """Verify _convert_docx_via_adobe_pdf warms Distiller if session exists but distiller_app is None."""
    from src.postprocessing.converters import BatchComSession

    converter = ComDocumentConverter()
    pdf_path = tmp_path / "session_distiller_none.pdf"

    def fake_print(*args, **kwargs):
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

    mock_doc = MagicMock()
    mock_doc.PrintOut.side_effect = fake_print
    mock_word = MagicMock()
    mock_word.ActivePrinter = "Adobe PDF on Ne07:"

    mock_session = MagicMock(spec=BatchComSession)
    mock_session.distiller_app = None
    mock_distiller = MagicMock(name="FreshlyWarmedDistiller")

    with (
        patch("src.postprocessing.converters.ensure_session_distiller_warmed", return_value=mock_distiller) as mock_warm,
        patch.object(converter, "_register_printer_job_control", return_value=[]),
        patch.object(converter, "_suppress_view_print_output", return_value=[]),
        patch.object(converter, "_cleanup_printer_job_control"),
        patch.object(converter, "_set_transient_distiller_joboptions", return_value={}),
        patch.object(converter, "_restore_distiller_joboptions"),
        patch.object(converter, "_wait_for_pdf", return_value=True),
        patch("src.postprocessing.converters.get_active_printer_job_ids", return_value=set()),
        patch("src.postprocessing.converters.wait_for_printer_job_drain", return_value=True),
    ):
        success = converter._convert_docx_via_adobe_pdf(
            mock_word,
            mock_doc,
            pdf_path,
            "Adobe PDF on Ne07:",
            session=mock_session,
        )

        assert success is True
        mock_warm.assert_called_once()
        assert mock_session.distiller_app is mock_distiller

