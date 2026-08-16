import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from pathlib import Path

from src.msms.models import (
    MsmsRecord,
    MSMS_COLUMN_MAPPING,
    ENGR_COLUMN_MAPPING_11KV,
    ENGR_COLUMN_MAPPING_33KV,
    TOTAL_PE_COLUMN_MAPPING,
)
from src.msms.repository import LocalExcelMsmsRepository


def test_msms_models():
    record = MsmsRecord("FL123", "Sub 1", "2026-01-01", "WO123")
    assert record.functional_location == "FL123"
    assert record.substation_name_erms == "Sub 1"
    assert record.date == "2026-01-01"
    assert record.wo == "WO123"


@patch("src.msms.repository.pd.read_excel")
def test_local_excel_msms_repository_get_work_order(mock_read, tmp_path):
    repo = LocalExcelMsmsRepository()
    
    data_path = tmp_path / "data.xlsx"
    data_path.touch()
    
    # Mock data msms dataframe with Column A (WO) and Column E (FL ERMS)
    df = pd.DataFrame(index=range(2), columns=range(26))
    df.iloc[:, 0] = ["WO1", "WO2"]
    df.iloc[:, 4] = ["FL1", "FL2"]
    mock_read.return_value = df
    
    wo = repo.get_work_order_by_fl(data_path, "FL2")
    assert wo == "WO2"

