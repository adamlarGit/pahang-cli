"""Unit and integration tests for Propagate Work Orders Workflow."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
import openpyxl
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.models import (
    PropagateWoRequest,
    PropagateWoResult,
)
from src.workflows.propagate_wo import (
    PropagateWoAuditor,
    PropagateWoExtractor,
    PropagateWoFilter,
    PropagateWoLoader,
    PropagateWoMsmsRow,
    PropagateWoPeRow,
    PropagateWoPlan,
    PropagateWoPreflightGuard,
    PropagateWoRawData,
    PropagateWoRowUpdate,
    PropagateWoTransformer,
    PropagateWoWorkflow,
    clean_substation_name,
)


def _create_sample_data_msms(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _create_sample_total_pe(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.append([
        "PE NO",
        "FL NUMBER",
        "SUBSTATION NAME",
        "DATE",
        "TYPE",
        "WO",
        "SCOPE",
        "CUSTOM FORMULA",
    ])
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _setup_test_env(
    tmp_path: Path, voltage_type: str = "11kV"
) -> tuple[ProjectEnvironment, Path, Path]:
    meta = ProjectMetadata(
        key="test_proj",
        name="Test Project",
        po_number="PO12345",
        state="Pahang",
        voltage_type=voltage_type,
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type=voltage_type)
    env = ProjectEnvironment(
        metadata=meta,
        storage=storage,
    )
    python_dir = storage.get_python_dir()
    testsheet_dir = storage.get_testsheet_dir()
    python_dir.mkdir(parents=True, exist_ok=True)
    testsheet_dir.mkdir(parents=True, exist_ok=True)

    msms_file = storage.get_data_msms_path()
    pe_file = storage.get_total_pe_path()
    return env, msms_file, pe_file


# ---------------------------------------------------------------------------
# Stage 1: PreflightGuard Tests
# ---------------------------------------------------------------------------


def test_preflight_guard_missing_data_msms_raises(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_total_pe(pe_file, [[1, "FL1", "PE 1", "2026-01-10", "ATT", None, "FULL", None]])
    
    guard = PropagateWoPreflightGuard()
    with pytest.raises(FileNotFoundError, match=r"DATA MSMS\.xlsx"):
        guard.validate(env)


def test_preflight_guard_missing_total_pe_raises(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [["45001", "CKTN01", "PE 1", "PE 1", "CKTN01", "2026-01-10", 1]])
    
    guard = PropagateWoPreflightGuard()
    with pytest.raises(FileNotFoundError, match=r"TOTAL PE\.xlsx"):
        guard.validate(env)


def test_preflight_guard_missing_datacycle1_sheet_raises(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [["45001", "CKTN01", "PE 1", "PE 1", "CKTN01", "2026-01-10", 1]])
    
    # Create TOTAL PE without DataCycle1
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "WrongSheet"
    ws.append(["Col1"])
    wb.save(pe_file)
    wb.close()

    guard = PropagateWoPreflightGuard()
    with pytest.raises(RuntimeError, match=r"DataCycle1"):
        guard.validate(env)


def test_preflight_guard_empty_data_msms_raises(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [])  # No data rows
    _create_sample_total_pe(pe_file, [[1, "FL1", "PE 1", "2026-01-10", "ATT", None, "FULL", None]])

    guard = PropagateWoPreflightGuard()
    with pytest.raises(RuntimeError, match=r"DATA MSMS.*records"):
        guard.validate(env)


def test_preflight_guard_locked_total_pe_raises_permission_error(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [["45001", "CKTN01", "PE 1", "PE 1", "CKTN01", "2026-01-10", 1]])
    _create_sample_total_pe(pe_file, [[1, "FL1", "PE 1", "2026-01-10", "ATT", None, "FULL", None]])

    # Simulate Excel lock file (~$TOTAL PE.xlsx)
    lock_file = pe_file.parent / f"~${pe_file.name}"
    lock_file.touch()

    guard = PropagateWoPreflightGuard()
    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        guard.validate(env)


def test_preflight_guard_success(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [["45001", "CKTN01", "PE 1", "PE 1", "CKTN01", "2026-01-10", 1]])
    _create_sample_total_pe(pe_file, [[1, "FL1", "PE 1", "2026-01-10", "ATT", None, "FULL", None]])

    guard = PropagateWoPreflightGuard()
    guard.validate(env)  # Should not raise


# ---------------------------------------------------------------------------
# Stage 2: Extractor Tests
# ---------------------------------------------------------------------------


def test_extractor_reads_fl_to_wo_and_pe_rows(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [
        ["45001001", "CKTN0001AAAA", "PE TELUK SISIK", "PE TELUK SISIK", "CKTN0001/AAAA", "2026-01-10", 1],
        ["45001002", "CKTN0002BBBB", "PE BUKIT UBI", "PE BUKIT UBI", "CKTN0002/BBBB", "2026-01-11", 2],
    ])
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE TELUK SISIK", "2026-01-10", "ATTACHED", None, "FULL", "=IF(A2>0, 1, 0)"],
        [2, "CKTN0002/BBBB", "PE BUKIT UBI", "2026-01-11", "ATTACHED", "45009999", "FULL", "=IF(A3>0, 1, 0)"],
    ])

    extractor = PropagateWoExtractor()
    raw_data = extractor.extract(pe_file, msms_file)

    assert isinstance(raw_data, PropagateWoRawData)
    assert raw_data.fl_to_wo.get("CKTN0001/AAAA") == "45001001"
    assert raw_data.fl_to_wo.get("CKTN0001AAAA") == "45001001"
    assert raw_data.fl_to_wo.get("CKTN0002/BBBB") == "45001002"
    assert len(raw_data.pe_rows) == 2
    assert raw_data.pe_rows[0].row_index == 2
    assert raw_data.pe_rows[0].fl_num == "CKTN0001/AAAA"
    assert raw_data.pe_rows[0].wo is None
    assert raw_data.pe_rows[1].wo == "45009999"

    # Verify structured msms_rows extraction
    assert len(raw_data.msms_rows) == 2
    assert raw_data.msms_rows[0].wo == "45001001"
    assert raw_data.msms_rows[0].location == "CKTN0001AAAA"
    assert raw_data.msms_rows[0].description == "PE TELUK SISIK"
    assert raw_data.msms_rows[0].fl_erms == "CKTN0001/AAAA"
    assert raw_data.msms_rows[0].date_str == "10-01-2026"
    assert raw_data.msms_rows[0].substation_number == 1


# ---------------------------------------------------------------------------
# Stage 3: Filter Tests (Multi-Tier Matching)
# ---------------------------------------------------------------------------


def test_clean_substation_name_preserves_trailing_station_number() -> None:
    """Voltage regex must preserve trailing station numbers like 'PUTRA SQUARE 2 33kV'."""
    assert clean_substation_name("PUTRA SQUARE 2 33kV") == "PUTRA SQUARE 2"
    assert clean_substation_name("SSU PUTRA SQUARE 2 ( ZENITH ) 33KV") == "SSU PUTRA SQUARE 2"
    assert clean_substation_name("PPU APMM 1 33/11kV") == "PPU APMM 1"
    assert clean_substation_name("PMU GBID 275/132/33/11kV") == "PMU GBID"


def test_filter_matches_fl_and_populates_empty_wo() -> None:
    raw_data = PropagateWoRawData(
        fl_to_wo={"CKTN0001/AAAA": "45001001", "CKTN0001AAAA": "45001001"},
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=1,
                fl_num="CKTN0001/AAAA",
                substation_name="PE TELUK SISIK",
                date_str="2026-01-10",
                type_c="ATTACHED",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 1
    assert filtered.already_populated_count == 0
    assert filtered.unmatched_count == 0
    assert len(filtered.updates) == 1
    assert filtered.updates[0] == PropagateWoRowUpdate(row_index=2, wo="45001001", fl="CKTN0001/AAAA")


def test_filter_skips_already_populated_wo() -> None:
    raw_data = PropagateWoRawData(
        fl_to_wo={"CKTN0001/AAAA": "45001001", "CKTN0001AAAA": "45001001"},
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=1,
                fl_num="CKTN0001/AAAA",
                substation_name="PE TELUK SISIK",
                date_str="2026-01-10",
                type_c="ATTACHED",
                wo="45009999",
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 0
    assert filtered.already_populated_count == 1
    assert filtered.unmatched_count == 0
    assert len(filtered.updates) == 0


def test_filter_flags_unmatched_fl() -> None:
    raw_data = PropagateWoRawData(
        fl_to_wo={"CKTN0001/AAAA": "45001001"},
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=2,
                fl_num="CKTN9999/ZZZZ",
                substation_name="PE UNKNOWN",
                date_str="2026-01-10",
                type_c="ATTACHED",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 0
    assert filtered.already_populated_count == 0
    assert filtered.unmatched_count == 1
    assert "CKTN9999/ZZZZ" in filtered.unmatched_fls
    assert len(filtered.updates) == 0


def test_filter_with_target_date() -> None:
    raw_data = PropagateWoRawData(
        fl_to_wo={
            "CKTN0001/AAAA": "45001001",
            "CKTN0002/BBBB": "45001002",
        },
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=1,
                fl_num="CKTN0001/AAAA",
                substation_name="PE 1",
                date_str="2026-01-10",
                type_c="ATTACHED",
                wo=None,
            ),
            PropagateWoPeRow(
                row_index=3,
                pe_no=2,
                fl_num="CKTN0002/BBBB",
                substation_name="PE 2",
                date_str="2026-01-11",
                type_c="ATTACHED",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data, target_date="2026-01-10")

    assert filtered.matched_count == 1
    assert len(filtered.updates) == 1
    assert filtered.updates[0].row_index == 2


def test_filter_tier2_normalized_name_voltage_stripping() -> None:
    """Tier 2: Matches when FL strings differ but substation name matches after voltage rating stripping."""
    raw_data = PropagateWoRawData(
        fl_to_wo={},  # No FL match
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=1,
                fl_num="CGBG/PPU/G00001",  # SAP FL in TOTAL PE
                substation_name="PPU APMM 33/11kV",
                date_str="2026-10-07",
                type_c="PPU",
                wo=None,
            ),
            PropagateWoPeRow(
                row_index=3,
                pe_no=2,
                fl_num="CKTN/SSU/G00006",
                substation_name="SSU KIIP (SSU CAMEL POWER) 33kV",
                date_str="2026-10-07",
                type_c="SSU",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
        msms_rows=(
            PropagateWoMsmsRow(
                row_index=2,
                wo="W1616898",
                location="CGBG/PPUAPMM",
                description="PPU APMM 33/11KV",
                fl_erms="CGBG/PPU/APMM",
            ),
            PropagateWoMsmsRow(
                row_index=3,
                wo="W1616956",
                location="CKTN/SSUKIIP",
                description="SSU KIIP 33kV",
                fl_erms="CKTN/SSU/KIIP",
            ),
        ),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 2
    assert filtered.unmatched_count == 0
    assert len(filtered.updates) == 2
    assert filtered.updates[0].wo == "W1616898"
    assert filtered.updates[0].row_index == 2
    assert filtered.updates[1].wo == "W1616956"
    assert filtered.updates[1].row_index == 3


def test_filter_tier2_prefix_and_token_subset_matching() -> None:
    """Tier 2b/2c: MINI PPU / MPPU normalization and token subset matching."""
    raw_data = PropagateWoRawData(
        fl_to_wo={},
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=5,
                fl_num="CGBG/SSU/G00006",
                substation_name="SSU KPC GEBENG 33kV",
                date_str="2026-10-08",
                type_c="SSU",
                wo=None,
            ),
            PropagateWoPeRow(
                row_index=3,
                pe_no=30,
                fl_num="CCHL/MPU/G00005",
                substation_name="MINI PPU HABU 33/11kV",
                date_str="2026-10-18",
                type_c="MPPU",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
        msms_rows=(
            PropagateWoMsmsRow(
                row_index=2,
                wo="W1616933",
                location="CGBG/SSUKPC",
                description="SSU KPC",
                fl_erms="CGBG/SSU/KPC",
            ),
            PropagateWoMsmsRow(
                row_index=3,
                wo="W1616966",
                location="CCHL/MPUHABU",
                description="MPPU HABU 33/11 kV",
                fl_erms="CCHL/MPU/HABU",
            ),
        ),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 2
    assert filtered.updates[0].wo == "W1616933"
    assert filtered.updates[1].wo == "W1616966"


def test_filter_tier2_cabin_vs_gis_domain_resolution() -> None:
    """Tier 2a: Disambiguates PMU GBID CABIN 33kV vs PMU GBID 275/132/33/11kV GIS."""
    raw_data = PropagateWoRawData(
        fl_to_wo={},
        pe_rows=(
            PropagateWoPeRow(
                row_index=8,
                pe_no=7,
                fl_num="CGBG/PMU/G00002",
                substation_name="PMU GBID CABIN 33kV",
                date_str="2026-10-08",
                type_c="PMU",
                wo=None,
            ),
            PropagateWoPeRow(
                row_index=9,
                pe_no=8,
                fl_num="CGBG/PMU/G00004",
                substation_name="PMU GBID 275/132/33/11kV",
                date_str="2026-10-08",
                type_c="PMU",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
        msms_rows=(
            PropagateWoMsmsRow(
                row_index=23,
                wo="W1616864",
                location="CGBG/PMUGBID",
                description="PMU GBID ( T ) 132/33KV",
                fl_erms="CGBG/PMU/GBID",
            ),
            PropagateWoMsmsRow(
                row_index=24,
                wo="W1616865",
                location="CGBG/PMUGBIG",
                description="PMU GBIG GIS 132/33/11kV",
                fl_erms="CGBG/PMU/GBIG",
            ),
        ),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 2
    # Row 8 (Cabin) must match W1616864 (GBID / Cabin)
    assert filtered.updates[0].row_index == 8
    assert filtered.updates[0].wo == "W1616864"
    # Row 9 (275 GIS) must match W1616865 (GBIG / GIS)
    assert filtered.updates[1].row_index == 9
    assert filtered.updates[1].wo == "W1616865"


def test_filter_tier2_cabin_heuristic_strictly_scoped_to_gebeng() -> None:
    """Non-Gebeng substations containing 'CABIN' or 'GIS' in their name must NOT steal Gebeng work orders."""
    raw_data = PropagateWoRawData(
        fl_to_wo={},
        pe_rows=(
            PropagateWoPeRow(
                row_index=2,
                pe_no=1,
                fl_num="CKLS/PE/G00010",
                substation_name="PE CABIN KUALA LIPIS",
                date_str="2026-10-08",
                type_c="PE",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
        msms_rows=(
            PropagateWoMsmsRow(
                row_index=23,
                wo="W1616864",
                location="CGBG/PMUGBID",
                description="PMU GBID ( T ) 132/33KV",
                fl_erms="CGBG/PMU/GBID",
            ),
        ),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 0
    assert filtered.unmatched_count == 1


def test_filter_tier3_station_acronym_and_whitespace_matching() -> None:
    """Tier 3: Station acronym / alias token matching (e.g. PPUSWIG -> PPU SWISS GARDEN)."""
    raw_data = PropagateWoRawData(
        fl_to_wo={},
        pe_rows=(
            PropagateWoPeRow(
                row_index=12,
                pe_no=11,
                fl_num="CGBG/PPU/G00003",
                substation_name="PPU SWISS GARDEN 33/11kV",
                date_str="2026-10-09",
                type_c="PPU",
                wo=None,
            ),
        ),
        total_pe_path=Path("TOTAL PE.xlsx"),
        data_msms_path=Path("DATA MSMS.xlsx"),
        msms_rows=(
            PropagateWoMsmsRow(
                row_index=6,
                wo="W1616941",
                location="CGBG/PPUSWIG",
                description="PPU SWISSGARDEN",
                fl_erms="CGBG/PPU/SWIG",
            ),
        ),
    )

    flt = PropagateWoFilter()
    filtered = flt.filter(raw_data)

    assert filtered.matched_count == 1
    assert filtered.updates[0].wo == "W1616941"


# ---------------------------------------------------------------------------
# Stage 4: Transformer Tests
# ---------------------------------------------------------------------------


def test_transformer_builds_immutable_plan() -> None:
    transformer = PropagateWoTransformer()
    total_pe_path = Path("TOTAL PE.xlsx")
    updates = (PropagateWoRowUpdate(row_index=2, wo="45001001", fl="CKTN0001/AAAA"),)

    plan = transformer.build_plan(
        total_pe_path=total_pe_path,
        updates=updates,
        matched_count=1,
        already_populated_count=2,
        unmatched_count=3,
        unmatched_fls=("CKTN9999/ZZZZ",),
        target_date="2026-01-10",
    )

    assert isinstance(plan, PropagateWoPlan)
    assert plan.total_pe_path == total_pe_path
    assert len(plan.updates) == 1
    assert plan.matched_count == 1
    assert plan.already_populated_count == 2
    assert plan.unmatched_count == 3
    assert plan.unmatched_fls == ("CKTN9999/ZZZZ",)
    assert plan.target_date == "2026-01-10"


# ---------------------------------------------------------------------------
# Stage 5: Loader Tests
# ---------------------------------------------------------------------------


def test_loader_preserves_formulas_and_updates_col_f(tmp_path: Path) -> None:
    pe_file = tmp_path / "TOTAL PE.xlsx"
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE TELUK SISIK", "2026-01-10", "ATTACHED", None, "FULL", "=IF(A2>0, 1, 0)"],
        [2, "CKTN0002/BBBB", "PE BUKIT UBI", "2026-01-11", "ATTACHED", "45009999", "FULL", "=IF(A3>0, 1, 0)"],
    ])

    loader = PropagateWoLoader()
    plan = PropagateWoPlan(
        total_pe_path=pe_file,
        updates=(PropagateWoRowUpdate(row_index=2, wo="45001001", fl="CKTN0001/AAAA"),),
        matched_count=1,
        already_populated_count=1,
        unmatched_count=0,
        unmatched_fls=(),
    )

    updated_count = loader.load(plan)
    assert updated_count == 1

    wb = openpyxl.load_workbook(pe_file)
    ws = wb["DataCycle1"]
    assert ws.cell(2, 6).value == "45001001"
    assert ws.cell(2, 8).value == "=IF(A2>0, 1, 0)"
    assert ws.cell(2, 1).value == 1
    assert ws.cell(3, 6).value == "45009999"
    assert ws.cell(3, 8).value == "=IF(A3>0, 1, 0)"
    wb.close()


def test_loader_locked_file_raises_permission_error(tmp_path: Path) -> None:
    pe_file = tmp_path / "TOTAL PE.xlsx"
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE TELUK SISIK", "2026-01-10", "ATTACHED", None, "FULL", None],
    ])

    # Simulate Excel lock file
    lock_file = pe_file.parent / f"~${pe_file.name}"
    lock_file.touch()

    loader = PropagateWoLoader()
    plan = PropagateWoPlan(
        total_pe_path=pe_file,
        updates=(PropagateWoRowUpdate(row_index=2, wo="45001001", fl="CKTN0001/AAAA"),),
        matched_count=1,
        already_populated_count=0,
        unmatched_count=0,
        unmatched_fls=(),
    )

    with pytest.raises(PermissionError, match=r"locked or currently open in Microsoft Excel"):
        loader.load(plan)


# ---------------------------------------------------------------------------
# Stage 6: Auditor Tests
# ---------------------------------------------------------------------------


def test_auditor_success(tmp_path: Path) -> None:
    pe_file = tmp_path / "TOTAL PE.xlsx"
    pe_file.write_text("dummy")

    auditor = PropagateWoAuditor()
    plan = PropagateWoPlan(
        total_pe_path=pe_file,
        updates=(PropagateWoRowUpdate(row_index=2, wo="45001001", fl="CKTN0001/AAAA"),),
        matched_count=1,
        already_populated_count=2,
        unmatched_count=1,
        unmatched_fls=("FL_UNMATCHED",),
    )

    result = auditor.audit(plan, updated_count=1)
    assert isinstance(result, PropagateWoResult)
    assert result.matched_count == 1
    assert result.already_populated_count == 2
    assert result.unmatched_count == 1
    assert result.unmatched_fls == ("FL_UNMATCHED",)
    assert result.updated_count == 1


def test_auditor_missing_file_raises(tmp_path: Path) -> None:
    pe_file = tmp_path / "NON_EXISTENT.xlsx"
    auditor = PropagateWoAuditor()
    plan = PropagateWoPlan(
        total_pe_path=pe_file,
        updates=(),
        matched_count=0,
        already_populated_count=0,
        unmatched_count=0,
        unmatched_fls=(),
    )
    with pytest.raises(RuntimeError, match=r"does not exist"):
        auditor.audit(plan, updated_count=0)


def test_auditor_empty_file_raises(tmp_path: Path) -> None:
    pe_file = tmp_path / "EMPTY.xlsx"
    pe_file.touch()
    auditor = PropagateWoAuditor()
    plan = PropagateWoPlan(
        total_pe_path=pe_file,
        updates=(),
        matched_count=0,
        already_populated_count=0,
        unmatched_count=0,
        unmatched_fls=(),
    )
    with pytest.raises(RuntimeError, match=r"empty"):
        auditor.audit(plan, updated_count=0)


# ---------------------------------------------------------------------------
# End-to-End Workflow Integration Tests
# ---------------------------------------------------------------------------


def test_propagate_wo_workflow_e2e_all(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [
        ["45001001", "CKTN0001AAAA", "PE TELUK SISIK", "PE TELUK SISIK", "CKTN0001/AAAA", "2026-01-10", 1],
        ["45001002", "CKTN0002BBBB", "PE BUKIT UBI", "PE BUKIT UBI", "CKTN0002/BBBB", "2026-01-11", 2],
        ["45001003", "CKTN0003CCCC", "PE ALOR AKAR", "PE ALOR AKAR", "CKTN0003/CCCC", "2026-01-12", 3],
    ])
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE TELUK SISIK", "2026-01-10", "ATTACHED", None, "FULL", "=IF(A2>0, 1, 0)"],
        [2, "CKTN0002/BBBB", "PE BUKIT UBI", "2026-01-11", "ATTACHED", "45009999", "FULL", "=IF(A3>0, 1, 0)"],
        [3, "CKTN0009/ZZZZ", "PE UNKNOWN", "2026-01-12", "COMPACT", None, "FULL", "=IF(A4>0, 1, 0)"],
    ])

    progress_messages: list[str] = []
    request = PropagateWoRequest(progress_sink=progress_messages.append)
    workflow = PropagateWoWorkflow()

    result = workflow.execute(env, request)

    assert isinstance(result, PropagateWoResult)
    assert result.matched_count == 1
    assert result.already_populated_count == 1
    assert result.unmatched_count == 1
    assert "CKTN0009/ZZZZ" in result.unmatched_fls
    assert result.updated_count == 1
    assert len(progress_messages) > 0

    # Verify openpyxl output
    wb = openpyxl.load_workbook(pe_file)
    ws = wb["DataCycle1"]
    assert ws.cell(2, 6).value == "45001001"
    assert ws.cell(2, 8).value == "=IF(A2>0, 1, 0)"
    assert ws.cell(3, 6).value == "45009999"
    assert ws.cell(4, 6).value is None
    wb.close()


def test_propagate_wo_workflow_e2e_target_date(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [
        ["45001001", "CKTN0001AAAA", "PE A", "PE A", "CKTN0001/AAAA", "2026-01-10", 1],
        ["45001002", "CKTN0002BBBB", "PE B", "PE B", "CKTN0002/BBBB", "2026-01-11", 2],
    ])
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE A", "2026-01-10", "ATTACHED", None, "FULL", None],
        [2, "CKTN0002/BBBB", "PE B", "2026-01-11", "ATTACHED", None, "FULL", None],
    ])

    request = PropagateWoRequest(target_date="2026-01-10")
    workflow = PropagateWoWorkflow()
    result = workflow.execute(env, request)

    assert result.matched_count == 1
    assert result.updated_count == 1

    wb = openpyxl.load_workbook(pe_file)
    ws = wb["DataCycle1"]
    assert ws.cell(2, 6).value == "45001001"
    assert ws.cell(3, 6).value is None  # Skipped
    wb.close()


def test_propagate_wo_workflow_idempotency(tmp_path: Path) -> None:
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [
        ["45001001", "CKTN0001AAAA", "PE A", "PE A", "CKTN0001/AAAA", "2026-01-10", 1],
    ])
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE A", "2026-01-10", "ATTACHED", None, "FULL", None],
    ])

    workflow = PropagateWoWorkflow()
    res1 = workflow.execute(env, PropagateWoRequest())
    assert res1.matched_count == 1
    assert res1.already_populated_count == 0
    assert res1.updated_count == 1

    # Second run: should be skipped as already populated
    res2 = workflow.execute(env, PropagateWoRequest())
    assert res2.matched_count == 0
    assert res2.already_populated_count == 1
    assert res2.updated_count == 0

    # Third run with overwrite=True: should overwrite
    res3 = workflow.execute(env, PropagateWoRequest(overwrite=True))
    assert res3.matched_count == 1
    assert res3.already_populated_count == 0
    assert res3.updated_count == 1


def test_propagate_wo_workflow_33kv_thunder_cycle4_e2e_100_percent(tmp_path: Path) -> None:
    """Acceptance Test: Achieves 100% match rate (25/25 work orders) on 33kV Thunder Cycle 4 dataset."""
    src_33kv = Path(r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\PYTHON")
    env, msms_file, pe_file = _setup_test_env(tmp_path, voltage_type="33kV")

    if (src_33kv / "DATA MSMS.xlsx").exists() and (src_33kv / "TOTAL PE.xlsx").exists():
        shutil.copy2(src_33kv / "DATA MSMS.xlsx", msms_file)
        shutil.copy2(src_33kv / "TOTAL PE.xlsx", pe_file)
    else:
        # Standalone fixture replicating the 33kV Thunder Cycle 4 structure
        _create_sample_data_msms(
            msms_file,
            [
                ["W1616898", "CGBG/PPUAPMM", "PPU APMM 33/11KV", None, "CGBG/PPU/APMM", None, None],
                ["W1616956", "CKTN/SSUKIIP", "SSU KIIP 33kV", None, "CKTN/SSU/KIIP", None, None],
                ["W1616922", "CGBG/SSULNAS", "SSU LYNAS 33KV", None, "CGBG/SSU/LNAS", None, None],
                ["W1616924", "CGBG/SSUFERRO", "SSU FERRO MANGANESE", None, "CGBG/SSU/FERRO", None, None],
                ["W1616933", "CGBG/SSUKPC", "SSU KPC", None, "CGBG/SSU/KPC", None, None],
                ["W1616923", "CGBG/SSUFLEXS", "SSU FLEXSYS CHEMICAL 33KV", None, "CGBG/SSU/FLEXS", None, None],
                ["W1616864", "CGBG/PMUGBID", "PMU GBID ( T ) 132/33KV", None, "CGBG/PMU/GBID", None, None],
                ["W1616865", "CGBG/PMUGBIG", "PMU GBIG GIS 132/33/11kV", None, "CGBG/PMU/GBIG", None, None],
                ["W1616906", "CKTN/PPUSMAB", "PPU SEMAMBU YARD 33/11kV", None, "CKTN/PPU/SMAB", None, None],
                ["W1616877", "CKTN/PMUSMBU", "PMU SEMAMBU 132/11KV", None, "CKTN/PMU/SMBU", None, None],
                ["W1616941", "CGBG/PPUSWIG", "PPU SWISSGARDEN", None, "CGBG/PPU/SWIG", None, None],
                ["W1616878", "CKTN/PMUKTCL", "PMU KUANTAN CENTRAL 132/11kV", None, "CKTN/PMU/KTCL", None, None],
                ["W1616928", "CKTN/SSUPUTS", "SSU PUTRA SQUARE 2 ( ZENITH ) 33KV", None, "CKTN/SSU/PUTS", None, None],
                ["W1616871", "CKLS/PMUBNTA", "PMU BENTA", None, "CKLS/PMU/BNTA", None, None],
                ["W1616870", "CKLS/PMUKLIP", "PMU KUALA LIPIS 132/33kV & 132/11kV", None, "CKLS/PMU/KLIP", None, None],
                ["W1616925", "CKLS/SSUMCHIP", "SSU MIECO 33kV", None, "CKLS/SSU/MCHIP", None, None],
                ["W1616945", "CKLS/MPUKECHAU", "MINI PPU KECHAU TUI", None, "CKLS/MPU/KECHAU", None, None],
                ["W1616901", "CKLS/MPUBKTBTONG", "MINI PPU BUKIT BETONG", None, "CKLS/MPU/BKTBTONG", None, None],
                ["W1616912", "CRAU/MPUSLSING", "MINI PPU SELINSING RAUB", None, "CRAU/MPU/SLSING", None, None],
                ["W1616913", "CRAU/MPUSKYN", "MINI PPU SG KOYAN", None, "CRAU/MPU/SKYN", None, None],
                ["W1616897", "CCHL/MPUTLNK", "MINI PPU TELANOK", None, "CCHL/MPU/TLNK", None, None],
                ["W1616861", "CCHL/PMUUJLI", "PMU ULU JELAI 132/33KV", None, "CCHL/PMU/UJLI", None, None],
                ["W1616896", "CCHL/MPUMPTERLA", "MINI PPU TERLA 33/11KV", None, "CCHL/MPU/MPTERLA", None, None],
                ["W1616862", "CCHL/PMUBTNG", "PMU BINTANG", None, "CCHL/PMU/BTNG", None, None],
                ["W1616966", "CCHL/MPUHABU", "MPPU HABU 33/11 kV", None, "CCHL/MPU/HABU", None, None],
            ],
        )
        _create_sample_total_pe(
            pe_file,
            [
                [1, "CGBG/PPU/G00001", "PPU APMM 33/11kV", "2026-10-07", "PPU", None, None, None],
                [2, "CKTN/SSU/G00006", "SSU KIIP (SSU CAMEL POWER) 33kV", "2026-10-07", "SSU", None, None, None],
                [3, "CGBG/SSU/G00003", "SSU LYNAS 33kV", "2026-10-07", "SSU", None, None, None],
                [4, "CGBG/SSU/G00005", "SSU FERRO MANGANESE 33kV", "2026-10-07", "SSU", None, None, None],
                [5, "CGBG/SSU/G00006", "SSU KPC GEBENG 33kV", "2026-10-08", "SSU", None, None, None],
                [6, "CGBG/SSU/G00004", "SSU FLEXSYS CHEMICAL 33kV", "2026-10-08", "SSU", None, None, None],
                [7, "CGBG/PMU/G00002", "PMU GBID CABIN 33kV", "2026-10-08", "PMU", None, None, None],
                [8, "CGBG/PMU/G00004", "PMU GBID 275/132/33/11kV", "2026-10-08", "PMU", None, None, None],
                [9, "CKTN/PPU/G00012", "PPU SEMAMBU YARD 33/11kV", "2026-10-09", "PPU", None, None, None],
                [10, "CKTN/PMU/J00003", "PMU SEMAMBU 132/11kV", "2026-10-09", "PMU", None, None, None],
                [11, "CGBG/PPU/G00003", "PPU SWISS GARDEN 33/11kV", "2026-10-09", "PPU", None, None, None],
                [12, "CKTN/PMU/J00001", "PMU KUANTAN  132/11kV", "2026-10-10", "PMU", None, None, None],
                [13, "CKTN/PMU/G00004", "PMU KUANTAN  132/33kV", "2026-10-10", "PMU", None, None, None],
                [14, "CKTN/PPU/G00018", "PPU INDERA SEMPURNA", "2026-10-10", "PPU", None, None, None],
                [15, "CKTN/PMU/J00005", "PMU KUANTAN CENTRAL 132/11kV", "2026-10-11", "PMU", None, None, None],
                [16, "CKTN/SSU/G00004", "SSU PUTRA SQUARE 2 (SSU ZENITH) 33kV", "2026-10-11", "SSU", None, None, None],
                [17, "CKLS/PMU/J00002", "PMU BENTA 132/11kV", "2026-10-14", "PMU", None, None, None],
                [19, "CKLS/PMU/G00001", "PMU KUALA LIPIS 132/33kV", "2026-10-14", "PMU", None, None, None],
                [20, "CKLS/SSU/G00001", "SSU MIECO 33kV", "2026-10-14", "SSU", None, None, None],
                [21, "CKLS/MPU/G00003", "MINI PPU TEMAU 33/11kV", "2026-10-15", "MPPU", None, None, None],
                [22, "CKLS/MPU/G00002", "MINI PPU KECHAU TUI 33/11kV", "2026-10-15", "MPPU", None, None, None],
                [23, "CKLS/MPU/G00001", "MINI PPU BUKIT BETONG 33/11kV", "2026-10-15", "MPPU", None, None, None],
                [24, "CRAU/MPU/G00001", "MINI PPU SELINSING RAUB 33/11kV", "2026-10-16", "MPPU", None, None, None],
                [25, "CRAU/MPU/G00002", "MINI PPU SG KOYAN 33/11kV", "2026-10-16", "MPPU", None, None, None],
                [26, "CCHL/MPU/G00002", "MINI PPU TELANOK 33/11kV", "2026-10-16", "MPPU", None, None, None],
                [27, "CCHL/PMU/G00001", "PMU ULU JELAI 132/33kV", "2026-10-16", "PMU", None, None, None],
                [28, "CCHL/MPU/G00001", "MINI PPU TERLA 33/11kV", "2026-10-17", "MPPU", None, None, None],
                [29, "CCHL/PMU/J00001", "PMU BINTANG 132/11/33kV", "2026-10-17", "PMU", None, None, None],
                [30, "CCHL/MPU/G00005", "MINI PPU HABU 33/11kV", "2026-10-18", "MPPU", None, None, None],
            ],
        )

    logs: list[str] = []
    wf = PropagateWoWorkflow()
    result = wf.execute(env, PropagateWoRequest(progress_sink=logs.append))

    # Acceptance Criteria Verification
    assert result.matched_count == 25, f"Expected 25 matches, got {result.matched_count}"
    assert result.updated_count == 25, f"Expected 25 updates, got {result.updated_count}"
    assert result.already_populated_count == 0
    assert result.unmatched_count == 4
    assert len(result.unmatched_fls) == 4

    # Verify TOTAL PE.xlsx was physically written with work orders in Column F
    wb = openpyxl.load_workbook(pe_file, data_only=True)
    ws = wb["DataCycle1"]
    populated_wos = [
        ws.cell(r, 6).value for r in range(2, ws.max_row + 1)
        if ws.cell(r, 6).value and str(ws.cell(r, 6).value).strip().lower() not in ("none", "nan")
    ]
    assert len(populated_wos) == 25
    wb.close()


def test_workflow_service_run_propagate_wo(tmp_path: Path) -> None:
    from src.workflows.service import WorkflowService
    env, msms_file, pe_file = _setup_test_env(tmp_path)
    _create_sample_data_msms(msms_file, [
        ["45001001", "CKTN0001AAAA", "PE A", "PE A", "CKTN0001/AAAA", "2026-01-10", 1],
    ])
    _create_sample_total_pe(pe_file, [
        [1, "CKTN0001/AAAA", "PE A", "2026-01-10", "ATTACHED", None, "FULL", None],
    ])

    service = WorkflowService()
    logs: list[str] = []
    res = service.run_propagate_wo(env, PropagateWoRequest(progress_sink=logs.append))
    assert res.matched_count == 1
    assert res.updated_count == 1
    assert any("Propagate" in msg for msg in logs)
