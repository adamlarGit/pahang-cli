"""Workflow for copying and renaming FLIR raw files with sequential numbering."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenameFlirSummary:
    input_folder: Path
    output_folder: Path
    starting_number: int
    copied_count: int


def copy_and_rename_flir_files(
    input_folder: str | Path,
    output_folder: str | Path,
    starting_number: int = 1,
) -> RenameFlirSummary:
    """Copy and rename files from input_folder to output_folder with FLIR0001 numbering."""
    input_path = Path(input_folder).expanduser().resolve()
    output_path = Path(output_folder).expanduser().resolve()

    if not input_path.exists() or not input_path.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    files = sorted(
        (path for path in input_path.iterdir() if path.is_file() and not path.name.startswith("~$")),
        key=lambda path: path.name.lower(),
    )

    current_number = starting_number
    for file_path in files:
        new_name = f"FLIR{current_number:04d}{file_path.suffix}"
        destination_path = output_path / new_name
        shutil.copy(file_path, destination_path)
        print(f'Copied and renamed "{file_path.name}" to "{new_name}"')
        current_number += 1

    print("Files copied and renamed successfully!")
    return RenameFlirSummary(
        input_folder=input_path,
        output_folder=output_path,
        starting_number=starting_number,
        copied_count=len(files),
    )


def run_rename_flir() -> RenameFlirSummary:
    """Interactive entrypoint for FLIR raw file renaming."""
    input_folder = input("Enter the input folder path: ").strip().strip('"')
    output_folder = input("Enter the output folder path: ").strip().strip('"')
    start_str = input("Enter the starting number [1]: ").strip()
    starting_number = int(start_str) if start_str else 1

    summary = copy_and_rename_flir_files(input_folder, output_folder, starting_number)
    print(f"Total FLIR files processed: {summary.copied_count}")
    return summary


run_rename_flir_raw_files = run_rename_flir
