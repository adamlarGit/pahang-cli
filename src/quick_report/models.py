"""Data models for Quick Report ETL pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.quick_report.cbm_family import QuickReportFamilySpec
    from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
    from src.testsheet.models import SubstationTestsheetPackage


@dataclass(frozen=True)
class CbmDefectDetailGroup:
    """Group of defects matching a specific detail role."""

    role_id: str
    defects: tuple[CbmDefectRecord, ...]


@dataclass(frozen=True)
class CbmDefectGroup:
    """Group of CBM defect records for a single equipment item within a family."""

    item_key: str
    item_suffix: str
    defects: tuple[CbmDefectRecord, ...]
    overview: CbmDefectRecord
    detail_groups: tuple[CbmDefectDetailGroup, ...] = ()


@dataclass(frozen=True)
class CbmDefectFamilyPlan:
    """Immutable execution plan for rendering a CBM defect family."""

    spec: QuickReportFamilySpec
    overview_template: Path
    detail_templates: tuple[tuple[str, Path], ...]
    groups: tuple[CbmDefectGroup, ...]


@dataclass(frozen=True)
class CbmDefectPagePlan:
    """Immutable plan for rendering a single CBM defect page (overview or detail)."""

    template_path: Path
    output_filename: str
    context: dict[str, Any]


@dataclass(frozen=True)
class ViDefectPagePlan:
    """Immutable plan for rendering a single VI defect page."""

    template_path: Path
    output_filename: str
    context: dict[str, Any]
    active_defect_count: int


@dataclass(frozen=True)
class CbmSummaryRow:
    """Prepared technical summary row for CBM defect report."""

    equipment: str = ""
    brand: str = ""
    model: str = ""
    rating: str = ""
    defect_area: str = ""
    remarks: str = ""
    ir_reading: str = ""
    us_reading: str = ""
    tev_reading: str = ""
    ir_abs: str = ""
    ir_delta: str = "-"
    us_dB: str = ""
    tev_dB: str = ""
    severity: str = ""
    status: str = ""


@dataclass(frozen=True)
class ViSummaryRow:
    """Prepared summary row for VI defect report."""

    equipment: str
    defect_area: str
    remarks: str


@dataclass(frozen=True)
class QuickReportStationPlan:
    """Immutable transformation plan for a single substation report rendering.

    Produced by QuickReportTransformer, consumed by QuickReportComposer (Loader).
    Self-contained: includes all pre-resolved template paths and data tuples.
    """

    package: SubstationTestsheetPackage
    pe_info: dict[str, Any]
    cbm_defects: tuple[CbmDefectRecord, ...]
    vi_defects: tuple[ViDefectRecord, ...]
    suffix: str
    suffix_parts: tuple[str, ...]
    output_dir: Path
    output_filename: str
    final_output_path: Path
    condition_pairs: tuple[tuple[str, str], ...]
    cond_template_path: Path | None
    front_page_template: Path
    cbm_summary_template: Path | None
    vi_summary_template: Path | None
    vi_defect_template: Path | None
    sticker_template: Path
    cbm_defect_family_plans: tuple[CbmDefectFamilyPlan, ...] = ()
