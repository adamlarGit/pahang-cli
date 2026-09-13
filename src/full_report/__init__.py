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
from src.full_report.photo_resolver import (
    PhotoPair,
    RawPhotoResolver,
)
from src.full_report.models import (
    BatteryBankScanSpec,
    FullReportScanPackage,
    LVDBFeederScanSpec,
    LVDBScanSpec,
    SwitchgearCategory,
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
    TransformerScanSpec,
    TRANSFORMER_STANDARD_COMPONENTS,
    VCB_STANDARD_COMPARTMENTS,
    build_battery_bank_scan_spec,
    build_full_report_scan_package,
    build_lvdb_scan_spec,
    build_switchgear_panel_scan_spec,
    build_switchgear_scan_spec,
    build_transformer_scan_spec,
    classify_switchgear,
    has_battery_bank,
    has_hv_cable_split,
    is_tx_feeder,
    resolve_overview_compartments,
    resolve_panel_page_count,
    resolve_switchgear_compartments,
)
from src.full_report.census import (
    CensusRowItem,
    ExecutiveSummaryCensusBuilder,
    ExecutiveSummaryCensusContext,
    ExecutiveSummaryCensusResult,
    apply_column_vertical_merge,
    apply_post_render_dom,
    apply_severity_shading,
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
    # Photo Resolver
    "PhotoPair",
    "RawPhotoResolver",
    # Scan Models & Compartment Matrix (Ticket #26 / T2.3)
    "BatteryBankScanSpec",
    "FullReportScanPackage",
    "LVDBFeederScanSpec",
    "LVDBScanSpec",
    "SwitchgearCategory",
    "SwitchgearPanelScanSpec",
    "SwitchgearScanSpec",
    "TransformerScanSpec",
    "TRANSFORMER_STANDARD_COMPONENTS",
    "VCB_STANDARD_COMPARTMENTS",
    "build_battery_bank_scan_spec",
    "build_full_report_scan_package",
    "build_lvdb_scan_spec",
    "build_switchgear_panel_scan_spec",
    "build_switchgear_scan_spec",
    "build_transformer_scan_spec",
    "classify_switchgear",
    "has_battery_bank",
    "has_hv_cable_split",
    "is_tx_feeder",
    "resolve_overview_compartments",
    "resolve_panel_page_count",
    "resolve_switchgear_compartments",
    # Executive Summary Census (Ticket #28 / T3.2)
    "CensusRowItem",
    "ExecutiveSummaryCensusBuilder",
    "ExecutiveSummaryCensusContext",
    "ExecutiveSummaryCensusResult",
    "apply_column_vertical_merge",
    "apply_post_render_dom",
    "apply_severity_shading",
]


