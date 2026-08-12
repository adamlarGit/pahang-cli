"""Transformation and plan construction stage for Quick Report workflow."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.quick_report.cbm_defect_planner import CbmDefectPlanner
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.utils import sanitize_filename

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
    from src.testsheet.models import SubstationTestsheetPackage


class QuickReportTransformer:
    """Pure logic transformation and plan construction stage for Quick Report."""

    def __init__(self, cbm_planner: CbmDefectPlanner | None = None) -> None:
        self._cbm_planner = cbm_planner or CbmDefectPlanner()

    def transform(
        self,
        pkg: SubstationTestsheetPackage,
        cbm_defects: list[CbmDefectRecord],
        vi_defects: list[ViDefectRecord],
        environment: ProjectEnvironment,
        cond_template_path: Path | None = None,
    ) -> QuickReportStationPlan:
        """Construct immutable, self-contained QuickReportStationPlan for single station rendering."""
        if not pkg.data:
            raise ValueError(f"Package for station '{pkg.station}' is missing data.")

        po_num = getattr(environment, "po_number", None)
        state = getattr(environment, "state", None)

        substation_name_erms = pkg.data.substation_name_erms or ""
        substation_name_site = pkg.data.substation_name_site or ""

        pe_info: dict[str, Any] = {
            "purchaseorder": {
                "number": po_num,
            },
            "substation": {
                "name_erms": substation_name_erms,
                "name_site": substation_name_site,
                "substation_name_erms": substation_name_erms,
                "substation_name_site": substation_name_site,
                "fl_erms": pkg.data.fl_erms,
                "fl_site": pkg.data.fl_site,
                "area": pkg.station or "",
                "state": state.upper() if state else "PAHANG",
                "datefrontpage": pkg.data.date_str or "",
                "date": pkg.data.date_str or "",
                "gps_coordinate": pkg.data.gps_coordinate or "",
                "gpscoordinate": pkg.data.gps_coordinate or "",
                "type": pkg.data.substation_type or "",
                "substation_type": pkg.data.substation_type or "",
                "building_type": pkg.data.building_type or "",
                "ambient": pkg.data.ambient if pkg.data.ambient else "-",
                "humidity": pkg.data.humidity if pkg.data.humidity else "-",
                "time": pkg.data.time if pkg.data.time else "-",
            },
        }

        pe_number = pkg.substation_number
        sanitized_name = sanitize_filename(
            pkg.data.substation_name_erms or pkg.data.station_name
        )

        suffix, suffix_parts = self._calculate_suffix(cbm_defects, vi_defects)
        output_filename = f"{pe_number:03d}. {sanitized_name}{suffix}.docx"

        output_dir = self._resolve_output_dir(environment, pkg)
        final_output_path = output_dir / output_filename

        condition_pairs = tuple(self._build_substation_condition_pairs(pkg))

        # Resolve required template paths
        front_page_template = environment.get_vi_front_page_template()
        cbm_summary_template = environment.get_cbm_summary_template() if cbm_defects else None
        vi_summary_template = environment.get_vi_summary_template() if vi_defects else None
        vi_defect_template = environment.get_vi_defect_template() if vi_defects else None
        sticker_template = environment.get_template("sticker_page")

        cbm_defect_family_plans = self._cbm_planner.plan(cbm_defects, environment)

        return QuickReportStationPlan(
            package=pkg,
            pe_info=pe_info,
            cbm_defects=tuple(cbm_defects),
            vi_defects=tuple(vi_defects),
            suffix=suffix,
            suffix_parts=tuple(suffix_parts),
            output_dir=output_dir,
            output_filename=output_filename,
            final_output_path=final_output_path,
            condition_pairs=condition_pairs,
            cond_template_path=cond_template_path,
            front_page_template=front_page_template,
            cbm_summary_template=cbm_summary_template,
            vi_summary_template=vi_summary_template,
            vi_defect_template=vi_defect_template,
            sticker_template=sticker_template,
            cbm_defect_family_plans=cbm_defect_family_plans,
        )

    def _resolve_output_dir(
        self, environment: ProjectEnvironment, pkg: SubstationTestsheetPackage
    ) -> Path:
        """Resolve output directory mirroring TESTSHEET hierarchy: QUICK REPORT/<STATION>/<MONTH>/<DATE>/."""
        if pkg.station and pkg.month and pkg.date_str:
            return (
                environment.get_quick_report_dir()
                / pkg.station
                / pkg.month
                / pkg.date_str
            )
        if pkg.date_str:
            return environment.get_quick_report_dir() / pkg.date_str
        return environment.get_quick_report_dir()

    def _calculate_suffix(
        self, cbm_defects: list[CbmDefectRecord], vi_defects: list[ViDefectRecord]
    ) -> tuple[str, list[str]]:
        """Calculate canonical defect status suffix (e.g. '(IR+US+VI)')."""
        suffix_parts = []
        if any(d.technology == "IR" for d in cbm_defects):
            suffix_parts.append("IR")
        if any(d.technology == "US" for d in cbm_defects):
            suffix_parts.append("US")
        if any(d.technology == "TEV" for d in cbm_defects):
            suffix_parts.append("TEV")
        if vi_defects:
            suffix_parts.append("VI")

        suffix_str = f" ({'+'.join(suffix_parts)})" if suffix_parts else ""
        return suffix_str, suffix_parts

    def _build_substation_condition_pairs(
        self, pkg: SubstationTestsheetPackage | None = None
    ) -> list[tuple[str, str]]:
        """Build active 2-column pairs for the substation condition page."""
        if not pkg or not getattr(pkg, "data", None):
            return [("SUBSTATION OVERVIEW", "SIGNBOARD")]
        return [
            ("SUBSTATION OVERVIEW", "SIGNBOARD"),
            ("SWITCHGEAR 1", "NAMEPLATE"),
            ("TRANSFORMER 1", "NAMEPLATE"),
            ("FEEDER PILLAR 1", "NAMEPLATE"),
            ("BATTERY CHARGER", "NAMEPLATE"),
            ("RTU", "NAMEPLATE"),
            ("EFI", "NAMEPLATE"),
            ("FIRE EXTINGUISHER", "EXPIRY"),
            ("TRANSFORMER OIL LEVEL INDICATOR", "NAMEPLATE"),
        ]
