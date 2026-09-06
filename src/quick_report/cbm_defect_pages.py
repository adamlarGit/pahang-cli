"""CBM Defect Detail Pages generation and planning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.quick_report.cbm_render import _build_family_render_context, _render_docx_template, _text_or_empty
from src.quick_report.models import CbmDefectFamilyPlan, CbmDefectPagePlan
from src.quick_report.prpd import discover_ultratev_survey_dir, generate_all_substation_prpd_graphs
from src.quick_report.utils import sanitize_filename


def build_cbm_defect_page_context(pe_info: dict[str, Any]) -> dict[str, Any]:
    """Build the base context for CBM defect pages."""
    return pe_info.copy()


class CbmDefectPageBuilder:
    """Builder for constructing ordered CBM defect page rendering plans."""

    def build(
        self,
        family_plan: CbmDefectFamilyPlan,
        pe_info: dict[str, Any],
        substation_number: int,
    ) -> list[CbmDefectPagePlan]:
        """Build ordered page rendering plans for a CBM defect family plan."""
        spec = family_plan.spec
        overview_template_path = family_plan.overview_template
        detail_template_paths: dict[str, Path] = dict(family_plan.detail_templates)
        groups = family_plan.groups

        if not groups or not overview_template_path or not overview_template_path.exists():
            return []

        if "prpd_catalog" not in pe_info:
            raw_dir = pe_info.get("raw_data_dir") or pe_info.get("survey_dir") or pe_info.get("raw_dir")
            if raw_dir:
                survey_root = discover_ultratev_survey_dir(raw_dir)
                if survey_root:
                    prpd_out = pe_info.get("prpd_output_dir")
                    if not prpd_out:
                        prpd_out = Path(raw_dir) / "prpd_temp"
                        prpd_out.mkdir(parents=True, exist_ok=True)
                        pe_info["prpd_output_dir"] = prpd_out
                    prpd_catalog = generate_all_substation_prpd_graphs(
                        survey_root=survey_root,
                        output_dir=Path(prpd_out),
                        mode=pe_info.get("prpd_mode", "option_c"),
                    )
                    pe_info["prpd_catalog"] = prpd_catalog

        page_plans: list[CbmDefectPagePlan] = []
        substation_number_str = f"{substation_number:03d}"

        for group_index, group in enumerate(groups, start=1):
            group_item_key = _text_or_empty(group.item_key).strip()
            group_item_suffix = _text_or_empty(group.item_suffix).strip()
            item_key = sanitize_filename(group_item_key or f"GROUP {group_index}")

            # Overview page
            overview_rec = group.overview
            overview_context = build_cbm_defect_page_context(pe_info)
            overview_context.update(
                _build_family_render_context(
                    spec,
                    overview_rec,
                    overview=True,
                    item_key=group_item_key,
                    item_suffix=group_item_suffix,
                    pe_info=pe_info,
                )
            )

            overview_filename = (
                f"{substation_number_str}_04_{spec.id.upper()}_OVERVIEW.docx"
                if len(groups) == 1
                else f"{substation_number_str}_04_{spec.id.upper()}_OVERVIEW_grp{group_index}.docx"
            )

            page_plans.append(
                CbmDefectPagePlan(
                    template_path=overview_template_path,
                    output_filename=overview_filename,
                    context=overview_context,
                )
            )

            # Render detail pages per detail role directly from group.detail_groups
            detail_groups_by_role = {dg.role_id: dg.defects for dg in group.detail_groups}

            for role_spec in spec.detail_roles:
                role_template_path = detail_template_paths.get(role_spec.id)
                if not role_template_path or not role_template_path.exists():
                    continue

                role_defects = detail_groups_by_role.get(role_spec.id, ())
                for defect_index, defect_rec in enumerate(role_defects, start=1):
                    render_context = build_cbm_defect_page_context(pe_info)
                    render_context.update(
                        _build_family_render_context(
                            spec,
                            defect_rec,
                            overview=False,
                            item_key=group_item_key,
                            item_suffix=group_item_suffix,
                            pe_info=pe_info,
                        )
                    )

                    defect_suffix = ""
                    if len(groups) > 1:
                        defect_suffix += f"_grp{group_index}"
                    if len(role_defects) > 1:
                        defect_suffix += f"_part{defect_index}"

                    defect_filename = (
                        f"{substation_number_str}_04_{spec.id.upper()}_{item_key}{defect_suffix}.docx"
                    )

                    page_plans.append(
                        CbmDefectPagePlan(
                            template_path=role_template_path,
                            output_filename=defect_filename,
                            context=render_context,
                        )
                    )

        return page_plans


def generate_cbm_defect_pages(
    plan: CbmDefectFamilyPlan,
    output_dir: Path,
    substation_number: int,
    pe_info: dict[str, Any],
) -> list[Path]:
    """Generate CBM defect detail pages using typed CbmDefectFamilyPlan."""
    pe_info_copy = pe_info.copy()
    if "prpd_output_dir" not in pe_info_copy:
        prpd_temp = output_dir / "prpd_temp"
        prpd_temp.mkdir(parents=True, exist_ok=True)
        pe_info_copy["prpd_output_dir"] = prpd_temp

    raw_dir = pe_info_copy.get("raw_data_dir") or pe_info_copy.get("survey_dir") or pe_info_copy.get("raw_dir")
    if raw_dir and "prpd_catalog" not in pe_info_copy:
        survey_root = discover_ultratev_survey_dir(raw_dir)
        if survey_root:
            prpd_catalog = generate_all_substation_prpd_graphs(
                survey_root=survey_root,
                output_dir=pe_info_copy["prpd_output_dir"],
                mode=pe_info_copy.get("prpd_mode", "option_c"),
            )
            pe_info_copy["prpd_catalog"] = prpd_catalog

    pages = CbmDefectPageBuilder().build(
        family_plan=plan,
        pe_info=pe_info_copy,
        substation_number=substation_number,
    )
    generated_paths: list[Path] = []
    for page in pages:
        output_path = output_dir / page.output_filename
        _render_docx_template(page.template_path, output_path, page.context)
        generated_paths.append(output_path)
    return generated_paths

