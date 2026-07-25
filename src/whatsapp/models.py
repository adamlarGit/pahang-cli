"""Data models for WhatsApp report generation deep module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WhatsAppReportResources:
    """Resolved resource paths and configuration for WhatsApp report generation."""

    quick_report_dir: Path
    save_dir: Path
    template_path: Path
    total_pe_path: Path
    station_mapping: dict[str, str]


@dataclass(frozen=True)
class WhatsAppReportSummary:
    """Summary result of a WhatsApp report generation run."""

    report_dir: Path
    output_path: Path
    substations_count: int = 0


@dataclass(frozen=True)
class WhatsAppReportItem:
    """Single substation item context for docxtpl Jinja rendering."""

    name: str
    defect: str
    msms: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "defect": self.defect,
            "msms": self.msms,
        }
