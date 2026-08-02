"""Pure planner for CBM defect family page rendering plans."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS
from src.quick_report.models import CbmDefectFamilyPlan, CbmDefectGroup

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
                d for d in cbm_defects if d.equipment.upper() in spec.equipment_values
            ]
            if not family_defects:
                continue

            overview_tmpl = environment.get_template(spec.overview_template_key)
            if not overview_tmpl or not Path(overview_tmpl).exists():
                continue

            detail_templates: list[tuple[str, Path]] = []
            for role in spec.detail_roles:
                tmpl = environment.get_template(role.template_key)
                if tmpl and Path(tmpl).exists():
                    detail_templates.append((role.id, Path(tmpl)))

            groups = [
                CbmDefectGroup(
                    item_key=d.equipment,
                    item_suffix="",
                    defects=(d,),
                    overview=d,
                    detail_groups=(),
                )
                for d in family_defects
            ]

            family_plans.append(
                CbmDefectFamilyPlan(
                    spec=spec,
                    overview_template=Path(overview_tmpl),
                    detail_templates=tuple(detail_templates),
                    groups=tuple(groups),
                )
            )

        return tuple(family_plans)
