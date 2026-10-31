"""Document converters using Windows COM automation and fake/mock implementations."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
import re
from types import TracebackType
from typing import Sequence

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PyPDF2 import PdfWriter


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
                word = win32.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                word.ScreenUpdating = False
                if self.configure_printer:
                    configure_uniform_printer(word)
                self.word_app = word

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

        # Cleanup Word
        if self.word_app is not None:
            word = self.word_app
            self.word_app = None
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
                    del word
                import gc
                gc.collect()
            finally:
                if was_enabled:
                    try:
                        faulthandler.enable()
                    except Exception:
                        pass

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
        try_adobe_printer: bool = True,
        adobe_timeout: float = 30.0,
    ) -> None:
        """Initialize the COM converter with optional PageSetup optimization and Adobe PDF virtual printer selection."""
        self.optimize_page_setup = optimize_page_setup
        self.try_adobe_printer = try_adobe_printer
        self.adobe_timeout = adobe_timeout

    def _find_adobe_pdf_printer(self) -> str | None:
        """Detect whether 'Adobe PDF' printer is available in the Windows registry Devices list."""
        devices = get_installed_printers()
        for dev_name, full_spec in devices.items():
            if "adobe pdf" in dev_name:
                return full_spec
        return None

    def _is_distiller_available(self) -> bool:
        """Detect whether Acrobat Distiller registry configuration is present on host."""
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Adobe\Acrobat Distiller",
            ):
                return True
        except Exception:
            return False

    def _detect_distiller_joboptions_preset(self) -> str:
        """Detect the optimal Acrobat Distiller joboptions preset name.

        Prioritizes 'High Quality Print(1)', followed by 'High Quality Print' and 'Press Quality'.
        """
        candidates = ["High Quality Print(1)", "High Quality Print", "Press Quality"]
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Adobe\Acrobat Distiller\AdobePDFSettings",
            ) as key:
                available_settings = set()
                i = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, i)
                        if name:
                            available_settings.add(str(name).strip())
                        i += 1
                    except OSError:
                        break
                for candidate in candidates:
                    if candidate in available_settings:
                        return candidate
        except Exception as exc:
            logging.debug("Could not query AdobePDFSettings in registry: %s", exc)

        fs_dirs = [
            Path(os.environ.get("APPDATA", "")) / "Adobe" / "Adobe PDF" / "Settings",
            Path(os.environ.get("ProgramData", "")) / "Adobe" / "Adobe PDF" / "Settings",
        ]
        for candidate in candidates:
            for d in fs_dirs:
                if (d / f"{candidate}.joboptions").exists():
                    return candidate

        return "High Quality Print(1)"

    def _set_transient_distiller_joboptions(self, preset: str) -> dict[str, str | None]:
        """Configure transient Distiller JobOptions preset across Distiller version keys, preserving original values."""
        import winreg

        backup: dict[str, str | None] = {}
        distiller_path = r"Software\Adobe\Acrobat Distiller"

        subkeys_to_check = [""]
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                distiller_path,
                0,
                winreg.KEY_READ,
            ) as root_key:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root_key, i)
                        if sub.lower() not in ("printerjobcontrol", "adobepdfsettings"):
                            subkeys_to_check.append(sub)
                        i += 1
                    except OSError:
                        break
        except OSError:
            return backup

        for sub in subkeys_to_check:
            full_sub_path = f"{distiller_path}\\{sub}" if sub else distiller_path
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    full_sub_path,
                    0,
                    winreg.KEY_READ | winreg.KEY_SET_VALUE,
                ) as key:
                    try:
                        orig_val, _ = winreg.QueryValueEx(key, "JobOptions")
                        backup[sub] = orig_val
                    except OSError:
                        if sub and (sub == "DC" or re.match(r"^\d+\.\d+$", sub)):
                            backup[sub] = None
                        else:
                            continue

                    winreg.SetValueEx(key, "JobOptions", 0, winreg.REG_SZ, preset)
            except OSError:
                pass

        return backup

    def _restore_distiller_joboptions(self, backup: dict[str, str | None]) -> None:
        """Restore Acrobat Distiller JobOptions settings to their previous values."""
        import winreg

        distiller_path = r"Software\Adobe\Acrobat Distiller"
        for sub, orig_val in backup.items():
            full_sub_path = f"{distiller_path}\\{sub}" if sub else distiller_path
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    full_sub_path,
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    if orig_val is not None:
                        winreg.SetValueEx(key, "JobOptions", 0, winreg.REG_SZ, orig_val)
                    else:
                        try:
                            winreg.DeleteValue(key, "JobOptions")
                        except OSError:
                            pass
            except OSError:
                pass

    def _register_printer_job_control(self, word_app: object, pdf_path: Path) -> list[str]:
        """Register output PDF path entries in HKCU\\Software\\Adobe\\Acrobat Distiller\\PrinterJobControl."""
        import winreg

        target_str = str(pdf_path.resolve())
        entries: list[str] = [
            "WINWORD.EXE",
            "splwow64.exe",
            str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "splwow64.exe"),
        ]
        word_path = getattr(word_app, "Path", None)
        if word_path:
            full_word_exe = str(Path(word_path) / "WINWORD.EXE")
            if full_word_exe not in entries:
                entries.append(full_word_exe)

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Adobe\Acrobat Distiller\PrinterJobControl",
        ) as pjc_key:
            for entry in entries:
                winreg.SetValueEx(pjc_key, entry, 0, winreg.REG_SZ, target_str)

        return entries

    def _cleanup_printer_job_control(self, entry_names: list[str]) -> None:
        """Deterministically remove registered entries from PrinterJobControl in registry."""
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Adobe\Acrobat Distiller\PrinterJobControl",
                0,
                winreg.KEY_SET_VALUE,
            ) as pjc_key:
                for entry in entry_names:
                    try:
                        winreg.DeleteValue(pjc_key, entry)
                    except OSError:
                        pass
        except OSError:
            pass

    def _wait_for_pdf(self, pdf_path: Path, timeout: float = 30.0, poll_interval: float = 0.25) -> bool:
        """Wait for PDF to be fully created, unlocked, and contain the valid EOF token."""
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            if pdf_path.exists():
                try:
                    size = pdf_path.stat().st_size
                    if size > 0:
                        with open(pdf_path, "rb+") as f:
                            f.seek(max(0, size - 1024))
                            tail = f.read()
                            if b"%%EOF" in tail:
                                return True
                except (OSError, PermissionError):
                    pass
            time.sleep(poll_interval)

        return False

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

    def _convert_docx_via_adobe_pdf(
        self,
        word_app: object,
        doc: object,
        pdf_path: Path,
        printer_spec: str,
    ) -> bool:
        """Route Word document conversion through Adobe PDF virtual printer with silent PrinterJobControl automation."""
        preset = self._detect_distiller_joboptions_preset()
        joboptions_backup: dict[str, str | None] = {}
        registered_entries: list[str] = []
        orig_printer = None

        try:
            joboptions_backup = self._set_transient_distiller_joboptions(preset)
            registered_entries = self._register_printer_job_control(word_app, pdf_path)

            try:
                orig_printer = getattr(word_app, "ActivePrinter", None)
            except Exception:
                orig_printer = None

            try:
                word_app.ActivePrinter = printer_spec
            except Exception:
                word_app.ActivePrinter = "Adobe PDF"

            if pdf_path.exists():
                try:
                    pdf_path.unlink()
                except OSError:
                    pass

            doc.PrintOut(Background=False)

            success = self._wait_for_pdf(pdf_path, timeout=self.adobe_timeout)
            if not success or not pdf_path.exists() or pdf_path.stat().st_size == 0:
                raise RuntimeError(f"Adobe PDF printer failed to produce output at {pdf_path}")
            return True

        finally:
            if registered_entries:
                self._cleanup_printer_job_control(registered_entries)
            if joboptions_backup:
                self._restore_distiller_joboptions(joboptions_backup)
            if orig_printer is not None:
                try:
                    word_app.ActivePrinter = orig_printer
                except Exception:
                    pass

    def _configure_adobe_printer(self, excel_app: object) -> None:
        """Configure printer for Excel COM automation."""
        self._configure_uniform_printer(excel_app)

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
    ) -> Path:
        """Convert Word document to PDF using dual-mode silent Adobe PDF printing with native ExportAsFixedFormat fallback."""
        if session is not None and word_app is None:
            word_app = session.word_app

        import pythoncom
        import win32com.client as win32

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        owns_word = word_app is None
        co_initialized = False

        if owns_word:
            pythoncom.CoInitialize()
            co_initialized = True
            word_app = win32.DispatchEx("Word.Application")
            word_app.Visible = False
            word_app.DisplayAlerts = 0
            self._configure_uniform_printer(word_app)

        doc = None
        try:
            doc = word_app.Documents.Open(str(docx_path.resolve()))
            converted = False

            if self.try_adobe_printer:
                printer_spec = self._find_adobe_pdf_printer()
                if printer_spec and self._is_distiller_available():
                    try:
                        converted = self._convert_docx_via_adobe_pdf(
                            word_app, doc, pdf_path, printer_spec
                        )
                    except Exception as exc:
                        logging.warning(
                            "Silent Adobe PDF print failed for %s (%s); falling back to native ExportAsFixedFormat",
                            docx_path.name,
                            exc,
                        )
                        converted = False

            if not converted:
                try:
                    self._export_fixed_format(doc, pdf_path)
                except Exception as export_exc:
                    logging.debug(
                        "Initial ExportAsFixedFormat failed (%s); retrying with fresh document handle",
                        export_exc,
                    )
                    try:
                        doc.Close(SaveChanges=False)
                    except Exception:
                        pass
                    doc = None
                    doc = word_app.Documents.Open(str(docx_path.resolve()))
                    self._export_fixed_format(doc, pdf_path)
        finally:
            if doc is not None:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    pass
                del doc
                doc = None
            if owns_word and word_app is not None:
                word_to_quit = word_app
                word_app = None
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
                    import gc
                    gc.collect()
                finally:
                    if was_enabled:
                        try:
                            faulthandler.enable()
                        except Exception:
                            pass
            if co_initialized:
                try:
                    import gc
                    gc.collect()
                    import time
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
        try_adobe_printer: bool = True,
        adobe_timeout: float = 30.0,
    ) -> None:
        """Initialize the fake converter and tracking lists for method invocations."""
        self.optimize_page_setup = optimize_page_setup
        self.try_adobe_printer = try_adobe_printer
        self.adobe_timeout = adobe_timeout
        self.convert_testsheet_calls: list[tuple[Path, Path, Sequence[str] | None]] = []
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
    ) -> Path:
        """Record the call and write valid mock PDF content to `pdf_path`."""
        self.convert_docx_calls.append((docx_path, pdf_path))
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
