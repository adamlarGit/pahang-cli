"""Generate TESTSHEET Folder Structure Workflow for Pahang CLI.

Implements a 6-stage ETL pipeline to idempotently create and audit:
TESTSHEET/<STATION>/<MONTH>/<DATE>/UNSORTED RAW DATA/ with DG/, IR/, and US+TEV/ subfolders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Sequence

from src.core.normalizers import format_month_folder, normalize_date_str
from src.project.environment import ProjectEnvironment
from src.workflows.models import (
    DateFolderPlan,
    GenerateTestsheetFolderPlan,
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
)


@dataclass(frozen=True)
class GenerateTestsheetFolderExtractionData:
    """Extracted discovery data for existing TESTSHEET hierarchy."""

    existing_stations: tuple[str, ...] = ()
    existing_months: tuple[str, ...] = ()
    existing_dates: tuple[str, ...] = ()


class GenerateTestsheetFolderPreflightGuard:
    """Pre-flight resource guard stage for TESTSHEET folder generation."""

    def validate(
        self, environment: ProjectEnvironment, request: GenerateTestsheetFolderRequest
    ) -> None:
        """Validate environmental preconditions and request inputs."""
        testsheet_dir = environment.storage.get_testsheet_dir()
        environment.storage.ensure_directory(testsheet_dir)

        if not request.station or not request.station.strip():
            raise ValueError("Station name cannot be empty.")

        if not request.month or not request.month.strip():
            raise ValueError("Month name cannot be empty.")

        if not request.target_dates or len(request.target_dates) == 0:
            raise ValueError("Target dates list cannot be empty.")


class GenerateTestsheetFolderExtractor:
    """Discovery extraction stage inspecting existing TESTSHEET folder hierarchy."""

    def extract(
        self, environment: ProjectEnvironment, request: GenerateTestsheetFolderRequest
    ) -> GenerateTestsheetFolderExtractionData:
        """Discover existing station, month, and date folders."""
        testsheet_dir = environment.storage.get_testsheet_dir()

        existing_stations: list[str] = []
        if testsheet_dir.exists() and testsheet_dir.is_dir():
            existing_stations = sorted(
                [p.name for p in testsheet_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
            )

        station_name = request.station.strip()
        station_dir = testsheet_dir / station_name

        existing_months: list[str] = []
        if station_dir.exists() and station_dir.is_dir():
            existing_months = sorted(
                [p.name for p in station_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
            )

        raw_month = request.month.strip()
        formatted_month = format_month_folder(raw_month) or raw_month
        month_dir = station_dir / formatted_month
        if not month_dir.exists() and (station_dir / raw_month).exists():
            month_dir = station_dir / raw_month

        existing_dates: list[str] = []
        if month_dir.exists() and month_dir.is_dir():
            existing_dates = sorted(
                [p.name for p in month_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
            )

        return GenerateTestsheetFolderExtractionData(
            existing_stations=tuple(existing_stations),
            existing_months=tuple(existing_months),
            existing_dates=tuple(existing_dates),
        )


class GenerateTestsheetFolderFilter:
    """Date filtering, normalization, and deduplication stage."""

    CANONICAL_DATE_REGEX = re.compile(r"^(\d{2})-(\d{2})-(\d{4})$")

    def filter_dates(
        self, target_dates: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Normalize, validate, and deduplicate date strings.

        Returns:
            (valid_dates, warnings)

        Raises:
            ValueError: If all dates in target_dates are invalid or empty.
        """
        valid_dates: list[str] = []
        warnings: list[str] = []
        seen: set[str] = set()

        for raw_date in target_dates:
            normalized = normalize_date_str(raw_date)
            match = self.CANONICAL_DATE_REGEX.match(normalized)
            is_valid = False
            if match:
                try:
                    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    datetime(year, month, day)
                    is_valid = True
                except ValueError:
                    is_valid = False

            if not is_valid:
                warnings.append(
                    f"Skipping invalid date entry: '{raw_date}'. Expected canonical DD-MM-YYYY format."
                )
                continue

            if normalized not in seen:
                seen.add(normalized)
                valid_dates.append(normalized)

        if not valid_dates:
            raise ValueError(
                f"No valid dates found in target_dates: {list(target_dates)}. "
                "Ensure date strings are in DD-MM-YYYY or standard date format."
            )

        return tuple(valid_dates), tuple(warnings)


