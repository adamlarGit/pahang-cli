"""Unit and integration tests for EnrichMsmsWorkflow."""
from pathlib import Path
import openpyxl
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.models import EnrichMsmsRequest, EnrichMsmsResult
from src.workflows.enrich_msms import (
    EnrichMsmsPreflightGuard,
    EnrichMsmsExtractor,
    EnrichMsmsFilter,
    EnrichMsmsTransformer,
    EnrichMsmsLoader,
    EnrichMsmsAuditor,
    EnrichMsmsWorkflow,
    EnrichCellUpdate,
    EnrichMsmsPlan,
    is_canonical_sap_fl,
    is_crude_mnemonic,
)


def _create_sample_data_msms(path: Path, rows: list[list]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DATA MSMS"
    ws.append([
        "Work Order",
        "Location",
        "Description",
        "Substation Name ERMS",
        "FL ERMS",
        "Cycle Date",
        "Substation Number",
    ])
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _create_sample_total_pe(path: Path, rows: list[list], sheet_name: str = "DataCycle1") -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append([
        "PE NO",
        "FL NUMBER",
        "SUBSTATION NAME",
        "DATE",
        "TYPE",
        "WO",
        "SCOPE",
    ])
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _setup_project_environment(tmp_path: Path) -> ProjectEnvironment:
    storage = LocalWorkspaceStorage(tmp_path)
    storage.get_python_dir().mkdir(parents=True, exist_ok=True)
    metadata = ProjectMetadata(
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
    return ProjectEnvironment(metadata=metadata, storage=storage)


# --- PreflightGuard Tests ---

def test_enrich_msms_preflight_missing_data_msms(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_total_pe(env.storage.get_total_pe_path(), [])

    guard = EnrichMsmsPreflightGuard()
    with pytest.raises(FileNotFoundError, match="DATA MSMS workbook not found"):
        guard.validate(env)


def test_enrich_msms_preflight_missing_total_pe(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_data_msms(env.storage.get_data_msms_path(), [])

    guard = EnrichMsmsPreflightGuard()
    with pytest.raises(FileNotFoundError, match="TOTAL PE workbook not found"):
        guard.validate(env)


def test_enrich_msms_preflight_missing_sheet(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_data_msms(env.storage.get_data_msms_path(), [])
    _create_sample_total_pe(env.storage.get_total_pe_path(), [], sheet_name="WrongSheet")

    guard = EnrichMsmsPreflightGuard()
    with pytest.raises(RuntimeError, match="'DataCycle1' sheet missing"):
        guard.validate(env)


def test_enrich_msms_preflight_success(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_data_msms(env.storage.get_data_msms_path(), [])
    _create_sample_total_pe(env.storage.get_total_pe_path(), [])

    guard = EnrichMsmsPreflightGuard()
    guard.validate(env)  # Should not raise


def test_enrich_msms_preflight_locked_data_msms_raises(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_data_msms(env.storage.get_data_msms_path(), [])
    _create_sample_total_pe(env.storage.get_total_pe_path(), [])

    lock_file = env.storage.get_python_dir() / "~$DATA MSMS.xlsx"
    lock_file.write_bytes(b"locked")

    guard = EnrichMsmsPreflightGuard()
    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        guard.validate(env)


def test_enrich_msms_preflight_locked_total_pe_raises(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    _create_sample_data_msms(env.storage.get_data_msms_path(), [])
    _create_sample_total_pe(env.storage.get_total_pe_path(), [])

    lock_file = env.storage.get_python_dir() / "~$TOTAL PE.xlsx"
    lock_file.write_bytes(b"locked")

    guard = EnrichMsmsPreflightGuard()
    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        guard.validate(env)


# --- Extractor Tests ---

def test_enrich_msms_extractor(tmp_path: Path):
    extractor = EnrichMsmsExtractor()
    msms_file = tmp_path / "DATA MSMS.xlsx"
    _create_sample_data_msms(msms_file, [
        ["45001001", "LOC1", "DESC1", None, None, None, None],
    ])

    pe_file = tmp_path / "TOTAL PE.xlsx"
    _create_sample_total_pe(pe_file, [
        [10, "CKTN0001/BBBB", "PE SUB 1", "2026-01-15", "ATTACHED", "45001001", "FULL"],
    ])

    msms_rows = extractor.read_data_msms_rows(msms_file)
    assert len(msms_rows) == 1
    assert msms_rows[0]["row_idx"] == 2
    assert msms_rows[0]["wo"] == "45001001"

    pe_lookups = extractor.read_total_pe_lookups(pe_file)
    assert "45001001" in pe_lookups.by_wo
    assert pe_lookups.by_wo["45001001"]["substation_name_erms"] == "PE SUB 1"
    assert pe_lookups.by_wo["45001001"]["substation_number"] == 10


# --- Filter & Transformer Tests ---

def test_enrich_msms_filter_and_transformer():
    filter_stage = EnrichMsmsFilter()
    transformer = EnrichMsmsTransformer()

    msms_rows = [
        # Row 2: Unpopulated D-G -> matched and needs update
        {
            "row_idx": 2,
            "wo": "45001001",
            "fl_erms": None,
            "substation_name_erms": None,
            "cycle_date": None,
            "substation_number": None,
        },
        # Row 3: Already populated D-G -> matched but no cell updates needed
        {
            "row_idx": 3,
            "wo": "45001002",
            "fl_erms": "MANUAL/FL",
            "substation_name_erms": "MANUAL NAME",
            "cycle_date": "2026-01-01",
            "substation_number": 99,
        },
        # Row 4: Unmatched WO
        {
            "row_idx": 4,
            "wo": "45009999",
            "fl_erms": None,
            "substation_name_erms": None,
            "cycle_date": None,
            "substation_number": None,
        },
    ]

    total_pe_by_wo = {
        "45001001": {
            "substation_number": 1,
            "fl_erms": "CKTN0001/BBBB",
            "substation_name_erms": "PE ALPHA",
            "cycle_date": "2026-01-10",
        },
        "45001002": {
            "substation_number": 2,
            "fl_erms": "CKTN0002/CCCC",
            "substation_name_erms": "PE BETA",
            "cycle_date": "2026-01-11",
        },
    }

    filtered_updates, matched_count, unmatched_count, unmatched_wos, updated_cells_count = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo=total_pe_by_wo,
        total_pe_by_fl={},
    )

    assert matched_count == 2
    assert unmatched_count == 1
    assert unmatched_wos == ("45009999",)
    assert updated_cells_count == 4
    assert len(filtered_updates) == 1
    assert filtered_updates[0].row_index == 2
    assert filtered_updates[0].substation_name_erms == "PE ALPHA"
    assert filtered_updates[0].fl_erms == "CKTN0001/BBBB"
    assert filtered_updates[0].cycle_date == "2026-01-10"
    assert filtered_updates[0].substation_number == 1

    plan = transformer.build_plan(
        data_msms_path=Path("DATA MSMS.xlsx"),
        updates=filtered_updates,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        unmatched_wos=unmatched_wos,
        updated_cells_count=updated_cells_count,
    )
    assert isinstance(plan, EnrichMsmsPlan)
    assert plan.matched_count == 2


# --- Loader Tests ---

def test_enrich_msms_loader(tmp_path: Path):
    loader = EnrichMsmsLoader()
    msms_file = tmp_path / "DATA MSMS.xlsx"
    _create_sample_data_msms(msms_file, [
        ["45001001", "LOC1", "DESC1", None, None, None, None],
        ["45001002", "LOC2", "DESC2", "EXISTING SUB", "EXISTING/FL", "2026-01-01", 99],
    ])

    plan = EnrichMsmsPlan(
        data_msms_path=msms_file,
        updates=(
            EnrichCellUpdate(
                row_index=2,
                substation_name_erms="PE TELUK SISIK",
                fl_erms="CKTN0001/BBBB",
                cycle_date="2026-01-15",
                substation_number=10,
            ),
        ),
        matched_count=1,
        unmatched_count=0,
        unmatched_wos=(),
        updated_cells_count=4,
    )

    loader.load(plan)

    # Verify openpyxl write
    wb = openpyxl.load_workbook(msms_file)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Row 2 (updated)
    assert rows[1][0] == "45001001"
    assert rows[1][3] == "PE TELUK SISIK"
    assert rows[1][4] == "CKTN0001/BBBB"
    assert str(rows[1][5]) == "2026-01-15"
    assert rows[1][6] == 10

    # Row 3 (untouched)
    assert rows[2][3] == "EXISTING SUB"
    assert rows[2][4] == "EXISTING/FL"
    assert str(rows[2][5]) == "2026-01-01"
    assert rows[2][6] == 99


def test_enrich_msms_loader_locked_data_msms_raises(tmp_path: Path):
    loader = EnrichMsmsLoader()
    msms_file = tmp_path / "DATA MSMS.xlsx"
    _create_sample_data_msms(msms_file, [
        ["45001001", "LOC1", "DESC1", None, None, None, None],
    ])
    lock_file = tmp_path / "~$DATA MSMS.xlsx"
    lock_file.write_bytes(b"locked")

    plan = EnrichMsmsPlan(
        data_msms_path=msms_file,
        updates=(
            EnrichCellUpdate(
                row_index=2,
                substation_name_erms="PE TEST",
                fl_erms="FL/TEST",
                cycle_date="2026-01-15",
                substation_number=1,
            ),
        ),
        matched_count=1,
        unmatched_count=0,
        unmatched_wos=(),
        updated_cells_count=4,
    )

    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        loader.load(plan)


def test_enrich_msms_loader_save_permission_error_closes_workbook(tmp_path: Path, monkeypatch):
    loader = EnrichMsmsLoader()
    msms_file = tmp_path / "DATA MSMS.xlsx"
    _create_sample_data_msms(msms_file, [
        ["45001001", "LOC1", "DESC1", None, None, None, None],
    ])

    plan = EnrichMsmsPlan(
        data_msms_path=msms_file,
        updates=(
            EnrichCellUpdate(
                row_index=2,
                substation_name_erms="PE TEST",
                fl_erms="FL/TEST",
                cycle_date="2026-01-15",
                substation_number=1,
            ),
        ),
        matched_count=1,
        unmatched_count=0,
        unmatched_wos=(),
        updated_cells_count=4,
    )

    closed = False

    def mock_save(self, path):
        raise PermissionError("Access denied")

    real_close = openpyxl.Workbook.close

    def mock_close(self):
        nonlocal closed
        closed = True
        real_close(self)

    monkeypatch.setattr(openpyxl.Workbook, "save", mock_save)
    monkeypatch.setattr(openpyxl.Workbook, "close", mock_close)

    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        loader.load(plan)

    assert closed is True


# --- End-to-End Integration Workflow Tests ---

def test_enrich_msms_workflow_e2e(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    msms_file = env.storage.get_data_msms_path()
    _create_sample_data_msms(msms_file, [
        ["45001001", "LOC1", "DESC1", None, None, None, None],
        ["45001002", "LOC2", "DESC2", "MANUAL SUB", "MANUAL/FL", "2026-01-05", 99],
        ["45009999", "LOC3", "DESC3", None, None, None, None],
    ])

    pe_file = env.storage.get_total_pe_path()
    _create_sample_total_pe(pe_file, [
        [12, "CKTN0001/BBBB", "PE BANDAR RAYA", "2026-01-15", "ATTACHED", "45001001", "FULL"],
        [15, "CKTN0002/CCCC", "PE BUKIT MEWAH", "2026-01-16", "COMPACT", "45001002", "FULL"],
    ])

    workflow = EnrichMsmsWorkflow()
    result = workflow.execute(env, EnrichMsmsRequest())

    assert isinstance(result, EnrichMsmsResult)
    assert result.matched_count == 2
    assert result.unmatched_count == 1
    assert "45009999" in result.unmatched_wos
    assert result.updated_cells_count == 4

    # Verify openpyxl update
    wb = openpyxl.load_workbook(msms_file)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Row 2 (45001001): was all None in cols D-G, enriched
    assert rows[1][0] == "45001001"
    assert rows[1][3] == "PE BANDAR RAYA"
    assert rows[1][4] == "CKTN0001/BBBB"
    assert str(rows[1][5]) == "2026-01-15"
    assert rows[1][6] == 12

    # Row 3 (45001002): had manual entries, not overwritten
    assert rows[2][3] == "MANUAL SUB"
    assert rows[2][4] == "MANUAL/FL"
    assert str(rows[2][5]) == "2026-01-05"
    assert rows[2][6] == 99


def test_enrich_msms_filter_matches_via_location_when_fl_erms_blank():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "45001001",
            "location": "CRAU/PCEJ00232",
            "fl_erms": None,
            "substation_name_erms": None,
            "cycle_date": None,
            "substation_number": None,
        }
    ]
    total_pe_by_fl = {
        "CRAU/PCE/J00232": {
            "substation_number": 25,
            "fl_erms": "CRAU/PCE/J00232",
            "substation_name_erms": "PE CRAU JAYA",
            "cycle_date": "2026-02-20",
        },
        "CRAUPCEJ00232": {
            "substation_number": 25,
            "fl_erms": "CRAU/PCE/J00232",
            "substation_name_erms": "PE CRAU JAYA",
            "cycle_date": "2026-02-20",
        },
    }

    filtered_updates, matched_count, unmatched_count, unmatched_wos, updated_cells_count = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl=total_pe_by_fl,
    )

    assert matched_count == 1
    assert unmatched_count == 0
    assert updated_cells_count == 4
    assert len(filtered_updates) == 1
    assert filtered_updates[0].row_index == 2
    assert filtered_updates[0].substation_name_erms == "PE CRAU JAYA"
    assert filtered_updates[0].fl_erms == "CRAU/PCE/J00232"
    assert filtered_updates[0].cycle_date == "2026-02-20"
    assert filtered_updates[0].substation_number == 25


def test_enrich_msms_workflow_e2e_matches_via_location_when_fl_erms_and_wo_blank(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    msms_file = env.storage.get_data_msms_path()
    # Row 2 has location CRAU/PCEJ00232 but FL ERMS (Col E) is None
    _create_sample_data_msms(msms_file, [
        ["45001001", "CRAU/PCEJ00232", "PE CRAU JAYA DESC", None, None, None, None],
    ])

    pe_file = env.storage.get_total_pe_path()
    # Total PE has WO as None (Col F) but FL NUMBER as CRAU/PCE/J00232
    _create_sample_total_pe(pe_file, [
        [35, "CRAU/PCE/J00232", "PE CRAU JAYA", "2026-03-01", "ATTACHED", None, "FULL"],
    ])

    workflow = EnrichMsmsWorkflow()
    result = workflow.execute(env, EnrichMsmsRequest())

    assert result.matched_count == 1
    assert result.unmatched_count == 0
    assert result.updated_cells_count == 4

    wb = openpyxl.load_workbook(msms_file)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    assert rows[1][0] == "45001001"
    assert rows[1][1] == "CRAU/PCEJ00232"
    assert rows[1][3] == "PE CRAU JAYA"
    assert rows[1][4] == "CRAU/PCE/J00232"
    assert str(rows[1][5]) == "2026-03-01"
    assert rows[1][6] == 35


# --- Unit Tests for Helpers ---

def test_is_canonical_sap_fl():
    assert is_canonical_sap_fl("CGBG/PPU/G00001") is True
    assert is_canonical_sap_fl("CKTN/PMU/J00003") is True
    assert is_canonical_sap_fl("CRAU/PCE/J00232") is True
    assert is_canonical_sap_fl("CKLS/SSU/G00001") is True
    assert is_canonical_sap_fl("CCHL/PMU/BTNG") is False
    assert is_canonical_sap_fl("CKTN0001/BBBB") is False
    assert is_canonical_sap_fl("MANUAL/FL") is False
    assert is_canonical_sap_fl(None) is False
    assert is_canonical_sap_fl("") is False


def test_is_crude_mnemonic():
    assert is_crude_mnemonic("CCHL/PMU/BTNG", "CCHL/PMUBTNG") is True
    assert is_crude_mnemonic("CGBG/PPU/APMM", "CGBG/PPUAPMM") is True
    assert is_crude_mnemonic("CCHL/MPU/MPTERLA", "CCHL/MPUMPTERLA") is True
    assert is_crude_mnemonic("MANUAL/FL", "LOC2") is False
    assert is_crude_mnemonic("CCHL/PMU/J00001", "CCHL/PMUBTNG") is False
    assert is_crude_mnemonic(None, "LOC1") is False


# --- 33kV Substation Name Matching & SAP FL Synchronization Tests ---

def test_enrich_msms_filter_matches_via_substation_name_and_syncs_sap_fl():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "W1616862",
            "location": "CCHL/PMUBTNG",
            "description": "PMU BINTANG",
            "substation_name_erms": None,
            "fl_erms": "CCHL/PMU/BTNG",  # Crude mnemonic
            "cycle_date": None,
            "substation_number": None,
        }
    ]
    total_pe_records = [
        {
            "pe_row_idx": 29,
            "substation_number": 29,
            "fl_erms": "CCHL/PMU/J00001",  # True SAP FL
            "substation_name_erms": "PMU BINTANG 132/11/33kV",
            "cycle_date": "2026-10-17",
            "wo": None,
        }
    ]

    filtered_updates, matched_count, unmatched_count, unmatched_wos, updated_cells_count = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl={},
        total_pe_records=total_pe_records,
    )

    assert matched_count == 1
    assert unmatched_count == 0
    assert updated_cells_count == 4
    assert len(filtered_updates) == 1
    up = filtered_updates[0]
    assert up.row_index == 2
    assert up.substation_name_erms == "PMU BINTANG 132/11/33kV"
    assert up.fl_erms == "CCHL/PMU/J00001"
    assert up.cycle_date == "2026-10-17"
    assert up.substation_number == 29


def test_enrich_msms_filter_matches_via_token_subset():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "W1616933",
            "location": "CGBG/SSUKPC",
            "description": "SSU KPC",
            "substation_name_erms": None,
            "fl_erms": "CGBG/SSU/KPC",
            "cycle_date": None,
            "substation_number": None,
        }
    ]
    total_pe_records = [
        {
            "pe_row_idx": 5,
            "substation_number": 5,
            "fl_erms": "CGBG/SSU/G00006",
            "substation_name_erms": "SSU KPC GEBENG 33kV",
            "cycle_date": "2026-10-08",
            "wo": None,
        }
    ]

    updates, matched, unmatched, _, updated_cells = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl={},
        total_pe_records=total_pe_records,
    )

    assert matched == 1
    assert unmatched == 0
    assert updated_cells == 4
    assert updates[0].substation_name_erms == "SSU KPC GEBENG 33kV"
    assert updates[0].fl_erms == "CGBG/SSU/G00006"


