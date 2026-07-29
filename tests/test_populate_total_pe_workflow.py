"""Integration tests for Populate TOTAL PE workflow in Pahang CLI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import openpyxl
import pytest

from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.models import PopulateMode, PopulateTotalPeRequest


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    meta = ProjectMetadata(
        key="pahang_2026",
        name="Pahang 2026 Test",
        po_number="PO42289580",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


def test_populate_total_pe_workflow_creates_and_updates_rows(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    # Setup TESTSHEET structure
    date_dir = tmp_path / "TESTSHEET" / "RAUB" / "01. MAY" / "01-05-2026"
    date_dir.mkdir(parents=True)
    (date_dir / "UNSORTED RAW DATA").mkdir()

    wb = openpyxl.Workbook()
    ws_pce = wb.active
    ws_pce.title = "PCE Testsheet"
    ws_pce["W5"] = "CRAU-S001"
    ws_pce["C5"] = "SSU CHEROH"
    ws_pce["P4"] = "01-05-2026"
    wb.save(date_dir / "001. SSU CHEROH.xlsx")
    wb.close()

    workflow = PopulateTotalPeWorkflow()
    request = PopulateTotalPeRequest(mode=PopulateMode.AUTO)
    result = workflow.execute(mock_env, request)

    assert result.new_rows_added == 1

    # Verify TOTAL PE.xlsx
    total_pe_path = mock_env.storage.get_total_pe_path()
    assert total_pe_path.exists()

    wb_res = openpyxl.load_workbook(total_pe_path)
    ws_res = wb_res["DataCycle1"]
    assert ws_res.cell(2, 1).value == 1
    assert ws_res.cell(2, 2).value == "CRAU-S001"
    assert ws_res.cell(2, 3).value == "SSU CHEROH"
    assert ws_res.cell(2, 4).value in (datetime(2026, 5, 1, 0, 0), datetime(2026, 5, 1, 0, 0).date(), "01-05-2026", "2026-05-01")
    wb_res.close()

    # Re-run AUTO mode to verify it skips already populated (1, "01-05-2026")
    second_res = workflow.execute(mock_env, request)
    assert second_res.new_rows_added == 0


def test_populate_total_pe_targets_column_a_empty_cells(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    # Pre-create TOTAL PE.xlsx with empty Column A at row 2 and a note in Column I at row 3
    total_pe_path = mock_env.storage.get_total_pe_path()
    mock_env.storage.ensure_directory(total_pe_path.parent)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE", "TYPE", "WO", "SCOPE"])
    ws.append([None, None, None, None, None, None])
    ws.cell(row=3, column=9, value="PASTE HERE AS TEXT")
    wb.save(total_pe_path)
    wb.close()

    # Setup TESTSHEET structure
    date_dir = tmp_path / "TESTSHEET" / "RAUB" / "01. MAY" / "17-06-2026"
    date_dir.mkdir(parents=True)
    (date_dir / "UNSORTED RAW DATA").mkdir()

    wb_ts = openpyxl.Workbook()
    ws_pce = wb_ts.active
    ws_pce.title = "PCE Testsheet"
    ws_pce["W5"] = "CCHL/PCE/J00293"
    ws_pce["C5"] = "CSU KEA FARM"
    ws_pce["P4"] = "17-06-2026"
    wb_ts.save(date_dir / "302. CSU KEA FARM.xlsx")
    wb_ts.close()

    workflow = PopulateTotalPeWorkflow()
    request = PopulateTotalPeRequest(mode=PopulateMode.AUTO)
    result = workflow.execute(mock_env, request)

    assert result.new_rows_added == 1

    wb_res = openpyxl.load_workbook(total_pe_path)
    ws_res = wb_res["DataCycle1"]
    # Record should be placed at Row 2 (first empty cell in Column A), preserving Column I note at Row 3
    assert ws_res.cell(2, 1).value == 302
    assert ws_res.cell(2, 2).value == "CCHL/PCE/J00293"
    assert ws_res.cell(2, 3).value == "CSU KEA FARM"
    assert ws_res.cell(3, 9).value == "PASTE HERE AS TEXT"
    wb_res.close()

