import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from pathlib import Path

from src.msms.models import (
    MsmsRecord,
    MsmsUpdateSummary,
    WorkbookUpdateMappings,
    MSMS_COLUMN_MAPPING,
    ENGR_COLUMN_MAPPING_11KV,
    TOTAL_PE_COLUMN_MAPPING,
)
from src.msms.repository import LocalExcelMsmsRepository
from src.master.total_pe import LocalExcelTotalPeRepository
from src.workflows.update_data_msms import update_data_msms, get_update_data_msms_resources


def test_msms_models():
    record = MsmsRecord("FL123", "Sub 1", "2026-01-01", "WO123")
    assert record.functional_location == "FL123"
    assert record.substation_name == "Sub 1"
    
    summary = MsmsUpdateSummary(Path("data.xlsx"), Path("pe.xlsx"), "*.xlsx")
    assert summary.engr_pattern == "*.xlsx"


@patch("src.msms.repository.pd.read_excel")
@patch("src.msms.repository.load_workbook")
def test_local_excel_msms_repository_get_work_order(mock_lw, mock_read, tmp_path):
    repo = LocalExcelMsmsRepository()
    
    data_path = tmp_path / "data.xlsx"
    data_path.touch()
    
    # Mock data msms dataframe
    df = pd.DataFrame({
        "A": ["WO1", "WO2"],
        "B": ["Loc1", "Loc2"],
        "D": ["Sub1", "Sub2"],
        "E": ["FL1", "FL2"],
        "F": ["2026-01-01", "2026-01-02"]
    })
    # the repo reads by index. Column A is index 0. E is 4.
    df = pd.DataFrame(index=range(2), columns=range(26))
    df.iloc[:, 0] = ["WO1", "WO2"]
    df.iloc[:, 4] = ["FL1", "FL2"]
    mock_read.return_value = df
    
    wo = repo.get_work_order_by_fl(data_path, "FL2")
    assert wo == "WO2"


@patch("src.workflows.update_data_msms.pd.read_excel")
@patch("src.workflows.update_data_msms.load_engr_files")
@patch("src.workflows.update_data_msms.LocalExcelMsmsRepository")
@patch("src.workflows.update_data_msms.LocalExcelTotalPeRepository")
@patch("src.workflows.update_data_msms.get_update_data_msms_resources")
def test_update_data_msms(mock_get_resources, mock_pe_repo, mock_msms_repo, mock_load, mock_read):
    env_mock = MagicMock()
    
    resources_mock = MagicMock()
    resources_mock.data_msms_path = Path("msms.xlsx")
    resources_mock.total_pe_path = Path("pe.xlsx")
    resources_mock.engr_pattern = "*.xlsx"
    resources_mock.data_msms_column_mapping = MSMS_COLUMN_MAPPING
    resources_mock.engr_column_mapping = ENGR_COLUMN_MAPPING_11KV
    resources_mock.total_pe_column_mapping = TOTAL_PE_COLUMN_MAPPING
    mock_get_resources.return_value = resources_mock
    
    mock_read.return_value = pd.DataFrame()
    mock_load.return_value = pd.DataFrame()
    
    summary = update_data_msms(env_mock)
    
    assert summary.data_msms_path == Path("msms.xlsx")
    assert summary.total_pe_path == Path("pe.xlsx")
    assert summary.engr_pattern == "*.xlsx"
    
    mock_msms_repo.return_value.update_msms.assert_called_once()
    mock_pe_repo.return_value.update_from_engr_and_msms.assert_called_once()
