"""Part 3: VI Defect Summary Generator"""
from pathlib import Path

from src.quick_report.cbm_render import _render_docx_template


def build_vi_summary_context(pe_info: dict, defects: list[dict]) -> dict:
    """Pure context builder for VI Defect Summary."""
    formatted_defects = []
    for d in defects:
        item = d.copy()
        item["equipment"] = d.get("equipment") or ""
        item["defect_area"] = d.get("defect_area") or d.get("description") or ""
        item["remarks"] = d.get("remarks") or d.get("additional_remarks") or d.get("remark") or ""
        item["description"] = item["defect_area"]
        item["remark"] = item["remarks"]
        formatted_defects.append(item)

    context = pe_info.copy()
    context["defects"] = formatted_defects
    return context


def generate_vi_summary(
    pe_info: dict,
    defects: list[dict],
    template_path: str | Path,
    output_dir: str | Path,
    substation_number: int,
) -> Path:
    """Generate VI defect summary page by rendering the Jinja2 docx template."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_vi_summary_context(pe_info, defects)

    sub_num_int = int(substation_number) if str(substation_number).isdigit() else substation_number
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sub_num_int:03d}_2 VI SUMMARY.docx"

    return _render_docx_template(template_p, out_path, context)
