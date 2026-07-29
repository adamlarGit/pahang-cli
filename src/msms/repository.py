"""MSMS Repository."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from src.msms.models import MSMS_COLUMN_MAPPING, WorkbookUpdateMappings


def col_to_index(col_letter: str) -> int:
    """Convert Excel column letter to 0-based index for pandas iloc."""
    return column_index_from_string(col_letter) - 1


def read_col(df: pd.DataFrame, col_letter: str):
    """Read a DataFrame column by Excel column letter."""
    return df.iloc[:, col_to_index(col_letter)]


def _resolve_named_column(dataframe: pd.DataFrame, header_names: list[str], fallback_col_letter: str) -> str:
    """Resolve a dataframe column by header names, with a positional fallback."""
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


def write_cell(ws, row: int, col_letter: str, value):
    """Write to a worksheet cell by column letter."""
    ws[f"{col_letter}{row}"] = value


class MsmsRepository(ABC):
    @abstractmethod
    def get_work_order_by_fl(self, data_msms_path: Path, functional_location: str) -> str | None:
        """Lookup Work Order by Functional Location."""
        ...

    @abstractmethod
    def update_msms(
        self,
        data_msms_path: Path,
        engr_excel: pd.DataFrame,
        workbook_mappings: WorkbookUpdateMappings
    ) -> None:
        """Update DATA_MSMS Excel file with ENGR data."""
        ...


class LocalExcelMsmsRepository(MsmsRepository):
    def get_work_order_by_fl(self, data_msms_path: Path, functional_location: str) -> str | None:
        if not data_msms_path.exists():
            return None
        df = pd.read_excel(data_msms_path)
        fl_idx = col_to_index(MSMS_COLUMN_MAPPING["functional_location"])
        wo_idx = col_to_index(MSMS_COLUMN_MAPPING["wo"])
        
        fl_col = df.iloc[:, fl_idx].astype(str)
        match = df[fl_col == functional_location]
        if not match.empty:
            return str(match.iloc[0, wo_idx])
        return None

    def update_msms(
        self,
        data_msms_path: Path,
        engr_excel: pd.DataFrame,
        workbook_mappings: WorkbookUpdateMappings
    ) -> None:
        if not data_msms_path.exists():
            logging.warning(f"DATA_MSMS not found at {data_msms_path}")
            return

        logging.info("Processing DATA_MSMS rows...")
        data_msms = pd.read_excel(data_msms_path)
        
        msms_map = workbook_mappings.data_msms
        engr_map = workbook_mappings.engr_excel
        
        msms_location_idx = col_to_index(msms_map["location"])
        
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
        
        for index, row in data_msms.iterrows():
            original_text = str(row.iloc[msms_location_idx])
            if len(original_text) >= 8:
                modified_text = original_text[:8] + "/" + original_text[8:]
                
                match = engr_excel[
                    engr_excel[engr_fl_col].astype(str).str.strip() == modified_text
                ]
                
                if not match.empty:
                    extracted_date = match.iloc[0][engr_date_col]
                    
                    if pd.isna(extracted_date) or extracted_date == "":
                        logging.warning(f"Skipping row {index + 2} due to missing date")
                        continue
                    
                    data_msms.iat[index, col_to_index(msms_map["substation_name"])] = match.iloc[0][engr_substation_col]
                    data_msms.iat[index, col_to_index(msms_map["functional_location"])] = match.iloc[0][engr_fl_col]
                    data_msms.iat[index, col_to_index(msms_map["date"])] = extracted_date
                else:
                    logging.warning(f"No match found for {modified_text} in row {index + 2}")
                    
        logging.info("Updating DATA_MSMS with Openpyxl...")
        wb = load_workbook(data_msms_path)
        ws = wb.active
        
        for index, row in data_msms.iterrows():
            excel_row = index + 2
            write_cell(ws, excel_row, msms_map["substation_name"], row.iloc[col_to_index(msms_map["substation_name"])])
            write_cell(ws, excel_row, msms_map["functional_location"], row.iloc[col_to_index(msms_map["functional_location"])])
            write_cell(ws, excel_row, msms_map["date"], row.iloc[col_to_index(msms_map["date"])])
            
        wb.save(data_msms_path)
        logging.info("DATA_MSMS saved successfully using Openpyxl")