class GenerateTestsheetFolderTransformer:
    """Transformation stage constructing the immutable folder hierarchy execution plan."""

    def transform(
        self,
        environment: ProjectEnvironment,
        request: GenerateTestsheetFolderRequest,
        valid_dates: Sequence[str],
    ) -> GenerateTestsheetFolderPlan:
        """Transform request and valid dates into GenerateTestsheetFolderPlan."""
        station = request.station.strip()
        raw_month = request.month.strip()
        formatted_month = format_month_folder(raw_month) or raw_month

        month_dir = environment.storage.get_testsheet_dir() / station / formatted_month

        date_plans: list[DateFolderPlan] = []
        for date_str in valid_dates:
            date_dir = month_dir / date_str
            unsorted_dir = date_dir / "UNSORTED RAW DATA"
            tech_dirs = (
                unsorted_dir / "DG",
                unsorted_dir / "IR",
                unsorted_dir / "US+TEV",
            )
            date_plans.append(
                DateFolderPlan(
                    date_str=date_str,
                    date_dir=date_dir,
                    unsorted_dir=unsorted_dir,
                    tech_dirs=tech_dirs,
                )
            )

        return GenerateTestsheetFolderPlan(
            station=station,
            month=formatted_month,
            month_dir=month_dir,
            date_plans=tuple(date_plans),
        )


class GenerateTestsheetFolderLoader:
    """Idempotent filesystem loader stage provisioning planned directories."""

    def load(
        self, plan: GenerateTestsheetFolderPlan
    ) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
        """Create planned directories on disk and track newly created vs existing.

        Returns:
            (created_directories, existing_directories)
        """
        created: list[Path] = []
        existing: list[Path] = []

        for directory in plan.all_directories_to_ensure:
            if directory.exists() and directory.is_dir():
                existing.append(directory)
            else:
                directory.mkdir(parents=True, exist_ok=True)
                created.append(directory)

        return tuple(created), tuple(existing)


class GenerateTestsheetFolderAuditor:
    """Disk verification and telemetry auditor stage."""

    def audit(
        self,
        plan: GenerateTestsheetFolderPlan,
        created_dirs: Sequence[Path],
        existing_dirs: Sequence[Path],
        warnings: Sequence[str] = (),
        errors: Sequence[str] = (),
    ) -> GenerateTestsheetFolderResult:
        """Verify physical presence of all planned directories and assemble result."""
        audit_errors: list[str] = list(errors)

        for directory in plan.all_directories_to_ensure:
            if not directory.exists() or not directory.is_dir():
                audit_errors.append(
                    f"Planned directory does not exist after provisioning: {directory}"
                )

        return GenerateTestsheetFolderResult(
            station=plan.station,
            month=plan.month,
            created_directories=tuple(created_dirs),
            existing_directories=tuple(existing_dirs),
            total_dates_processed=len(plan.date_plans),
            warnings=tuple(warnings),
            errors=tuple(audit_errors),
        )


class GenerateTestsheetFolderStructureWorkflow:
    """6-stage ETL workflow for TESTSHEET folder hierarchy generation."""

    def __init__(
        self,
        preflight_guard: GenerateTestsheetFolderPreflightGuard | None = None,
        extractor: GenerateTestsheetFolderExtractor | None = None,
        filter_stage: GenerateTestsheetFolderFilter | None = None,
        transformer: GenerateTestsheetFolderTransformer | None = None,
        loader: GenerateTestsheetFolderLoader | None = None,
        auditor: GenerateTestsheetFolderAuditor | None = None,
    ) -> None:
        self.preflight_guard = preflight_guard or GenerateTestsheetFolderPreflightGuard()
        self.extractor = extractor or GenerateTestsheetFolderExtractor()
        self.filter_stage = filter_stage or GenerateTestsheetFolderFilter()
        self.transformer = transformer or GenerateTestsheetFolderTransformer()
        self.loader = loader or GenerateTestsheetFolderLoader()
        self.auditor = auditor or GenerateTestsheetFolderAuditor()

    def execute(
        self,
        environment: ProjectEnvironment,
        request: GenerateTestsheetFolderRequest,
    ) -> GenerateTestsheetFolderResult:
        """Execute the 6-stage TESTSHEET folder generation workflow."""
        if request.progress_sink:
            request.progress_sink("Validating environment and folder generation request...")

        self.preflight_guard.validate(environment, request)

        if request.progress_sink:
            request.progress_sink(
                f"Extracting existing folder hierarchy for station '{request.station}'..."
            )

        _extraction_data = self.extractor.extract(environment, request)

        if request.progress_sink:
            request.progress_sink(
                f"Filtering and normalizing {len(request.target_dates)} date(s)..."
            )

        valid_dates, warnings = self.filter_stage.filter_dates(request.target_dates)

        if request.progress_sink:
            request.progress_sink(
                f"Building folder creation plan for {len(valid_dates)} date(s)..."
            )

        plan = self.transformer.transform(environment, request, valid_dates)

        if request.progress_sink:
            request.progress_sink(
                f"Provisioning {len(plan.all_directories_to_ensure)} directories on disk..."
            )

        created_dirs, existing_dirs = self.loader.load(plan)

        if request.progress_sink:
            request.progress_sink("Auditing provisioned directories...")

        result = self.auditor.audit(
            plan, created_dirs, existing_dirs, warnings=warnings
        )

        if request.progress_sink:
            request.progress_sink(
                f"Completed: {result.created_count} directory(ies) created, "
                f"{len(result.existing_directories)} existing, "
                f"{result.total_dates_processed} date(s) processed."
            )

        return result
