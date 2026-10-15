"""Unit and integration tests for 33kV Contract 750-39 QR02 CBA and defect operations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import openpyxl
import pytest

from src.project.storage import LocalWorkspaceStorage
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.workflows.update_qr02_cba import (
    UpdateQr02CbaTransformer,
    get_package_key,
)


def _make_dummy_package(
    station: str = "THUNDER",
    month: str = "05. MAY",
    date_str: str = "01-05-2026",
    sub_num: int = 1,
    testsheet_filename: str = "001. PPU CHEROH.xlsx",
) -> SubstationTestsheetPackage:
    pkg_path = Path(f"/testsheet/{station}/{month}/{date_str}/{testsheet_filename}")
    return SubstationTestsheetPackage(
        station=station,
        month=month,
        date_str=date_str,
        substation_number=sub_num,
        testsheet_path=pkg_path,
        unsorted_raw_data_dir=pkg_path.parent / "UNSORTED RAW DATA",
        data=None,
    )


# =========================================================================
# Seam 1: Storage Resolution (Contract 750-39)
# =========================================================================

def test_storage_resolves_33kv_contract_750_39_strictly(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    cba_path = storage.get_engr_cba_path(station="UNKNOWN_STATION", year="2026")
    expected = tmp_path / "PYTHON" / "ENGR FROM DRIVE" / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"
    assert cba_path == expected


def test_storage_resolves_33kv_via_voltage_type_kwarg(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="11kV")
    cba_path = storage.get_engr_cba_path(station="ANY", year="2026", voltage_type="33kV")
    expected = tmp_path / "PYTHON" / "ENGR FROM DRIVE" / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"
    assert cba_path == expected


def test_storage_get_engr_33kv_cba_path(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)
    cba_path = storage.get_engr_33kv_cba_path(year="2026")
    expected = tmp_path / "PYTHON" / "ENGR FROM DRIVE" / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"
    assert cba_path == expected


def test_storage_preserves_11kv_resolution_with_station_code(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="11kV")
    cba_path = storage.get_engr_cba_path(station="RAUB", year="2026")
    expected = tmp_path / "PYTHON" / "ENGR FROM DRIVE" / "ENGR-750-36-CBA-RAU-2026.xlsx"
    assert cba_path == expected


# =========================================================================
# Seam 2: Two-Tier Functional Location Resolution in Transformer
# =========================================================================

def test_transformer_33kv_primary_fl_from_testsheet(tmp_path: Path) -> None:
    pkg = _make_dummy_package("THUNDER", "05. MAY", "01-05-2026", 1)
    data = TestsheetData(
        substation_number=1,
        substation_name_erms="PPU CHEROH",
        fl_erms="CGBG/PPU/G00001",
        date_str="01-05-2026",
    )
    records_map = {get_package_key(pkg): [data]}

    transformer = UpdateQr02CbaTransformer()
    plan = transformer.transform(
        [pkg],
        records_map,
        extraction_warnings=[],
        voltage_type="33kV",
    )
    assert len(plan.station_plans) == 1
    assert plan.station_plans[0].records[0].fl_erms == "CGBG/PPU/G00001"


def test_transformer_33kv_fallback_fl_from_total_pe(tmp_path: Path) -> None:
    # Setup synthetic TOTAL PE.xlsx with DataCycle1 sheet
    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.cell(row=1, column=1, value="PE NO")
    ws.cell(row=1, column=2, value="FL NUMBER")
    ws.cell(row=1, column=3, value="SUBSTATION NAME")

    ws.cell(row=2, column=1, value=1)
    ws.cell(row=2, column=2, value="CGBG/PPU/G00001")
    ws.cell(row=2, column=3, value="PPU CHEROH")
    wb.save(total_pe_path)
    wb.close()

    pkg = _make_dummy_package("THUNDER", "05. MAY", "01-05-2026", 1)
    # Record has missing FL on testsheet
    data = TestsheetData(
        substation_number=1,
        substation_name_erms="PPU CHEROH",
        fl_erms="",
        fl_site="",
        date_str="01-05-2026",
    )
    records_map = {get_package_key(pkg): [data]}

    transformer = UpdateQr02CbaTransformer()
    plan = transformer.transform(
        [pkg],
        records_map,
        extraction_warnings=[],
        total_pe_path=total_pe_path,
        voltage_type="33kV",
    )
    assert len(plan.station_plans) == 1
    assert plan.station_plans[0].records[0].fl_erms == "CGBG/PPU/G00001"


def test_transformer_33kv_unresolved_fl_raises_value_error(tmp_path: Path) -> None:
    # Empty TOTAL PE.xlsx with no matching PE NO
    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.cell(row=1, column=1, value="PE NO")
    ws.cell(row=1, column=2, value="FL NUMBER")
    wb.save(total_pe_path)
    wb.close()

    pkg = _make_dummy_package("THUNDER", "05. MAY", "01-05-2026", 42)
    data = TestsheetData(
        substation_number=42,
        substation_name_erms="PPU UNKNOWN",
        fl_erms="",
        fl_site="",
        date_str="01-05-2026",
    )
    records_map = {get_package_key(pkg): [data]}

    transformer = UpdateQr02CbaTransformer()
    with pytest.raises(
        ValueError,
        match=r"Cannot resolve Functional Location for substation 42 \(PPU UNKNOWN\) from testsheet or TOTAL PE\.xlsx",
    ):
        transformer.transform(
            [pkg],
            records_map,
            extraction_warnings=[],
            total_pe_path=total_pe_path,
            voltage_type="33kV",
        )


# =========================================================================
# Seam 3: Qr02Cba33kVTransaction & Factory Dispatch
# =========================================================================

def test_create_qr02_transaction_dispatch_11kv(tmp_path: Path) -> None:
    from src.master.qr02 import (
        LocalExcelQr02Transaction,
        create_qr02_transaction,
    )
    cba_path = tmp_path / "dummy_cba.xlsx"
    tx = create_qr02_transaction(cba_path, voltage_type="11kV")
    assert isinstance(tx, LocalExcelQr02Transaction)
    assert not hasattr(tx, "cycle") or tx.cycle is None or isinstance(tx, LocalExcelQr02Transaction)


def test_create_qr02_transaction_dispatch_33kv(tmp_path: Path) -> None:
    from src.master.qr02 import (
        Qr02Cba33kVTransaction,
        create_qr02_transaction,
    )
    cba_path = tmp_path / "dummy_cba.xlsx"
    tx = create_qr02_transaction(cba_path, voltage_type="33kV", cycle=4, vendor="EET")
    assert isinstance(tx, Qr02Cba33kVTransaction)
    assert tx.cycle == 4
    assert tx.vendor == "EET"


def test_local_excel_qr02_repository_dispatches_33kv(tmp_path: Path) -> None:
    from src.master.qr02 import (
        LocalExcelQr02Repository,
        Qr02Cba33kVTransaction,
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    repo = LocalExcelQr02Repository(
        storage=storage,
        station="THUNDER",
        year="2026",
        voltage_type="33kV",
        cycle=4,
        vendor="EET",
    )
    tx = repo.transaction()
    assert isinstance(tx, Qr02Cba33kVTransaction)
    assert tx.cycle == 4
    assert tx.vendor == "EET"


def _create_synthetic_750_39_wb(cba_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "QR02 CBA"

    # Row 1: Title/Metadata
    ws.cell(row=1, column=1, value="CONTRACT 750-39 MASTER")

    # Row 2: Headers
    ws.cell(row=2, column=7, value="FUNCTIONAL LOCATION")  # Col G
    ws.cell(row=2, column=8, value="SUBSTATION NAME")      # Col H
    ws.cell(row=2, column=9, value="TYPE")                 # Col I
    ws.cell(row=2, column=10, value="SYSTEM")              # Col J
    ws.cell(row=2, column=11, value="CYCLE 1 DATE")        # Col K
    ws.cell(row=2, column=12, value="CYCLE 1 VENDOR")      # Col L
    ws.cell(row=2, column=13, value="CYCLE 2 DATE")        # Col M
    ws.cell(row=2, column=14, value="CYCLE 2 VENDOR")      # Col N
    ws.cell(row=2, column=15, value="CYCLE 3 DATE")        # Col O
    ws.cell(row=2, column=16, value="CYCLE 3 VENDOR")      # Col P
    ws.cell(row=2, column=17, value="CYCLE 4 DATE")        # Col Q
    ws.cell(row=2, column=18, value="CYCLE 4 VENDOR")      # Col R

    # Row 3: Existing 33kV substation record
    ws.cell(row=3, column=7, value="CGBG/PPU/G00001")
    ws.cell(row=3, column=8, value="PPU CHEROH")
    ws.cell(row=3, column=9, value="PPU")
    ws.cell(row=3, column=10, value="33/11")
    ws.cell(row=3, column=11, value="2023-01-15")
    ws.cell(row=3, column=12, value="VENDOR_C1")
    ws.cell(row=3, column=13, value="2024-01-15")
    ws.cell(row=3, column=14, value="VENDOR_C2")
    ws.cell(row=3, column=15, value="2025-01-15")
    ws.cell(row=3, column=16, value="VENDOR_C3")

    # Row 3 other columns that should be untouched:
    ws.cell(row=3, column=4, value="PRESERVED_COL_D")
    ws.cell(row=3, column=5, value="PRESERVED_COL_E")

    wb.save(cba_path)
    wb.close()


def test_qr02_33kv_transaction_exact_fl_match_updates_cycle4(tmp_path: Path) -> None:
    from src.master.qr02 import Qr02Cba33kVTransaction

    cba_path = tmp_path / "test_750_39.xlsx"
    _create_synthetic_750_39_wb(cba_path)

    rec = TestsheetData(
        substation_number=1,
        substation_name_erms="PPU CHEROH",
        fl_erms="CGBG/PPU/G00001",
        date_str="01-05-2026",
        cycle_1=datetime(2026, 5, 1, 0, 0, 0),
    )

    tx = Qr02Cba33kVTransaction(cba_path, cycle=4, vendor="EET")
    with tx:
        count = tx.upsert_qr02_cba_records([rec])
        assert count == 1

    wb_read = openpyxl.load_workbook(cba_path)
    ws_read = wb_read["QR02 CBA"]

    # Existing metadata preserved
    assert ws_read.cell(row=3, column=7).value == "CGBG/PPU/G00001"
    assert ws_read.cell(row=3, column=8).value == "PPU CHEROH"
    assert ws_read.cell(row=3, column=9).value == "PPU"
    assert ws_read.cell(row=3, column=10).value == "33/11"

    # Prior cycles K-P preserved
    assert str(ws_read.cell(row=3, column=11).value).startswith("2023-01-15")
    assert ws_read.cell(row=3, column=12).value == "VENDOR_C1"
    assert str(ws_read.cell(row=3, column=13).value).startswith("2024-01-15")
    assert ws_read.cell(row=3, column=14).value == "VENDOR_C2"
    assert str(ws_read.cell(row=3, column=15).value).startswith("2025-01-15")
    assert ws_read.cell(row=3, column=16).value == "VENDOR_C3"

    # Cycle 4 (Cols Q & R) updated
    assert ws_read.cell(row=3, column=17).value in (
        datetime(2026, 5, 1, 0, 0, 0),
        datetime(2026, 5, 1, 0, 0, 0).date(),
        "2026-05-01 00:00:00",
        "2026-05-01",
    )
    assert ws_read.cell(row=3, column=18).value == "EET"

    # Preserved columns D & E untouched
    assert ws_read.cell(row=3, column=4).value == "PRESERVED_COL_D"
    assert ws_read.cell(row=3, column=5).value == "PRESERVED_COL_E"

    wb_read.close()


def test_qr02_33kv_transaction_unmatched_fl_appends_new_row(tmp_path: Path) -> None:
    from src.master.qr02 import Qr02Cba33kVTransaction

    cba_path = tmp_path / "test_750_39.xlsx"
    _create_synthetic_750_39_wb(cba_path)

    rec = TestsheetData(
        substation_number=2,
        substation_name_erms="PPU BENTONG NEW",
        substation_name_site="PPU BENTONG NEW",
        fl_erms="CBTG/PPU/G00002",
        substation_type="PPU",
        date_str="15-06-2026",
        cycle_1=datetime(2026, 6, 15, 0, 0, 0),
    )

    tx = Qr02Cba33kVTransaction(cba_path, cycle=4, vendor="EET")
    with tx:
        count = tx.upsert_qr02_cba_records([rec])
        assert count == 1

    wb_read = openpyxl.load_workbook(cba_path)
    ws_read = wb_read["QR02 CBA"]

    # Target row should be row 4 (appended)
    assert ws_read.cell(row=4, column=7).value == "CBTG/PPU/G00002"
    assert ws_read.cell(row=4, column=8).value == "PPU BENTONG NEW"
    assert ws_read.cell(row=4, column=9).value == "PPU"
    assert ws_read.cell(row=4, column=10).value == "33/11"

    # Prior cycles K-P should be empty
    assert ws_read.cell(row=4, column=11).value is None
    assert ws_read.cell(row=4, column=12).value is None

    # Cycle 4 (Cols Q & R) populated
    assert ws_read.cell(row=4, column=17).value in (
        datetime(2026, 6, 15, 0, 0, 0),
        datetime(2026, 6, 15, 0, 0, 0).date(),
        "2026-06-15 00:00:00",
        "2026-06-15",
    )
    assert ws_read.cell(row=4, column=18).value == "EET"

    # Column protection: GPS / Building / Site columns strictly NOT written
    # Col 11 (Site Name in 11kV) is Cycle 1 Date in 33kV (empty for new row)
    # Col 12 (GPS in 11kV) is Cycle 1 Vendor in 33kV (empty for new row)
    # Col 14 (Building Type in 11kV) is Cycle 2 Vendor in 33kV (empty for new row)
    assert ws_read.cell(row=4, column=4).value is None
    assert ws_read.cell(row=4, column=5).value is None
    assert ws_read.cell(row=4, column=6).value is None

    wb_read.close()


def test_qr02_33kv_transaction_custom_cycle(tmp_path: Path) -> None:
    from src.master.qr02 import Qr02Cba33kVTransaction

    cba_path = tmp_path / "test_750_39.xlsx"
    _create_synthetic_750_39_wb(cba_path)

    rec = TestsheetData(
        substation_number=1,
        substation_name_erms="PPU CHEROH",
        fl_erms="CGBG/PPU/G00001",
        date_str="20-03-2024",
        cycle_1=datetime(2024, 3, 20, 0, 0, 0),
    )

    # Update Cycle 2 explicitly
    tx = Qr02Cba33kVTransaction(cba_path, cycle=2, vendor="CUSTOM_VENDOR")
    with tx:
        count = tx.upsert_qr02_cba_records([rec])
        assert count == 1

    wb_read = openpyxl.load_workbook(cba_path)
    ws_read = wb_read["QR02 CBA"]

    # Cycle 2 is Col M (13) and Col N (14)
    assert ws_read.cell(row=3, column=13).value in (
        datetime(2024, 3, 20, 0, 0, 0),
        datetime(2024, 3, 20, 0, 0, 0).date(),
        "2024-03-20 00:00:00",
        "2024-03-20",
    )
    assert ws_read.cell(row=3, column=14).value == "CUSTOM_VENDOR"
    wb_read.close()


def test_qr02_33kv_atomic_rollback_on_error(tmp_path: Path) -> None:
    from src.master.qr02 import Qr02Cba33kVTransaction

    cba_path = tmp_path / "test_750_39.xlsx"
    _create_synthetic_750_39_wb(cba_path)

    rec = TestsheetData(
        substation_number=1,
        substation_name_erms="PPU CHEROH",
        fl_erms="CGBG/PPU/G00001",
        date_str="01-05-2026",
    )

    with pytest.raises(RuntimeError, match="Simulated crash"):
        with Qr02Cba33kVTransaction(cba_path, cycle=4, vendor="EET") as tx:
            tx.upsert_qr02_cba_records([rec])
            raise RuntimeError("Simulated crash")

    # Workbook on disk should NOT be modified
    wb_read = openpyxl.load_workbook(cba_path)
    ws_read = wb_read["QR02 CBA"]
    assert ws_read.cell(row=3, column=17).value is None
    assert ws_read.cell(row=3, column=18).value is None
    wb_read.close()


# =========================================================================
# Seam 4: MasterQr03DefectRepository 750-39 Defect Verification
# =========================================================================

def test_master_qr03_defect_repository_compatibility_with_750_39(tmp_path: Path) -> None:
    from src.quick_report.defects import MasterQr03DefectRepository

    engr_dir = tmp_path / "PYTHON" / "ENGR FROM DRIVE"
    engr_dir.mkdir(parents=True)
    cba_path = engr_dir / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"

    wb = openpyxl.Workbook()
    # Sheet 1: QR03 CBA (CBM defects)
    ws_cbm = wb.active
    ws_cbm.title = "QR03 CBA"
    ws_cbm.append([
        "FUNCTIONAL LOCATION",
        "DEFECT FROM",
        "EQUIPMENT",
        "EQUIPMENT ID",
        "DEFECT AREA",
        "US READING",
        "US CHAR",
        "ADDITIONAL REMARKS",
    ])
    ws_cbm.append([
        "CGBG/PPU/G00001",
        "US",
        "SWITCHGEAR",
        "CB 1",
        "CABLE TERMINATION",
        "18",
        "Tracking",
        "Audible hiss",
    ])

    # Sheet 2: QR03 VI (Visual Inspection defects)
    ws_vi = wb.create_sheet("QR03 VI")
    ws_vi.append([
        "FUNCTIONAL LOCATION",
        "EQUIPMENT",
        "DEFECT AREA",
        "ADDITIONAL REMARKS",
        "REPORT BY",
    ])
    ws_vi.append([
        "CGBG/PPU/G00001",
        "SWITCHGEAR",
        "BREAKER",
        "Rusty door hinge",
        "EET",
    ])
    # Non-EET row that should be ignored
    ws_vi.append([
        "CGBG/PPU/G00001",
        "TRANSFORMER",
        "BODY",
        "Non-EET finding",
        "OTHER_VENDOR",
    ])

    wb.save(cba_path)
    wb.close()

    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    repo = MasterQr03DefectRepository(storage=storage, voltage_type="33kV")

    # Fetch CBM defects
    cbm_defects = repo.fetch_cbm_defects("CGBG/PPU/G00001", station="THUNDER")
    assert len(cbm_defects) == 1
    assert cbm_defects[0].technology == "US"
    assert cbm_defects[0].equipment == "SWITCHGEAR"
    assert cbm_defects[0].equipment_id == "CB 1"
    assert cbm_defects[0].defect_area == "CABLE TERMINATION"
    assert cbm_defects[0].us_reading == "18"
    assert cbm_defects[0].us_char == "TRACKING"
    assert cbm_defects[0].additional_remarks == "Audible hiss"

    # Fetch VI defects (filtered to REPORT BY == 'EET')
    vi_defects = repo.fetch_vi_defects("CGBG/PPU/G00001", station="THUNDER")
    assert len(vi_defects) == 1
    assert vi_defects[0].equipment == "SWITCHGEAR"
    assert vi_defects[0].defect_area == "BREAKER"
    assert vi_defects[0].additional_remarks == "Rusty door hinge"


