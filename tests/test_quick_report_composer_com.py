from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.quick_report.composer import QuickReportComposer


def test_compile_document_com_recopy_paste(tmp_path: Path):
    """Verify _compile_document calls Add(), Open(), Copy(), Paste(), SaveAs2() when compiled."""
    p1 = tmp_path / "part1.docx"
    p2 = tmp_path / "part2.docx"
    out = tmp_path / "out.docx"

    p1.touch()
    p2.touch()

    composer = QuickReportComposer()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc1 = MagicMock()
    mock_part_doc2 = MagicMock()
    mock_rng = MagicMock()

    mock_word.Documents.Add.return_value = mock_main_doc
    mock_word.Documents.Open.side_effect = [mock_part_doc1, mock_part_doc2]
    mock_main_doc.Content = mock_rng

    with (
        patch("src.quick_report.composer.win32com.client.Dispatch", return_value=mock_word),
        patch("src.quick_report.composer.pythoncom"),
    ):
        composer._compile_document([p1, p2], out)

    mock_word.Documents.Add.assert_called_once()
    assert mock_word.Documents.Open.call_count == 2
    mock_part_doc1.Content.Copy.assert_called_once()
    mock_part_doc1.Close.assert_called_once_with(False)
    mock_part_doc2.Content.Copy.assert_called_once()
    mock_part_doc2.Close.assert_called_once_with(False)

    mock_rng.InsertBreak.assert_called_once_with(7)
    assert mock_rng.Paste.call_count == 2
    mock_main_doc.SaveAs2.assert_called_once_with(str(out.resolve()))
    mock_main_doc.Close.assert_called_once_with(False)
    mock_word.Quit.assert_called_once()


def test_compile_document_with_external_word_app(tmp_path: Path):
    """Verify _compile_document reuses provided word_app without quitting it."""
    p1 = tmp_path / "part1.docx"
    out = tmp_path / "out.docx"
    p1.touch()

    composer = QuickReportComposer()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc = MagicMock()
    mock_rng = MagicMock()

    mock_word.Documents.Add.return_value = mock_main_doc
    mock_word.Documents.Open.return_value = mock_part_doc
    mock_main_doc.Content = mock_rng

    composer._compile_document([p1], out, word_app=mock_word)

    mock_word.Documents.Add.assert_called_once()
    mock_part_doc.Content.Copy.assert_called_once()
    mock_part_doc.Close.assert_called_once_with(False)
    mock_rng.Paste.assert_called_once()
    mock_main_doc.SaveAs2.assert_called_once_with(str(out.resolve()))
    mock_main_doc.Close.assert_called_once_with(False)
    mock_word.Quit.assert_not_called()


def test_compile_document_raises_when_win32com_missing(tmp_path: Path):
    """Verify _compile_document raises RuntimeError when win32com/pythoncom is missing."""
    composer = QuickReportComposer()
    p1 = tmp_path / "part1.docx"
    out = tmp_path / "out.docx"

    with patch("src.quick_report.composer.win32com", None):
        with pytest.raises(RuntimeError, match="win32com is required"):
            composer._compile_document([p1], out)
