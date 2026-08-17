"""Workflow for converting all testsheet files in a folder to PDF using Excel COM automation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]

from src.postprocessing.converters import ComDocumentConverter, DocumentConverter
from src.workflows.progress import ProgressSink, QuantityProgressTracker

SUPPORTED_TESTSHEET_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".xlsb"}


@dataclass(frozen=True)
class TestsheetToPdfSummary:
    input_directory: Path
    converted_count: int
    __test__ = False


def convert_testsheet_folder_to_pdf(
    folder_path: str | Path,
    *,
    converter: DocumentConverter | None = None,
    progress_sink: ProgressSink | None = print,
) -> TestsheetToPdfSummary:
    """Convert every testsheet workbook in a folder to a PDF file using DocumentConverter seam."""
    input_dir = Path(folder_path).expanduser().resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {input_dir}")

    testsheet_files = [
        path for path in sorted(input_dir.iterdir())
        if path.suffix.lower() in SUPPORTED_TESTSHEET_EXTENSIONS and not path.name.startswith("~$")
    ]

    if not testsheet_files:
        print(f"No testsheet files found in: {input_dir}")
        return TestsheetToPdfSummary(input_directory=input_dir, converted_count=0)

    if converter is None:
        converter = ComDocumentConverter()

    tracker = QuantityProgressTracker(total=len(testsheet_files), sink=progress_sink)
    converted = 0

    is_com = isinstance(converter, ComDocumentConverter)
    excel_app = None
    co_initialized = False

    try:
        if is_com and pythoncom and win32com and getattr(win32com, "client", None):
            pythoncom.CoInitialize()
            co_initialized = True
            excel_app = win32com.client.DispatchEx("Excel.Application")
            excel_app.Visible = False
            excel_app.DisplayAlerts = False

        for idx, testsheet_path in enumerate(testsheet_files, start=1):
            output_path = testsheet_path.with_suffix(".pdf")
            tracker.emit(idx, f"Converting: {testsheet_path.name} -> {output_path.name}")
            if excel_app is not None:
                converter.convert_testsheet_to_pdf(testsheet_path, output_path, excel_app=excel_app)
            else:
                converter.convert_testsheet_to_pdf(testsheet_path, output_path)
            converted += 1
    finally:
        if excel_app is not None:
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

    tracker.complete(f"Conversion complete. Converted {converted} testsheet file(s).")
    return TestsheetToPdfSummary(input_directory=input_dir, converted_count=converted)


def run_testsheet_to_pdf() -> TestsheetToPdfSummary:
    """Interactive entrypoint for batch testsheet to PDF conversion."""
    folder_path = input("Enter the path to the folder containing testsheet files: ").strip().strip('"')
    summary = convert_testsheet_folder_to_pdf(folder_path)
    print(f"Converted {summary.converted_count} testsheet file(s) to PDF in {summary.input_directory}.")
    return summary
