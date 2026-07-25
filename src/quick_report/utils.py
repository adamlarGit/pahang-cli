"""Shared quick-report utility functions."""

from __future__ import annotations

from pathlib import Path

from src.project.storage import sanitize_filename

def normalize_functional_location_input(value: str) -> str:
    """Normalize a user-entered functional-location string."""
    normalized = value.strip()
    if normalized.upper().startswith("F/L "):
        normalized = normalized[4:].strip()
    return normalized

def sort_quick_report_detail_jobs(jobs: list[dict]) -> list[dict]:
    """Sort quick-report detail jobs in source-Excel order."""
    return sorted(
        jobs,
        key=lambda job: (
            int(job.get("source_order", 0) or 0),
            int(job.get("family_order", 0) or 0),
            str(job.get("item_key", "")),
        ),
    )

def _find_dg_photo(raw_data_dir: Path, stem: str) -> str:
    """Find DG photo by stem matching. TODO: Implement stem-based discovery."""
    return ""  # Fallback: empty string per ticket #028

def _find_ir_photo(raw_data_dir: Path, stem: str) -> str:
    """Find IR photo by stem matching. TODO: Implement for future map."""
    return ""

def _find_us_photo(raw_data_dir: Path, stem: str) -> str:
    """Find US photo by stem matching. TODO: Implement for future map."""
    return ""

def _find_tev_photo(raw_data_dir: Path, stem: str) -> str:
    """Find TEV photo by stem matching. TODO: Implement for future map."""
    return ""

__all__ = [
    "normalize_functional_location_input",
    "sort_quick_report_detail_jobs",
    "sanitize_filename",
    "_find_dg_photo",
    "_find_ir_photo",
    "_find_us_photo",
    "_find_tev_photo",
]
