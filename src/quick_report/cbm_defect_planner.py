"""Pure planner for CBM defect family page rendering plans."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.quick_report.cbm_family import (
    QUICK_REPORT_FAMILY_SPECS,
    QuickReportDetailRoleSpec,
    QuickReportFamilySpec,
)
from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.quick_report.defects import CbmDefectRecord


class CbmDefectPlanner:
    """Pure planner: matches CBM defects to family specs and template files."""

    def plan(
        self,
        cbm_defects: Sequence[CbmDefectRecord],
        environment: ProjectEnvironment,
    ) -> tuple[CbmDefectFamilyPlan, ...]:
        """Construct CbmDefectFamilyPlan tuples for all matching families with valid templates."""
        family_plans: list[CbmDefectFamilyPlan] = []

        if not cbm_defects:
            return ()

        for spec in QUICK_REPORT_FAMILY_SPECS:
            family_defects = [
                d for d in cbm_defects if self._defect_matches_family(d, spec)
            ]
            if not family_defects:
                continue

            # Check overview template
            overview_tmpl = environment.get_template(spec.overview_template_key)
            if not overview_tmpl or not Path(overview_tmpl).exists():
                raise FileNotFoundError(
                    f"Missing CBM template '{spec.overview_template_key}' for family '{spec.id}'"
                )

            # Check all detail role templates
            detail_templates: list[tuple[str, Path]] = []
            for role in spec.detail_roles:
                tmpl = environment.get_template(role.template_key)
                if not tmpl or not Path(tmpl).exists():
                    raise FileNotFoundError(
                        f"Missing CBM template '{role.template_key}' for family '{spec.id}'"
                    )
                detail_templates.append((role.id, Path(tmpl)))

            # Group family defects by equipment item
            equipment_groups: dict[str, list[CbmDefectRecord]] = {}
            for d in family_defects:
                equipment_groups.setdefault(d.equipment, []).append(d)

            groups: list[CbmDefectGroup] = []
            for item_key, item_defects in equipment_groups.items():
                overview = item_defects[0]

                detail_groups: list[CbmDefectDetailGroup] = []
                for role in spec.detail_roles:
                    matched_defects = [
                        d for d in item_defects if self._defect_matches_role(d, role)
                    ]
                    detail_groups.append(
                        CbmDefectDetailGroup(
                            role_id=role.id,
                            defects=tuple(matched_defects),
                        )
                    )

                groups.append(
                    CbmDefectGroup(
                        item_key=item_key,
                        item_suffix="",
                        defects=tuple(item_defects),
                        overview=overview,
                        detail_groups=tuple(detail_groups),
                    )
                )

            family_plans.append(
                CbmDefectFamilyPlan(
                    spec=spec,
                    overview_template=Path(overview_tmpl),
                    detail_templates=tuple(detail_templates),
                    groups=tuple(groups),
                )
            )

        return tuple(family_plans)

    @staticmethod
    def _defect_matches_family(defect: CbmDefectRecord, spec: QuickReportFamilySpec) -> bool:
        """Check if defect matches family equipment_values and technologies (case-insensitive)."""
        if spec.equipment_values:
            eq_upper = (defect.equipment or "").upper()
            if eq_upper not in [ev.upper() for ev in spec.equipment_values]:
                return False
        if spec.technologies:
            tech_upper = (defect.technology or "").upper()
            if tech_upper not in [t.upper() for t in spec.technologies]:
                return False
        return True

    @staticmethod
    def _defect_matches_role(defect: CbmDefectRecord, role: QuickReportDetailRoleSpec) -> bool:
        """Check if defect matches detail role equipment_values and technologies (case-insensitive)."""
        if role.equipment_values:
            eq_upper = (defect.equipment or "").upper()
            if eq_upper not in [ev.upper() for ev in role.equipment_values]:
                return False
        if role.technologies:
            tech_upper = (defect.technology or "").upper()
            if tech_upper not in [t.upper() for t in role.technologies]:
                return False
        return True
