"""Document converters using Windows COM automation and fake/mock implementations."""

from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

from PyPDF2 import PdfReader, PdfWriter


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


def select_and_sort_sheets(
    worksheet_names: Sequence[str],
    target_sheets: Sequence[str] | None = None,
) -> list[str]:
    """Select and sort target worksheet names from a workbook.

    If `target_sheets` is None, matches any sheets where `_is_pce_testsheet_sheet`
    or `_is_pce_vi_sheet` returns True. Sorts PCE Testsheet and copied variations
    (`(2)`, `(3)`) first, and PCE VI and copied variations (`(2)`, `(3)`) last.
    If `target_sheets` is specified, matches exact sheet names present in the
    workbook.
    """
    if target_sheets is not None:
        return [name for name in target_sheets if name in worksheet_names]

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


class DocumentConverter(ABC):
    """Abstract base class defining the document converter contract."""

    @abstractmethod
    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
    ) -> Path:
        """Convert an Excel testsheet workbook to a PDF file."""
        ...

    @abstractmethod
    def convert_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> Path:
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


class ComDocumentConverter(DocumentConverter):
    """Document converter utilizing Windows COM automation (`win32com.client`)."""

    def __init__(self, optimize_page_setup: bool = True, try_adobe_printer: bool = True) -> None:
        """Initialize the COM converter with optional PageSetup optimization and Adobe PDF virtual printer selection."""
        self.optimize_page_setup = optimize_page_setup
        self.try_adobe_printer = try_adobe_printer

    def _configure_adobe_printer(self, excel_app: object) -> None:
        """Attempt to switch `ActivePrinter` to 'Adobe PDF' if installed."""
        if not self.try_adobe_printer:
            return
        try:
            current_printer = str(getattr(excel_app, "ActivePrinter", ""))
            if "adobe pdf" not in current_printer.lower():
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows NT\CurrentVersion\Devices",
                ) as key:
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(key, i)
                            if "adobe pdf" in name.lower():
                                parts = str(val).split(",")
                                if len(parts) >= 2:
                                    port = parts[1].strip()
                                    target_printer = f"{name} on {port}"
                                    excel_app.ActivePrinter = target_printer
                                    break
                            i += 1
                        except OSError:
                            break
        except Exception as exc:
            logging.debug("Could not configure Adobe PDF printer: %s", exc)

    def _configure_target_page_setup(self, target: object) -> None:
        """Enforce standardized PageSetup properties (`FitToPagesWide=1`, `FitToPagesTall=1`, `Zoom=False`)."""
        if not self.optimize_page_setup:
            return
        try:
            sheets_to_process = []
            if hasattr(target, "PageSetup"):
                sheets_to_process.append(target)
            elif hasattr(target, "Worksheets"):
                sheets_to_process.extend(list(target.Worksheets))

            for ws in sheets_to_process:
                try:
                    ws.PageSetup.Zoom = False
                    ws.PageSetup.FitToPagesWide = 1
                    ws.PageSetup.FitToPagesTall = 1
                except Exception as exc:
                    logging.debug("Could not configure PageSetup for sheet: %s", exc)
        except Exception as exc:
            logging.debug("Could not inspect sheets for PageSetup: %s", exc)

    def _merge_temp_pdfs(self, temp_pdfs: Sequence[Path], output_pdf: Path) -> Path:
        """Merge temporary sheet PDFs into `output_pdf` sequentially using PyPDF2."""
        writer = PdfWriter()
        open_streams = []
        try:
            for temp_pdf in temp_pdfs:
                if temp_pdf.exists():
                    stream = open(temp_pdf, "rb")
                    open_streams.append(stream)
                    reader = PdfReader(stream)
                    for page in reader.pages:
                        writer.add_page(page)

            buffer = io.BytesIO()
            writer.write(buffer)
        finally:
            for stream in open_streams:
                try:
                    stream.close()
                except Exception:
                    pass

        with open(output_pdf, "wb") as f_out:
            f_out.write(buffer.getvalue())
        return output_pdf

    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
    ) -> Path:
        """Convert testsheet workbook to PDF using COM automation."""
        import win32com.client as win32

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        excel_app = win32.Dispatch("Excel.Application")
        excel_app.Visible = False
        excel_app.DisplayAlerts = False

        wb = None
        try:
            self._configure_adobe_printer(excel_app)
            wb = excel_app.Workbooks.Open(str(xlsx_path.resolve()), ReadOnly=True)
            worksheet_names = [ws.Name for ws in wb.Worksheets]
            selected_names = select_and_sort_sheets(worksheet_names, target_sheets)
            ws_map = {ws.Name: ws for ws in wb.Worksheets}
            selected_sheets = [ws_map[name] for name in selected_names if name in ws_map]

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
            try:
                excel_app.Quit()
            except Exception:
                pass
            excel_app = None

        if not pdf_path.exists():
            raise RuntimeError(f"COM export failed: {pdf_path} not found after export.")
        return pdf_path

    def convert_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> Path:
        """Convert Word document to PDF using COM SaveAs2."""
        import win32com.client as win32

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        word_app = win32.Dispatch("Word.Application")
        word_app.Visible = False
        word_app.DisplayAlerts = 0

        doc = None
        try:
            doc = word_app.Documents.Open(str(docx_path.resolve()))
            doc.SaveAs2(str(pdf_path.resolve()), FileFormat=17)
        finally:
            if doc is not None:
                try:
                    doc.Close(SaveChanges=False)
                except Exception:
                    pass
                doc = None
            try:
                word_app.Quit()
            except Exception:
                pass
            word_app = None

        if not pdf_path.exists():
            raise RuntimeError(f"COM export failed: {pdf_path} not found after export.")
        return pdf_path

    def merge_pdfs(
        self,
        primary_pdf: Path,
        secondary_pdf: Path,
        output_pdf: Path,
    ) -> Path:
        """Combine `primary_pdf` and `secondary_pdf` sequentially into `output_pdf` via PyPDF2.

        Supports in-place merge where `output_pdf` is the same path as `primary_pdf`
        or `secondary_pdf` by buffering the merged result before writing to disk.
        """
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with open(primary_pdf, "rb") as f_primary, open(secondary_pdf, "rb") as f_secondary:
            primary_reader = PdfReader(f_primary)
            secondary_reader = PdfReader(f_secondary)

            writer = PdfWriter()
            for page in primary_reader.pages:
                writer.add_page(page)
            for page in secondary_reader.pages:
                writer.add_page(page)

            buffer = io.BytesIO()
            writer.write(buffer)

        with open(output_pdf, "wb") as f_out:
            f_out.write(buffer.getvalue())

        return output_pdf