def test_enrich_msms_filter_matches_gebeng_domain_aliases():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "W1616864",
            "location": "CGBG/PMUGBID",
            "description": "PMU GBID ( T ) 132/33KV",
            "substation_name_erms": None,
            "fl_erms": "CGBG/PMU/GBID",
            "cycle_date": None,
            "substation_number": None,
        },
        {
            "row_idx": 3,
            "wo": "W1616865",
            "location": "CGBG/PMUGBIG",
            "description": "PMU GBIG GIS 132/33/11kV",
            "substation_name_erms": None,
            "fl_erms": "CGBG/PMU/GBIG",
            "cycle_date": None,
            "substation_number": None,
        },
    ]
    total_pe_records = [
        {
            "pe_row_idx": 7,
            "substation_number": 7,
            "fl_erms": "CGBG/PMU/G00002",
            "substation_name_erms": "PMU GBID CABIN 33kV",
            "cycle_date": "2026-10-08",
            "wo": None,
        },
        {
            "pe_row_idx": 8,
            "substation_number": 8,
            "fl_erms": "CGBG/PMU/G00004",
            "substation_name_erms": "PMU GBID 275/132/33/11kV",
            "cycle_date": "2026-10-08",
            "wo": None,
        },
    ]

    updates, matched, unmatched, _, updated_cells = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl={},
        total_pe_records=total_pe_records,
    )

    assert matched == 2
    assert unmatched == 0
    assert updated_cells == 8
    # W1616864 -> CABIN (PE 7)
    up1 = next(u for u in updates if u.row_index == 2)
    assert up1.substation_name_erms == "PMU GBID CABIN 33kV"
    assert up1.fl_erms == "CGBG/PMU/G00002"
    assert up1.substation_number == 7
    # W1616865 -> 275/GIS (PE 8)
    up2 = next(u for u in updates if u.row_index == 3)
    assert up2.substation_name_erms == "PMU GBID 275/132/33/11kV"
    assert up2.fl_erms == "CGBG/PMU/G00004"
    assert up2.substation_number == 8


