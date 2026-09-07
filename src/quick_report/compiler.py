"""DocumentCompiler seam isolating Microsoft Word COM document assembly."""

from __future__ import annotations

import ctypes
import gc
import logging
from pathlib import Path
import sys
import time
from typing import Any, Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None

try:
    import pywintypes
except ImportError:
    pywintypes = None


def _clear_clipboard() -> None:
    """Clear Windows clipboard to eliminate Word COM OLE serialization stall on document close."""
    comp_mod = sys.modules.get("src.quick_report.composer")
    if (
        comp_mod
        and hasattr(comp_mod, "_clear_clipboard")
        and getattr(comp_mod, "_clear_clipboard") is not _clear_clipboard
    ):
        getattr(comp_mod, "_clear_clipboard")()
        return

    for _ in range(3):
        try:
            if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
                if ctypes.windll.user32.OpenClipboard(None):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()
                    return
        except Exception:
            pass
        time.sleep(0.01)


def _collapse_and_escape_table(main_doc: Any) -> Any:
    """Collapse range to document end, inserting a minimal paragraph after table if selection is inside a table."""
    rng = main_doc.Content
    rng.Collapse(0)  # wdCollapseEnd = 0
    if rng.Information(12):  # 12 = wdWithInTable
        if main_doc.Tables.Count > 0:
            last_table = main_doc.Tables(main_doc.Tables.Count)
            last_table.Range.InsertParagraphAfter()
            # Minimize the escape paragraph to prevent blank page overflow.
            escape_rng = last_table.Range
            escape_rng.Collapse(0)  # wdCollapseEnd
            escape_rng.MoveEnd(1, 1)  # wdCharacter = 1, extend by 1 char
            escape_rng.Font.Size = 1
            escape_rng.ParagraphFormat.SpaceBefore = 0
            escape_rng.ParagraphFormat.SpaceAfter = 0
            escape_rng.ParagraphFormat.LineSpacingRule = 0  # wdLineSpaceSingle
        rng = main_doc.Content
        rng.Collapse(0)
    return rng


def _paste_with_retry(rng: Any, max_attempts: int = 5, delay: float = 0.15) -> None:
    """Retry rng.PasteAndFormat(16) / rng.Paste() up to max_attempts times to preserve source formatting and handle COM errors."""
    exceptions: tuple[type[BaseException], ...]
    if pywintypes and hasattr(pywintypes, "com_error"):
        exceptions = (pywintypes.com_error, Exception)
    else:
        exceptions = (Exception,)

    for attempt in range(1, max_attempts + 1):
        try:
            if hasattr(rng, "PasteAndFormat"):
                try:
                    rng.PasteAndFormat(16)  # 16 = wdFormatOriginalFormatting
                    return
                except (AttributeError, TypeError):
                    rng.Paste()
                    return
            else:
                rng.Paste()
                return
        except exceptions as exc:
            if attempt == max_attempts:
                logger.error("rng paste failed after %d attempts: %s", max_attempts, exc)
                raise
            time.sleep(delay)


def _terminate_word_process(pid: int | None) -> None:
    """Safely terminate Word COM process if still running in background after Quit."""
    if not pid:
        return
    try:
        is_alive = False
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                is_alive = True
        else:
            is_alive = True

        if is_alive:
            import subprocess

            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        pass


def _get_win32com() -> Any:
    wf_mod = sys.modules.get("src.workflows.quick_report")
    if wf_mod and hasattr(wf_mod, "win32com") and getattr(wf_mod, "win32com") is not win32com:
        return getattr(wf_mod, "win32com")
    return win32com


def _get_pythoncom() -> Any:
    wf_mod = sys.modules.get("src.workflows.quick_report")
    if wf_mod and hasattr(wf_mod, "pythoncom") and getattr(wf_mod, "pythoncom") is not pythoncom:
        return getattr(wf_mod, "pythoncom")
    return pythoncom


def _get_terminate_fn() -> Any:
    wf_mod = sys.modules.get("src.workflows.quick_report")
    if (
        wf_mod
        and hasattr(wf_mod, "_terminate_word_process")
        and getattr(wf_mod, "_terminate_word_process") is not _terminate_word_process
    ):
        return getattr(wf_mod, "_terminate_word_process")
    return _terminate_word_process


@runtime_checkable
class DocumentCompiler(Protocol):
    """External seam isolating Microsoft Word COM document assembly."""

    def compile(self, parts: Sequence[Path], output_path: Path) -> Path: ...


class WordComDocumentCompiler:
    """Production adapter: assembles parts via Word COM copy/paste pipeline."""

    def compile(
        self, parts: Sequence[Path], output_path: Path, word_app: Any = None
    ) -> Path:
        if not parts:
            return output_path

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if word_app is not None:
            main_doc = None
            try:
                main_doc = word_app.Documents.Add()
                for idx, part in enumerate(parts):
                    part_path = str(Path(part).resolve())
                    part_doc = None
                    try:
                        part_doc = word_app.Documents.Open(part_path, False, True)
                        part_doc.Content.Copy()

                        rng = _collapse_and_escape_table(main_doc)
                        if idx > 0:
                            rng.InsertBreak(7)  # wdPageBreak = 7
                            rng = _collapse_and_escape_table(main_doc)

                        _paste_with_retry(rng)
                    finally:
                        _clear_clipboard()
                        if part_doc is not None:
                            try:
                                part_doc.Close(False)
                            except Exception:
                                pass
                            part_doc = None

                main_doc.SaveAs2(str(output_path))
                main_doc.Close(False)
                main_doc = None
                return output_path
            finally:
                _clear_clipboard()
                if main_doc is not None:
                    try:
                        main_doc.Close(False)
                    except Exception:
                        pass
                    main_doc = None

        if not (win32com and getattr(win32com, "client", None) and pythoncom):
            raise RuntimeError("win32com is required for Quick Report compilation.")

        co_initialized = False
        dispatched_word = None
        word_pid = None
        main_doc = None
        try:
            pythoncom.CoInitialize()
            co_initialized = True
            dispatched_word = win32com.client.Dispatch("Word.Application")
            try:
                import win32process

                hwnd = getattr(dispatched_word, "Hwnd", None)
                if hwnd:
                    _, word_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                word_pid = None

            dispatched_word.Visible = False
            dispatched_word.ScreenUpdating = False
            dispatched_word.DisplayAlerts = 0

            main_doc = dispatched_word.Documents.Add()
            for idx, part in enumerate(parts):
                part_path = str(Path(part).resolve())
                part_doc = None
                try:
                    part_doc = dispatched_word.Documents.Open(part_path, False, True)
                    part_doc.Content.Copy()

                    rng = _collapse_and_escape_table(main_doc)
                    if idx > 0:
                        rng.InsertBreak(7)  # wdPageBreak = 7
                        rng = _collapse_and_escape_table(main_doc)

                    _paste_with_retry(rng)
                finally:
                    _clear_clipboard()
                    if part_doc is not None:
                        try:
                            part_doc.Close(False)
                        except Exception:
                            pass
                        part_doc = None

            main_doc.SaveAs2(str(output_path))
            main_doc.Close(False)
            main_doc = None
            return output_path
        finally:
            _clear_clipboard()
            if main_doc is not None:
                try:
                    main_doc.Close(False)
                except Exception:
                    pass
                main_doc = None

            if dispatched_word is not None:
                try:
                    dispatched_word.ScreenUpdating = True
                except Exception:
                    pass
                try:
                    dispatched_word.Quit()
                except Exception:
                    pass
                dispatched_word = None
                gc.collect()

            if word_pid is not None:
                _terminate_word_process(word_pid)

            if co_initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