class FakeDocumentConverter(DocumentConverter):
    """Fake document converter implementation for testing without COM execution."""

    def __init__(self, optimize_page_setup: bool = True, try_adobe_printer: bool = True) -> None:
        """Initialize the fake converter and tracking lists for method invocations."""
        self.optimize_page_setup = optimize_page_setup
        self.try_adobe_printer = try_adobe_printer
        self.convert_testsheet_calls: list[tuple[Path, Path, Sequence[str] | None]] = []
        self.convert_docx_calls: list[tuple[Path, Path]] = []
        self.merge_pdfs_calls: list[tuple[Path, Path, Path]] = []
        self.testsheet_calls = self.convert_testsheet_calls
        self.docx_calls = self.convert_docx_calls
        self.merge_calls = self.merge_pdfs_calls

    def convert_testsheet_to_pdf(
        self,
        xlsx_path: Path,
        pdf_path: Path,
        target_sheets: Sequence[str] | None = None,
    ) -> Path:
        """Record the call and write valid mock PDF content to `pdf_path`."""
        self.convert_testsheet_calls.append((xlsx_path, pdf_path, target_sheets))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        writer = PdfWriter()
        page_count = len(target_sheets) if target_sheets is not None and len(target_sheets) > 0 else 1
        for _ in range(page_count):
            writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        return pdf_path

    def convert_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> Path:
        """Record the call and write valid mock PDF content to `pdf_path`."""
        self.convert_docx_calls.append((docx_path, pdf_path))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        return pdf_path

    def merge_pdfs(
        self,
        primary_pdf: Path,
        secondary_pdf: Path,
        output_pdf: Path,
    ) -> Path:
        """Record the call and merge PDFs via PyPDF2 or write mock merged PDF content."""
        self.merge_pdfs_calls.append((primary_pdf, secondary_pdf, output_pdf))
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        if primary_pdf.exists() and secondary_pdf.exists():
            with open(primary_pdf, "rb") as f_primary, open(secondary_pdf, "rb") as f_secondary:
                primary_reader = PdfReader(f_primary)
                secondary_reader = PdfReader(f_secondary)

                writer = PdfWriter()
                for page in primary_reader.pages:
                    writer.add_page(page)
                for page in secondary_reader.pages:
                    writer.add_page(page)

                buffer = io.BytesIO()
                writer.write(buffer)

            with open(output_pdf, "wb") as f_out:
                f_out.write(buffer.getvalue())
        else:
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_blank_page(width=612, height=792)
            with open(output_pdf, "wb") as f:
                writer.write(f)

        return output_pdf
