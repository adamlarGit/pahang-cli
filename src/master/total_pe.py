"""Total PE repository and domain logic for Pahang CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import Sequence
import openpyxl
import pandas as pd
from openpyxl.utils import column_index_from_string

from src.testsheet.models import SubstationTestsheetPackage
from src.msms.models import WorkbookUpdateMappings

def col_to_index(col_letter: str) -> int:
    return column_index_from_string(col_letter) - 1

def read_col(df: pd.DataFrame, col_letter: str):
    return df.iloc[:, col_to_index(col_letter)]

def write_cell(ws, row: int, col_letter: str, value):
    ws[f"{col_letter}{row}"] = value

def _resolve_named_column(dataframe: pd.DataFrame, header_names: list[str], fallback_col_letter: str) -> str:
    columns = dataframe.columns
    normalized_headers = {
        str(header).strip().lower(): header
        for header in columns
    }
    for header_name in header_names:
        actual_header = normalized_headers.get(header_name.strip().lower())
        if actual_header is not None:
            return actual_header
            
    fallback_idx = col_to_index(fallback_col_letter)
    if fallback_idx < len(columns):
        return columns[fallback_idx]
        
    raise KeyError(f"None of the headers {header_names} were found")


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

    @abstractmethod
    def update_from_engr_and_msms(
        self,
        total_pe_path: Path,
        data_msms: pd.DataFrame,
        engr_excel: pd.DataFrame,
        workbook_mappings: WorkbookUpdateMappings,
    ) -> None:
        """Update TOTAL_PE with ENGR and MSMS data."""
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

    def update_from_engr_and_msms(
        self,
        total_pe_path: Path,
        data_msms: pd.DataFrame,
        engr_excel: pd.DataFrame,
        workbook_mappings: WorkbookUpdateMappings,
    ) -> None:
        import logging
        logging.info("Processing TOTAL_PE rows...")
        
        if not total_pe_path.exists():
            logging.warning(f"TOTAL PE not found at {total_pe_path}")
            return
            
        total_pe = pd.read_excel(total_pe_path, sheet_name="DataCycle1")
        
        msms_map = workbook_mappings.data_msms
        engr_map = workbook_mappings.engr_excel
        pe_map = workbook_mappings.total_pe
        
        pe_fl_idx = col_to_index(pe_map["functional_location"])
        pe_substation_idx = col_to_index(pe_map["substation_name"])
        pe_date_idx = col_to_index(pe_map["date"])
        pe_type_idx = col_to_index(pe_map["type"])
        pe_wo_idx = col_to_index(pe_map["wo"])
        
        engr_fl_col = _resolve_named_column(
            engr_excel,
            ["FUNCTIONAL LOCATION (ERMS)", "FUNCTIONAL LOCATION"],
            engr_map["functional_location"],
        )
        engr_substation_col = _resolve_named_column(
            engr_excel,
            ["SUBSTATION NAME (ERMS)", "SUBSTATION NAME"],
            engr_map["substation_name"],
        )
        engr_date_col = _resolve_named_column(
            engr_excel,
            ["CYCLE 1", "CYCLE 1 DATE", "SCAN DATE", "DATE"],
            engr_map["date"],
        )
        engr_type_col = _resolve_named_column(
            engr_excel,
            ["TYPE", "BUILDING TYPE", "SUBSTATION TYPE"],
            engr_map["type"],
        )
        
        msms_wo_idx = col_to_index(msms_map["wo"])
        
        total_pe.iloc[:, pe_fl_idx] = total_pe.iloc[:, pe_fl_idx].astype(str).fillna("")
        engr_excel[engr_fl_col] = engr_excel[engr_fl_col].astype(str).fillna("")
        
        for index, row in total_pe.iterrows():
            current_fl = str(row.iloc[pe_fl_idx]).strip()
            if not current_fl:
                logging.warning(f"Skipping row {index + 2} due to empty FL NUMBER")
                continue
            
            engr_match = engr_excel[engr_excel[engr_fl_col].astype(str).str.strip() == current_fl]
            if not engr_match.empty:
                engr_row = engr_match.iloc[0]
                extracted_date = engr_row[engr_date_col]
                if pd.isna(extracted_date) or extracted_date == "":
                    logging.warning(f"Skipping row {index + 2} due to missing ENGR date")
                    continue
                
                total_pe.iat[index, pe_substation_idx] = engr_row[engr_substation_col]
                total_pe.iat[index, pe_date_idx] = extracted_date
                total_pe.iat[index, pe_type_idx] = engr_row[engr_type_col]
                
                msms_match = data_msms[read_col(data_msms, msms_map["functional_location"]) == current_fl]
                if not msms_match.empty:
                    total_pe.iat[index, pe_wo_idx] = msms_match.iloc[0, msms_wo_idx]
                else:
                    logging.warning(f"No MSMS match for Work Order on row {index + 2}")
            else:
                logging.warning(f"No ENGR match found for {current_fl} in row {index + 2}")
                msms_match = data_msms[read_col(data_msms, msms_map["functional_location"]) == current_fl]
                if not msms_match.empty:
                    total_pe.iat[index, pe_wo_idx] = msms_match.iloc[0, msms_wo_idx]
                    logging.info(f"Updated row {index + 2} with Work Order {total_pe.iat[index, pe_wo_idx]}")
                else:
                    logging.warning(f"No DATA_MSMS match found for {current_fl} in row {index + 2}")
        
        logging.info("Updating TOTAL_PE with Openpyxl...")
        wb = openpyxl.load_workbook(total_pe_path)
        ws = wb["DataCycle1"]
        
        for idx, row in total_pe.iterrows():
            excel_row = idx + 2
            write_cell(ws, excel_row, pe_map["substation_name"], row.iloc[pe_substation_idx])
            write_cell(ws, excel_row, pe_map["date"], row.iloc[pe_date_idx])
            write_cell(ws, excel_row, pe_map["type"], row.iloc[pe_type_idx])
            write_cell(ws, excel_row, pe_map["wo"], row.iloc[pe_wo_idx])
        
        wb.save(total_pe_path)
        logging.info("TOTAL_PE saved successfully using Openpyxl")