def test_enrich_msms_filter_token_subset_ignores_empty_p_dist():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "W1616999",
            "location": "CKTN/PESMBU",
            "description": "PE SEMAMBU",
            "substation_name_erms": None,
            "fl_erms": None,
            "cycle_date": None,
            "substation_number": None,
        }
    ]
    # Record has only electrical prefix "PE", so p_dist is empty
    total_pe_records = [
        {
            "pe_row_idx": 99,
            "substation_number": 99,
            "fl_erms": "CKTN/PE/G99999",
            "substation_name_erms": "PE",
            "cycle_date": "2026-10-08",
            "wo": None,
        }
    ]

    updates, matched, unmatched, unmatched_wos, updated_cells = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl={},
        total_pe_records=total_pe_records,
    )

    # Empty p_dist must NOT cause false positive subset match
    assert matched == 0
    assert unmatched == 1
    assert unmatched_wos == ("W1616999",)
    assert len(updates) == 0


def test_enrich_msms_filter_non_gebeng_gis_does_not_match_gebeng():
    filter_stage = EnrichMsmsFilter()
    msms_rows = [
        {
            "row_idx": 2,
            "wo": "W1616998",
            "location": "CKLS/PMUBTG",
            "description": "PMU BENTONG GIS 132/33kV",
            "substation_name_erms": None,
            "fl_erms": "CKLS/PMU/BTG",
            "cycle_date": None,
            "substation_number": None,
        }
    ]
    total_pe_records = [
        {
            "pe_row_idx": 8,
            "substation_number": 8,
            "fl_erms": "CGBG/PMU/G00004",
            "substation_name_erms": "PMU GBID 275/132/33/11kV",
            "cycle_date": "2026-10-08",
            "wo": None,
        }
    ]

    updates, matched, unmatched, unmatched_wos, _ = filter_stage.filter_rows(
        msms_rows=msms_rows,
        total_pe_by_wo={},
        total_pe_by_fl={},
        total_pe_records=total_pe_records,
    )

    # Non-Gebeng GIS station must NOT match Gebeng GIS record
    assert matched == 0
    assert unmatched == 1
    assert unmatched_wos == ("W1616998",)
    assert len(updates) == 0


