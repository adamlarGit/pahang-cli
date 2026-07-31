"""Granular component unit tests for Update QR02 CBA 6-stage ETL pipeline in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.workflows.models import PopulateMode, UpdateQr02CbaRequest
from src.workflows.update_qr02_cba import (
    UpdateQr02CbaFilter,
    UpdateQr02CbaPreflightGuard,
    UpdateQr02CbaTransformer,
    get_package_key,
)


def _make_dummy_package(
    station: str = "RAUB",
    month: str = "01. MAY",
    date_str: str = "01-05-2026",
    sub_num: int = 1,
    testsheet_filename: str = "001. SSU CHEROH.xlsx",
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


def test_get_package_key_formatting() -> None:
    pkg = _make_dummy_package("KUANTAN", "02. JUNE", "15-06-2026")
    key = get_package_key(pkg)
    assert key == "KUANTAN/02. JUNE/15-06-2026"


def test_filter_all_mode() -> None:
    pkg1 = _make_dummy_package("RAUB", "01. MAY", "01-05-2026")
    pkg2 = _make_dummy_package("KUANTAN", "02. JUNE", "15-06-2026")
    packages = [pkg1, pkg2]

    filter_stage = UpdateQr02CbaFilter()
    request = UpdateQr02CbaRequest(mode=PopulateMode.ALL)

    result = filter_stage.filter(packages, request, history={})
    assert len(result) == 2
    assert result == packages


def test_filter_specific_mode_matching() -> None:
    pkg1 = _make_dummy_package("RAUB", "01. MAY", "01-05-2026")
    pkg2 = _make_dummy_package("KUANTAN", "02. JUNE", "15-06-2026")
    packages = [pkg1, pkg2]

    filter_stage = UpdateQr02CbaFilter()
    request = UpdateQr02CbaRequest(
        mode=PopulateMode.SPECIFIC_FOLDERS,
        target_package_names=("15-06-2026",),
    )

    result = filter_stage.filter(packages, request, history={})
    assert len(result) == 1
    assert result[0].station == "KUANTAN"


def test_filter_auto_mode_skips_history() -> None:
    pkg1 = _make_dummy_package("RAUB", "01. MAY", "01-05-2026")
    pkg2 = _make_dummy_package("KUANTAN", "02. JUNE", "15-06-2026")
    packages = [pkg1, pkg2]

    history = {"RAUB/01. MAY/01-05-2026": {"last_processed": "2026-05-01"}}

    filter_stage = UpdateQr02CbaFilter()
    request = UpdateQr02CbaRequest(mode=PopulateMode.AUTO)

    result = filter_stage.filter(packages, request, history=history)
    assert len(result) == 1
    assert result[0].station == "KUANTAN"


def test_transformer_groups_by_station() -> None:
    pkg1 = _make_dummy_package("RAUB", "01. MAY", "01-05-2026", 1)
    pkg2 = _make_dummy_package("RAUB", "01. MAY", "02-05-2026", 2)
    pkg3 = _make_dummy_package("KUANTAN", "02. JUNE", "15-06-2026", 1)

    data1 = TestsheetData(substation_number=1, substation_name_erms="SSU CHEROH", fl_erms="CRAU-S001")
    data2 = TestsheetData(substation_number=2, substation_name_erms="SSU BENTA", fl_erms="CRAU-S002")
    data3 = TestsheetData(substation_number=1, substation_name_erms="PE KUANTAN", fl_erms="CKTN-S001")

    records_map = {
        get_package_key(pkg1): [data1],
        get_package_key(pkg2): [data2],
        get_package_key(pkg3): [data3],
    }

    transformer = UpdateQr02CbaTransformer()
    plan = transformer.transform([pkg1, pkg2, pkg3], records_map, extraction_warnings=["warn1"])

    assert len(plan.station_plans) == 2
    assert plan.warnings == ["warn1"]

    raub_plan = next(sp for sp in plan.station_plans if sp.station == "RAUB")
    assert len(raub_plan.packages) == 2
    assert len(raub_plan.records) == 2

    ktn_plan = next(sp for sp in plan.station_plans if sp.station == "KUANTAN")
    assert len(ktn_plan.packages) == 1
    assert len(ktn_plan.records) == 1


def test_preflight_guard_missing_workbook_raises_file_not_found(tmp_path: Path) -> None:
    from src.project.environment import ProjectEnvironment
    from src.project.models import ProjectMetadata
    from src.project.storage import LocalWorkspaceStorage

    meta = ProjectMetadata(
        key="pahang_2026",
        name="Pahang 2026",
        po_number="PO123",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR",),
        base_path=str(tmp_path),
    )
    env = ProjectEnvironment(metadata=meta, storage=LocalWorkspaceStorage(tmp_path))

    guard = UpdateQr02CbaPreflightGuard()
    with pytest.raises(FileNotFoundError, match="Target QR02 CBA workbook not found"):
        guard.validate(env, station="RAUB", year="2026")
