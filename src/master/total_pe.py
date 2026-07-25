"""Total PE repository and domain logic for Pahang CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import Sequence
import openpyxl

from src.testsheet.models import SubstationTestsheetPackage


def normalize_date_str(date_input: str) -> str:
    """Normalize date strings (e.g., '01/05/2026' -> '01-05-2026')."""
    if not date_input:
        return ""
    s = str(date_input).strip().replace("/", "-")
    match = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return f"{day:02d}-{month:02d}-{year:04d}"
    return s


class TotalPeRepository(ABC):
    """Abstract repository for TOTAL PE workbook management."""

    @abstractmethod
    def get_existing_auto_keys(self, total_pe_path: Path) -> set[tuple[str, str]]:
        """Return set of existing (PE/Station, Date) keys in TOTAL PE.xlsx."""
        ...

    @abstractmethod
    def upsert_packages(
        self, total_pe_path: Path, packages: Sequence[SubstationTestsheetPackage]
    ) -> tuple[int, int]:
        """Upsert testsheet packages into TOTAL PE.xlsx.

        Returns (new_count, updated_count).
        """
        ...


class LocalExcelTotalPeRepository(TotalPeRepository):
    """Excel-backed repository for TOTAL PE workbook management."""

    def get_existing_auto_keys(self, total_pe_path: Path) -> set[tuple[str, str]]:
        if not total_pe_path.exists():
            return set()

        wb_check = openpyxl.load_workbook(total_pe_path, data_only=True)
        try:
            ws_check = (
                wb_check["DataCycle1"]
                if "DataCycle1" in wb_check.sheetnames
                else wb_check.active
            )
            existing_keys: set[tuple[str, str]] = set()
            for r_idx in range(2, ws_check.max_row + 1):
                pe_val = str(ws_check.cell(r_idx, 1).value or "").strip()
                sub_val = str(ws_check.cell(r_idx, 3).value or "").strip().upper()
                dt_val = str(ws_check.cell(r_idx, 4).value or "").strip()
                norm_dt = normalize_date_str(dt_val)

                for d in (dt_val, norm_dt):
                    if not d:
                        continue
                    if pe_val:
                        existing_keys.add((pe_val, d))
                        try:
                            num_int = int(pe_val)
                            existing_keys.add((str(num_int), d))
                            existing_keys.add((f"{num_int:03d}", d))
                        except ValueError:
                            pass
                    if sub_val:
                        existing_keys.add((sub_val, d))
            return existing_keys
        finally:
            wb_check.close()

    def upsert_packages(
        self, total_pe_path: Path, packages: Sequence[SubstationTestsheetPackage]
    ) -> tuple[int, int]:
        total_pe_path.parent.mkdir(parents=True, exist_ok=True)

        if not total_pe_path.exists():
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "DataCycle1"
            ws.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE", "TYPE", "WO", "SCOPE"])
        else:
            wb = openpyxl.load_workbook(total_pe_path)
            ws = wb["DataCycle1"] if "DataCycle1" in wb.sheetnames else wb.active

        new_count = 0
        updated_count = 0

        existing_rows: dict[tuple[str, str], int] = {}
        for r_idx in range(2, ws.max_row + 1):
            pe_val_raw = str(ws.cell(r_idx, 1).value or "").strip()
            sub_val = str(ws.cell(r_idx, 3).value or "").strip().upper()
            date_val = str(ws.cell(r_idx, 4).value or "").strip()
            norm_dt = normalize_date_str(date_val)

            for d in (date_val, norm_dt):
                if not d:
                    continue
                if pe_val_raw:
                    existing_rows[(pe_val_raw, d)] = r_idx
                    try:
                        pe_int = int(pe_val_raw)
                        existing_rows[(str(pe_int), d)] = r_idx
                        existing_rows[(f"{pe_int:03d}", d)] = r_idx
                    except ValueError:
                        pass
                if sub_val:
                    existing_rows[(sub_val, d)] = r_idx

        for pkg in packages:
            data = pkg.data
            if data is None:
                continue

            pe_no = data.pe_number
            fl_num = data.fl_number
            sub_name = data.substation_name
            dt_str = data.date_str or pkg.date_str
            norm_pkg_dt = normalize_date_str(dt_str)
            type_c = data.type_code
            wo = data.wo_number

            lookup_key = (str(pe_no), dt_str)
            norm_lookup_key = (str(pe_no), norm_pkg_dt)
            padded_key = (f"{pe_no:03d}", dt_str)
            norm_padded_key = (f"{pe_no:03d}", norm_pkg_dt)
            sub_key = (sub_name.upper(), dt_str)
            norm_sub_key = (sub_name.upper(), norm_pkg_dt)

            target_row = (
                existing_rows.get(lookup_key)
                or existing_rows.get(norm_lookup_key)
                or existing_rows.get(padded_key)
                or existing_rows.get(norm_padded_key)
                or existing_rows.get(sub_key)
                or existing_rows.get(norm_sub_key)
            )

            if target_row is not None:
                ws.cell(target_row, 1, pe_no)
                ws.cell(target_row, 2, fl_num)
                ws.cell(target_row, 3, sub_name)
                ws.cell(target_row, 4, dt_str)
                ws.cell(target_row, 5, type_c)
                ws.cell(target_row, 6, wo)
                updated_count += 1
            else:
                ws.append([pe_no, fl_num, sub_name, dt_str, type_c, wo, ""])
                new_row_idx = ws.max_row
                existing_rows[lookup_key] = new_row_idx
                existing_rows[sub_key] = new_row_idx
                new_count += 1

        wb.save(total_pe_path)
        wb.close()

        return new_count, updated_count
