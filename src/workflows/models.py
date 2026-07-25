"""Workflow request/response models for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from src.raw_material_workflow import AutomatedRawMaterialSummary

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
