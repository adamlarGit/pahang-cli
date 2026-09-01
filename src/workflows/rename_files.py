"""Workflow for renaming files in output directory to match input directory names."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.project.storage import extract_numerical_prefix


@dataclass(frozen=True)
class RenamePair:
    old_name: str
    new_name: str


@dataclass(frozen=True)
class RenameFilesSummary:
    input_directory: Path
    output_directory: Path
    renamed: tuple[RenamePair, ...]


def rename_files_match(
    input_directory: str | Path,
    output_directory: str | Path,
    *,
    target_type: str | None = None,
) -> RenameFilesSummary:
    """Rename files or folders in output directory to match names from input directory sorted by numerical prefix."""
    input_dir = Path(input_directory).expanduser().resolve()
    output_dir = Path(output_directory).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found or not a directory: {input_dir}")
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found or not a directory: {output_dir}")

    def sort_key(filename: str) -> tuple[int, str]:
        try:
            return (extract_numerical_prefix(filename), filename.lower())
        except ValueError:
            try:
                return (extract_numerical_prefix(filename, split_char="_"), filename.lower())
            except ValueError:
                return (999999, filename.lower())

    norm_target = (target_type or "").strip().lower()

    output_xlsx_files = [
        p.name
        for p in output_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".xlsx"
        and not p.name.startswith(("~$", "."))
    ]
    output_subdirectories = [
        p.name
        for p in output_dir.iterdir()
        if p.is_dir()
        and not p.name.startswith(("~$", ".", "processed_"))
    ]

    if norm_target in ("xlsx", "testsheet", "testsheets") or (not norm_target and output_xlsx_files):
        # Testsheet mode: strictly rename .xlsx files, ignoring subdirectories (UNSORTED RAW DATA, processed_testsheet, pdf, etc.)
        output_items = sorted(output_xlsx_files, key=sort_key)
    elif norm_target in ("dir", "directory", "directories", "raw_material", "raw_materials") or (not norm_target and output_subdirectories and not output_xlsx_files):
        # Raw material / directory mode: strictly rename subdirectories, ignoring loose files
        output_items = sorted(output_subdirectories, key=sort_key)
    else:
        # Fallback generic mode
        output_items = sorted(
            [
                p.name
                for p in output_dir.iterdir()
                if (p.is_file() or p.is_dir())
                and not p.name.startswith(("~$", ".", "processed_"))
            ],
            key=sort_key,
        )

    all_input_items = [
        p.name
        for p in input_dir.iterdir()
        if (p.is_file() or p.is_dir())
        and not p.name.startswith(("~$", "."))
    ]
    input_docx_files = [p for p in all_input_items if p.lower().endswith(".docx")]

    if input_docx_files and (output_xlsx_files or output_subdirectories):
        input_files = sorted(input_docx_files, key=sort_key)
    else:
        input_files = sorted(all_input_items, key=sort_key)

    if len(input_files) != len(output_items):
        raise ValueError(
            f"Quantity mismatch: Input directory has {len(input_files)} item(s), but Output directory has {len(output_items)} item(s). "
            f"Exact quantity match is required before renaming."
        )

    prefix_to_input: dict[int, str] = {}
    for inp in input_files:
        try:
            num = extract_numerical_prefix(inp)
            prefix_to_input[num] = inp
        except ValueError:
            pass

    paired: list[tuple[str, str]] = []
    prefix_matched = True
    for out in output_items:
        try:
            num = extract_numerical_prefix(out)
            if num in prefix_to_input:
                paired.append((out, prefix_to_input[num]))
            else:
                prefix_matched = False
                break
        except ValueError:
            prefix_matched = False
            break

    if not prefix_matched or len(paired) != len(output_items):
        paired = list(zip(output_items, input_files))

    renamed: list[RenamePair] = []
    for old_name, input_name in paired:
        old_path = output_dir / old_name
        if old_path.is_dir():
            ext = ""
        else:
            _, ext = os.path.splitext(old_name)
        new_name = os.path.splitext(input_name)[0] + ext

        new_path = output_dir / new_name
        if new_path.exists() and new_path != old_path:
            raise FileExistsError(f"'{new_name}' already exists in output directory. Rename aborted.")

        if new_path != old_path:
            old_path.rename(new_path)
            renamed.append(RenamePair(old_name=old_name, new_name=new_name))

    return RenameFilesSummary(
        input_directory=input_dir,
        output_directory=output_dir,
        renamed=tuple(renamed),
    )


from src.workflows.progress import QuantityProgressTracker


def run_rename_files() -> RenameFilesSummary:
    """Interactive entrypoint for renaming files to match input directory ordering."""
    input_directory = input("Enter path to input folder: ").strip().strip('"')
    output_directory = input("Enter path to output folder: ").strip().strip('"')

    try:
        summary = rename_files_match(input_directory, output_directory)
        tracker = QuantityProgressTracker(total=len(summary.renamed), sink=print)
        for idx, pair in enumerate(summary.renamed, start=1):
            tracker.emit(idx, f"Renamed: {pair.old_name} -> {pair.new_name}")
        tracker.complete(f"Total renamed: {len(summary.renamed)} items.")
        return summary
    except (ValueError, FileExistsError, FileNotFoundError) as err:
        print(f"\n [X] HARD STOP: {err}\n")
        logging.error("Rename files aborted: %s", err)
        return RenameFilesSummary(
            input_directory=Path(input_directory),
            output_directory=Path(output_directory),
            renamed=(),
        )


run_copy_file_names = run_rename_files
