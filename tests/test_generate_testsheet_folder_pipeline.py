"""Unit tests for the 6-stage ETL pipeline for TESTSHEET folder generation (Ticket 088)."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.generate_testsheet_folder import (
    GenerateTestsheetFolderAuditor,
    GenerateTestsheetFolderExtractionData,
    GenerateTestsheetFolderExtractor,
    GenerateTestsheetFolderFilter,
    GenerateTestsheetFolderLoader,
    GenerateTestsheetFolderPreflightGuard,
    GenerateTestsheetFolderStructureWorkflow,
    GenerateTestsheetFolderTransformer,
)
from src.workflows.models import (
    DateFolderPlan,
    GenerateTestsheetFolderPlan,
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
)


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    """Fixture providing a real ProjectEnvironment backed by a temporary directory."""
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
# 1. PreflightGuard Tests
# ==============================================================================


def test_preflight_guard_success(mock_env: ProjectEnvironment):
    """Preflight guard succeeds and ensures testsheet_dir exists when valid request is provided."""
    guard = GenerateTestsheetFolderPreflightGuard()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    guard.validate(mock_env, req)
    assert mock_env.storage.get_testsheet_dir().exists()


def test_preflight_guard_empty_station(mock_env: ProjectEnvironment):
    """Preflight guard raises ValueError when station is empty or whitespace."""
    guard = GenerateTestsheetFolderPreflightGuard()
    req = GenerateTestsheetFolderRequest(
        station="   ",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Ss]tation"):
        guard.validate(mock_env, req)


def test_preflight_guard_empty_month(mock_env: ProjectEnvironment):
    """Preflight guard raises ValueError when month is empty or whitespace."""
    guard = GenerateTestsheetFolderPreflightGuard()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="",
        target_dates=("10-08-2026",),
    )
    with pytest.raises(ValueError, match="[Mm]onth"):
        guard.validate(mock_env, req)


def test_preflight_guard_empty_target_dates(mock_env: ProjectEnvironment):
    """Preflight guard raises ValueError when target_dates is empty."""
    guard = GenerateTestsheetFolderPreflightGuard()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=(),
    )
    with pytest.raises(ValueError, match="[Dd]ate"):
        guard.validate(mock_env, req)


# ==============================================================================
# 2. Extractor Tests
# ==============================================================================


def test_extractor_discovers_hierarchy(mock_env: ProjectEnvironment):
    """Extractor discovers existing stations, months under station, and dates under station/month."""
    testsheet_dir = mock_env.storage.get_testsheet_dir()
    month_dir = testsheet_dir / "KUANTAN" / "01. AUGUST"
    (month_dir / "10-08-2026").mkdir(parents=True, exist_ok=True)
    (month_dir / "11-08-2026").mkdir(parents=True, exist_ok=True)
    (testsheet_dir / "TEMERLOH" / "01. JULY").mkdir(parents=True, exist_ok=True)

    extractor = GenerateTestsheetFolderExtractor()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("12-08-2026",),
    )
    data = extractor.extract(mock_env, req)

    assert isinstance(data, (GenerateTestsheetFolderExtractionData, dict))
    if isinstance(data, GenerateTestsheetFolderExtractionData):
        assert set(data.existing_stations) == {"KUANTAN", "TEMERLOH"}
        assert list(data.existing_months) == ["01. AUGUST"]
        assert set(data.existing_dates) == {"10-08-2026", "11-08-2026"}
    else:
        assert set(data["existing_stations"]) == {"KUANTAN", "TEMERLOH"}
        assert list(data["existing_months"]) == ["01. AUGUST"]
        assert set(data["existing_dates"]) == {"10-08-2026", "11-08-2026"}


def test_extractor_empty_hierarchy(mock_env: ProjectEnvironment):
    """Extractor handles non-existent station and month gracefully."""
    extractor = GenerateTestsheetFolderExtractor()
    req = GenerateTestsheetFolderRequest(
        station="NON_EXISTENT",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    data = extractor.extract(mock_env, req)
    if isinstance(data, GenerateTestsheetFolderExtractionData):
        assert data.existing_stations == ()
        assert data.existing_months == ()
        assert data.existing_dates == ()
    else:
        assert data["existing_stations"] == ()
        assert data["existing_months"] == ()
        assert data["existing_dates"] == ()


# ==============================================================================
# 3. Filter Tests
# ==============================================================================


def test_filter_normalizes_and_deduplicates():
    """Filter normalizes various date formats, deduplicates entries, and preserves order."""
    filter_stage = GenerateTestsheetFolderFilter()
    target_dates = ["10/08/2026", "2026-08-11", "10-08-2026", "12-08-2026"]
    valid_dates, warnings = filter_stage.filter_dates(target_dates)

    assert valid_dates == ("10-08-2026", "11-08-2026", "12-08-2026")
    assert warnings == ()


def test_filter_records_warnings_for_invalid_dates_best_effort():
    """Filter records warnings for invalid dates while keeping valid ones."""
    filter_stage = GenerateTestsheetFolderFilter()
    target_dates = ["10-08-2026", "invalid-date", "32-13-2026", "11-08-2026"]
    valid_dates, warnings = filter_stage.filter_dates(target_dates)

    assert valid_dates == ("10-08-2026", "11-08-2026")
    assert len(warnings) == 2
    assert any("invalid-date" in w for w in warnings)
    assert any("32-13-2026" in w for w in warnings)


def test_filter_raises_if_all_dates_invalid():
    """Filter raises ValueError when all supplied dates are invalid."""
    filter_stage = GenerateTestsheetFolderFilter()
    target_dates = ["invalid-1", "99-99-9999", "abc"]
    with pytest.raises(ValueError, match="[Nn]o valid date"):
        filter_stage.filter_dates(target_dates)


# ==============================================================================
# 4. Transformer Tests
# ==============================================================================


def test_transformer_builds_plan(mock_env: ProjectEnvironment):
    """Transformer constructs a GenerateTestsheetFolderPlan with exact path hierarchy."""
    transformer = GenerateTestsheetFolderTransformer()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026", "11-08-2026"),
    )
    plan = transformer.transform(mock_env, req, ("10-08-2026", "11-08-2026"))

    assert plan.station == "KUANTAN"
    assert plan.month == "01. AUGUST"
    expected_month_dir = mock_env.storage.get_testsheet_dir() / "KUANTAN" / "01. AUGUST"
    assert plan.month_dir == expected_month_dir
    assert len(plan.date_plans) == 2

    # Verify first date plan hierarchy
    dp1 = plan.date_plans[0]
    assert dp1.date_str == "10-08-2026"
    assert dp1.date_dir == expected_month_dir / "10-08-2026"
    assert dp1.unsorted_dir == expected_month_dir / "10-08-2026" / "UNSORTED RAW DATA"
    assert dp1.tech_dirs == (
        dp1.unsorted_dir / "DG",
        dp1.unsorted_dir / "IR",
        dp1.unsorted_dir / "US+TEV",
    )


def test_transformer_normalizes_month_string(mock_env: ProjectEnvironment):
    """Transformer normalizes month string e.g. 'AUGUST' -> '08. AUGUST'."""
    transformer = GenerateTestsheetFolderTransformer()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="AUGUST",
        target_dates=("10-08-2026",),
    )
    plan = transformer.transform(mock_env, req, ("10-08-2026",))
    assert plan.month == "08. AUGUST"
    assert plan.month_dir.name == "08. AUGUST"


# ==============================================================================
# 5. Loader Tests
# ==============================================================================


def test_loader_creates_directories_and_tracks_new_vs_existing(mock_env: ProjectEnvironment):
    """Loader provisions missing directories and correctly identifies created vs existing."""
    transformer = GenerateTestsheetFolderTransformer()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    plan = transformer.transform(mock_env, req, ("10-08-2026",))

    # Pre-create month_dir to test existing detection
    plan.month_dir.mkdir(parents=True, exist_ok=True)

    loader = GenerateTestsheetFolderLoader()
    created_dirs, existing_dirs = loader.load(plan)

    assert plan.month_dir in existing_dirs
    assert plan.date_plans[0].date_dir in created_dirs
    assert plan.date_plans[0].unsorted_dir in created_dirs
    for tech_dir in plan.date_plans[0].tech_dirs:
        assert tech_dir in created_dirs
        assert tech_dir.exists()

    # Second run (idempotency): all should be existing, none created
    created_dirs2, existing_dirs2 = loader.load(plan)
    assert len(created_dirs2) == 0
    assert len(existing_dirs2) == len(plan.all_directories_to_ensure)


# ==============================================================================
# 6. Auditor Tests
# ==============================================================================


def test_auditor_verifies_all_directories_present(mock_env: ProjectEnvironment):
    """Auditor succeeds when all planned directories physically exist on disk."""
    transformer = GenerateTestsheetFolderTransformer()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    plan = transformer.transform(mock_env, req, ("10-08-2026",))

    loader = GenerateTestsheetFolderLoader()
    created_dirs, existing_dirs = loader.load(plan)

    auditor = GenerateTestsheetFolderAuditor()
    result = auditor.audit(plan, created_dirs, existing_dirs, warnings=("Warning 1",))

    assert result.station == "KUANTAN"
    assert result.month == "01. AUGUST"
    assert result.created_directories == created_dirs
    assert result.existing_directories == existing_dirs
    assert result.total_dates_processed == 1
    assert result.warnings == ("Warning 1",)
    assert result.errors == ()
    assert result.is_successful is True


def test_auditor_flags_missing_directory_errors(mock_env: ProjectEnvironment):
    """Auditor reports errors if any planned directory does not physically exist on disk."""
    transformer = GenerateTestsheetFolderTransformer()
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )
    plan = transformer.transform(mock_env, req, ("10-08-2026",))

    # Do not call loader, directories don't exist
    auditor = GenerateTestsheetFolderAuditor()
    result = auditor.audit(plan, created_dirs=(), existing_dirs=(), warnings=())

    assert len(result.errors) > 0
    assert result.is_successful is False


# ==============================================================================
# 7. Workflow End-to-End & Seam Tests
# ==============================================================================


def test_workflow_orchestration_end_to_end(mock_env: ProjectEnvironment):
    """Workflow coordinates all 6 stages and emits progress events."""
    events: list[str] = []
    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026", "11-08-2026"),
        progress_sink=events.append,
    )

    workflow = GenerateTestsheetFolderStructureWorkflow()
    result = workflow.execute(mock_env, req)

    assert result.is_successful is True
    assert result.station == "KUANTAN"
    assert result.month == "01. AUGUST"
    assert result.total_dates_processed == 2
    assert len(events) > 0

    # Verify physical directories created
    testsheet_dir = mock_env.storage.get_testsheet_dir()
    for date_str in ("10-08-2026", "11-08-2026"):
        date_dir = testsheet_dir / "KUANTAN" / "01. AUGUST" / date_str
        assert (date_dir / "UNSORTED RAW DATA" / "DG").is_dir()
        assert (date_dir / "UNSORTED RAW DATA" / "IR").is_dir()
        assert (date_dir / "UNSORTED RAW DATA" / "US+TEV").is_dir()


def test_workflow_dependency_injection_seam(mock_env: ProjectEnvironment):
    """Workflow correctly calls injected stages."""
    guard = MagicMock(spec=GenerateTestsheetFolderPreflightGuard)
    extractor = MagicMock(spec=GenerateTestsheetFolderExtractor)
    filter_stage = MagicMock(spec=GenerateTestsheetFolderFilter)
    transformer = MagicMock(spec=GenerateTestsheetFolderTransformer)
    loader = MagicMock(spec=GenerateTestsheetFolderLoader)
    auditor = MagicMock(spec=GenerateTestsheetFolderAuditor)

    filter_stage.filter_dates.return_value = (("10-08-2026",), ("Warning 1",))
    plan = GenerateTestsheetFolderPlan(
        station="KUANTAN",
        month="01. AUGUST",
        month_dir=mock_env.storage.get_testsheet_dir() / "KUANTAN" / "01. AUGUST",
    )
    transformer.transform.return_value = plan
    loader.load.return_value = ((Path("/dummy/dir"),), ())
    auditor.audit.return_value = GenerateTestsheetFolderResult(
        station="KUANTAN",
        month="01. AUGUST",
        created_directories=(Path("/dummy/dir"),),
        total_dates_processed=1,
    )

    workflow = GenerateTestsheetFolderStructureWorkflow(
        preflight_guard=guard,
        extractor=extractor,
        filter_stage=filter_stage,
        transformer=transformer,
        loader=loader,
        auditor=auditor,
    )

    req = GenerateTestsheetFolderRequest(
        station="KUANTAN",
        month="01. AUGUST",
        target_dates=("10-08-2026",),
    )

    result = workflow.execute(mock_env, req)

    guard.validate.assert_called_once_with(mock_env, req)
    extractor.extract.assert_called_once_with(mock_env, req)
    filter_stage.filter_dates.assert_called_once_with(("10-08-2026",))
    transformer.transform.assert_called_once_with(mock_env, req, ("10-08-2026",))
    loader.load.assert_called_once_with(plan)
    auditor.audit.assert_called_once_with(
        plan, (Path("/dummy/dir"),), (), warnings=("Warning 1",)
    )
    assert result.station == "KUANTAN"
