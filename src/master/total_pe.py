"""Total PE repository and domain logic for Pahang CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence
import openpyxl
import pandas as pd
from openpyxl.utils import column_index_from_string

from src.core.normalizers import normalize_date_str
from src.testsheet.extractor import to_excel_date
from src.testsheet.models import SubstationTestsheetPackage
from src.msms.models import WorkbookUpdateMappings

def col_to_index(col_letter: str) -> int:
    return column_index_from_string(col_letter) - 1

def read_col(df: pd.DataFrame, col_letter: str) -> pd.Series:
    return df.iloc[:, col_to_index(col_letter)]

def write_cell(ws: Any, row: int, col_letter: str, value: Any) -> None:
    ws[f"{col_letter}{row}"] = value

def _resolve_named_column(dataframe: pd.DataFrame, header_names: Sequence[str], fallback_col_letter: str) -> str:
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

    @staticmethod
    def _get_real_dimensions(ws: openpyxl.worksheet.worksheet.Worksheet) -> tuple[int, int]:
        max_r = 1
        max_c = 1
        if hasattr(ws, "_cells"):
            for (r, c), cell in ws._cells.items():
                if cell.value is not None:
                    if isinstance(cell.value, str) and str(cell.value).strip() == "":
                        continue
                    if r > max_r:
                        max_r = r
                    if c > max_c:
                        max_c = c
        else:
            max_r = ws.max_row
            max_c = ws.max_column
        return max_r, max_c

    @classmethod
    def _sanitize_ghost_formatting(cls, wb: openpyxl.Workbook) -> None:
        for ws in wb.worksheets:
            real_max_r, real_max_c = cls._get_real_dimensions(ws)
            reported_max_r = ws.max_row or 1
            reported_max_c = ws.max_column or 1

            if reported_max_r > real_max_r + 1:
                ghost_rows = reported_max_r - real_max_r
                ws.delete_rows(real_max_r + 1, ghost_rows)

            if reported_max_c > real_max_c + 1:
                ghost_cols = reported_max_c - real_max_c
                ws.delete_cols(real_max_c + 1, ghost_cols)

    @classmethod
    def _sort_datacycle_sheet(cls, ws: openpyxl.worksheet.worksheet.Worksheet) -> bool:
        max_r, max_c = cls._get_real_dimensions(ws)
        if max_r < 2:
            return False

        real_max_col = max(max_c, 7)

        last_row = 1
        for row in range(2, max_r + 1):
            pe_val = ws.cell(row=row, column=1).value
            fl_val = ws.cell(row=row, column=2).value
            sub_val = ws.cell(row=row, column=3).value
            if pe_val is not None or fl_val is not None or sub_val is not None:
                last_row = row

        if last_row < 2:
            return False

        rows_data = []
        for r in range(2, last_row + 1):
            vals = []
            for c in range(1, real_max_col + 1):
                val = ws.cell(row=r, column=c).value
                if isinstance(val, str) and val.startswith("="):
                    vals.append(None)
                else:
                    vals.append(val)
            substation_val = vals[0]
            try:
                substation_key = int(float(str(substation_val).strip())) if substation_val is not None and str(substation_val).strip() != "" else 999999
            except (ValueError, TypeError):
                substation_key = 999999
            rows_data.append((substation_key, r, vals))

        sorted_rows = sorted(rows_data, key=lambda x: (x[0], x[1]))

        for idx, (_, _, vals) in enumerate(sorted_rows, start=2):
            for c, val in enumerate(vals, start=1):
                existing_val = ws.cell(row=idx, column=c).value
                if isinstance(existing_val, str) and existing_val.startswith("="):
                    continue
                cell = ws.cell(row=idx, column=c, value=val)
                if c == 1 and val is not None:
                    try:
                        cell.value = int(float(str(val).strip()))
                    except (ValueError, TypeError):
                        pass

        return True

    def get_existing_auto_keys(self, total_pe_path: Path) -> set[tuple[str, str]]:
        if not total_pe_path.exists():
            return set()

        wb_check = openpyxl.load_workbook(total_pe_path, data_only=True)
        try:
            if "DataCycle1" not in wb_check.sheetnames:
                raise RuntimeError(f"'DataCycle1' sheet missing in {total_pe_path}")
            ws_check = wb_check["DataCycle1"]
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
            if "DataCycle1" not in wb.sheetnames:
                raise RuntimeError(f"'DataCycle1' sheet missing in {total_pe_path}")
            ws = wb["DataCycle1"]

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

            pe_no = data.substation_number
            try:
                pe_no = int(float(str(pe_no).strip()))
            except (ValueError, TypeError):
                pass

            fl_num = data.fl_erms
            sub_name = data.substation_name_erms
            dt_str = data.date_str or pkg.date_str
            norm_pkg_dt = normalize_date_str(dt_str)
            type_c = data.substation_type
            wo = data.wo_number

            dt_obj = to_excel_date(dt_str)
            date_cell_val = dt_obj.date() if dt_obj is not None else norm_pkg_dt

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
                c_dt = ws.cell(target_row, 4, date_cell_val)
                c_dt.number_format = "DD-MMM-YYYY"
                ws.cell(target_row, 5, type_c)
                ws.cell(target_row, 6, wo)
                updated_count += 1
            else:
                next_row = 2
                while ws.cell(next_row, 1).value is not None and str(ws.cell(next_row, 1).value).strip() != "":
                    next_row += 1

                ws.cell(next_row, 1, pe_no)
                ws.cell(next_row, 2, fl_num)
                ws.cell(next_row, 3, sub_name)
                c_dt = ws.cell(next_row, 4, date_cell_val)
                c_dt.number_format = "DD-MMM-YYYY"
                ws.cell(next_row, 5, type_c)
                ws.cell(next_row, 6, wo)
                existing_rows[lookup_key] = next_row
                existing_rows[sub_key] = next_row
                new_count += 1

        self._sort_datacycle_sheet(ws)
        self._sanitize_ghost_formatting(wb)
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
        pe_substation_idx = col_to_index(pe_map["substation_name_erms"])
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
            engr_map["substation_name_erms"],
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
            write_cell(ws, excel_row, pe_map["substation_name_erms"], row.iloc[pe_substation_idx])
            dt_obj = to_excel_date(row.iloc[pe_date_idx])
            cell_date = ws[f"{pe_map['date']}{excel_row}"]
            cell_date.value = dt_obj.date() if dt_obj is not None else normalize_date_str(row.iloc[pe_date_idx])
            cell_date.number_format = "DD-MMM-YYYY"
            write_cell(ws, excel_row, pe_map["type"], row.iloc[pe_type_idx])
            write_cell(ws, excel_row, pe_map["wo"], row.iloc[pe_wo_idx])
        
        wb.save(total_pe_path)
        logging.info("TOTAL_PE saved successfully using Openpyxl")
