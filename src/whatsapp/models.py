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
