"""Workflow for converting all DOCX files in a folder to PDF using Word COM automation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.postprocessing.converters import ComDocumentConverter, DocumentConverter


@dataclass(frozen=True)
class DocxToPdfSummary:
    input_directory: Path
    converted_count: int


from src.workflows.progress import ProgressSink, QuantityProgressTracker


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
    for idx, docx_path in enumerate(docx_files, start=1):
        output_path = docx_path.with_suffix(".pdf")
        tracker.emit(idx, f"Converting: {docx_path.name} -> {output_path.name}")
        converter.convert_docx_to_pdf(docx_path, output_path)
        converted += 1

    tracker.complete(f"Conversion complete! Converted {converted} DOCX file(s).")
    return DocxToPdfSummary(input_directory=input_dir, converted_count=converted)


def run_docx_to_pdf() -> DocxToPdfSummary:
    """Interactive entrypoint for batch DOCX to PDF conversion."""
    input_directory = input("Enter the path to the folder that you want to convert to pdf: ").strip().strip('"')
    summary = convert_docx_folder_to_pdf(input_directory)
    print(f"Converted {summary.converted_count} DOCX file(s) to PDF in {summary.input_directory}.")
    return summary


run_convert_docx_to_pdf = run_docx_to_pdf
