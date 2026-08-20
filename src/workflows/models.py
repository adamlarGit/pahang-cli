"""Workflow request/response models for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from src.workflows.raw_material import AutomatedRawMaterialSummary

ProgressSink = Callable[..., None]


class PopulateMode(Enum):
    """Processing mode enum for Populate TOTAL PE workflow."""

    AUTO = "auto"
    ALL = "all"
    SPECIFIC_FOLDERS = "specific"


class QuickReportMode(Enum):
    """Selection mode enum for Quick Report generation."""

    FL = "fl"
    FOLDER = "folder"


@dataclass(frozen=True)
class PopulateTotalPeRequest:
    """Request model for Populate TOTAL PE workflow."""

    mode: PopulateMode
    target_folder_names: Sequence[str] = ()
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class PopulateTotalPeResult:
    """Result model for Populate TOTAL PE workflow."""

    new_rows_added: int = 0


@dataclass(frozen=True)
class RawMaterialRequest:
    """Request model for Raw Material Creation & Sorting workflow."""

    output_path: Path
    target_dir: Path | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class RawMaterialResult:
    """Result model for Raw Material Creation & Sorting workflow."""

    substations_count: int = 0
    ir_copied_count: int = 0
    dg_copied_count: int = 0
    us_tev_extracted_count: int = 0
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()
    summary: AutomatedRawMaterialSummary | Any | None = None



@dataclass(frozen=True)
class UpdateQr02CbaRequest:
    """Request model for updating QR02 CBA sheet."""

    mode: PopulateMode = PopulateMode.AUTO
    target_package_names: Sequence[str] = ()
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class UpdateQr02CbaResult:
    """Result model for updating QR02 CBA sheet."""

    records_updated: int = 0
    processed_folders: Sequence[str] = ()
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()


@dataclass(frozen=True)
class QuickReportRequest:
    """Request model for Quick Report generation workflow."""

    mode: QuickReportMode
    target_package_names: Sequence[str] = ()
    target_folders: Sequence[str] = ()
    substation_condition_template_path: Path | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class QuickReportResult:
    """Result model for Quick Report generation workflow."""

    reports_generated: int = 0
    generated_paths: Sequence[Path] = ()
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()


@dataclass(frozen=True)
class WhatsAppReportRequest:
    """Request model for WhatsApp report generation workflow."""

    target_date: date | None = None
    report_dir: Path | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class WhatsAppReportResult:
    """Result model for WhatsApp report generation workflow."""

    substations_count: int = 0
    output_path: Path | None = None


@dataclass(frozen=True)
class PropagateWoRequest:
    """Request model for Propagate Work Orders workflow."""

    target_date: str | None = None
    overwrite: bool = False
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class PropagateWoResult:
    """Result model for Propagate Work Orders workflow."""

    matched_count: int = 0
    already_populated_count: int = 0
    unmatched_count: int = 0
    unmatched_fls: tuple[str, ...] = ()
    updated_count: int = 0


@dataclass(frozen=True)
class IngestMsmsCsvRequest:
    """Request model for Ingest MSMS CSV workflow."""

    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class IngestMsmsCsvResult:
    """Result model for Ingest MSMS CSV workflow."""

    files_ingested: int = 0
    files_skipped_duplicate: int = 0
    ingested_files: Sequence[Path] = ()
    skipped_files: Sequence[Path] = ()
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()

    @property
    def duplicates_skipped(self) -> int:
        return self.files_skipped_duplicate


@dataclass(frozen=True)
class PopulateDataMsmsRequest:
    """Request model for Populate Data MSMS workflow."""

    mode: PopulateMode = PopulateMode.AUTO
    target_folder_names: Sequence[str] = ()
    overwrite: bool = False
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class PopulateDataMsmsResult:
    """Result model for Populate Data MSMS workflow."""

    csv_files_processed: int = 0
    total_rows_evaluated: int = 0
    rows_populated: int = 0
    rows_skipped_already_filled: int = 0
    rows_skipped_no_testsheet: int = 0
    unmapped_meters_count: int = 0
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()


@dataclass(frozen=True)
class ConsolidateMsmsRequest:
    """Request model for Consolidate MSMS workflow."""

    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class ConsolidateMsmsResult:
    """Result model for Consolidate MSMS workflow."""

    files_processed: int = 0
    rows_appended: int = 0
    duplicates_skipped: int = 0
    errors: Sequence[str] = ()
    files_moved: Sequence[Path] = ()


@dataclass(frozen=True)
class EnrichMsmsRequest:
    """Request model for Enrich MSMS workflow."""

    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class EnrichMsmsResult:
    """Result model for Enrich MSMS workflow."""

    matched_count: int = 0
    unmatched_count: int = 0
    unmatched_wos: Sequence[str] = ()
    updated_cells_count: int = 0


@dataclass(frozen=True)
class GenerateTestsheetFolderRequest:
    """Request model for Generate TESTSHEET Folder Structure workflow."""

    station: str
    month: str
    target_dates: Sequence[str] = ()
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class DateFolderPlan:
    """Execution plan for a single date folder hierarchy."""

    date_str: str
    date_dir: Path
    unsorted_dir: Path
    tech_dirs: tuple[Path, ...] = ()

    @property
    def all_directories(self) -> tuple[Path, ...]:
        return (self.date_dir, self.unsorted_dir, *self.tech_dirs)


@dataclass(frozen=True)
class GenerateTestsheetFolderPlan:
    """Complete folder generation plan for a station and month."""

    station: str
    month: str
    month_dir: Path
    date_plans: tuple[DateFolderPlan, ...] = ()

    @property
    def all_directories_to_ensure(self) -> tuple[Path, ...]:
        dirs: list[Path] = [self.month_dir]
        for date_plan in self.date_plans:
            dirs.extend(date_plan.all_directories)
        return tuple(dirs)


@dataclass(frozen=True)
class GenerateTestsheetFolderResult:
    """Result model for Generate TESTSHEET Folder Structure workflow."""

    station: str
    month: str
    created_directories: Sequence[Path] = ()
    existing_directories: Sequence[Path] = ()
    total_dates_processed: int = 0
    warnings: Sequence[str] = ()
    errors: Sequence[str] = ()

    @property
    def created_count(self) -> int:
        return len(self.created_directories)

    @property
    def is_successful(self) -> bool:
        return len(self.errors) == 0 and self.total_dates_processed > 0



