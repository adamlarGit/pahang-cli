"""Unit tests for compiler and slicer copy-paste clipboard resilience (#63)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.full_report.slicer import _slice_range_to_doc
from src.quick_report.compiler import (
    WordComDocumentCompiler,
    pywintypes,
)


def _make_com_error() -> Exception:
    """Create a COM error simulating error 4605 (wdErrClipboardEmptyOrInvalid)."""
    if pywintypes and hasattr(pywintypes, "com_error"):
        return pywintypes.com_error(-2146823683, "This method or property is not available because the Clipboard is empty or not valid", None, None)
    return RuntimeError("COM Error 4605: Clipboard empty or invalid")


def test_compiler_retries_copy_and_paste_on_transient_paste_error(tmp_path: Path):
    """WordComDocumentCompiler catches transient paste COM error, zeroes clipboard, re-copies and succeeds."""
    p1 = tmp_path / "part1.docx"
    out = tmp_path / "out.docx"
    p1.touch()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc = MagicMock()
    mock_rng = MagicMock()

    mock_word.Documents.Add.return_value = mock_main_doc
    mock_word.Documents.Open.return_value = mock_part_doc
    mock_main_doc.Content = mock_rng
    mock_main_doc.Tables.Count = 0
    mock_rng.Information.return_value = False

    compiler = WordComDocumentCompiler(word_app=mock_word)

    # Simulate _paste_with_retry raising COM error on first attempt, then succeeding on second attempt
    paste_calls = []

    def mock_paste(rng, max_attempts=5, delay=0.15):
        paste_calls.append(len(paste_calls) + 1)
        if len(paste_calls) == 1:
            raise _make_com_error()
        return None

    with patch("src.quick_report.compiler._paste_with_retry", side_effect=mock_paste):
        with patch("src.quick_report.compiler.time.sleep") as mock_sleep:
            res = compiler.compile([p1], out)

    assert res == out.resolve()
    # Content.Copy() must be called twice (once for initial attempt, once for retry)
    assert mock_part_doc.Content.Copy.call_count == 2
    assert len(paste_calls) == 2
    # Verify sleep of 0.25s occurred during backoff
    mock_sleep.assert_any_call(0.25)
    mock_main_doc.SaveAs2.assert_called_once_with(str(out.resolve()))


def test_compiler_re_raises_after_three_failed_paste_attempts(tmp_path: Path):
    """WordComDocumentCompiler re-raises the paste exception after 3 failed attempts."""
    p1 = tmp_path / "part1.docx"
    out = tmp_path / "out.docx"
    p1.touch()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc = MagicMock()
    mock_rng = MagicMock()

    mock_word.Documents.Add.return_value = mock_main_doc
    mock_word.Documents.Open.return_value = mock_part_doc
    mock_main_doc.Content = mock_rng
    mock_main_doc.Tables.Count = 0
    mock_rng.Information.return_value = False

    compiler = WordComDocumentCompiler(word_app=mock_word)

    with patch("src.quick_report.compiler._paste_with_retry", side_effect=_make_com_error()):
        with patch("src.quick_report.compiler.time.sleep"):
            with pytest.raises(Exception, match=r"Clipboard.*(empty|valid)"):
                compiler.compile([p1], out)

    # 3 attempts made, each attempting .Copy()
    assert mock_part_doc.Content.Copy.call_count == 3


def test_slicer_retries_copy_and_paste_on_transient_paste_error(tmp_path: Path):
    """_slice_range_to_doc catches transient paste error, clears clipboard, re-copies and succeeds."""
    out = tmp_path / "sliced.docx"

    mock_word = MagicMock()
    mock_source_doc = MagicMock()
    mock_new_doc = MagicMock()
    mock_range = MagicMock()

    mock_word.Documents.Add.return_value = mock_new_doc
    mock_source_doc.Range.return_value = mock_range

    paste_calls = []

    def mock_paste(rng, max_attempts=5, delay=0.15):
        paste_calls.append(len(paste_calls) + 1)
        if len(paste_calls) == 1:
            raise _make_com_error()
        return None

    with patch("src.full_report.slicer._paste_with_retry", side_effect=mock_paste):
        with patch("src.full_report.slicer.time.sleep") as mock_sleep:
            res = _slice_range_to_doc(
                word_app=mock_word,
                source_doc=mock_source_doc,
                start_pos=10,
                end_pos=100,
                output_path=out,
                max_copy_paste_attempts=3,
            )

    assert res == out.resolve()
    # rng.Copy() must be called twice
    assert mock_range.Copy.call_count == 2
    assert len(paste_calls) == 2
    mock_sleep.assert_any_call(0.25)
    mock_new_doc.SaveAs2.assert_called_once_with(str(out.resolve()))


def test_slicer_re_raises_after_max_failed_paste_attempts(tmp_path: Path):
    """_slice_range_to_doc re-raises paste exception after max attempts fail."""
    out = tmp_path / "sliced.docx"

    mock_word = MagicMock()
    mock_source_doc = MagicMock()
    mock_new_doc = MagicMock()
    mock_range = MagicMock()

    mock_word.Documents.Add.return_value = mock_new_doc
    mock_source_doc.Range.return_value = mock_range

    with patch("src.full_report.slicer._paste_with_retry", side_effect=_make_com_error()):
        with patch("src.full_report.slicer.time.sleep"):
            with pytest.raises(Exception, match=r"Clipboard.*(empty|valid)"):
                _slice_range_to_doc(
                    word_app=mock_word,
                    source_doc=mock_source_doc,
                    start_pos=10,
                    end_pos=100,
                    output_path=out,
                    max_copy_paste_attempts=3,
                )

    assert mock_range.Copy.call_count == 3
