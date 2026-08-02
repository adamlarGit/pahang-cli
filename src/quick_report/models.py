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
class CbmDefectGroup:
    """Group of CBM defect records for a single equipment item within a family."""

    item_key: str
    item_suffix: str
    defects: tuple[CbmDefectRecord, ...]
    overview: CbmDefectRecord
    detail_groups: tuple[tuple[str, tuple[CbmDefectRecord, ...]], ...] = ()


@dataclass(frozen=True)
class CbmDefectFamilyPlan:
    """Immutable execution plan for rendering a CBM defect family."""

    spec: QuickReportFamilySpec
    overview_template: Path
    detail_templates: tuple[tuple[str, Path], ...]
    groups: tuple[CbmDefectGroup, ...]


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
    family_template_paths: tuple[tuple[str, str], ...] = ()
