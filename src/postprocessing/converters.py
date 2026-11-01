"""Document converters using Windows COM automation and fake/mock implementations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
import re
import time
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Sequence
import uuid

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PyPDF2 import PdfWriter

if TYPE_CHECKING:
    from .image_restoration import RestorationReport


def calculate_exponential_delays(max_attempts: int, total_wait: float) -> list[float]:
    """Calculate geometric backoff delays distributed across total_wait seconds."""
    if max_attempts > 1:
        weights = [2**i for i in range(max_attempts - 1)]
        total_weight = sum(weights)
        return [total_wait * (w / total_weight) for w in weights]
    return []


def safe_unlink_with_retry(
    path: Path | str,
    max_attempts: int = 5,
    total_wait: float = 5.0,
) -> bool:
    """Safely unlink a file with exponential backoff retry to overcome transient Windows locks.

    Attempts unlinking up to max_attempts times scaled across total_wait seconds.
    Returns True if file was successfully removed or did not exist, False otherwise.
    """
    p = Path(path)
    if not p.exists():
        return True

    delays = calculate_exponential_delays(max_attempts, total_wait)

    for attempt in range(max_attempts):
        try:
            if not p.exists():
                return True
            p.unlink()
            return True
        except (OSError, PermissionError) as exc:
            if attempt < max_attempts - 1:
                delay = delays[attempt]
                time.sleep(delay)
            else:
                msg = f"Failed to unlink {p} after {max_attempts} attempts: {exc}"
                logging.debug(msg)
                return False
    return not p.exists()


def safe_replace_with_retry(
    src: Path | str,
    dst: Path | str,
    max_attempts: int = 5,
    total_wait: float = 5.0,
) -> bool:
    """Safely replace dst with src using exponential backoff retry to overcome transient Windows locks.

    Attempts replacement up to max_attempts times scaled across total_wait seconds.
    Returns True if file was successfully replaced, False otherwise.
    """
    src_p = Path(src)
    dst_p = Path(dst)
    if not src_p.exists():
        return False

    delays = calculate_exponential_delays(max_attempts, total_wait)

    for attempt in range(max_attempts):
        try:
            os.replace(src_p, dst_p)
            return True
        except (OSError, PermissionError) as exc:
            if attempt < max_attempts - 1:
                delay = delays[attempt]
                time.sleep(delay)
            else:
                msg = f"Failed to replace {dst_p} with {src_p} after {max_attempts} attempts: {exc}"
                logging.debug(msg)
                return False
    return False


def _is_pce_testsheet_sheet(ws_name: str) -> bool:
    """Check if a worksheet name corresponds to a PCE Testsheet sheet."""
    name = ws_name.strip().lower()
    return (
        name == "pce testsheet"
        or name.startswith("pce testsheet ")
        or name.startswith("pce testsheet(")
        or name.startswith("pce testsheet-")
        or name.startswith("pce testsheet_")
    )


def _is_pce_vi_sheet(ws_name: str) -> bool:
    """Check if a worksheet name corresponds to a PCE VI sheet."""
    name = ws_name.strip().lower()
    return (
        name == "pce vi"
        or name.startswith("pce vi ")
        or name.startswith("pce vi(")
        or name.startswith("pce vi-")
        or name.startswith("pce vi_")
    )


def _is_visual_inspection_sheet(ws_name: str) -> bool:
    """Return True if worksheet name represents a visual inspection sheet."""
    s = ws_name.strip().lower()
    if "visual inspec" in s or "visual inspection" in s:
        return True
    remainder = re.sub(r"^(?:33\s*kv|11\s*kv)[\s\-_.]*", "", s)
    return (
        remainder == "vi"
        or remainder.startswith("vi ")
        or remainder.startswith("vi(")
        or remainder.startswith("vi-")
        or remainder.startswith("vi_")
        or remainder.startswith("vi/")
        or remainder.startswith("vi.")
        or bool(re.match(r"^vi\d", remainder))
    )


def classify_sheet_layout(sheet_name: str) -> str:
    """Classify worksheet name into layout keys: switchgear, transformer, visual_inspection, pce_testsheet, pce_vi."""
    s = re.sub(r"\s+", " ", str(sheet_name).strip().lower())
    s = re.sub(r"\b(\d+)\s+kv\b", r"\1kv", s)
    if _is_pce_testsheet_sheet(s):
        return "pce_testsheet"
    if _is_pce_vi_sheet(s):
        return "pce_vi"
    if s == "tx" or s.startswith("tx ") or s.startswith("tx(") or s.startswith("tx-") or s.startswith("tx_"):
        return "transformer"
    if _is_visual_inspection_sheet(s):
        return "visual_inspection"
    if s.startswith("33kv") or s.startswith("11kv") or "33kv" in s or "11kv" in s:
        return "switchgear"
    return "unknown"


def _is_33kv_workbook(worksheet_names: Sequence[str]) -> bool:
    """Return True if workbook contains 33kV-family sheets."""
    for ws_name in worksheet_names:
        name = re.sub(r"\s+", " ", ws_name.strip().lower())
        name = re.sub(r"\b(\d+)\s+kv\b", r"\1kv", name)
        if (
            name.startswith("33kv")
            or name.startswith("11kv (main)")
            or name.startswith("11kv (extra)")
            or name == "11kv main"
            or name.startswith("11kv main ")
            or name == "11kv extra"
            or name.startswith("11kv extra ")
            or name == "tx"
            or name.startswith("tx ")
        ):
            return True
    return False


def _extract_extra_index(sheet_name: str) -> int:
    """Extract sequential numbering from extra switchgear sheet name (e.g. 33kV (Extra) (2) -> 2)."""
    clean = re.sub(r"\s+", " ", sheet_name.strip())
    m = re.search(r"\((\d+)\)\s*$", clean)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(?:extra|\))\s*[-_]?\s*(\d+)\s*$", clean, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    return 1


def select_and_sort_sheets(
    worksheet_names: Sequence[str],
    target_sheets: Sequence[str] | None = None,
) -> list[str]:
    """Select and sort target worksheet names from a workbook.

    For 33kV workbooks:
      Sorts sheets in strict sequential order:
        1. 33kV (Main)
        2. 33kV (Extra), 33kV (Extra) (2) ... (sorted by extra index)
        3. 11kV (Main)
        4. 11kV (Extra), 11kV (Extra) (2) ... (sorted by extra index)
        5. TX
        6. Visual Inspec. / Visual Inspection
      Strictly excludes RAW DATA and unpopulated extra template sheets.

    For 11kV workbooks:
      Preserves PCE Testsheet first and PCE VI last.
    """
    if target_sheets is not None:
        return [name for name in target_sheets if name in worksheet_names]

    if _is_33kv_workbook(worksheet_names):
        main_33: list[str] = []
        extra_33: list[str] = []
        main_11: list[str] = []
        extra_11: list[str] = []
        tx_sheets: list[str] = []
        vi_sheets: list[str] = []

        for name in worksheet_names:
            s_clean = re.sub(r"\s+", " ", name.strip())
            s_lower = re.sub(r"\b(\d+)\s+kv\b", r"\1kv", s_clean.lower())

            # Strictly exclude RAW DATA
            if s_lower == "raw data" or s_lower.startswith("raw data"):
                continue

            # Strictly exclude template sheets
            if "template" in s_lower or "unpopulated" in s_lower:
                continue

            layout = classify_sheet_layout(s_clean)
            if layout == "switchgear":
                if (
                    s_lower.startswith("33kv (main)")
                    or s_lower == "33kv (main)"
                    or s_lower == "33kv main"
                    or s_lower.startswith("33kv main ")
                ):
                    main_33.append(name)
                elif s_lower.startswith("33kv (extra)") or s_lower.startswith("33kv extra"):
                    extra_33.append(name)
                elif (
                    s_lower.startswith("11kv (main)")
                    or s_lower == "11kv (main)"
                    or s_lower == "11kv main"
                    or s_lower.startswith("11kv main ")
                ):
                    main_11.append(name)
                elif s_lower.startswith("11kv (extra)") or s_lower.startswith("11kv extra"):
                    extra_11.append(name)
                elif "33kv" in s_lower:
                    main_33.append(name)
                elif "11kv" in s_lower:
                    main_11.append(name)
            elif layout == "transformer":
                tx_sheets.append(name)
            elif layout == "visual_inspection":
                vi_sheets.append(name)

        # Sort extras sequentially
        extra_33.sort(key=_extract_extra_index)
        extra_11.sort(key=_extract_extra_index)

        return main_33 + extra_33 + main_11 + extra_11 + tx_sheets + vi_sheets

    # 11kV fallback:
    testsheet_names: list[str] = []
    vi_names: list[str] = []
    for name in worksheet_names:
        if _is_pce_testsheet_sheet(name):
            testsheet_names.append(name)
        elif _is_pce_vi_sheet(name):
            vi_names.append(name)

    testsheet_names.sort(
        key=lambda s: (0 if s.strip().lower() == "pce testsheet" else 1, s.strip().lower())
    )
    vi_names.sort(
        key=lambda s: (0 if s.strip().lower() == "pce vi" else 1, s.strip().lower())
    )
    return testsheet_names + vi_names


def get_installed_printers() -> dict[str, str]:
    """Enumerate installed printers from Windows registry Devices list.

    Returns:
        dict[str, str]: Mapping of lowercase printer name to full printer spec (e.g. 'adobe pdf': 'Adobe PDF on Ne07:').
    """
    devices: dict[str, str] = {}
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows NT\CurrentVersion\Devices",
        ) as key:
            i = 0
            while True:
                try:
                    name, val, _ = winreg.EnumValue(key, i)
                    parts = str(val).split(",")
                    port = parts[1].strip() if len(parts) >= 2 else ""
                    spec = f"{name} on {port}" if port else str(name)
                    devices[str(name).lower()] = spec
                    i += 1
                except OSError:
                    break
    except Exception as exc:
        logging.debug("Could not query Devices registry for installed printers: %s", exc)
    return devices


def configure_uniform_printer(app: object) -> None:
    """Configure ActivePrinter to a standardized virtual PDF printer (Adobe PDF or Microsoft Print to PDF) to ensure uniform scaling."""
    try:
        current_printer = str(getattr(app, "ActivePrinter", ""))
        preferred_printers = ["adobe pdf", "microsoft print to pdf"]
        if any(p in current_printer.lower() for p in preferred_printers):
            return

        devices = get_installed_printers()
        for pref in preferred_printers:
            for dev_name, full_spec in devices.items():
                if pref in dev_name:
                    app.ActivePrinter = full_spec
                    return
    except Exception as exc:
        logging.debug("Could not configure uniform printer: %s", exc)


def _start_word(configure_printer: bool = True) -> object:
    """Start a new, hidden Word instance owned by the caller."""
    import win32com.client as win32

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    word.ScreenUpdating = False
    if configure_printer:
        configure_uniform_printer(word)
    return word


def _quit_word(word: object) -> None:
    """Quit a Word instance, tolerating a dead COM server (faulthandler is paused around the call)."""
    try:
        import faulthandler

        was_enabled = faulthandler.is_enabled()
        if was_enabled:
            faulthandler.disable()
    except Exception:
        was_enabled = False
    try:
        try:
            word.Quit()
        except Exception as exc:
            logging.debug("Error quitting Word COM: %s", exc)
    finally:
        if was_enabled:
            try:
                faulthandler.enable()
            except Exception:
                pass


class BatchComSession:
    """Context manager managing the shared lifecycle of Word and Excel COM applications."""

    def __init__(
        self,
        word_app: object | None = None,
        excel_app: object | None = None,
        configure_printer: bool = True,
        suppress_errors: bool = False,
    ) -> None:
        self.word_app = word_app
        self.excel_app = excel_app
        self.configure_printer = configure_printer
        self.suppress_errors = suppress_errors
        self._co_initialized: bool = False
        self._closed: bool = False
        self._word_started_here: bool = False

    def __enter__(self) -> BatchComSession:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def open(self) -> BatchComSession:
        """Initialize COM and start Word/Excel applications if not already provided."""
        if self.word_app is not None and self.excel_app is not None:
            return self

        try:
            import pythoncom
            import win32com.client as win32

            pythoncom.CoInitialize()
            self._co_initialized = True

            if self.word_app is None:
                self.word_app = _start_word(self.configure_printer)
                self._word_started_here = True

            if self.excel_app is None:
                excel = win32.DispatchEx("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                if self.configure_printer:
                    configure_uniform_printer(excel)
                self.excel_app = excel

        except Exception as exc:
            logging.warning("Could not initialize COM session: %s", exc)
            self.close()
            if not self.suppress_errors:
                raise
        return self

    def restart_word(self) -> bool:
        """Quit this session's own Word instance and start a fresh one (ticket #147 Word session health).

        Only an instance this session started itself is ever quit; an injected `word_app` is left alone and
        False is returned so the caller keeps using it.
        """
        if not self._word_started_here or self.word_app is None or self._closed:
            return False
        old = self.word_app
        self.word_app = None
        _quit_word(old)
        del old
        import gc

        gc.collect()
        time.sleep(0.2)
        self.word_app = _start_word(self.configure_printer)
        return True

    def close(self) -> None:
        """Gracefully quit COM applications, release references, and uninitialize COM."""
        if self._closed:
            return
        self._closed = True

        # Cleanup Excel
        if self.excel_app is not None:
            excel = self.excel_app
            self.excel_app = None
            try:
                excel.Quit()
            except Exception as exc:
                logging.debug("Error quitting Excel COM: %s", exc)
            finally:
                del excel

        # Cleanup Word: only an instance this session started; an injected one belongs to its caller
        if self.word_app is not None:
            word = self.word_app
            self.word_app = None
            if self._word_started_here:
                _quit_word(word)
            del word
            import gc

            gc.collect()

        # Cleanup COM runtime
        if self._co_initialized:
            try:
                import gc
                gc.collect()
                import time
                time.sleep(0.2)
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception as exc:
                logging.debug("Error uninitializing pythoncom: %s", exc)
            finally:
                self._co_initialized = False


def batch_com_session(
    word_app: object | None = None,
    excel_app: object | None = None,
    configure_printer: bool = True,
    suppress_errors: bool = False,
) -> BatchComSession:
    """Create and return a BatchComSession context manager."""
    return BatchComSession(
        word_app=word_app,
        excel_app=excel_app,
        configure_printer=configure_printer,
        suppress_errors=suppress_errors,
    )


# --------------------------------------------------------------------------- native export + restoration (ADR 0009)


@dataclass(frozen=True)
class PartConversionOutcome:
    """How one DOCX became its PDF: the Restoration Report (None when restoration did not run) and fallback state."""

    docx_path: Path
    report: RestorationReport | None = None
    fell_back: bool = False
    warning: str | None = None


_OPEN_RETRY_DELAYS: tuple[float, ...] = (0.2, 0.5, 1.0)


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logging.debug("Could not remove temp file %s: %s", path, exc)


def _pdf_export_problem(pdf_path: Path, retry_delays: Sequence[float]) -> str | None:
    """Return None when `pdf_path` exists, opens and has pages; otherwise a description of the problem."""
    problem = "export produced no file"
    for delay in (0.0, *retry_delays):
        if delay:
            time.sleep(delay)
        if not pdf_path.exists():
            problem = "export produced no file"
            continue
        if pdf_path.stat().st_size == 0:
            problem = "export produced an empty file"
            continue
        try:
            doc = fitz.open(str(pdf_path))
            try:
                pages = doc.page_count
            finally:
                doc.close()
        except Exception as exc:
            problem = f"export does not open ({exc})"
            continue
        if pages <= 0:
            return "export has no pages"
        return None
    return problem


def _export_validated(
    export: Callable[[Path, Path], None],
    docx_path: Path,
    native_tmp: Path,
    recycle: Callable[[], None] | None,
    retry_delays: Sequence[float],
) -> None:
    """Export, validate, and on failure recycle Word and retry once (Word session health)."""
    problem = ""
    for attempt in range(2):
        _unlink_quiet(native_tmp)
        try:
            export(docx_path, native_tmp)
            found = _pdf_export_problem(native_tmp, retry_delays)
        except Exception as exc:
            found = f"export raised {type(exc).__name__}: {exc}"
        if found is None:
            return
        problem = found
        if attempt == 0:
            logging.warning(
                "Word export failed for %s (%s); recycling Word and retrying once", docx_path.name, problem
            )
            if recycle is not None:
                try:
                    recycle()
                except Exception as exc:
                    logging.warning("Could not recycle Word: %s", exc)
    raise RuntimeError(f"Word export failed for {docx_path.name}: {problem}")


def _publish(src: Path, dst: Path) -> None:
    if not safe_replace_with_retry(src, dst):
        raise RuntimeError(f"Could not publish {src.name} to {dst}")


def convert_docx_native_restored(
    docx_path: Path,
    pdf_path: Path,
    export: Callable[[Path, Path], None],
    *,
    restore: Callable[[bytes, Path, Path], RestorationReport] | None = None,
    recycle: Callable[[], None] | None = None,
    retry_delays: Sequence[float] | None = None,
    restore_images: bool = True,
) -> PartConversionOutcome:
    """Native export of one DOCX followed by Source Image Restoration (ADR 0009 Decision section 2-4).

    `export(docx, out_pdf)` performs Word's ExportAsFixedFormat. The DOCX is snapshotted and hashed before export
    and re-hashed after; a change triggers one redo, a second change keeps the native PDF. A restoration failure
    publishes the native PDF instead. All temp files are removed on every path. With `restore_images=False`
    (Quick Report, out of ADR 0009 scope) the validated native PDF is published as is.
    """
    if restore is None and restore_images:
        from .image_restoration import restore_source_images as restore  # lazy: it imports this module
    delays = _OPEN_RETRY_DELAYS if retry_delays is None else retry_delays
    token = uuid.uuid4().hex[:8]
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    native_tmp = pdf_path.parent / f".tmp_native_{token}.pdf"  # short: 33kV stems already near MAX_PATH
    restore_tmp = pdf_path.parent / f".tmp_restore_{token}.pdf"
    try:
        if not restore_images:  # no snapshot or hash: nothing will consume them
            _export_validated(export, docx_path, native_tmp, recycle, delays)
            _publish(native_tmp, pdf_path)
            return PartConversionOutcome(docx_path)

        snapshot = b""
        stable = False
        for attempt in range(2):
            snapshot = docx_path.read_bytes()
            digest = hashlib.sha256(snapshot).hexdigest()
            _export_validated(export, docx_path, native_tmp, recycle, delays)
            if _sha256_of_file(docx_path) == digest:
                stable = True
                break
            if attempt == 0:
                logging.info("%s changed during conversion; redoing once", docx_path.name)

        if not stable:
            warning = f"source changed during conversion: {docx_path.name}; kept native PDF"
            logging.warning(warning)
            _publish(native_tmp, pdf_path)
            return PartConversionOutcome(docx_path, None, True, warning)

        try:
            report = restore(snapshot, native_tmp, restore_tmp)
        except Exception as exc:
            warning = f"image restoration failed for {docx_path.name} ({exc}); kept native PDF"
            logging.warning(warning)
            _publish(native_tmp, pdf_path)
            return PartConversionOutcome(docx_path, None, True, warning)
        snapshot = b""
        try:
            _publish(restore_tmp, pdf_path)
        except Exception as exc:
            warning = f"could not publish restored PDF for {docx_path.name} ({exc}); kept native PDF"
            logging.warning(warning)
            _publish(native_tmp, pdf_path)
            return PartConversionOutcome(docx_path, None, True, warning)
        return PartConversionOutcome(docx_path, report, False, None)
    finally:
        _unlink_quiet(native_tmp)
        _unlink_quiet(restore_tmp)


class DocumentConverter(ABC):
    """Abstract base class defining the document converter contract."""

    @abstractmethod
    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
        excel_app: object | None = None,
        session: BatchComSession | None = None,
    ) -> Path:
        """Convert an Excel testsheet workbook to a PDF file."""
        ...

    @abstractmethod
    def convert_docx_to_pdf(
        self,
        docx_path: Path,
        pdf_path: Path,
        word_app: object | None = None,
        session: BatchComSession | None = None,
        restore_images: bool = True,
    ) -> Path:
        """Convert a Word document (`.docx`) to a PDF file."""
        ...

    @abstractmethod
    def merge_pdfs(
        self,
        primary_pdf: Path,
        secondary_pdf: Path,
        output_pdf: Path,
    ) -> Path:
        """Merge primary and secondary PDFs into `output_pdf`."""
        ...

    @abstractmethod
    def merge_pdfs_batch(
        self,
        pdf_paths: Sequence[Path],
        output_pdf: Path,
    ) -> Path:
        """Merge a sequence of PDFs in order into `output_pdf`."""
        ...



class ComDocumentConverter(DocumentConverter):
    """Document converter utilizing Windows COM automation (`win32com.client`)."""

    def __init__(
        self,
        optimize_page_setup: bool = True,
    ) -> None:
        """Initialize the COM converter with optional PageSetup optimization."""
        self.optimize_page_setup = optimize_page_setup
        self.last_conversion: PartConversionOutcome | None = None

    def _export_fixed_format(self, doc: object, pdf_path: Path) -> None:
        """Export Word document using native ExportAsFixedFormat engine (wdExportOptimizeForPrint)."""
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf_path.resolve()),
            ExportFormat=17,  # wdExportFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,  # wdExportOptimizeForPrint (High Quality)
            Range=0,  # wdExportAllDocument
            Item=0,  # wdExportDocumentContent
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=0,  # wdExportCreateNoBookmarks
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )

    def _configure_uniform_printer(self, excel_app: object) -> None:
        """Configure ActivePrinter to a standardized virtual PDF printer (e.g. Microsoft Print to PDF) to ensure uniform sheet scaling."""
        configure_uniform_printer(excel_app)

    def _configure_target_page_setup(self, target: object, sheet_name: str | None = None) -> None:
        """Enforce standardized PageSetup properties per sheet family.

        Switchgear & Transformer: Landscape A4, 2.83pt (~1mm) margins, fit 1-page wide, unconstrained height.
        Visual Inspection: Portrait A4, 18pt/54pt margins, fit 1-page wide, unconstrained height.
        11kV sheets: Landscape A4, fit 1-page wide and tall.
        """
        if not self.optimize_page_setup:
            return
        try:
            sheets_to_process = []
            if hasattr(target, "PageSetup"):
                sheets_to_process.append(target)
            elif hasattr(target, "Worksheets"):
                sheets_to_process.extend(list(target.Worksheets))

            for ws in sheets_to_process:
                name = getattr(ws, "Name", "") or sheet_name or ""
                layout = classify_sheet_layout(name)
                try:
                    ws.PageSetup.Zoom = False
                    ws.PageSetup.PaperSize = 9  # xlPaperA4 (210 x 297 mm)

                    if layout in ("switchgear", "transformer"):
                        ws.PageSetup.Orientation = 2  # xlLandscape
                        ws.PageSetup.LeftMargin = 2.83
                        ws.PageSetup.RightMargin = 2.83
                        ws.PageSetup.TopMargin = 0
                        ws.PageSetup.BottomMargin = 0
                        ws.PageSetup.FitToPagesWide = 1
                        ws.PageSetup.FitToPagesTall = False
                    elif layout == "visual_inspection":
                        ws.PageSetup.Orientation = 1  # xlPortrait
                        ws.PageSetup.LeftMargin = 18.0
                        ws.PageSetup.RightMargin = 18.0
                        ws.PageSetup.TopMargin = 54.0
                        ws.PageSetup.BottomMargin = 54.0
                        ws.PageSetup.FitToPagesWide = 1
                        ws.PageSetup.FitToPagesTall = False
                    else:
                        ws.PageSetup.Orientation = 2  # xlLandscape
                        ws.PageSetup.FitToPagesWide = 1
                        ws.PageSetup.FitToPagesTall = 1
                except Exception as exc:
                    logging.debug("Could not configure PageSetup for sheet %s: %s", name, exc)
        except Exception as exc:
            logging.debug("Could not inspect sheets for PageSetup: %s", exc)

    def _merge_temp_pdfs(self, temp_pdfs: Sequence[Path], output_pdf: Path) -> Path:
        """Merge temporary sheet PDFs into `output_pdf` sequentially via merge_pdfs_batch."""
        return self.merge_pdfs_batch(temp_pdfs, output_pdf)

    def _open_workbook(self, excel_app: object, xlsx_path: Path) -> object:
        """Open Excel workbook via COM with fallback to repair mode for openpyxl-modified files."""
        abs_path = str(xlsx_path.resolve())
        try:
            return excel_app.Workbooks.Open(Filename=abs_path, UpdateLinks=0, ReadOnly=True)
        except Exception as exc:
            logging.debug("Standard Workbooks.Open failed for %s, trying CorruptLoad=xlRepairFile: %s", abs_path, exc)
            return excel_app.Workbooks.Open(
                abs_path, 0, True, None, None, None, True, None, None, False, False, None, False, None, 2
            )

    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
        excel_app: object | None = None,
        session: BatchComSession | None = None,
    ) -> Path:
        """Convert testsheet workbook to PDF using COM automation."""
        if session is not None and excel_app is None:
            excel_app = session.excel_app

        import pythoncom
        import win32com.client as win32

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        owns_excel = excel_app is None
        co_initialized = False

        if owns_excel:
            pythoncom.CoInitialize()
            co_initialized = True
            excel_app = win32.DispatchEx("Excel.Application")
            excel_app.Visible = False
            excel_app.DisplayAlerts = False

        wb = None
        try:
            wb = self._open_workbook(excel_app, xlsx_path)
            self._configure_uniform_printer(excel_app)
            worksheet_names = [ws.Name for ws in wb.Worksheets]
            selected_names = select_and_sort_sheets(worksheet_names, target_sheets)
            ws_map = {ws.Name: ws for ws in wb.Worksheets}
            selected_sheets = [ws_map[name] for name in selected_names if name in ws_map]

            # In COM mode, filter out unpopulated extra template sheets whose B15 and C15 are empty
            filtered_sheets = []
            for ws in selected_sheets:
                s_lower = ws.Name.strip().lower()
                if "extra" in s_lower:
                    try:
                        b15 = ws.Range("B15").Value
                        c15 = ws.Range("C15").Value
                        if (b15 is None or str(b15).strip() == "") and (c15 is None or str(c15).strip() == ""):
                            logging.info("Skipping unpopulated extra template sheet: %s", ws.Name)
                            continue
                    except Exception:
                        pass
                filtered_sheets.append(ws)
            selected_sheets = filtered_sheets

            if not selected_sheets:
                self._configure_target_page_setup(wb)
                wb.ExportAsFixedFormat(0, str(pdf_path.resolve()), 0, True, False)
            elif len(selected_sheets) == 1:
                ws = selected_sheets[0]
                self._configure_target_page_setup(ws)
                ws.ExportAsFixedFormat(0, str(pdf_path.resolve()), 0, True, False)
            else:
                temp_pdfs: list[Path] = []
                try:
                    for i, ws in enumerate(selected_sheets):
                        self._configure_target_page_setup(ws)
                        temp_pdf = pdf_path.parent / f".tmp_{pdf_path.stem}_sheet_{i}.pdf"
                        ws.ExportAsFixedFormat(0, str(temp_pdf.resolve()), 0, True, False)
                        temp_pdfs.append(temp_pdf)

                    self._merge_temp_pdfs(temp_pdfs, pdf_path)
                finally:
                    for temp_pdf in temp_pdfs:
                        if temp_pdf.exists():
                            try:
                                temp_pdf.unlink()
                            except Exception:
                                pass
            selected_sheets = None
            ws_map = None

        finally:
            if wb is not None:
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
                wb = None
            if owns_excel and excel_app is not None:
                try:
                    excel_app.Quit()
                except Exception:
                    pass
                excel_app = None
            if co_initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        if not pdf_path.exists():
            raise RuntimeError(f"COM export failed: {pdf_path} not found after export.")
        return pdf_path

    def convert_docx_to_pdf(
        self,
        docx_path: Path,
        pdf_path: Path,
        word_app: object | None = None,
        session: BatchComSession | None = None,
        restore_images: bool = True,
    ) -> Path:
        """Convert a Full Report DOCX to PDF: native ExportAsFixedFormat, then Source Image Restoration (ADR 0009).

        Never prints. The outcome is left in `last_conversion`.
        """
        self.last_conversion = None
        if session is not None and session.word_app is not None:
            word_app = session.word_app  # the session's current Word wins over a handle captured before a recycle

        import pythoncom

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        owns_word = word_app is None
        co_initialized = False

        if owns_word:
            pythoncom.CoInitialize()
            co_initialized = True
            word_app = _start_word()

        state: dict[str, object] = {"word": word_app}

        def export(docx: Path, out_pdf: Path) -> None:
            if session is not None and session.word_app is not None:
                state["word"] = session.word_app
            word = state["word"]
            doc = None
            try:
                doc = word.Documents.Open(str(docx.resolve()))
                self._export_fixed_format(doc, out_pdf)
            finally:
                if doc is not None:
                    try:
                        doc.Close(SaveChanges=False)
                    except Exception:
                        pass

        def recycle() -> None:
            if session is not None:
                if session.restart_word():
                    state["word"] = session.word_app
                return
            if owns_word:
                _quit_word(state["word"])
                state["word"] = _start_word()

        try:
            self.last_conversion = convert_docx_native_restored(
                docx_path, pdf_path, export, recycle=recycle, restore_images=restore_images
            )
        finally:
            if owns_word and state["word"] is not None:
                word_to_quit = state["word"]
                state["word"] = None
                _quit_word(word_to_quit)
                del word_to_quit
                import gc

                gc.collect()
            if co_initialized:
                try:
                    import gc

                    gc.collect()
                    time.sleep(0.2)
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        if not pdf_path.exists():
            raise RuntimeError(f"COM export failed: {pdf_path} not found after export.")
        return pdf_path

    def merge_pdfs(
        self,
        primary_pdf: Path,
        secondary_pdf: Path,
        output_pdf: Path,
    ) -> Path:
        """Combine `primary_pdf` and `secondary_pdf` sequentially into `output_pdf` via merge_pdfs_batch."""
        return self.merge_pdfs_batch([primary_pdf, secondary_pdf], output_pdf)

    def merge_pdfs_batch(
        self,
        pdf_paths: Sequence[Path],
        output_pdf: Path,
    ) -> Path:
        """Combine a sequence of PDFs in order into `output_pdf` via PyMuPDF in one pass.

        Supports in-place merge where `output_pdf` is an input path by writing to a temporary
        file and atomically replacing the target after closing all handles.
        """
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        temp_out = output_pdf.parent / f".tmp_mrg_{output_pdf.name}"
        out_doc = fitz.open()
        try:
            for p in pdf_paths:
                p_resolved = Path(p).resolve()
                if not p_resolved.exists():
                    continue
                src_doc = fitz.open(p_resolved)
                try:
                    out_doc.insert_pdf(src_doc)
                finally:
                    src_doc.close()

            out_doc.save(temp_out, garbage=3, deflate=True)
        except Exception:
            try:
                temp_out.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        finally:
            out_doc.close()

        os.replace(temp_out, output_pdf)
        return output_pdf


class FakeDocumentConverter(DocumentConverter):
    """Fake document converter implementation for testing without COM execution."""

    def __init__(
        self,
        optimize_page_setup: bool = True,
    ) -> None:
        """Initialize the fake converter and tracking lists for method invocations."""
        self.optimize_page_setup = optimize_page_setup
        self.convert_testsheet_calls: list[tuple[Path, Path, Sequence[str] | None]] = []
        self.conversion_outcomes: dict[str, PartConversionOutcome] = {}
        self.last_conversion: PartConversionOutcome | None = None
        self.convert_docx_calls: list[tuple[Path, Path]] = []
        self.merge_pdfs_calls: list[tuple[Path, Path, Path]] = []
        self.merge_pdfs_batch_calls: list[tuple[Sequence[Path], Path]] = []
        self.testsheet_calls = self.convert_testsheet_calls
        self.docx_calls = self.convert_docx_calls
        self.merge_calls = self.merge_pdfs_calls

    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
        excel_app: object | None = None,
        session: BatchComSession | None = None,
    ) -> Path:
        """Record the call and write valid mock PDF content to `pdf_path`."""
        self.convert_testsheet_calls.append((xlsx_path, pdf_path, target_sheets))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        selected_sheets = list(target_sheets) if target_sheets is not None else None
        if selected_sheets is None and xlsx_path.exists():
            try:
                import openpyxl
                wb = openpyxl.load_workbook(xlsx_path, data_only=True)
                raw_selected = select_and_sort_sheets(wb.sheetnames)
                filtered_sheets = []
                for sname in raw_selected:
                    s_lower = sname.strip().lower()
                    if "extra" in s_lower and sname in wb.sheetnames:
                        ws = wb[sname]
                        b15 = ws["B15"].value
                        c15 = ws["C15"].value
                        if (b15 is None or str(b15).strip() == "") and (c15 is None or str(c15).strip() == ""):
                            continue
                    filtered_sheets.append(sname)
                selected_sheets = filtered_sheets
                wb.close()
            except Exception:
                selected_sheets = None

        writer = PdfWriter()
        if selected_sheets:
            for sname in selected_sheets:
                layout = classify_sheet_layout(sname)
                if layout == "visual_inspection":
                    writer.add_blank_page(width=612, height=792)  # Portrait A4
                else:
                    writer.add_blank_page(width=792, height=612)  # Landscape A4
        else:
            page_count = len(target_sheets) if target_sheets is not None and len(target_sheets) > 0 else 1
            for _ in range(page_count):
                writer.add_blank_page(width=792, height=612)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        return pdf_path

    def convert_docx_to_pdf(
        self,
        docx_path: Path,
        pdf_path: Path,
        word_app: object | None = None,
        session: BatchComSession | None = None,
        restore_images: bool = True,
    ) -> Path:
        """Record the call and write valid mock PDF content to `pdf_path`."""
        self.convert_docx_calls.append((docx_path, pdf_path))
        self.last_conversion = self.conversion_outcomes.get(docx_path.name, PartConversionOutcome(docx_path))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        return pdf_path

    def _merge_pdf_files(
        self,
        pdf_paths: Sequence[Path],
        output_pdf: Path,
        default_pages: int,
    ) -> Path:
        """Internal helper to merge PDF files via PyMuPDF or write fallback mock blank pages."""
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        temp_out = output_pdf.parent / f".tmp_mrg_{output_pdf.name}"

        existing_paths = [Path(p).resolve() for p in pdf_paths if Path(p).exists()]
        if existing_paths:
            out_doc = fitz.open()
            try:
                for p in existing_paths:
                    src_doc = fitz.open(p)
                    try:
                        out_doc.insert_pdf(src_doc)
                    finally:
                        src_doc.close()
                out_doc.save(temp_out, garbage=3, deflate=True)
            finally:
                out_doc.close()
            os.replace(temp_out, output_pdf)
        else:
            out_doc = fitz.open()
            try:
                for _ in range(default_pages):
                    out_doc.new_page(width=612, height=792)
                out_doc.save(temp_out, garbage=3, deflate=True)
            finally:
                out_doc.close()
            os.replace(temp_out, output_pdf)

        return output_pdf

    def merge_pdfs(
        self,
        primary_pdf: Path,
        secondary_pdf: Path,
        output_pdf: Path,
    ) -> Path:
        """Record the call and merge PDFs via PyMuPDF or write mock merged PDF content."""
        self.merge_pdfs_calls.append((primary_pdf, secondary_pdf, output_pdf))
        return self._merge_pdf_files([primary_pdf, secondary_pdf], output_pdf, default_pages=2)

    def merge_pdfs_batch(
        self,
        pdf_paths: Sequence[Path],
        output_pdf: Path,
    ) -> Path:
        """Record the call and merge multiple PDFs sequentially via PyMuPDF."""
        self.merge_pdfs_batch_calls.append((tuple(pdf_paths), output_pdf))
        return self._merge_pdf_files(pdf_paths, output_pdf, default_pages=max(1, len(pdf_paths)))
