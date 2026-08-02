"""CBM Defect Detail Pages generation (Part 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from src.quick_report.cbm_family import QuickReportFamilySpec
from src.quick_report.cbm_render import _build_family_render_context, _render_docx_template, _payload_get, _text_or_empty
from src.quick_report.models import CbmDefectFamilyPlan, CbmDefectGroup
from src.quick_report.utils import sanitize_filename


def build_cbm_defect_page_context(pe_info: dict, group: Any) -> dict:
    """Build the base context for CBM defect pages."""
    return pe_info.copy()


def generate_cbm_defect_pages(
    plan_or_groups: CbmDefectFamilyPlan | Sequence[Any],
    output_dir_or_spec: str | Path | QuickReportFamilySpec,
    substation_number_or_paths: int | dict[str, str],
    pe_info_or_output_dir: dict | str | Path = None,
    substation_number: int | None = None,
    pe_info: dict | None = None,
) -> list[Path]:
    """Generate CBM defect detail pages.

    Supports both:
    1. Typed plan signature: generate_cbm_defect_pages(plan, output_dir, substation_number, pe_info)
    2. Legacy signature: generate_cbm_defect_pages(groups, spec, template_paths, output_dir, substation_number, pe_info)
    """
    if isinstance(plan_or_groups, CbmDefectFamilyPlan):
        plan = plan_or_groups
        spec = plan.spec
        overview_template_path = plan.overview_template
        detail_template_paths: dict[str, Path] = dict(plan.detail_templates)
        groups = plan.groups
        out_dir = Path(output_dir_or_spec)
        sub_num = int(substation_number_or_paths)
        pe_ctx = pe_info_or_output_dir or {}
    else:
        groups = plan_or_groups
        spec = output_dir_or_spec
        template_paths = substation_number_or_paths
        out_dir = Path(pe_info_or_output_dir)
        sub_num = substation_number
        pe_ctx = pe_info or {}

        if not template_paths:
            return []
        for t_key, t_path in template_paths.items():
            if not Path(t_path).exists():
                raise FileNotFoundError(f"Template path does not exist for key {t_key}: {t_path}")

        overview_template_path = Path(template_paths[spec.overview_template_key]) if spec.overview_template_key in template_paths else None
        detail_template_paths = {
            role_spec.id: Path(template_paths[role_spec.template_key])
            for role_spec in spec.detail_roles
            if role_spec.template_key in template_paths
        }

    if not groups or not overview_template_path or not overview_template_path.exists():
        return []

    output_paths: list[Path] = []
    substation_number_str = f"{sub_num:03d}"
    output_dir_path = Path(out_dir)

    for group_index, group in enumerate(groups, start=1):
        group_item_key = _text_or_empty(_payload_get(group, "item_key", "")).strip()
        group_item_suffix = _text_or_empty(_payload_get(group, "item_suffix", "")).strip()
        item_key = sanitize_filename(group_item_key or f"GROUP {group_index}")

        # Overview page
        overview_rec = _payload_get(group, "overview", group)
        overview_context = build_cbm_defect_page_context(pe_ctx, group)
        overview_context.update(_build_family_render_context(
            spec, overview_rec, overview=True, item_key=group_item_key, item_suffix=group_item_suffix
        ))
        
        overview_filename = (
            f"{substation_number_str}_3 {spec.id.upper()} OVERVIEW.docx"
            if len(groups) == 1
            else f"{substation_number_str}_3 {spec.id.upper()} OVERVIEW_grp{group_index}.docx"
        )
        overview_output = output_dir_path / overview_filename
        
        _render_docx_template(overview_template_path, overview_output, overview_context)
        output_paths.append(overview_output)

        raw_detail_groups = _payload_get(group, "detail_groups", None)
        detail_groups = dict(raw_detail_groups) if isinstance(raw_detail_groups, tuple) else (raw_detail_groups or {})

        if not detail_groups:
            if spec.detail_roles:
                defects = _payload_get(group, "defects", [])
                detail_groups[spec.detail_roles[0].id] = list(defects) if isinstance(defects, tuple) else defects

        for role_index, role_spec in enumerate(spec.detail_roles, start=1):
            role_template_path = detail_template_paths.get(role_spec.id)
            if not role_template_path or not role_template_path.exists():
                continue

            role_defects = detail_groups.get(role_spec.id, [])
            for defect_index, defect_context in enumerate(role_defects, start=1):
                render_context = build_cbm_defect_page_context(pe_ctx, group)
                render_context.update(_build_family_render_context(
                    spec, defect_context, overview=False, item_key=group_item_key, item_suffix=group_item_suffix
                ))
                
                defect_suffix = ""
                if len(groups) > 1:
                    defect_suffix += f"_grp{group_index}"
                if len(role_defects) > 1:
                    defect_suffix += f"_part{defect_index}"

                defect_filename = f"{substation_number_str}_3 {spec.id.upper()} {item_key}{defect_suffix}.docx"
                defect_path = output_dir_path / defect_filename
                
                _render_docx_template(role_template_path, defect_path, render_context)
                output_paths.append(defect_path)

    return output_paths


# Re-export generate_quick_report_detail_pages as an alias to generate_cbm_defect_pages
generate_quick_report_detail_pages = generate_cbm_defect_pages
