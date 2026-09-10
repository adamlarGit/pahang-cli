"""Full Report package for Pahang CLI."""

from __future__ import annotations

from src.full_report.preflight import (
    MIN_FILE_SIZE_BYTES,
    MIN_MEDIA_COUNT,
    VALID_IMAGE_EXTENSIONS,
    PreFlightValidationError,
    PreFlightValidationResult,
    resolve_quick_report_path,
    validate_finalized_quick_report,
)
from src.full_report.slicer import (
    DocumentSlicer,
    FakeDocumentSlicer,
    SlicedSections,
    SlicingError,
    WordComDocumentSlicer,
    get_temp_parts_dir,
    temp_parts_workspace,
)
from src.full_report.defect_parser import (
    CbmDefectHeaderParser,
    CbmDefectSliceMetadata,
    build_d37_defect_filename,
    normalize_defect_area,
    normalize_equipment_id,
)

__all__ = [
    # Pre-Flight
    "MIN_FILE_SIZE_BYTES",
    "MIN_MEDIA_COUNT",
    "VALID_IMAGE_EXTENSIONS",
    "PreFlightValidationError",
    "PreFlightValidationResult",
    "resolve_quick_report_path",
    "validate_finalized_quick_report",
    # Document Slicer
    "DocumentSlicer",
    "FakeDocumentSlicer",
    "SlicedSections",
    "SlicingError",
    "WordComDocumentSlicer",
    "get_temp_parts_dir",
    "temp_parts_workspace",
    # Defect Parser & D37 Naming
    "CbmDefectHeaderParser",
    "CbmDefectSliceMetadata",
    "build_d37_defect_filename",
    "normalize_defect_area",
    "normalize_equipment_id",
]
