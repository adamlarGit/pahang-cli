"""Workflow request/response models for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from src.postprocessing.converters import DocumentConverter
    from src.testsheet.models import SubstationPackage
    from src.workflows.raw_material import AutomatedRawMaterialSummary


ProgressSink = Callable[..., None]


class PopulateMode(Enum):
    """Processing mode enum for Populate TOTAL PE workflow."""

    AUTO = "auto"
    ALL = "all"
    SPECIFIC_FOLDERS = "specific"



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
class SubstationInspectionItem:
    """Dry-run inspection data for a single substation."""

    pe_number: int
    substation_name: str
    functional_location: str
    defect_suffix: str
    stem: str
    target_output_path: Path
    cbm_defect_count: int
    vi_defect_count: int
    condition_pair_count: int
    station: str = ""



@dataclass(frozen=True)
class QuickReportInspection:
    """Dry-run outcome returned by inspect()."""

    targets: tuple[SubstationInspectionItem, ...]
    missing_templates: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.targets, tuple):
            object.__setattr__(self, "targets", tuple(self.targets))
        if not isinstance(self.missing_templates, tuple):
            object.__setattr__(self, "missing_templates", tuple(self.missing_templates))
        if not isinstance(self.warnings, tuple):
            object.__setattr__(self, "warnings", tuple(self.warnings))
        if not isinstance(self.errors, tuple):
            object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def ready_to_generate(self) -> bool:
        return (
            len(self.missing_templates) == 0
            and len(self.errors) == 0
            and len(self.targets) > 0
        )


@dataclass(frozen=True)
class QuickReportResult:
    """Consolidated execution outcome returned by generate()."""

    reports_generated: int = 0
    generated_paths: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.generated_paths, tuple):
            object.__setattr__(self, "generated_paths", tuple(self.generated_paths))
        if not isinstance(self.warnings, tuple):
            object.__setattr__(self, "warnings", tuple(self.warnings))
        if not isinstance(self.errors, tuple):
            object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0 and self.reports_generated > 0

    @property
    def is_successful(self) -> bool:
        """Standardized alias for is_success across workflow models."""
        return self.is_success


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


class PostProcessingMode(Enum):
    """Selection mode enum for Post-Processing Pipeline."""

    BY_DATE = "by_date"
    BY_FL = "by_fl"


@dataclass(frozen=True)
class PostProcessingRequest:
    """Request model for 1-Click Substation Post-Processing Pipeline."""

    mode: PostProcessingMode = PostProcessingMode.BY_DATE
    target_dates: Sequence[str] = ()
    target_fls: Sequence[str] = ()
    target_packages: Sequence[SubstationPackage] = ()
    apply_signatures: bool = False
    vendor_signature_path: Path | None = None
    tnb_signature_path: Path | None = None
    generate_whatsapp: bool = False
    converter: DocumentConverter | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class PostProcessingFailure:
    """Record of a failed substation during post-processing."""

    package: SubstationPackage
    error: str


@dataclass(frozen=True)
class PostProcessingSummary:
    """Summary of completed post-processing executions."""

    processed_packages: tuple[SubstationPackage, ...] = ()
    final_deliverables: tuple[Path, ...] = ()
    failed_packages: tuple[PostProcessingFailure, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    duration_seconds: float = 0.0

    @property
    def total_target_count(self) -> int:
        return len(self.processed_packages) + len(self.failed_packages)

    @property
    def is_successful(self) -> bool:
        return len(self.failed_packages) == 0 and len(self.errors) == 0 and len(self.processed_packages) > 0




