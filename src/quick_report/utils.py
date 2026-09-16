"""Shared quick-report utility functions and re-exported shading utilities."""

from __future__ import annotations

from src.core.shading import (
    COLOR_DEFECT,
    COLOR_HEALTHY,
    COLOR_NORMAL,
    COLOR_WHITE,
    clear_cell_text,
    get_cell_shading,
    set_cell_no_borders,
    set_cell_shading,
    apply_scan_post_processing,
    apply_technology_severity_shading,
    apply_banner_shading,
)
from src.project.storage import sanitize_filename


def normalize_functional_location_input(value: object) -> str:
    """Normalize a user-entered functional-location string or cell value."""
    if value is None:
        return ""
    normalized = str(value).strip()
    if normalized.endswith(".0"):
        normalized = normalized[:-2]
    if normalized.upper().startswith("F/L "):
        normalized = normalized[4:].strip()
    return normalized


__all__ = [
    "COLOR_DEFECT",
    "COLOR_HEALTHY",
    "COLOR_NORMAL",
    "COLOR_WHITE",
    "clear_cell_text",
    "get_cell_shading",
    "normalize_functional_location_input",
    "sanitize_filename",
    "set_cell_no_borders",
    "set_cell_shading",
    "apply_scan_post_processing",
    "apply_technology_severity_shading",
    "apply_banner_shading",
]
