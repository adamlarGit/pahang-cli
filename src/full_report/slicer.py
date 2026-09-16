"""DocumentSlicer seam isolating finalized Quick Report document section slicing (Ticket #22 / T1.3a)."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import gc
import logging
from pathlib import Path
import shutil
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

# Microsoft Word COM Constants
WD_PAGE_BREAK: int = 7
WD_STATISTIC_PAGES: int = 2
WD_GOTO_PAGE: int = 1
WD_GOTO_ABSOLUTE: int = 1
WD_REPLACE_ALL: int = 2
WD_REPLACE_NONE: int = 0
WD_FIND_CONTINUE: int = 1
WD_FIND_STOP: int = 0
WD_ACTIVE_END_PAGE_NUMBER: int = 3
WD_FORMAT_ORIGINAL: int = 16

from src.full_report.defect_parser import (
    CbmDefectHeaderParser,
    CbmDefectSliceMetadata,
    build_d37_defect_filename,
)

__all__ = [
    "DocumentSlicer",
    "FakeDocumentSlicer",
    "SlicedSections",
    "SlicingError",
    "WordComDocumentSlicer",
    "get_temp_parts_dir",
    "temp_parts_workspace",
    "CbmDefectHeaderParser",
    "CbmDefectSliceMetadata",
    "build_d37_defect_filename",
]


class SlicingError(ValueError):
    """Raised when section boundary detection or document slicing fails."""


@dataclass(frozen=True)
class ParagraphBoundary:
    """Immutable location of a boundary paragraph within Word COM document."""

    start: int
    end: int
    text: str
    page_number: int = 1


@dataclass(frozen=True)
class SlicedSections:
    """Structured references to docx part files sliced from a finalized Quick Report."""

    station: str
    front_page: Path
    condition_pages: Path
    sticker_page: Path
    vi_summary: Path | None = None
    vi_defect_pages: Path | None = None
    cbm_defect_pages: tuple[Path, ...] = ()


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


def _paste_with_retry(rng: Any, max_attempts: int = 5, delay: float = 0.15) -> None:
    """Retry rng.PasteAndFormat(16) / rng.Paste() up to max_attempts times to preserve source formatting."""
    exceptions: tuple[type[BaseException], ...]
    if pywintypes and hasattr(pywintypes, "com_error"):
        exceptions = (pywintypes.com_error, Exception)
    else:
        exceptions = (Exception,)

    for attempt in range(1, max_attempts + 1):
        try:
            if hasattr(rng, "PasteAndFormat"):
                try:
                    rng.PasteAndFormat(WD_FORMAT_ORIGINAL)
                    return
                except (AttributeError, TypeError):
                    rng.Paste()
                    return
            else:
                rng.Paste()
                return
        except exceptions as exc:
            if attempt == max_attempts:
                logger.error("Word COM range paste failed after %d attempts: %s", max_attempts, exc)
                raise
            time.sleep(delay)


def _terminate_word_process(pid: int | None, timeout_ms: int = 500) -> None:
    """Safely terminate Word COM process if still running in background after Quit."""
    if not pid:
        return
    try:
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            handle = ctypes.windll.kernel32.OpenProcess(0x00101000, False, pid)
            if handle:
                wait_res = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
                ctypes.windll.kernel32.CloseHandle(handle)
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
class DocumentSlicer(Protocol):
    """External seam isolating Quick Report section slicing automation."""

    def slice_sections(
        self,
        source_path: Path,
        target_dir: Path,
        station: str = "",
        has_vi_summary: bool = True,
        has_vi_defects: bool = True,
    ) -> SlicedSections:
        """Slice static sections from finalized Quick Report into target_dir."""
        ...

    def slice_cbm_defects(
        self,
        source_path: Path,
        target_dir: Path,
    ) -> Sequence[Path]:
        """Slice individual CBM defect detail pages into target_dir."""
        ...


class FakeDocumentSlicer:
    """Headless test adapter conforming to DocumentSlicer: writes minimal stub docx files."""

    def __init__(self, mock_cbm_defects: Sequence[Path] | None = None) -> None:
        self.sliced_calls: list[tuple[Path, Path, str]] = []
        self.mock_cbm_defects = list(mock_cbm_defects) if mock_cbm_defects is not None else None

    def slice_sections(
        self,
        source_path: Path,
        target_dir: Path,
        station: str = "",
        has_vi_summary: bool = True,
        has_vi_defects: bool = True,
    ) -> SlicedSections:
        source_path = Path(source_path).resolve()
        target_dir = Path(target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        station_name = station or target_dir.name or "UNKNOWN"
        self.sliced_calls.append((source_path, target_dir, station_name))

        stub_payload = b"PK\x03\x04fake_sliced_docx"

        front_page = target_dir / "front_page.docx"
        front_page.write_bytes(stub_payload)

        condition_pages = target_dir / "condition_pages.docx"
        condition_pages.write_bytes(stub_payload)

        sticker_page = target_dir / "sticker_page.docx"
        sticker_page.write_bytes(stub_payload)

        vi_summary: Path | None = None
        if has_vi_summary:
            vi_summary = target_dir / "vi_summary.docx"
            vi_summary.write_bytes(stub_payload)

        vi_defect_pages: Path | None = None
        if has_vi_defects:
            vi_defect_pages = target_dir / "vi_defect_pages.docx"
            vi_defect_pages.write_bytes(stub_payload)

        cbm_defect_pages: list[Path] = []
        if self.mock_cbm_defects:
            cbm_defects_dir = target_dir / "cbm_defects"
            cbm_defects_dir.mkdir(parents=True, exist_ok=True)
            for p in self.mock_cbm_defects:
                dest = cbm_defects_dir / p.name
                if p.exists() and p != dest:
                    dest.write_bytes(p.read_bytes())
                elif not dest.exists():
                    dest.write_bytes(stub_payload)
                cbm_defect_pages.append(dest)

        return SlicedSections(
            station=station_name,
            front_page=front_page,
            condition_pages=condition_pages,
            sticker_page=sticker_page,
            vi_summary=vi_summary,
            vi_defect_pages=vi_defect_pages,
            cbm_defect_pages=tuple(cbm_defect_pages),
        )

    def slice_cbm_defects(
        self,
        source_path: Path,
        target_dir: Path,
    ) -> Sequence[Path]:
        source_path = Path(source_path).resolve()
        target_dir = Path(target_dir).resolve()
        cbm_defects_dir = target_dir if target_dir.name == "cbm_defects" else target_dir / "cbm_defects"
        cbm_defects_dir.mkdir(parents=True, exist_ok=True)

        if self.mock_cbm_defects:
            results: list[Path] = []
            for p in self.mock_cbm_defects:
                dest = cbm_defects_dir / p.name
                if p.exists() and p != dest:
                    dest.write_bytes(p.read_bytes())
                elif not dest.exists():
                    dest.write_bytes(b"PK\x03\x04fake_sliced_cbm_defect")
                results.append(dest)
            return tuple(results)
        return ()


def _find_paragraph(
    doc: Any,
    text: str,
    start_pos: int | None = None,
    end_pos: int | None = None,
    must_not_contain: str | None = None,
) -> ParagraphBoundary | None:
    """Find a paragraph containing text within character bounds [start_pos, end_pos]."""
    if start_pos is not None or end_pos is not None:
        s = start_pos if start_pos is not None else 0
        e = end_pos if end_pos is not None else int(doc.Content.End)
        rng = doc.Range(s, e)
    else:
        rng = doc.Content

    # 1. Primary Word COM Find.Execute
    try:
        find = rng.Find
        find.ClearFormatting()
        found = False
        try:
            found = bool(
                find.Execute(
                    text,
                    False,  # MatchCase
                    False,  # MatchWholeWord
                    False,  # MatchWildcards
                    False,  # MatchSoundsLike
                    False,  # MatchAllWordForms
                    True,   # Forward
                    WD_FIND_STOP,
                    False,  # Format
                    "",     # ReplaceWith
                    WD_REPLACE_NONE,
                )
            )
        except (TypeError, Exception):
            found = bool(find.Execute(FindText=text, Forward=True, Wrap=WD_FIND_STOP))

        if found:
            para = rng.Paragraphs(1)
            para_rng = para.Range
            para_text = str(getattr(para_rng, "Text", "") or "")
            if text in para_text:
                if not must_not_contain or must_not_contain not in para_text:
                    p_start = int(para_rng.Start)
                    p_end = int(para_rng.End)
                    try:
                        p_page = int(para_rng.Information(WD_ACTIVE_END_PAGE_NUMBER))
                    except Exception:
                        p_page = 1
                    return ParagraphBoundary(
                        start=p_start,
                        end=p_end,
                        text=para_text,
                        page_number=p_page,
                    )
    except Exception:
        pass

    # 2. Resilient fallback searching doc.Paragraphs (supports mocks and non-standard run layouts)
    try:
        paras = getattr(doc, "Paragraphs", None)
        if paras is not None:
            count = len(paras) if isinstance(paras, list) else getattr(paras, "Count", 0)
            for idx in range(1, count + 1):
                p = paras[idx - 1] if isinstance(paras, list) else paras(idx)
                p_rng = getattr(p, "Range", None)
                if p_rng is None:
                    continue
                p_start = getattr(p_rng, "Start", None)
                if start_pos is not None and p_start is not None and p_start < start_pos:
                    continue
                if end_pos is not None and p_start is not None and p_start >= end_pos:
                    break
                p_text = str(getattr(p_rng, "Text", "") or "")
                if text in p_text:
                    if not must_not_contain or must_not_contain not in p_text:
                        p_end = getattr(p_rng, "End", p_start)
                        try:
                            p_page = int(p_rng.Information(WD_ACTIVE_END_PAGE_NUMBER))
                        except Exception:
                            p_page = 1
                        return ParagraphBoundary(
                            start=int(p_start if p_start is not None else 0),
                            end=int(p_end if p_end is not None else 0),
                            text=p_text,
                            page_number=p_page,
                        )
    except Exception:
        pass

    return None


def _replace_front_page_title(doc: Any) -> None:
    """Execute native Word COM Find & Replace to transform Quick Report title to Full Report (D46)."""
    find = doc.Content.Find
    find.ClearFormatting()
    if hasattr(find, "Replacement"):
        find.Replacement.ClearFormatting()

    success = False
    try:
        success = bool(
            find.Execute(
                "QUICK SCANNING REPORT",
                False,
                False,
                False,
                False,
                False,
                True,
                WD_FIND_CONTINUE,
                False,
                "FULL SCANNING REPORT",
                WD_REPLACE_ALL,
            )
        )
    except (TypeError, Exception):
        try:
            success = bool(
                find.Execute(
                    FindText="QUICK SCANNING REPORT",
                    ReplaceWith="FULL SCANNING REPORT",
                    Replace=WD_REPLACE_ALL,
                )
            )
        except Exception as exc:
            raise SlicingError(f"Word COM Find.Execute failed during front page title replacement: {exc}") from exc

    # In mock environments, success might be a MagicMock
    if isinstance(success, bool) and not success:
        # Check whether document content already contains target or didn't contain source
        content_text = str(getattr(doc.Content, "Text", "") or "")
        if "FULL SCANNING REPORT" not in content_text and "QUICK SCANNING REPORT" in content_text:
            raise SlicingError("Word COM Find & Replace failed to transform 'QUICK SCANNING REPORT' to 'FULL SCANNING REPORT'.")


def _slice_range_to_doc(
    word_app: Any,
    source_doc: Any,
    start_pos: int,
    end_pos: int,
    output_path: Path,
    is_front_page: bool = False,
) -> Path:
    """Slice range [start_pos, end_pos] from source_doc and write to output_path docx."""
    while end_pos > start_pos:
        try:
            trailing_char = source_doc.Range(end_pos - 1, end_pos).Text
            if trailing_char in ("\x0c", "\r", "\n"):
                end_pos -= 1
            else:
                break
        except Exception:
            break

    rng = source_doc.Range(start_pos, end_pos)
    rng.Copy()

    new_doc = word_app.Documents.Add()
    try:
        # Mirror PageSetup from source doc
        try:
            new_doc.PageSetup.TopMargin = source_doc.PageSetup.TopMargin
            new_doc.PageSetup.BottomMargin = source_doc.PageSetup.BottomMargin
            new_doc.PageSetup.LeftMargin = source_doc.PageSetup.LeftMargin
            new_doc.PageSetup.RightMargin = source_doc.PageSetup.RightMargin
            new_doc.PageSetup.Orientation = source_doc.PageSetup.Orientation
            new_doc.PageSetup.PaperSize = source_doc.PageSetup.PaperSize
            if hasattr(source_doc, "CompatibilityMode") and hasattr(new_doc, "SetCompatibilityMode"):
                new_doc.SetCompatibilityMode(source_doc.CompatibilityMode)
        except Exception:
            pass

        dest_rng = new_doc.Range(0, 0)
        _paste_with_retry(dest_rng)

        try:
            p_count = int(getattr(new_doc.Paragraphs, "Count", 0))
            if p_count > 1:
                last_p = getattr(new_doc.Paragraphs, "Last", None) or new_doc.Paragraphs(p_count)
                if last_p and getattr(last_p.Range, "Text", "") in ("\r", "\n", "\r\n", "\x0c"):
                    last_p.Range.Delete()
        except (TypeError, ValueError, Exception):
            pass

        if is_front_page:
            _replace_front_page_title(new_doc)

        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        new_doc.SaveAs2(str(output_path))
        return output_path
    finally:
        _clear_clipboard()
        try:
            new_doc.Close(False)
        except Exception:
            pass


def _slice_cbm_defects_from_doc(
    word_app: Any,
    source_doc: Any,
    target_dir: Path,
    total_pages: int,
    cond_start: int | None,
    p_cond: ParagraphBoundary | None,
    vi_summary_start: int | None = None,
    header_parser: CbmDefectHeaderParser | None = None,
) -> tuple[Path, ...]:
    """Slice individual CBM defect detail pages from source_doc into target_dir / 'cbm_defects'."""
    parser = header_parser or CbmDefectHeaderParser()
    target_dir = Path(target_dir).resolve()
    cbm_defects_dir = target_dir if target_dir.name == "cbm_defects" else target_dir / "cbm_defects"
    cbm_defects_dir.mkdir(parents=True, exist_ok=True)

    cond_page = p_cond.page_number if p_cond else (total_pages + 1)
    if cond_page <= 2:
        return ()

    # Discover CBM summary page if present
    p_cbmsum = _find_paragraph(
        source_doc,
        "EXECUTIVE Summary",
        start_pos=0,
        end_pos=cond_start,
    )
    if not p_cbmsum:
        p_cbmsum = _find_paragraph(
            source_doc,
            "CBM DEFECT SUMMARY",
            start_pos=0,
            end_pos=cond_start,
        )
    cbm_sum_page = p_cbmsum.page_number if p_cbmsum else None

    # Discover VI summary page if present
    p_visum = _find_paragraph(
        source_doc,
        "VISUAL DEFECT SUMMARY",
        start_pos=0,
        end_pos=cond_start,
    )
    vi_sum_page = p_visum.page_number if p_visum else None

    candidate_slices: list[tuple[Path, CbmDefectSliceMetadata]] = []
    temp_files: list[Path] = []

    try:
        for p_num in range(2, cond_page):
            if p_num == cbm_sum_page or p_num == vi_sum_page:
                continue

            try:
                p_start_rng = source_doc.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, p_num)
                p_start = p_start_rng.Start
                if p_num < total_pages:
                    p_next_rng = source_doc.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, p_num + 1)
                    p_end = min(p_next_rng.Start, cond_start) if cond_start else p_next_rng.Start
                else:
                    p_end = cond_start if cond_start else source_doc.Content.End
            except Exception:
                continue

            if p_start >= p_end:
                continue

            temp_slice_path = cbm_defects_dir / f"_temp_defect_p{p_num}.docx"
            temp_files.append(temp_slice_path)

            try:
                _slice_range_to_doc(
                    word_app=word_app,
                    source_doc=source_doc,
                    start_pos=p_start,
                    end_pos=p_end,
                    output_path=temp_slice_path,
                )
            except Exception as e:
                logger.warning("Failed to slice candidate CBM defect page %d: %s", p_num, e)
                continue

            try:
                if not temp_slice_path.exists():
                    temp_slice_path.touch()
                meta = parser.parse(temp_slice_path, slice_path=temp_slice_path)
                candidate_slices.append((temp_slice_path, meta))
            except Exception as e:
                logger.debug("Page %d is not a CBM defect detail page: %s", p_num, e)
                try:
                    temp_slice_path.unlink(missing_ok=True)
                except Exception:
                    pass

        if not candidate_slices:
            return ()

        # Deduplicate and index multiple defects on same component / area
        counts: dict[tuple[str, str, str, str], int] = {}
        final_paths: list[Path] = []

        for temp_path, meta in candidate_slices:
            key = (meta.equipment_instance, meta.sequence, meta.equipment_id, meta.defect_area)
            idx = counts.get(key, 0) + 1
            counts[key] = idx

            if idx > 1:
                meta = CbmDefectSliceMetadata(
                    equipment_category=meta.equipment_category,
                    equipment_instance=meta.equipment_instance,
                    sequence=meta.sequence,
                    equipment_id=meta.equipment_id,
                    defect_area=meta.defect_area,
                    severity=meta.severity,
                    index=idx,
                    substation=meta.substation,
                    manufacturer=meta.manufacturer,
                    model=meta.model,
                    filename=build_d37_defect_filename(
                        CbmDefectSliceMetadata(
                            equipment_category=meta.equipment_category,
                            equipment_instance=meta.equipment_instance,
                            sequence=meta.sequence,
                            equipment_id=meta.equipment_id,
                            defect_area=meta.defect_area,
                            index=idx,
                        )
                    ),
                    slice_path=temp_path,
                )

            final_filename = meta.filename or build_d37_defect_filename(meta)
            final_path = cbm_defects_dir / final_filename

            if temp_path.exists():
                if final_path.exists():
                    final_path.unlink(missing_ok=True)
                temp_path.rename(final_path)

            final_paths.append(final_path)

        return tuple(final_paths)

    finally:
        for tf in temp_files:
            if tf.exists() and tf.name.startswith("_temp_"):
                try:
                    tf.unlink(missing_ok=True)
                except Exception:
                    pass


class WordComDocumentSlicer:
    """Production adapter: slices finalized Quick Report sections using Microsoft Word COM Automation."""

    def __init__(
        self,
        word_app: Any = None,
        header_parser: CbmDefectHeaderParser | None = None,
    ) -> None:
        self._word_app: Any = word_app
        self._header_parser: CbmDefectHeaderParser = header_parser or CbmDefectHeaderParser()

    @contextmanager
    def session(self) -> Iterator[WordComDocumentSlicer]:
        """Context manager managing an active Word COM application session."""
        if self._word_app is not None:
            yield self
            return

        if not (win32com and getattr(win32com, "client", None) and pythoncom):
            raise RuntimeError("win32com is required for Word COM document slicing.")

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

    def slice_sections(
        self,
        source_path: Path,
        target_dir: Path,
        station: str = "",
        has_vi_summary: bool = True,
        has_vi_defects: bool = True,
    ) -> SlicedSections:
        """Slice static sections from finalized Quick Report into target_dir."""
        if self._word_app is None:
            with self.session():
                return self.slice_sections(
                    source_path=source_path,
                    target_dir=target_dir,
                    station=station,
                    has_vi_summary=has_vi_summary,
                    has_vi_defects=has_vi_defects,
                )

        source_path = Path(source_path).resolve()
        target_dir = Path(target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        station_name = station or target_dir.name or "UNKNOWN"

        word_app = self._word_app
        source_doc = None
        try:
            source_doc = word_app.Documents.Open(str(source_path), False, True)

            # 1. Page 1 boundary (Page 2 start)
            p2_start: int
            try:
                num_pages = source_doc.ComputeStatistics(WD_STATISTIC_PAGES)
                if num_pages > 1:
                    p2_rng = source_doc.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, 2)
                    p2_start = p2_rng.Start
                else:
                    p2_start = source_doc.Content.End
            except Exception:
                p2_start = source_doc.Content.End

            # 2. Substation condition boundary ("SUBSTATION CONDITION") per D16
            p_cond = _find_paragraph(source_doc, "SUBSTATION CONDITION")
            if not p_cond:
                raise SlicingError("Substation condition boundary paragraph 'SUBSTATION CONDITION' not found in Quick Report.")
            cond_start = p_cond.start

            # 3. Sticker page boundary ("NORMAL/DEFECT STICKER") per D16
            p_sticker = _find_paragraph(source_doc, "NORMAL/DEFECT STICKER", start_pos=cond_start)
            if not p_sticker:
                raise SlicingError("Sticker page boundary paragraph 'NORMAL/DEFECT STICKER' not found in Quick Report.")
            sticker_start = p_sticker.start

            # 4. Visual defect pages boundary ("VISUAL DEFECT") per D16
            vi_start: int | None = None
            if has_vi_defects:
                p_vi = _find_paragraph(
                    source_doc,
                    "VISUAL DEFECT",
                    start_pos=cond_start,
                    end_pos=sticker_start,
                    must_not_contain="SUMMARY",
                )
                if p_vi:
                    vi_start = p_vi.start

            # 5. Visual defect summary boundary ("VISUAL DEFECT SUMMARY") per D16
            vi_summary_start: int | None = None
            vi_summary_end: int | None = None
            if has_vi_summary and p2_start < cond_start:
                p_visum = _find_paragraph(
                    source_doc,
                    "VISUAL DEFECT SUMMARY",
                    start_pos=p2_start,
                    end_pos=cond_start,
                )
                if p_visum:
                    vi_summary_start = p_visum.start
                    try:
                        next_page = source_doc.GoTo(WD_GOTO_PAGE, WD_GOTO_ABSOLUTE, p_visum.page_number + 1)
                        if next_page.Start > vi_summary_start:
                            vi_summary_end = min(next_page.Start, cond_start)
                        else:
                            vi_summary_end = cond_start
                    except Exception:
                        vi_summary_end = cond_start

            # Slice Section 1: Front Page (Page 1) with D46 title replacement
            front_page_path = _slice_range_to_doc(
                word_app,
                source_doc,
                start_pos=0,
                end_pos=p2_start,
                output_path=target_dir / "front_page.docx",
                is_front_page=True,
            )

            # Slice Section 2: Visual Defect Summary (if present)
            vi_summary_path: Path | None = None
            if vi_summary_start is not None and vi_summary_end is not None:
                vi_summary_path = _slice_range_to_doc(
                    word_app,
                    source_doc,
                    start_pos=vi_summary_start,
                    end_pos=vi_summary_end,
                    output_path=target_dir / "vi_summary.docx",
                )

            # Slice Section 3: Substation Condition
            cond_end = vi_start if vi_start is not None else sticker_start
            condition_pages_path = _slice_range_to_doc(
                word_app,
                source_doc,
                start_pos=cond_start,
                end_pos=cond_end,
                output_path=target_dir / "condition_pages.docx",
            )

            # Slice Section 4: Visual Defect Pages (if present)
            vi_defect_pages_path: Path | None = None
            if vi_start is not None:
                vi_defect_pages_path = _slice_range_to_doc(
                    word_app,
                    source_doc,
                    start_pos=vi_start,
                    end_pos=sticker_start,
                    output_path=target_dir / "vi_defect_pages.docx",
                )

            # Slice Section 5: Sticker Page
            sticker_page_path = _slice_range_to_doc(
                word_app,
                source_doc,
                start_pos=sticker_start,
                end_pos=source_doc.Content.End,
                output_path=target_dir / "sticker_page.docx",
            )

            # Slice Section 6: CBM Defect Pages (into temp_parts/cbm_defects/ per D37)
            cbm_defect_paths = _slice_cbm_defects_from_doc(
                word_app=word_app,
                source_doc=source_doc,
                target_dir=target_dir,
                total_pages=num_pages,
                cond_start=cond_start,
                p_cond=p_cond,
                vi_summary_start=vi_summary_start,
                header_parser=self._header_parser,
            )

            return SlicedSections(
                station=station_name,
                front_page=front_page_path,
                condition_pages=condition_pages_path,
                sticker_page=sticker_page_path,
                vi_summary=vi_summary_path,
                vi_defect_pages=vi_defect_pages_path,
                cbm_defect_pages=cbm_defect_paths,
            )
        finally:
            _clear_clipboard()
            if source_doc is not None:
                try:
                    source_doc.Close(False)
                except Exception:
                    pass

    def slice_cbm_defects(
        self,
        source_path: Path,
        target_dir: Path,
    ) -> Sequence[Path]:
        """Slice individual CBM defect detail pages into target_dir/cbm_defects per D37."""
        if self._word_app is None:
            with self.session():
                return self.slice_cbm_defects(
                    source_path=source_path,
                    target_dir=target_dir,
                )

        source_path = Path(source_path).resolve()
        target_dir = Path(target_dir).resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Quick report source document not found: {source_path}")

        word_app = self._word_app
        source_doc = None
        try:
            source_doc = word_app.Documents.Open(str(source_path), False, True)
            total_pages = source_doc.ComputeStatistics(WD_STATISTIC_PAGES)
            p_cond = _find_paragraph(source_doc, "SUBSTATION CONDITION")
            cond_start = p_cond.start if p_cond else None

            p_visum = _find_paragraph(source_doc, "VISUAL DEFECT SUMMARY", start_pos=0, end_pos=cond_start)
            vi_summary_start = p_visum.start if p_visum else None

            return _slice_cbm_defects_from_doc(
                word_app=word_app,
                source_doc=source_doc,
                target_dir=target_dir,
                total_pages=total_pages,
                cond_start=cond_start,
                p_cond=p_cond,
                vi_summary_start=vi_summary_start,
                header_parser=self._header_parser,
            )
        finally:
            _clear_clipboard()
            if source_doc is not None:
                try:
                    source_doc.Close(False)
                except Exception:
                    pass


def get_temp_parts_dir(station: str, base_dir: Path | None = None) -> Path:
    """Resolve the temporary parts directory for a given station."""
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    return root / ".temp" / "temp_parts" / station


@contextmanager
def temp_parts_workspace(
    station: str,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> Iterator[Path]:
    """Context manager provisioning and cleaning up the station temp_parts directory."""
    temp_dir = get_temp_parts_dir(station, base_dir=base_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield temp_dir
    finally:
        if not keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)
            try:
                temp_dir.parent.rmdir()
                temp_dir.parent.parent.rmdir()
            except OSError:
                pass
        gc.collect()
