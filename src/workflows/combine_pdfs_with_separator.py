"""Workflow for combining PDFs in ascending numerical order with a separator sheet inserted between files."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from src.workflows.progress import ProgressSink, QuantityProgressTracker


@dataclass(frozen=True)
class CombinePdfsWithSeparatorSummary:
    """Execution summary for combining PDFs with separator sheets."""

    target_folder: Path
    separator_path: Path
    output_pdf_path: Path
    merged_count: int


def combine_pdfs_with_separator(
    target_folder: str | Path,
    separator_path: str | Path,
    *,
    output_filename: str = "combined.pdf",
    progress_sink: ProgressSink | None = print,
) -> CombinePdfsWithSeparatorSummary:
    """Combine PDF files in target_folder in ascending numerical order with separator_path between them."""
    target = Path(target_folder).expanduser().resolve()
    separator = Path(separator_path).expanduser().resolve()

    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Target folder not found or not a directory: {target}")

    if not separator.exists() or not separator.is_file():
        raise FileNotFoundError(f"Separator sheet PDF not found: {separator}")

    pdf_files = [
        p for p in target.iterdir()
        if p.is_file() and p.name.lower().endswith(".pdf") and not p.name.startswith("~$") and not p.name.startswith(".")
    ]

    if not pdf_files:
        raise ValueError(f"HARD STOP: No PDF files found in directory '{target.name}'.")

    numbered_files: list[tuple[int, Path]] = []
    for pdf in pdf_files:
        match = re.match(r"^(\d+)", pdf.name)
        if not match:
            raise ValueError(
                f"HARD STOP: File '{pdf.name}' does not start with a numerical prefix."
            )
        num = int(match.group(1))
        numbered_files.append((num, pdf))

    numbered_files.sort(key=lambda item: (item[0], item[1].name))

    output_dir = target / "combined_pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf_path = output_dir / output_filename

    tracker = QuantityProgressTracker(total=len(numbered_files), sink=progress_sink)
    writer = PdfWriter()

    with open(separator, "rb") as f_sep:
        sep_reader = PdfReader(f_sep)
        sep_pages = list(sep_reader.pages)

        open_streams = []
        try:
            for idx, (num_val, pdf_path) in enumerate(numbered_files, start=1):
                tracker.emit(idx, f"Processing PDF #{idx}: {pdf_path.name}")
                if idx > 1:
                    for s_page in sep_pages:
                        writer.add_page(s_page)

                stream = open(pdf_path, "rb")
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

    with open(output_pdf_path, "wb") as f_out:
        f_out.write(buffer.getvalue())

    merged_count = len(numbered_files)
    tracker.complete(
        f"Successfully combined {merged_count} PDF file(s) into '{output_pdf_path.name}' with separator sheets."
    )

    return CombinePdfsWithSeparatorSummary(
        target_folder=target,
        separator_path=separator,
        output_pdf_path=output_pdf_path,
        merged_count=merged_count,
    )


def run_combine_pdfs_with_separator(environment: object | None = None) -> CombinePdfsWithSeparatorSummary | None:
    """Interactive CLI entrypoint for combining PDFs with a separator sheet."""
    from src import cli_selectors
    from src.project.environment import get_or_create_utility_environment

    env = environment or get_or_create_utility_environment()
    if env is None:
        print("No project environment available.")
        return None

    try:
        separator_path = env.get_template("separator_sheet")
    except Exception as err:
        print(f"\n [X] HARD STOP: Could not resolve separator sheet template: {err}\n")
        logging.error("Combine PDFs with separator aborted: %s", err)
        return None

    target_dir = cli_selectors.select_testsheet_subfolder(
        environment=env,
        title="Select TESTSHEET folder containing PDFs to combine",
    )

    if target_dir is None:
        print("Operation cancelled.")
        return None

    try:
        summary = combine_pdfs_with_separator(target_dir, separator_path)
        print(f"\n[SUCCESS] Merged {summary.merged_count} file(s) into '{summary.output_pdf_path}'.")
        return summary
    except (ValueError, FileNotFoundError) as err:
        print(f"\n [X] HARD STOP: {err}\n")
        logging.error("Combine PDFs with separator aborted: %s", err)
        return None
