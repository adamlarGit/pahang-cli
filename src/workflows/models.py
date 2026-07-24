"""Workflow request/response models for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

ProgressSink = Callable[[str], None]


class PopulateMode(Enum):
    AUTO = "auto"
    ALL = "all"
    SPECIFIC_FOLDERS = "specific"


class QuickReportMode(Enum):
    FL = "fl"
    FOLDER = "folder"


@dataclass(frozen=True)
class PopulateTotalPeRequest:
    mode: PopulateMode
    target_folder_names: Sequence[str] = ()
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class PopulateTotalPeResult:
    new_rows_added: int = 0


@dataclass(frozen=True)
class RawMaterialRequest:
    output_path: Path
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class RawMaterialResult:
    substations_count: int = 0


@dataclass(frozen=True)
class UpdateQr02CbaRequest:
    target_package_names: Sequence[str] = ()
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class UpdateQr02CbaResult:
    records_updated: int = 0


@dataclass(frozen=True)
class QuickReportRequest:
    mode: QuickReportMode
    target_package_names: Sequence[str] = ()
    target_folders: Sequence[str] = ()
    substation_condition_template_path: Path | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class QuickReportResult:
    reports_generated: int = 0


@dataclass(frozen=True)
class WhatsAppReportRequest:
    target_date: date | None = None
    report_dir: Path | None = None
    progress_sink: ProgressSink | None = None


@dataclass(frozen=True)
class WhatsAppReportResult:
    substations_count: int = 0
