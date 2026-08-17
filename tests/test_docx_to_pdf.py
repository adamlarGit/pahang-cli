"""Unit tests for docx_to_pdf workflow and COM session lifecycle management."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.postprocessing.converters import ComDocumentConverter, FakeDocumentConverter
from src.workflows.docx_to_pdf import convert_docx_folder_to_pdf, DocxToPdfSummary


def test_convert_docx_folder_to_pdf_empty_folder(tmp_path: Path) -> None:
    """Test that an empty directory returns summary with converted_count=0."""
    converter = FakeDocumentConverter()
    summary = convert_docx_folder_to_pdf(tmp_path, converter=converter)

    assert isinstance(summary, DocxToPdfSummary)
    assert summary.converted_count == 0
    assert summary.input_directory == tmp_path
    assert len(converter.convert_docx_calls) == 0


def test_convert_docx_folder_to_pdf_nonexistent_folder() -> None:
    """Test that FileNotFoundError is raised for a nonexistent directory."""
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        convert_docx_folder_to_pdf(Path("C:/nonexistent_folder_xyz_123"))


def test_convert_docx_folder_to_pdf_fake_converter(tmp_path: Path) -> None:
    """Test batch conversion using FakeDocumentConverter skips temporary files."""
    f1 = tmp_path / "001. Doc A.docx"
    f2 = tmp_path / "002. Doc B.docx"
    temp_lock = tmp_path / "~$001. Doc A.docx"
    other_file = tmp_path / "notes.txt"

    f1.write_bytes(b"dummy1")
    f2.write_bytes(b"dummy2")
    temp_lock.write_bytes(b"lock")
    other_file.write_text("notes")

    sink_messages: list[str] = []
    converter = FakeDocumentConverter()

    summary = convert_docx_folder_to_pdf(
        tmp_path,
        converter=converter,
        progress_sink=sink_messages.append,
    )

    assert summary.converted_count == 2
    assert len(converter.convert_docx_calls) == 2
    # Verify outputs were generated
    assert (tmp_path / "001. Doc A.pdf").exists()
    assert (tmp_path / "002. Doc B.pdf").exists()
    assert not (tmp_path / "~$001. Doc A.pdf").exists()
    assert len(sink_messages) >= 3  # 2 file progresses + 1 complete


@patch("src.workflows.docx_to_pdf.pythoncom")
@patch("src.workflows.docx_to_pdf.win32com.client.DispatchEx")
def test_convert_docx_folder_to_pdf_com_session_lifecycle(
    mock_dispatch_ex: MagicMock,
    mock_pythoncom: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify Word.Application is spawned ONCE, passed to converter, and Quit() ONCE in finally."""
    f1 = tmp_path / "doc1.docx"
    f2 = tmp_path / "doc2.docx"
    f3 = tmp_path / "doc3.docx"
    f1.touch()
    f2.touch()
    f3.touch()

    mock_word_app = MagicMock()
    mock_dispatch_ex.return_value = mock_word_app

    mock_converter = MagicMock(spec=ComDocumentConverter)

    summary = convert_docx_folder_to_pdf(
        tmp_path,
        converter=mock_converter,
        progress_sink=None,
    )

    assert summary.converted_count == 3
    # COM initialized once
    mock_pythoncom.CoInitialize.assert_called_once()
    mock_dispatch_ex.assert_called_once_with("Word.Application")
    assert mock_word_app.Visible is False
    assert mock_word_app.DisplayAlerts == 0

    # Converter called 3 times with the exact same word_app session
    assert mock_converter.convert_docx_to_pdf.call_count == 3
    for call in mock_converter.convert_docx_to_pdf.call_args_list:
        assert call.kwargs.get("word_app") == mock_word_app

    # Word Quit and COM uninitialized once in finally
    mock_word_app.Quit.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()


@patch("src.workflows.docx_to_pdf.pythoncom")
@patch("src.workflows.docx_to_pdf.win32com.client.DispatchEx")
def test_convert_docx_folder_to_pdf_com_exception_cleans_up(
    mock_dispatch_ex: MagicMock,
    mock_pythoncom: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify Word.Application is quit and COM uninitialized even if an error occurs during conversion."""
    f1 = tmp_path / "doc1.docx"
    f1.touch()

    mock_word_app = MagicMock()
    mock_dispatch_ex.return_value = mock_word_app

    mock_converter = MagicMock(spec=ComDocumentConverter)
    mock_converter.convert_docx_to_pdf.side_effect = RuntimeError("COM conversion failure")

    with pytest.raises(RuntimeError, match="COM conversion failure"):
        convert_docx_folder_to_pdf(tmp_path, converter=mock_converter)

    # Word Quit and COM uninitialized must still be called in finally
    mock_word_app.Quit.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()
