"""Workflow for converting all DOCX files in a folder to PDF using Word COM automation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]

from src.postprocessing.converters import (
    ComDocumentConverter,
    DocumentConverter,
    configure_uniform_printer,
)
from src.workflows.progress import ProgressSink, QuantityProgressTracker


@dataclass(frozen=True)
class DocxToPdfSummary:
    input_directory: Path
    converted_count: int
    __test__ = False


def convert_docx_folder_to_pdf(
    input_directory: str | Path,
    *,
    converter: DocumentConverter | None = None,
    progress_sink: ProgressSink | None = print,
) -> DocxToPdfSummary:
    """Convert every DOCX file in a directory to PDF using DocumentConverter seam."""
    input_dir = Path(input_directory).expanduser().resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {input_dir}")

    docx_files = [
        path for path in sorted(input_dir.iterdir())
        if path.suffix.lower() == ".docx" and not path.name.startswith("~$")
    ]

    if not docx_files:
        print(f"No DOCX files found in: {input_dir}")
        return DocxToPdfSummary(input_directory=input_dir, converted_count=0)

    if converter is None:
        converter = ComDocumentConverter()

    tracker = QuantityProgressTracker(total=len(docx_files), sink=progress_sink)
    converted = 0

    is_com = isinstance(converter, ComDocumentConverter)
    word_app = None
    co_initialized = False

    try:
        if is_com and pythoncom and win32com and getattr(win32com, "client", None):
            pythoncom.CoInitialize()
            co_initialized = True
            word_app = win32com.client.DispatchEx("Word.Application")
            word_app.Visible = False
            word_app.DisplayAlerts = 0
            configure_uniform_printer(word_app)

        for idx, docx_path in enumerate(docx_files, start=1):
            output_path = docx_path.with_suffix(".pdf")
            tracker.emit(idx, f"Converting: {docx_path.name} -> {output_path.name}")
            if word_app is not None:
                converter.convert_docx_to_pdf(docx_path, output_path, word_app=word_app)
            else:
                converter.convert_docx_to_pdf(docx_path, output_path)
            converted += 1
    finally:
        if word_app is not None:
            try:
                word_app.Quit()
            except Exception:
                pass
            word_app = None
        if co_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    tracker.complete(f"Conversion complete! Converted {converted} DOCX file(s).")
    return DocxToPdfSummary(input_directory=input_dir, converted_count=converted)


def run_docx_to_pdf() -> DocxToPdfSummary:
    """Interactive entrypoint for batch DOCX to PDF conversion."""
    input_directory = input("Enter the path to the folder that you want to convert to pdf: ").strip().strip('"')
    summary = convert_docx_folder_to_pdf(input_directory)
    print(f"Converted {summary.converted_count} DOCX file(s) to PDF in {summary.input_directory}.")
    return summary


run_convert_docx_to_pdf = run_docx_to_pdf
