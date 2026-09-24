"""DocumentCompiler seam isolating Microsoft Word COM document assembly."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import gc
import logging
from pathlib import Path
import time
from typing import Any, Iterator, Protocol, Sequence, runtime_checkable

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

__all__ = [
    "DocumentCompiler",
    "FakeDocumentCompiler",
    "WordComDocumentCompiler",
]


def _clear_clipboard() -> None:
    """Clear Windows clipboard to eliminate Word COM OLE serialization stall on document close."""
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


# Windows COM HRESULT for RPC_E_DISCONNECTED (0x80010108 / -2147417848)
RPC_E_DISCONNECTED: int = -2147417848
RPC_E_DISCONNECTED_UNSIGNED: int = 0x80010108


def _is_rpc_disconnected_error(exc: BaseException) -> bool:
    """Check if exception represents RPC_E_DISCONNECTED (0x80010108 / -2147417848)."""
    hresult = getattr(exc, "hresult", None)
    if hresult in (RPC_E_DISCONNECTED, RPC_E_DISCONNECTED_UNSIGNED):
        return True
    if hasattr(exc, "args") and exc.args and isinstance(exc.args[0], int):
        if exc.args[0] in (RPC_E_DISCONNECTED, RPC_E_DISCONNECTED_UNSIGNED):
            return True
    return False


def _safe_close_document(
    doc: Any, word_app: Any = None, expected_name: str | None = None
) -> None:
    """Safely close a COM document, handling RPC_E_DISCONNECTED post-SaveAs2 gracefully."""
    if doc is not None:
        try:
            doc.Close(False)
            return
        except Exception as exc:
            if not _is_rpc_disconnected_error(exc):
                raise

    if word_app is not None and expected_name:
        try:
            docs = getattr(word_app, "Documents", None)
            if docs is not None and getattr(docs, "Count", 0) > 0:
                try:
                    item_getter = getattr(docs, "Item", None)
                    if callable(item_getter):
                        item_getter(expected_name).Close(False)
                    else:
                        docs(expected_name).Close(False)
                    return
                except Exception:
                    pass
                for i in range(docs.Count, 0, -1):
                    try:
                        open_doc = docs.Item(i) if hasattr(docs, "Item") else docs(i)
                        if getattr(open_doc, "Name", "") == expected_name:
                            open_doc.Close(False)
                            break
                    except Exception:
                        pass
        except Exception:
            pass


def _terminate_word_process(pid: int | None, timeout_ms: int = 500) -> None:
    """Safely terminate Word COM process if still running in background after Quit."""
    if not pid:
        return
    try:
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            # SYNCHRONIZE (0x00100000) | PROCESS_QUERY_LIMITED_INFORMATION (0x1000)
            handle = ctypes.windll.kernel32.OpenProcess(0x00101000, False, pid)
            if handle:
                wait_res = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
                ctypes.windll.kernel32.CloseHandle(handle)
                # WAIT_OBJECT_0 = 0 (process exited cleanly on its own)
                if wait_res == 0:
                    return

        import subprocess

        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


@runtime_checkable
class DocumentCompiler(Protocol):
    """External seam isolating Microsoft Word COM document assembly."""

    def compile(self, parts: Sequence[Path], output_path: Path) -> Path: ...


class FakeDocumentCompiler:
    """Headless test adapter conforming to DocumentCompiler: writes stub bytes."""

    def __init__(self) -> None:
        self.compiled_calls: list[tuple[tuple[Path, ...], Path]] = []

    @contextmanager
    def session(self) -> Iterator[FakeDocumentCompiler]:
        yield self

    def compile(self, parts: Sequence[Path], output_path: Path) -> Path:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import docx
            doc = docx.Document()
            doc.save(str(output_path))
        except Exception:
            output_path.write_bytes(b"PK\x03\x04stub_docx_payload")
        self.compiled_calls.append((tuple(parts), output_path))
        return output_path


class WordComDocumentCompiler:
    """Production adapter: assembles parts via Word COM copy/paste pipeline."""

    def __init__(self, word_app: Any = None) -> None:
        self._word_app: Any = word_app

    @contextmanager
    def session(self) -> Iterator[WordComDocumentCompiler]:
        """Context manager managing an active Word COM application session across batch runs."""
        if self._word_app is not None:
            yield self
            return

        if not (win32com and getattr(win32com, "client", None) and pythoncom):
            raise RuntimeError("win32com is required for Quick Report compilation.")

        co_initialized = False
        dispatched_word = None
        word_pid: int | None = None
        try:
            pythoncom.CoInitialize()
            co_initialized = True
            dispatched_word = win32com.client.Dispatch("Word.Application")
            try:
                import win32process

                hwnd = getattr(dispatched_word, "Hwnd", None)
                if not hwnd:
                    try:
                        hwnd = getattr(dispatched_word.ActiveWindow, "Hwnd", None)
                    except Exception:
                        pass
                if not hwnd:
                    try:
                        import win32gui
                        hwnd = win32gui.FindWindow("OpusApp", None)
                    except Exception:
                        pass
                if hwnd:
                    _, word_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                word_pid = None

            dispatched_word.Visible = False
            dispatched_word.ScreenUpdating = False
            dispatched_word.DisplayAlerts = 0
            self._word_app = dispatched_word

            yield self
        finally:
            self._word_app = None
            if dispatched_word is not None:
                word_to_quit = dispatched_word
                dispatched_word = None
                try:
                    import faulthandler
                    was_enabled = faulthandler.is_enabled()
                    if was_enabled:
                        faulthandler.disable()
                except Exception:
                    was_enabled = False
                try:
                    try:
                        word_to_quit.Quit()
                    except Exception:
                        pass
                    del word_to_quit
                    gc.collect()
                finally:
                    if was_enabled:
                        try:
                            faulthandler.enable()
                        except Exception:
                            pass

            if co_initialized:
                try:
                    time.sleep(0.2)
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

            if word_pid is not None:
                _terminate_word_process(word_pid)

    def compile(self, parts: Sequence[Path], output_path: Path) -> Path:
        """Compile document parts into final deliverable via Word COM recopy & paste."""
        if not parts:
            return output_path

        if self._word_app is None:
            with self.session():
                return self.compile(parts, output_path)

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        word_app = self._word_app
        main_doc = None
        try:
            main_doc = word_app.Documents.Add()
            for idx, part in enumerate(parts):
                part_path = str(Path(part).resolve())
                part_doc = None
                try:
                    part_doc = word_app.Documents.Open(part_path, False, True)

                    # Atomic copy-paste handshake with pre-copy zeroing and range expansion assertion (Ticket #44 / Seam 3)
                    for attempt in range(1, 4):
                        _clear_clipboard()
                        part_doc.Content.Copy()

                        rng = _collapse_and_escape_table(main_doc)
                        if idx > 0 and attempt == 1:
                            rng.InsertBreak(7)  # wdPageBreak = 7
                            rng = _collapse_and_escape_table(main_doc)

                        end_before = getattr(getattr(main_doc, "Content", None), "End", None)
                        _paste_with_retry(rng)
                        end_after = getattr(getattr(main_doc, "Content", None), "End", None)

                        if isinstance(end_before, (int, float)) and isinstance(end_after, (int, float)):
                            if end_after > end_before:
                                break
                        else:
                            # In mock testing environments where Content.End is a MagicMock
                            break

                        if attempt == 3:
                            logger.warning(
                                "Compilation paste did not expand document content for %s after 3 attempts",
                                part_path,
                            )
                        _clear_clipboard()
                        time.sleep(0.1)
                finally:
                    _clear_clipboard()
                    if part_doc is not None:
                        try:
                            part_doc.Close(False)
                        except Exception:
                            pass
                        part_doc = None

            main_doc.SaveAs2(str(output_path))
            _safe_close_document(main_doc, word_app=word_app, expected_name=output_path.name)
            main_doc = None
            return output_path
        finally:
            _clear_clipboard()
            if main_doc is not None:
                try:
                    _safe_close_document(
                        main_doc,
                        word_app=word_app,
                        expected_name=output_path.name,
                    )
                except Exception:
                    pass
                main_doc = None
