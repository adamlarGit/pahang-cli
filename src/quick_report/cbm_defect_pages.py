"""CBM Defect Detail Pages generation (Part 4)."""

from __future__ import annotations

from pathlib import Path
from src.quick_report.cbm_family import QuickReportFamilySpec
from src.quick_report.cbm_render import _build_family_render_context, _render_docx_template, _payload_get, _text_or_empty
from src.quick_report.utils import sanitize_filename


def build_cbm_defect_page_context(pe_info: dict, group: dict) -> dict:
    """Build the base context for CBM defect pages."""
    return pe_info.copy()


def generate_cbm_defect_pages(
    groups: list[dict],
    spec: QuickReportFamilySpec,
    template_paths: dict[str, str],
    output_dir: str | Path,
    substation_number: int,
    pe_info: dict
) -> list[Path]:
    """Generate CBM defect detail pages (Part 4)."""
    if not groups:
        return []

    for t_key, t_path in template_paths.items():
        if not Path(t_path).exists():
            raise FileNotFoundError(f"Template path does not exist for key {t_key}: {t_path}")

    overview_template_path = template_paths.get(spec.overview_template_key)
    if not overview_template_path:
        return []

    output_paths: list[Path] = []
    substation_number_str = f"{substation_number:03d}"
    output_dir_path = Path(output_dir)

    for group_index, group in enumerate(groups, start=1):
        group_item_key = _text_or_empty(_payload_get(group, "item_key", "")).strip()
        group_item_suffix = _text_or_empty(_payload_get(group, "item_suffix", "")).strip()
        item_key = sanitize_filename(group_item_key or f"GROUP {group_index}")

        # Overview page
        overview_context = build_cbm_defect_page_context(pe_info, group)
        overview_context.update(_build_family_render_context(
            spec, _payload_get(group, "overview", {}), overview=True, item_key=group_item_key, item_suffix=group_item_suffix
        ))
        
        overview_filename = (
            f"{substation_number_str}_3 {spec.id.upper()} OVERVIEW.docx"
            if len(groups) == 1
            else f"{substation_number_str}_3 {spec.id.upper()} OVERVIEW_grp{group_index}.docx"
        )
        overview_output = output_dir_path / overview_filename
        
        _render_docx_template(overview_template_path, overview_output, overview_context)
        output_paths.append(overview_output)

        detail_groups = _payload_get(group, "detail_groups", None)
        if not detail_groups:
            detail_groups = {}
            if spec.detail_roles:
                detail_groups[spec.detail_roles[0].id] = list(_payload_get(group, "defects", []))
        for role_index, role_spec in enumerate(spec.detail_roles, start=1):
            role_template_path = template_paths.get(role_spec.template_key)
            if not role_template_path:
                continue

            role_defects = detail_groups.get(role_spec.id, [])
            for defect_index, defect_context in enumerate(role_defects, start=1):
                render_context = build_cbm_defect_page_context(pe_info, group)
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