def test_enrich_msms_workflow_e2e_33kv(tmp_path: Path):
    env = _setup_project_environment(tmp_path)
    msms_file = env.storage.get_data_msms_path()
    _create_sample_data_msms(msms_file, [
        ["W1616862", "CCHL/PMUBTNG", "PMU BINTANG", None, "CCHL/PMU/BTNG", None, None],
        ["W1616898", "CGBG/PPUAPMM", "PPU APMM 33/11KV", None, "CGBG/PPU/APMM", None, None],
        ["W1616956", "CKTN/SSUKIIP", "SSU KIIP 33kV", None, "CKTN/SSU/KIIP", None, None],
    ])

    pe_file = env.storage.get_total_pe_path()
    _create_sample_total_pe(pe_file, [
        [1, "CGBG/PPU/G00001", "PPU APMM 33/11kV", "2026-10-07", "PPU", None, "FULL"],
        [2, "CKTN/SSU/G00006", "SSU KIIP (SSU CAMEL POWER) 33kV", "2026-10-07", "SSU", None, "FULL"],
        [29, "CCHL/PMU/J00001", "PMU BINTANG 132/11/33kV", "2026-10-17", "PMU", None, "FULL"],
    ])

    workflow = EnrichMsmsWorkflow()
    result = workflow.execute(env, EnrichMsmsRequest())

    assert result.matched_count == 3
    assert result.unmatched_count == 0
    assert result.updated_cells_count == 12

    wb = openpyxl.load_workbook(msms_file)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Row 1 (W1616862): PMU BINTANG -> SAP FL CCHL/PMU/J00001, Number 29
    assert rows[1][0] == "W1616862"
    assert rows[1][3] == "PMU BINTANG 132/11/33kV"
    assert rows[1][4] == "CCHL/PMU/J00001"
    assert str(rows[1][5]) == "2026-10-17"
    assert rows[1][6] == 29

    # Row 2 (W1616898): PPU APMM -> SAP FL CGBG/PPU/G00001, Number 1
    assert rows[2][0] == "W1616898"
    assert rows[2][3] == "PPU APMM 33/11kV"
    assert rows[2][4] == "CGBG/PPU/G00001"
    assert str(rows[2][5]) == "2026-10-07"
    assert rows[2][6] == 1

    # Row 3 (W1616956): SSU KIIP -> SAP FL CKTN/SSU/G00006, Number 2
    assert rows[3][0] == "W1616956"
    assert rows[3][3] == "SSU KIIP (SSU CAMEL POWER) 33kV"
    assert rows[3][4] == "CKTN/SSU/G00006"
    assert str(rows[3][5]) == "2026-10-07"
    assert rows[3][6] == 2


def test_enrich_msms_workflow_thunder_cycle_4_regression(tmp_path: Path):
    """Integration regression against actual 33kV Thunder Cycle 4 dataset if available."""
    src_dir = Path(r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\PYTHON")
    data_msms_src = src_dir / "DATA MSMS.xlsx"
    total_pe_src = src_dir / "TOTAL PE.xlsx"
    if not data_msms_src.exists() or not total_pe_src.exists():
        pytest.skip("33kV Thunder Cycle 4 reference data not present on host")

    import shutil
    env = _setup_project_environment(tmp_path)
    dest_msms = env.storage.get_data_msms_path()
    dest_pe = env.storage.get_total_pe_path()

    shutil.copyfile(data_msms_src, dest_msms)
    shutil.copyfile(total_pe_src, dest_pe)

    workflow = EnrichMsmsWorkflow()
    result = workflow.execute(env, EnrichMsmsRequest())

    assert result.matched_count == 25
    assert result.unmatched_count == 0
    assert result.updated_cells_count == 100


