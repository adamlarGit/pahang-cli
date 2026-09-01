"""Workflow for combining PDFs from primary and secondary folders."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.postprocessing.converters import ComDocumentConverter, DocumentConverter


@dataclass(frozen=True)
class CombinePdfsSummary:
    primary_folder: Path
    secondary_folder: Path
    merged_count: int


from src.workflows.progress import ProgressSink, QuantityProgressTracker


def combine_primary_secondary_pdfs(
    primary_folder: str | Path,
    secondary_folder: str | Path,
    *,
    converter: DocumentConverter | None = None,
    progress_sink: ProgressSink | None = print,
) -> CombinePdfsSummary:
    """Merge pages of matching PDFs in secondary folder into primary folder PDFs using DocumentConverter seam."""
    primary = Path(primary_folder).expanduser().resolve()
    secondary = Path(secondary_folder).expanduser().resolve()

    if not primary.is_dir():
        raise FileNotFoundError(f"Primary folder not found: {primary}")
    if not secondary.is_dir():
        raise FileNotFoundError(f"Secondary folder not found: {secondary}")

    primary_files = sorted([p.name for p in primary.iterdir() if p.is_file() and p.name.lower().endswith(".pdf") and not p.name.startswith("~$")])
    secondary_files = sorted([p.name for p in secondary.iterdir() if p.is_file() and p.name.lower().endswith(".pdf") and not p.name.startswith("~$")])

    if len(primary_files) != len(secondary_files):
        raise ValueError(
            f"Quantity mismatch: Primary folder has {len(primary_files)} PDF file(s), but Secondary folder has {len(secondary_files)} PDF file(s). "
            f"Exact quantity match is required before merging."
        )

    if converter is None:
        converter = ComDocumentConverter()

    tracker = QuantityProgressTracker(total=len(primary_files), sink=progress_sink)
    merged_count = 0
    for idx, filename in enumerate(primary_files, start=1):
        primary_path = primary / filename
        secondary_path = secondary / filename

        if not secondary_path.exists():
            raise FileNotFoundError(
                f"Cannot merge: Secondary PDF '{filename}' not found in '{secondary.name}' for primary PDF '{filename}'. Exact matching is required."
            )

        tracker.emit(idx, f"Merging PDF: {filename}")
        converter.merge_pdfs(primary_path, secondary_path, primary_path)

        logging.info(f"Successfully merged and replaced: {filename}")
        merged_count += 1

    tracker.complete(f"Successfully merged {merged_count} PDF file(s).")
    return CombinePdfsSummary(
        primary_folder=primary,
        secondary_folder=secondary,
        merged_count=merged_count,
    )


def run_combine_pdfs() -> CombinePdfsSummary:
    """Interactive entrypoint for combining PDFs from primary and secondary folders."""
    primary_folder = input("Enter primary folder directory: ").strip().strip('"')
    secondary_folder = input("Enter secondary folder directory: ").strip().strip('"')

    try:
        summary = combine_primary_secondary_pdfs(primary_folder, secondary_folder)
        print(f"Successfully merged {summary.merged_count} PDF file(s).")
        return summary
    except (ValueError, FileNotFoundError) as err:
        print(f"\n [X] HARD STOP: {err}\n")
        logging.error("Combine PDFs aborted: %s", err)
        return CombinePdfsSummary(
            primary_folder=Path(primary_folder),
            secondary_folder=Path(secondary_folder),
            merged_count=0,
        )
