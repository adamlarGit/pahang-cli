"""Shared quick-report family/role specifications.

The report generator uses these specs to decide which QR03 CBA rows belong to
each detail-page family, which templates to render, and how the generated page
names should be labeled.
"""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class QuickReportDetailRoleSpec:
    """Detail-page role within a quick-report family."""

    id: str
    output_label: str
    template_key: str
    equipment_values: tuple[str, ...]
    technologies: tuple[str, ...]


@dataclass(frozen=True)
class QuickReportFamilySpec:
    """Quick-report family with one overview page and one or more roles."""

    id: str
    output_label: str
    overview_template_key: str
    equipment_values: tuple[str, ...]
    technologies: tuple[str, ...]
    detail_roles: tuple[QuickReportDetailRoleSpec, ...]


QUICK_REPORT_FAMILY_SPECS: tuple[QuickReportFamilySpec, ...] = (
    QuickReportFamilySpec(
        id="fp_lvdb",
        output_label="FP LVDB",
        overview_template_key="fp_overview",
        equipment_values=("FP (D)", "FP (J)", "LVDB"),
        technologies=("IR",),
        detail_roles=(
            QuickReportDetailRoleSpec(
                id="fp_detail",
                output_label="FP LVDB",
                template_key="fp_individual_defect",
                equipment_values=("FP (D)", "FP (J)", "LVDB"),
                technologies=("IR",),
            ),
        ),
    ),
    QuickReportFamilySpec(
        id="swg",
        output_label="SWG",
        overview_template_key="swg_overview",
        equipment_values=("RMU SF6", "CABLE SWG", "EARTHING"),
        technologies=("IR", "US", "TEV"),
        detail_roles=(
            QuickReportDetailRoleSpec(
                id="panel_area",
                output_label="SWG",
                template_key="swg_panel",
                equipment_values=("RMU SF6", "CABLE SWG", "EARTHING"),
                technologies=("IR", "US", "TEV"),
            ),
        ),
    ),
    QuickReportFamilySpec(
        id="tx",
        output_label="TX",
        overview_template_key="tx_overview",
        equipment_values=("LTX/DTX", "CABLE LTX/DTX"),
        technologies=("IR", "US"),
        detail_roles=(
            QuickReportDetailRoleSpec(
                id="tx_hv_side",
                output_label="TX HV SIDE",
                template_key="tx_hv_sides",
                equipment_values=("CABLE LTX/DTX",),
                technologies=("IR", "US"),
            ),
            QuickReportDetailRoleSpec(
                id="tx_lv_side",
                output_label="TX LV SIDE",
                template_key="tx_lv_sides",
                equipment_values=("LTX/DTX",),
                technologies=("IR",),
            ),
        ),
    ),
    QuickReportFamilySpec(
        id="blackbox",
        output_label="BLACK BOX",
        overview_template_key="blackbox_overview",
        equipment_values=("BLACKBOX", "BLACK BOX"),
        technologies=("IR",),
        detail_roles=(
            QuickReportDetailRoleSpec(
                id="blackbox_detail",
                output_label="BLACK BOX",
                template_key="blackbox_overview",
                equipment_values=("BLACKBOX", "BLACK BOX"),
                technologies=("IR",),
            ),
        ),
    ),
    QuickReportFamilySpec(
        id="battery",
        output_label="BATTERY",
        overview_template_key="battery_overview",
        equipment_values=("BATTERY BANK", "BATTERY"),
        technologies=("IR",),
        detail_roles=(
            QuickReportDetailRoleSpec(
                id="battery_detail",
                output_label="BATTERY",
                template_key="battery_overview",
                equipment_values=("BATTERY BANK", "BATTERY"),
                technologies=("IR",),
            ),
        ),
    ),
)

QUICK_REPORT_FAMILY_SPECS_BY_ID: dict[str, QuickReportFamilySpec] = {
    spec.id: spec for spec in QUICK_REPORT_FAMILY_SPECS
}
