"""Integration tests for Populate TOTAL PE workflow in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
import openpyxl
import pytest

from src.populate_total_pe_workflow import PopulateTotalPeWorkflow
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
    ws = wb.active
    ws.title = "RAW DATA"
    ws.cell(1, 1, "PE NO")
    ws.cell(1, 2, 1)
    ws.cell(2, 1, "SUBSTATION NAME")
    ws.cell(2, 2, "SSU CHEROH")
    ws.cell(3, 1, "FL NUMBER")
    ws.cell(3, 2, "CRAU-S001")
    ws.cell(4, 1, "DATE")
    ws.cell(4, 2, "01-05-2026")
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
    assert ws_res.cell(2, 4).value == "01-05-2026"
    wb_res.close()

    # Re-run AUTO mode to verify it skips already populated (1, "01-05-2026")
    second_res = workflow.execute(mock_env, request)
    assert second_res.new_rows_added == 0
