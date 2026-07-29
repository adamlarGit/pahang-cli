"""Automated Raw Material Creation & Sorting Workflow for Pahang CLI."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
import openpyxl

from src.project.environment import ProjectEnvironment
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import PhotoRange
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.models import RawMaterialRequest, RawMaterialResult


from datetime import date, datetime


def normalize_date_str(date_input: object) -> str:
    """Normalize date inputs (date, datetime, or strings) to DD-MM-YYYY format."""
    if not date_input:
        return ""
    if isinstance(date_input, (datetime, date)):
        return date_input.strftime("%d-%m-%Y")
    s = str(date_input).strip().replace("/", "-")
    match_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if match_iso:
        year, month, day = int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3))
        return f"{day:02d}-{month:02d}-{year:04d}"
    match = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{day:02d}-{month:02d}-{year:04d}"
    return s


@dataclass(frozen=True)
class AutomatedRawMaterialSummary:
    """Execution summary for Raw Material Creation & Sorting workflow."""

    substations_count: int = 0
    ir_copied_count: int = 0
    dg_copied_count: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class RawMaterialWorkflow:
    """Orchestrates TOTAL PE validation, folder provisioning, and photo sorting."""

    def __init__(
        self,
        repository: SubstationTestsheetRepository | None = None,
        extractor: TestsheetExtractor | None = None,
    ) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self.extractor = extractor or TestsheetExtractor()

    def execute(
        self, environment: ProjectEnvironment, request: RawMaterialRequest
    ) -> RawMaterialResult:
        """Execute the Raw Material workflow."""
        total_pe_path = environment.storage.get_total_pe_path()
        if not total_pe_path.exists():
            raise RuntimeError(
                f"TOTAL PE.xlsx pre-check failed: File missing at {total_pe_path}. "
                "Please run 'Populate TOTAL PE' workflow first."
            )

        try:
            wb = openpyxl.load_workbook(total_pe_path, read_only=True)
            ws = wb["DataCycle1"] if "DataCycle1" in wb.sheetnames else wb.active
            has_data = ws.max_row >= 2
            wb.close()
            if not has_data:
                raise RuntimeError(
                    "TOTAL PE.xlsx pre-check failed: 'DataCycle1' sheet is empty. "
                    "Please run 'Populate TOTAL PE' workflow first."
                )
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"TOTAL PE.xlsx pre-check failed while reading: {e}")

        input_path = request.target_dir or request.output_path
        if not input_path.exists():
            input_path = environment.storage.get_testsheet_dir()

        if not input_path.exists():
            raise FileNotFoundError(f"Input directory does not exist: {input_path}")

        packages = self.repository.discover_packages(input_path)
        if not packages:
            testsheet_dir = environment.storage.get_testsheet_dir()
            if testsheet_dir.exists() and testsheet_dir != input_path:
                packages = self.repository.discover_packages(testsheet_dir)

        if not packages:
            raise FileNotFoundError(
                f"Input directory verification failed: No testsheets or packages found in {input_path}"
            )

        # 2. Strict Input Directory Verification: UNSORTED RAW DATA must exist
        for pkg in packages:
            if not pkg.unsorted_raw_data_dir.exists():
                raise RuntimeError(
                    f"Input directory verification failed: 'UNSORTED RAW DATA' directory missing in {pkg.testsheet_path.parent}. "
                    "Field engineers must provide UNSORTED RAW DATA/ folder containing raw photos."
                )

        # 3. Strict TOTAL PE.xlsx Alignment Verification (Strict Batch Validation with normalized PE padding)
        wb_pe = openpyxl.load_workbook(total_pe_path, data_only=True)
        try:
            ws_pe = wb_pe["DataCycle1"] if "DataCycle1" in wb_pe.sheetnames else wb_pe.active
            existing_tuples = set()
            for r_idx in range(2, ws_pe.max_row + 1):
                pe_val_raw = str(ws_pe.cell(r_idx, 1).value or "").strip()
                sub_val = str(ws_pe.cell(r_idx, 3).value or "").strip().upper()
                dt_val = str(ws_pe.cell(r_idx, 4).value or "").strip()
                norm_dt = normalize_date_str(dt_val)

                for d in (dt_val, norm_dt):
                    if not d:
                        continue
                    if pe_val_raw:
                        existing_tuples.add((pe_val_raw, d))
                        try:
                            num_int = int(pe_val_raw)
                            existing_tuples.add((str(num_int), d))
                            existing_tuples.add((f"{num_int:03d}", d))
                        except ValueError:
                            pass
                    if sub_val:
                        existing_tuples.add((sub_val, d))

            unmatched_packages = [
                pkg for pkg in packages
                if (str(pkg.pe_num), pkg.date_str) not in existing_tuples
                and (str(pkg.pe_num), normalize_date_str(pkg.date_str)) not in existing_tuples
                and (f"{pkg.pe_num:03d}", pkg.date_str) not in existing_tuples
                and (f"{pkg.pe_num:03d}", normalize_date_str(pkg.date_str)) not in existing_tuples
                and not (pkg.data and ((pkg.data.substation_name.upper(), pkg.date_str) in existing_tuples or (pkg.data.substation_name.upper(), normalize_date_str(pkg.date_str)) in existing_tuples))
            ]

            if unmatched_packages:
                unmatched_desc = ", ".join(f"PE {p.pe_num} ({p.date_str})" for p in unmatched_packages)
                raise RuntimeError(
                    f"TOTAL PE.xlsx alignment pre-check failed: Target records missing for: {unmatched_desc}. "
                    "Please run 'Populate TOTAL PE' workflow first."
                )
        finally:
            wb_pe.close()

        raw_material_root = environment.storage.get_raw_material_dir()

        substations_count = 0
        total_ir_copied = 0
        total_dg_copied = 0
        warnings: list[str] = []
        errors: list[str] = []

        for pkg in packages:
            substations_count += 1
            pe_folder_name = f"{pkg.pe_num:03d}"

            pe_dest_dir = (
                raw_material_root
                / (pkg.station or "UNASSIGNED")
                / (pkg.month or "01. UNKNOWN")
                / (pkg.date_str or "01-01-2026")
                / pe_folder_name
                / "RAW DATA"
            )

            ir_dest_dir = environment.storage.ensure_directory(pe_dest_dir / "IR")
            dg_dest_dir = environment.storage.ensure_directory(pe_dest_dir / "DG")
            environment.storage.ensure_directory(pe_dest_dir / "US+TEV")

            data = pkg.data
            if data is None:
                try:
                    data = self.extractor.extract_testsheet_data(pkg.testsheet_path)
                except Exception as ex:
                    warnings.append(f"Failed to extract testsheet data from {pkg.testsheet_path}: {ex}")

            photo_ranges = data.photo_ranges if data else None

            unsorted_dir = pkg.unsorted_raw_data_dir
            if not unsorted_dir.exists():
                warnings.append(f"PE {pe_folder_name}: Unsorted raw data directory missing at {unsorted_dir}")
                continue

            # Scope photo scanning to tech subdirectories under UNSORTED RAW DATA if present
            ir_source_dir = unsorted_dir / "IR" if (unsorted_dir / "IR").exists() else unsorted_dir
            dg_source_dir = unsorted_dir / "DG" if (unsorted_dir / "DG").exists() else unsorted_dir

            ir_photos = [
                p for p in ir_source_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in [".jpg", ".jpeg", ".png"]
            ]
            dg_photos = [
                p for p in dg_source_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in [".jpg", ".jpeg", ".png"]
            ]

            ir_range = photo_ranges.ir if photo_ranges else None
            dg_range = photo_ranges.dg if photo_ranges else None

            ir_copied = self._sort_photos_for_tech(
                photos=ir_photos,
                prefix="FLIR",
                photo_range=ir_range,
                dest_dir=ir_dest_dir,
                tech_name="IR",
                pe_folder_name=pe_folder_name,
                warnings=warnings,
            )

            dg_copied = self._sort_photos_for_tech(
                photos=dg_photos,
                prefix="IMG_",
                photo_range=dg_range,
                dest_dir=dg_dest_dir,
                tech_name="DG",
                pe_folder_name=pe_folder_name,
                warnings=warnings,
            )

            total_ir_copied += ir_copied
            total_dg_copied += dg_copied

            if request.progress_sink:
                request.progress_sink(
                    f"Processed PE {pe_folder_name}: {ir_copied} IR photos, {dg_copied} DG photos copied."
                )

        summary = AutomatedRawMaterialSummary(
            substations_count=substations_count,
            ir_copied_count=total_ir_copied,
            dg_copied_count=total_dg_copied,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

        return RawMaterialResult(
            substations_count=substations_count,
            ir_copied_count=total_ir_copied,
            dg_copied_count=total_dg_copied,
            summary=summary,
            warnings=tuple(warnings),
        )

    def _sort_photos_for_tech(
        self,
        photos: list[Path],
        prefix: str,
        photo_range: PhotoRange | None,
        dest_dir: Path,
        tech_name: str,
        pe_folder_name: str,
        warnings: list[str],
    ) -> int:
        """Sort and copy photos matching tech prefix and PhotoRange bounds."""
        if not photo_range or not photo_range.is_valid:
            warnings.append(f"PE {pe_folder_name}: {tech_name} photo range not specified or incomplete.")
            return 0

        start_num = photo_range.start_num if photo_range.start_num is not None else photo_range.end_num
        end_num = photo_range.end_num if photo_range.end_num is not None else photo_range.start_num

        if start_num is None or end_num is None:
            warnings.append(f"PE {pe_folder_name}: {tech_name} photo range bounds missing.")
            return 0

        min_val = min(start_num, end_num)
        max_val = max(start_num, end_num)

        found_nums: set[int] = set()
        copied = 0

        for p_file in photos:
            num = self._extract_photo_number(p_file.name, prefix)
            if num is not None and min_val <= num <= max_val:
                shutil.copy2(p_file, dest_dir / p_file.name)
                found_nums.add(num)
                copied += 1

        expected_nums = set(range(min_val, max_val + 1))
        missing_nums = sorted(expected_nums - found_nums)

        if copied == 0:
            warnings.append(
                f"PE {pe_folder_name}: No {tech_name} photos matched range [{min_val}-{max_val}] with prefix '{prefix}'"
            )
        elif missing_nums:
            for missing_no in missing_nums:
                warnings.append(
                    f"{tech_name} photo {prefix}{missing_no:04d} missing for PE {pe_folder_name}"
                )

        return copied

    def _extract_photo_number(self, filename: str, prefix: str) -> int | None:
        """Extract sequence number directly after technology prefix or trailing sequence."""
        name_upper = filename.upper()
        prefix_upper = prefix.upper()
        if not name_upper.startswith(prefix_upper):
            return None

        after_prefix = name_upper[len(prefix_upper):]
        digits = re.findall(r"\d+", after_prefix)
        if not digits:
            return None

        if len(digits) > 1 and len(digits[0]) == 8:
            return int(digits[-1])
        return int(digits[0])
