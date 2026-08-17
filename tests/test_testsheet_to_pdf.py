"""Unit tests for testsheet_to_pdf workflow and Excel COM session lifecycle management."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.postprocessing.converters import ComDocumentConverter, FakeDocumentConverter
from src.workflows.testsheet_to_pdf import convert_testsheet_folder_to_pdf, TestsheetToPdfSummary


def test_convert_testsheet_folder_to_pdf_empty_folder(tmp_path: Path) -> None:
    """Test that an empty directory returns summary with converted_count=0."""
    converter = FakeDocumentConverter()
    summary = convert_testsheet_folder_to_pdf(tmp_path, converter=converter)

    assert isinstance(summary, TestsheetToPdfSummary)
    assert summary.converted_count == 0
    assert summary.input_directory == tmp_path
    assert len(converter.convert_testsheet_calls) == 0


def test_convert_testsheet_folder_to_pdf_nonexistent_folder() -> None:
    """Test that FileNotFoundError is raised for a nonexistent directory."""
    with pytest.raises(FileNotFoundError, match="Input folder does not exist"):
        convert_testsheet_folder_to_pdf(Path("C:/nonexistent_folder_abc_999"))


def test_convert_testsheet_folder_to_pdf_fake_converter(tmp_path: Path) -> None:
    """Test batch conversion using FakeDocumentConverter skips temporary files."""
    f1 = tmp_path / "001. Testsheet A.xlsx"
    f2 = tmp_path / "002. Testsheet B.xls"
    temp_lock = tmp_path / "~$001. Testsheet A.xlsx"
    other_file = tmp_path / "notes.txt"

    f1.write_bytes(b"dummy1")
    f2.write_bytes(b"dummy2")
    temp_lock.write_bytes(b"lock")
    other_file.write_text("notes")

    sink_messages: list[str] = []
    converter = FakeDocumentConverter()

    summary = convert_testsheet_folder_to_pdf(
        tmp_path,
        converter=converter,
        progress_sink=sink_messages.append,
    )

    assert summary.converted_count == 2
    assert len(converter.convert_testsheet_calls) == 2
    assert (tmp_path / "001. Testsheet A.pdf").exists()
    assert (tmp_path / "002. Testsheet B.pdf").exists()
    assert not (tmp_path / "~$001. Testsheet A.pdf").exists()
    assert len(sink_messages) >= 3


@patch("src.workflows.testsheet_to_pdf.pythoncom")
@patch("src.workflows.testsheet_to_pdf.win32com.client.DispatchEx")
def test_convert_testsheet_folder_to_pdf_com_session_lifecycle(
    mock_dispatch_ex: MagicMock,
    mock_pythoncom: MagicMock,
    tmp_path: Path,
) -> None:
    """Verify Excel.Application is spawned ONCE, passed to converter, and Quit() ONCE in finally."""
    f1 = tmp_path / "sheet1.xlsx"
    f2 = tmp_path / "sheet2.xlsx"
    f1.touch()
    f2.touch()

    mock_excel_app = MagicMock()
    mock_dispatch_ex.return_value = mock_excel_app

    mock_converter = MagicMock(spec=ComDocumentConverter)

    summary = convert_testsheet_folder_to_pdf(
        tmp_path,
        converter=mock_converter,
        progress_sink=None,
    )

    assert summary.converted_count == 2
    mock_pythoncom.CoInitialize.assert_called_once()
    mock_dispatch_ex.assert_called_once_with("Excel.Application")
    assert mock_excel_app.Visible is False
    assert mock_excel_app.DisplayAlerts is False

    assert mock_converter.convert_testsheet_to_pdf.call_count == 2
    for call in mock_converter.convert_testsheet_to_pdf.call_args_list:
        assert call.kwargs.get("excel_app") == mock_excel_app

    mock_excel_app.Quit.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()
