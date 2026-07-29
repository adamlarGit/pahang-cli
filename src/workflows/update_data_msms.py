"""Workflow for updating DATA_MSMS and TOTAL PE workbooks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from glob import glob
import pandas as pd

from src.project import ProjectEnvironment
from src.msms.models import (
    MsmsUpdateSummary,
    WorkbookUpdateMappings,
    MSMS_COLUMN_MAPPING,
    ENGR_COLUMN_MAPPING_11KV,
    ENGR_COLUMN_MAPPING_33KV,
    TOTAL_PE_COLUMN_MAPPING,
)
from src.msms.repository import LocalExcelMsmsRepository
from src.master.total_pe import LocalExcelTotalPeRepository
from src.msms.repository import col_to_index


def load_engr_files(pattern: str, engr_mapping: dict[str, str], sheet_name: str = "QR02 CBA") -> pd.DataFrame:
    """Load and combine multiple ENGR Excel files."""
    engr_files = list(glob(pattern))
    if not engr_files:
        raise FileNotFoundError(f"No ENGR files found matching pattern: {pattern}")
    
    logging.info(f"Found {len(engr_files)} ENGR files")
    
    fl_col_idx = col_to_index(engr_mapping["functional_location"])
    
    engr_dfs = []
    for filepath in engr_files:
        logging.info(f"Reading ENGR file {Path(filepath).name}")
        df = pd.read_excel(filepath, sheet_name=sheet_name, header=1)
        df.iloc[:, fl_col_idx] = df.iloc[:, fl_col_idx].astype(str).fillna("")
        engr_dfs.append(df)
    
    combined = pd.concat(engr_dfs, ignore_index=True)
    return combined


def get_update_data_msms_resources(env: ProjectEnvironment):
    """Get project resources needed for MSMS updates."""
    from dataclasses import make_dataclass
    
    UpdateDataMsmsResources = make_dataclass('UpdateDataMsmsResources', [
        ('data_msms_path', Path),
        ('total_pe_path', Path),
        ('engr_pattern', str),
        ('data_msms_column_mapping', dict),
        ('engr_column_mapping', dict),
        ('total_pe_column_mapping', dict),
    ])
    
    engr_mapping = ENGR_COLUMN_MAPPING_33KV if "33kV" in env.voltage_type else ENGR_COLUMN_MAPPING_11KV
    engr_pattern_str = f"{env.base_path}/PYTHON/ENGR FROM DRIVE/ENGR-*.xlsx"
    if hasattr(env, "get_engr_pattern"):
        engr_pattern_str = env.get_engr_pattern()
        
    data_msms_path = env.base_path / "PYTHON" / "DATA MSMS.xlsx"
    
    return UpdateDataMsmsResources(
        data_msms_path=data_msms_path,
        total_pe_path=env.get_total_pe_path(),
        engr_pattern=engr_pattern_str,
        data_msms_column_mapping=MSMS_COLUMN_MAPPING,
        engr_column_mapping=engr_mapping,
        total_pe_column_mapping=TOTAL_PE_COLUMN_MAPPING,
    )


def update_data_msms(env: ProjectEnvironment) -> MsmsUpdateSummary:
    """Update DATA_MSMS and TOTAL_PE with ENGR data."""
    resources = get_update_data_msms_resources(env)

    data_msms = pd.read_excel(resources.data_msms_path)
    engr_excel = load_engr_files(resources.engr_pattern, resources.engr_column_mapping)
    
    workbook_mappings = WorkbookUpdateMappings(
        data_msms=resources.data_msms_column_mapping,
        engr_excel=resources.engr_column_mapping,
        total_pe=resources.total_pe_column_mapping,
    )

    msms_repo = LocalExcelMsmsRepository()
    msms_repo.update_msms(resources.data_msms_path, engr_excel, workbook_mappings)
    
    # Reload MSMS data since we just updated it, to update TOTAL PE
    data_msms_updated = pd.read_excel(resources.data_msms_path)
    
    pe_repo = LocalExcelTotalPeRepository()
    pe_repo.update_from_engr_and_msms(resources.total_pe_path, data_msms_updated, engr_excel, workbook_mappings)

    return MsmsUpdateSummary(
        data_msms_path=resources.data_msms_path,
        total_pe_path=resources.total_pe_path,
        engr_pattern=resources.engr_pattern,
    )


def run_update_data_msms(env: ProjectEnvironment) -> MsmsUpdateSummary:
    """Interactive entrypoint for the DATA_MSMS workflow."""
    print("Updating DATA_MSMS and TOTAL PE...")
    summary = update_data_msms(env)
    print("Update DATA_MSMS completed.")
    print(f"DATA_MSMS: {summary.data_msms_path}")
    print(f"TOTAL PE: {summary.total_pe_path}")
    return summary
