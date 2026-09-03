"""Unit tests for BatchComSession context manager and COM application lifecycle management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.postprocessing.converters import (
    BatchComSession,
    ComDocumentConverter,
    FakeDocumentConverter,
    batch_com_session,
)


def test_batch_com_session_successful_lifecycle() -> None:
    """Test that BatchComSession initializes COM, dispatches Word & Excel, configures properties, and cleans up on exit."""
    mock_word = MagicMock()
    mock_excel = MagicMock()

    def dispatch_side_effect(prog_id: str) -> MagicMock:
        if prog_id == "Word.Application":
            return mock_word
        if prog_id == "Excel.Application":
            return mock_excel
        raise ValueError(f"Unexpected ProgID: {prog_id}")

    with patch("pythoncom.CoInitialize") as mock_co_init, patch(
        "pythoncom.CoUninitialize"
    ) as mock_co_uninit, patch(
        "win32com.client.DispatchEx", side_effect=dispatch_side_effect
    ) as mock_dispatch:
        with batch_com_session() as session:
            assert isinstance(session, BatchComSession)
            assert session.word_app is mock_word
            assert session.excel_app is mock_excel

            # Word configuration
            assert mock_word.Visible is False
            assert mock_word.DisplayAlerts == 0

            # Excel configuration
            assert mock_excel.Visible is False
            assert mock_excel.DisplayAlerts is False

            # Neither app should be quit inside context
            mock_word.Quit.assert_not_called()
            mock_excel.Quit.assert_not_called()

        # After context exit
        mock_co_init.assert_called_once()
        assert mock_dispatch.call_count == 2
        mock_word.Quit.assert_called_once()
        mock_excel.Quit.assert_called_once()
        mock_co_uninit.assert_called_once()
        assert session.word_app is None
        assert session.excel_app is None


def test_batch_com_session_cleanup_on_exception() -> None:
    """Test that BatchComSession guarantees .Quit() and CoUninitialize() cleanup even on unhandled exceptions."""
    mock_word = MagicMock()
    mock_excel = MagicMock()

    def dispatch_side_effect(prog_id: str) -> MagicMock:
        if prog_id == "Word.Application":
            return mock_word
        if prog_id == "Excel.Application":
            return mock_excel
        raise ValueError(f"Unexpected ProgID: {prog_id}")

    with patch("pythoncom.CoInitialize"), patch("pythoncom.CoUninitialize") as mock_co_uninit, patch(
        "win32com.client.DispatchEx", side_effect=dispatch_side_effect
    ):
        with pytest.raises(RuntimeError, match="Simulated failure inside batch"):
            with BatchComSession() as session:
                assert session.word_app is mock_word
                assert session.excel_app is mock_excel
                raise RuntimeError("Simulated failure inside batch")

        # Must ensure cleanup ran despite exception
        mock_word.Quit.assert_called_once()
        mock_excel.Quit.assert_called_once()
        mock_co_uninit.assert_called_once()
        assert session.word_app is None
        assert session.excel_app is None


def test_batch_com_session_resilient_to_quit_exceptions() -> None:
    """Test that if Word.Quit() raises an exception, Excel.Quit() and CoUninitialize() still execute."""
    mock_word = MagicMock()
    mock_excel = MagicMock()
    mock_word.Quit.side_effect = RuntimeError("Word RPC failed")

    def dispatch_side_effect(prog_id: str) -> MagicMock:
        if prog_id == "Word.Application":
            return mock_word
        if prog_id == "Excel.Application":
            return mock_excel
        raise ValueError(f"Unexpected ProgID: {prog_id}")

    with patch("pythoncom.CoInitialize"), patch("pythoncom.CoUninitialize") as mock_co_uninit, patch(
        "win32com.client.DispatchEx", side_effect=dispatch_side_effect
    ):
        with batch_com_session() as session:
            assert session.word_app is mock_word
            assert session.excel_app is mock_excel

        mock_word.Quit.assert_called_once()
        mock_excel.Quit.assert_called_once()
        mock_co_uninit.assert_called_once()


def test_batch_com_session_non_windows_mock_fallback() -> None:
    """Test graceful handling when pythoncom or win32com is not available."""
    with patch.dict("sys.modules", {"pythoncom": None, "win32com": None, "win32com.client": None}):
        session = BatchComSession(suppress_errors=True)
        with session:
            assert session.word_app is None
            assert session.excel_app is None
        # Exiting should not raise
        assert session.word_app is None


def test_com_document_converter_reuses_session_apps(tmp_path: Path) -> None:
    """Test that ComDocumentConverter accepts session/apps and does not quit them across multiple conversions."""
    converter = ComDocumentConverter()

    mock_word = MagicMock()
    mock_doc1 = MagicMock()
    mock_doc2 = MagicMock()
    mock_word.Documents.Open.side_effect = [mock_doc1, mock_doc2]

    mock_excel = MagicMock()
    mock_wb1 = MagicMock()
    mock_wb2 = MagicMock()
    mock_ws1 = MagicMock()
    mock_ws1.Name = "PCE Testsheet"
    mock_ws2 = MagicMock()
    mock_ws2.Name = "PCE Testsheet"
    mock_wb1.Worksheets = [mock_ws1]
    mock_wb2.Worksheets = [mock_ws2]
    mock_excel.Workbooks.Open.side_effect = [mock_wb1, mock_wb2]

    def fake_word_export(OutputFileName: str, **kwargs) -> None:
        Path(OutputFileName).write_bytes(b"%PDF-word")

    mock_doc1.ExportAsFixedFormat.side_effect = fake_word_export
    mock_doc2.ExportAsFixedFormat.side_effect = fake_word_export

    def fake_excel_export(format_type: int, path: str, *args, **kwargs) -> None:
        Path(path).write_bytes(b"%PDF-excel")

    mock_ws1.ExportAsFixedFormat.side_effect = fake_excel_export
    mock_ws2.ExportAsFixedFormat.side_effect = fake_excel_export

    session = BatchComSession(word_app=mock_word, excel_app=mock_excel)

    # First substation
    docx1 = tmp_path / "substation1.docx"
    docx1.write_bytes(b"content1")
    pdf_docx1 = tmp_path / "substation1_qr.pdf"

    xlsx1 = tmp_path / "substation1.xlsx"
    xlsx1.write_bytes(b"content1")
    pdf_xlsx1 = tmp_path / "substation1_ts.pdf"

    converter.convert_docx_to_pdf(docx1, pdf_docx1, session=session)
    converter.convert_testsheet_to_pdf(xlsx1, pdf_xlsx1, session=session)

    # Second substation
    docx2 = tmp_path / "substation2.docx"
    docx2.write_bytes(b"content2")
    pdf_docx2 = tmp_path / "substation2_qr.pdf"

    xlsx2 = tmp_path / "substation2.xlsx"
    xlsx2.write_bytes(b"content2")
    pdf_xlsx2 = tmp_path / "substation2_ts.pdf"

    converter.convert_docx_to_pdf(docx2, pdf_docx2, session=session)
    converter.convert_testsheet_to_pdf(xlsx2, pdf_xlsx2, session=session)

    # Verify documents were opened and closed
    assert mock_word.Documents.Open.call_count == 2
    assert mock_doc1.Close.call_count == 1
    assert mock_doc2.Close.call_count == 1

    assert mock_excel.Workbooks.Open.call_count == 2
    assert mock_wb1.Close.call_count == 1
    assert mock_wb2.Close.call_count == 1

    # Neither Word nor Excel should have been quit by individual conversions
    mock_word.Quit.assert_not_called()
    mock_excel.Quit.assert_not_called()

    # Now close session
    session.close()
    mock_word.Quit.assert_called_once()
    mock_excel.Quit.assert_called_once()


def test_fake_document_converter_with_session(tmp_path: Path) -> None:
    """Test that FakeDocumentConverter accepts session and excel_app/word_app kwargs without error."""
    fake_converter = FakeDocumentConverter()
    session = BatchComSession(word_app=MagicMock(), excel_app=MagicMock())

    docx_path = tmp_path / "test.docx"
    docx_path.write_bytes(b"docx")
    out_docx_pdf = tmp_path / "test_docx.pdf"

    xlsx_path = tmp_path / "test.xlsx"
    xlsx_path.write_bytes(b"xlsx")
    out_xlsx_pdf = tmp_path / "test_xlsx.pdf"

    result_docx = fake_converter.convert_docx_to_pdf(docx_path, out_docx_pdf, session=session)
    result_xlsx = fake_converter.convert_testsheet_to_pdf(xlsx_path, out_xlsx_pdf, session=session)

    assert result_docx.exists()
    assert result_xlsx.exists()
    assert len(fake_converter.convert_docx_calls) == 1
    assert len(fake_converter.convert_testsheet_calls) == 1
