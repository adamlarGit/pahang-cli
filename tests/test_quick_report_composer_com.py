from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.quick_report.composer import QuickReportComposer, _paste_with_retry


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
    mock_main_doc.Tables.Count = 0
    mock_rng.Information.return_value = False

    composer._compile_document([p1, p2], out, word_app=mock_word)

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
    mock_main_doc.Tables.Count = 0
    mock_rng.Information.return_value = False

    composer._compile_document([p1], out, word_app=mock_word)

    mock_word.Documents.Add.assert_called_once()
    mock_part_doc.Content.Copy.assert_called_once()
    mock_part_doc.Close.assert_called_once_with(False)
    mock_rng.Paste.assert_called_once()
    mock_main_doc.SaveAs2.assert_called_once_with(str(out.resolve()))
    mock_main_doc.Close.assert_called_once_with(False)


def test_compile_document_raises_when_win32com_missing(tmp_path: Path):
    """Verify _compile_document raises RuntimeError when word_app is None."""
    composer = QuickReportComposer()
    p1 = tmp_path / "part1.docx"
    out = tmp_path / "out.docx"

    with pytest.raises(RuntimeError, match="word_app is required for Quick Report compilation."):
        composer._compile_document([p1], out, word_app=None)


def test_paste_with_retry_success_first_attempt():
    """Verify _paste_with_retry succeeds on first attempt without retrying."""
    mock_rng = MagicMock()
    _paste_with_retry(mock_rng, max_attempts=3, delay=0.01)
    mock_rng.Paste.assert_called_once()


def test_paste_with_retry_success_after_retries():
    """Verify _paste_with_retry retries rng.Paste() until success."""
    mock_rng = MagicMock()
    mock_rng.Paste.side_effect = [Exception("Clipboard locked"), Exception("COM error"), None]
    _paste_with_retry(mock_rng, max_attempts=5, delay=0.01)
    assert mock_rng.Paste.call_count == 3


def test_paste_with_retry_fails_and_reraises():
    """Verify _paste_with_retry re-raises exception when all retry attempts fail."""
    mock_rng = MagicMock()
    mock_rng.Paste.side_effect = Exception("Persistent COM failure")
    with pytest.raises(Exception, match="Persistent COM failure"):
        _paste_with_retry(mock_rng, max_attempts=3, delay=0.01)
    assert mock_rng.Paste.call_count == 3


def test_compile_document_escapes_table_cell(tmp_path: Path):
    """Verify _compile_document escapes table cells when rng is inside a table."""
    p1 = tmp_path / "part1.docx"
    p2 = tmp_path / "part2.docx"
    out = tmp_path / "out.docx"
    p1.touch()
    p2.touch()

    composer = QuickReportComposer()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc = MagicMock()
    mock_rng = MagicMock()
    mock_table = MagicMock()

    mock_word.Documents.Add.return_value = mock_main_doc
    mock_word.Documents.Open.return_value = mock_part_doc
    mock_main_doc.Content = mock_rng
    mock_main_doc.Tables.Count = 1
    mock_main_doc.Tables.return_value = mock_table
    mock_rng.Information.return_value = True  # wdWithInTable = True

    composer._compile_document([p1, p2], out, word_app=mock_word)

    # Verify InsertParagraphAfter was called to escape table cell
    assert mock_table.Range.InsertParagraphAfter.call_count >= 2
    mock_main_doc.Tables.assert_called_with(1)
