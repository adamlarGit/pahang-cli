"""Unit tests for TESTSHEET folder generation domain models and plans (Ticket 087)."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest

from src.workflows.models import (
    DateFolderPlan,
    GenerateTestsheetFolderPlan,
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
)


def test_generate_testsheet_folder_request_defaults():
    """Verify default values and basic initialization of GenerateTestsheetFolderRequest."""
    req = GenerateTestsheetFolderRequest(station="KUANTAN", month="01. AUGUST")
    assert req.station == "KUANTAN"
    assert req.month == "01. AUGUST"
    assert req.target_dates == ()
    assert req.progress_sink is None


def test_generate_testsheet_folder_request_custom_values():
    """Verify custom values initialization and callable progress_sink."""
    events: list[str] = []

    def sink(msg: str) -> None:
        events.append(msg)

    req = GenerateTestsheetFolderRequest(
        station="TEMERLOH",
        month="02. SEPTEMBER",
        target_dates=("10-08-2026", "11-08-2026"),
        progress_sink=sink,
    )
    assert req.station == "TEMERLOH"
    assert req.month == "02. SEPTEMBER"
    assert req.target_dates == ("10-08-2026", "11-08-2026")
    assert req.progress_sink is not None
    req.progress_sink("test message")
    assert events == ["test message"]


def test_generate_testsheet_folder_request_immutability():
    """Verify GenerateTestsheetFolderRequest is frozen and immutable."""
    req = GenerateTestsheetFolderRequest(station="KUANTAN", month="01. AUGUST")
    with pytest.raises(FrozenInstanceError):
        req.station = "ROMPIN"  # type: ignore[misc]


def test_date_folder_plan_properties_and_defaults():
    """Verify DateFolderPlan initialization, defaults, and all_directories property."""
    date_dir = Path("/testsheet/KUANTAN/01. AUGUST/10-08-2026")
    unsorted_dir = date_dir / "UNSORTED RAW DATA"
    dg_dir = unsorted_dir / "DG"
    ir_dir = unsorted_dir / "IR"
    us_dir = unsorted_dir / "US+TEV"

    plan = DateFolderPlan(
        date_str="10-08-2026",
        date_dir=date_dir,
        unsorted_dir=unsorted_dir,
        tech_dirs=(dg_dir, ir_dir, us_dir),
    )

    assert plan.date_str == "10-08-2026"
    assert plan.date_dir == date_dir
    assert plan.unsorted_dir == unsorted_dir
    assert plan.tech_dirs == (dg_dir, ir_dir, us_dir)
    assert plan.all_directories == (date_dir, unsorted_dir, dg_dir, ir_dir, us_dir)


def test_date_folder_plan_empty_tech_dirs():
    """Verify DateFolderPlan with default empty tech_dirs."""
    date_dir = Path("/testsheet/KUANTAN/01. AUGUST/10-08-2026")
    unsorted_dir = date_dir / "UNSORTED RAW DATA"

    plan = DateFolderPlan(
        date_str="10-08-2026",
        date_dir=date_dir,
        unsorted_dir=unsorted_dir,
    )
    assert plan.tech_dirs == ()
    assert plan.all_directories == (date_dir, unsorted_dir)


def test_date_folder_plan_immutability():
    """Verify DateFolderPlan is frozen and immutable."""
    plan = DateFolderPlan(
        date_str="10-08-2026",
        date_dir=Path("/date"),
        unsorted_dir=Path("/date/unsorted"),
    )
    with pytest.raises(FrozenInstanceError):
        plan.date_str = "11-08-2026"  # type: ignore[misc]


def test_generate_testsheet_folder_plan_empty_date_plans():
    """Verify GenerateTestsheetFolderPlan with empty date_plans."""
    month_dir = Path("/testsheet/KUANTAN/01. AUGUST")
    plan = GenerateTestsheetFolderPlan(
        station="KUANTAN",
        month="01. AUGUST",
        month_dir=month_dir,
    )
    assert plan.station == "KUANTAN"
    assert plan.month == "01. AUGUST"
    assert plan.month_dir == month_dir
    assert plan.date_plans == ()
    assert plan.all_directories_to_ensure == (month_dir,)


def test_generate_testsheet_folder_plan_all_directories_to_ensure():
    """Verify GenerateTestsheetFolderPlan flattens month_dir and all date plans."""
    month_dir = Path("/testsheet/KUANTAN/01. AUGUST")

    date1_dir = month_dir / "10-08-2026"
    unsorted1_dir = date1_dir / "UNSORTED RAW DATA"
    dg1 = unsorted1_dir / "DG"
    ir1 = unsorted1_dir / "IR"
    us1 = unsorted1_dir / "US+TEV"

    date2_dir = month_dir / "11-08-2026"
    unsorted2_dir = date2_dir / "UNSORTED RAW DATA"
    dg2 = unsorted2_dir / "DG"
    ir2 = unsorted2_dir / "IR"
    us2 = unsorted2_dir / "US+TEV"

    dp1 = DateFolderPlan("10-08-2026", date1_dir, unsorted1_dir, (dg1, ir1, us1))
    dp2 = DateFolderPlan("11-08-2026", date2_dir, unsorted2_dir, (dg2, ir2, us2))

    plan = GenerateTestsheetFolderPlan(
        station="KUANTAN",
        month="01. AUGUST",
        month_dir=month_dir,
        date_plans=(dp1, dp2),
    )

    expected = (
        month_dir,
        date1_dir,
        unsorted1_dir,
        dg1,
        ir1,
        us1,
        date2_dir,
        unsorted2_dir,
        dg2,
        ir2,
        us2,
    )
    assert plan.all_directories_to_ensure == expected


def test_generate_testsheet_folder_plan_immutability():
    """Verify GenerateTestsheetFolderPlan is frozen and immutable."""
    plan = GenerateTestsheetFolderPlan(
        station="KUANTAN",
        month="01. AUGUST",
        month_dir=Path("/testsheet/KUANTAN/01. AUGUST"),
    )
    with pytest.raises(FrozenInstanceError):
        plan.station = "PEKAN"  # type: ignore[misc]


def test_generate_testsheet_folder_result_defaults():
    """Verify default values and helper properties on GenerateTestsheetFolderResult."""
    res = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
    )
    assert res.station == "KUANTAN"
    assert res.month == "01. AUGUST"
    assert res.created_directories == ()
    assert res.existing_directories == ()
    assert res.total_dates_processed == 0
    assert res.warnings == ()
    assert res.errors == ()
    assert res.created_count == 0
    assert res.is_successful is False  # total_dates_processed == 0


def test_generate_testsheet_folder_result_success():
    """Verify is_successful is True when no errors and total_dates_processed > 0."""
    dir1 = Path("/testsheet/KUANTAN/01. AUGUST/10-08-2026")
    dir2 = Path("/testsheet/KUANTAN/01. AUGUST/10-08-2026/UNSORTED RAW DATA")

    res = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
        created_directories=(dir1, dir2),
        existing_directories=(Path("/testsheet/KUANTAN/01. AUGUST"),),
        total_dates_processed=1,
        warnings=("Some non-fatal warning",),
        errors=(),
    )
    assert res.created_count == 2
    assert res.is_successful is True


def test_generate_testsheet_folder_result_failure_with_errors():
    """Verify is_successful is False when errors list is not empty."""
    res = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
        total_dates_processed=2,
        errors=("Failed to create directory due to permission denied",),
    )
    assert res.created_count == 0
    assert res.is_successful is False


def test_generate_testsheet_folder_result_failure_zero_dates_processed():
    """Verify is_successful is False when total_dates_processed == 0 even if no errors."""
    res = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
        total_dates_processed=0,
        errors=(),
    )
    assert res.is_successful is False


def test_generate_testsheet_folder_result_immutability():
    """Verify GenerateTestsheetFolderResult is frozen and immutable."""
    res = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
    )
    with pytest.raises(FrozenInstanceError):
        res.total_dates_processed = 5  # type: ignore[misc]
