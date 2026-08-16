"""Integration tests for Generate TESTSHEET Folder Structure workflow (Ticket 091)."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.models import (
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
)
from src.workflows.service import WorkflowService


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    """Fixture providing an isolated ProjectEnvironment backed by a temporary directory."""
    meta = ProjectMetadata(
        key="pahang_2026_test",
        name="Pahang 2026 Test",
        po_number="PO42289580",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(root_path=tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


# ==============================================================================
# Test 1: Single Date Folder Provisioning
# ==============================================================================


def test_single_date_folder_provisioning(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    """Execute workflow for a single date and verify the complete folder hierarchy on disk."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )

    result: GenerateTestsheetFolderResult = service.run_generate_testsheet_folder(mock_env, request)

    assert result.is_successful is True
    assert result.station == "KUANTAN"
    assert result.month == "01. AUGUST"
    assert result.total_dates_processed == 1
    assert len(result.errors) == 0
    assert result.created_count > 0

    # Assert directory hierarchy on disk
    testsheet_dir = mock_env.storage.get_testsheet_dir()
    date_dir = testsheet_dir / "KUANTAN" / "01. AUGUST" / "10-08-2026"
    unsorted_dir = date_dir / "UNSORTED RAW DATA"

    assert unsorted_dir.exists() and unsorted_dir.is_dir()
    for tech in ("DG", "IR", "US+TEV"):
        tech_dir = unsorted_dir / tech
        assert tech_dir.exists() and tech_dir.is_dir()


# ==============================================================================
# Test 2: Multi-Date Batch Generation
# ==============================================================================


def test_multi_date_batch_generation(mock_env: ProjectEnvironment) -> None:
    """Execute workflow with multiple target dates and verify all hierarchies are created."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("11-08-2026", "12-08-2026"),
    )

    result: GenerateTestsheetFolderResult = service.run_generate_testsheet_folder(mock_env, request)

    assert result.is_successful is True
    assert result.station == "KUANTAN"
    assert result.month == "01. AUGUST"
    assert result.total_dates_processed == 2
    assert len(result.errors) == 0

    testsheet_dir = mock_env.storage.get_testsheet_dir()
    for date_str in ("11-08-2026", "12-08-2026"):
        unsorted_dir = testsheet_dir / "KUANTAN" / "01. AUGUST" / date_str / "UNSORTED RAW DATA"
        assert unsorted_dir.exists() and unsorted_dir.is_dir()
        for tech in ("DG", "IR", "US+TEV"):
            tech_dir = unsorted_dir / tech
            assert tech_dir.exists() and tech_dir.is_dir()


# ==============================================================================
# Test 3: Idempotent Re-Run & Data Preservation
# ==============================================================================


def test_idempotent_rerun_and_data_preservation(mock_env: ProjectEnvironment) -> None:
    """Re-running the workflow preserves existing files and directories without data loss."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )

    # First run
    first_result = service.run_generate_testsheet_folder(mock_env, request)
    assert first_result.is_successful is True
    assert first_result.created_count > 0

    # Place a dummy file in UNSORTED RAW DATA/DG/
    testsheet_dir = mock_env.storage.get_testsheet_dir()
    dummy_file = (
        testsheet_dir / "KUANTAN" / "01. AUGUST" / "10-08-2026" / "UNSORTED RAW DATA" / "DG" / "dummy_photo.jpg"
    )
    dummy_file.write_bytes(b"dummy image content bytes")

    # Second run (idempotent re-run)
    second_result = service.run_generate_testsheet_folder(mock_env, request)

    assert second_result.is_successful is True
    assert second_result.total_dates_processed == 1
    assert second_result.created_count == 0
    assert len(second_result.existing_directories) > 0

    # Assert dummy file is untouched and preserved
    assert dummy_file.exists()
    assert dummy_file.read_bytes() == b"dummy image content bytes"


# ==============================================================================
# Test 4: Invalid Date Best-Effort Filtering
# ==============================================================================


def test_invalid_date_best_effort_filtering(mock_env: ProjectEnvironment) -> None:
    """Workflow processes valid dates and issues warnings for invalid ones without crashing."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026", "invalid-date", "32-13-2026"),
    )

    result = service.run_generate_testsheet_folder(mock_env, request)

    assert result.is_successful is True
    assert result.total_dates_processed == 1
    assert len(result.warnings) == 2
    assert any("invalid-date" in w for w in result.warnings)
    assert any("32-13-2026" in w for w in result.warnings)

    testsheet_dir = mock_env.storage.get_testsheet_dir()
    valid_unsorted = (
        testsheet_dir / "KUANTAN" / "01. AUGUST" / "10-08-2026" / "UNSORTED RAW DATA"
    )
    assert valid_unsorted.exists()

    # Invalid dates should not have directories created
    assert not (testsheet_dir / "KUANTAN" / "01. AUGUST" / "invalid-date").exists()


# ==============================================================================
# Test 5: Preflight Fail-Fast on Empty Inputs
# ==============================================================================


def test_preflight_fail_fast_on_empty_target_dates(mock_env: ProjectEnvironment) -> None:
    """Submitting empty target_dates raises ValueError."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=(),
    )
    with pytest.raises(ValueError, match="[Dd]ate"):
        service.run_generate_testsheet_folder(mock_env, request)


def test_preflight_fail_fast_on_empty_station(mock_env: ProjectEnvironment) -> None:
    """Submitting empty station raises ValueError."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Ss]tation"):
        service.run_generate_testsheet_folder(mock_env, request)

    # Whitespace only
    request_whitespace = GenerateTestsheetFolderRequest(
        station="   ",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Ss]tation"):
        service.run_generate_testsheet_folder(mock_env, request_whitespace)


def test_preflight_fail_fast_on_empty_month(mock_env: ProjectEnvironment) -> None:
    """Submitting empty month raises ValueError."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Mm]onth"):
        service.run_generate_testsheet_folder(mock_env, request)

    # Whitespace only
    request_whitespace = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="   ",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Mm]onth"):
        service.run_generate_testsheet_folder(mock_env, request_whitespace)


# ==============================================================================
# Test 6: All Invalid Dates Fail-Fast
# ==============================================================================


def test_all_invalid_dates_fail_fast(mock_env: ProjectEnvironment) -> None:
    """Submitting only invalid dates raises ValueError with informative message."""
    service = WorkflowService()
    request = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("invalid-1", "invalid-2", "99-99-9999"),
    )
    with pytest.raises(ValueError, match="[Nn]o valid date"):
        service.run_generate_testsheet_folder(mock_env, request)


# ==============================================================================
# Additional E2E Behavior Tests
# ==============================================================================


def test_workflow_service_progress_sink_integration(mock_env: ProjectEnvironment) -> None:
    """WorkflowService forwards progress events through to the caller sink."""
    service = WorkflowService()
    events: list[str] = []

    request = GenerateTestsheetFolderRequest(
        station="PEKAN",
        month="02. FEBRUARY",
        target_dates=("15-02-2026",),
        progress_sink=events.append,
    )

    result = service.run_generate_testsheet_folder(mock_env, request)

    assert result.is_successful is True
    assert len(events) >= 5
    assert any("Generating folder structure for PEKAN / 02. FEBRUARY" in e for e in events)
    assert any("Validating environment" in e for e in events)
    assert any("Completed:" in e for e in events)
