from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.quick_report.cbm_render import _render_docx_template

if TYPE_CHECKING:
    from src.quick_report.defects import ViDefectRecord


def build_vi_summary_context(pe_info: dict, defects: Sequence[ViDefectRecord]) -> dict:
    """Pure context builder for VI Defect Summary."""
    formatted_defects = []
    for d in defects:
        if hasattr(d, "to_dict"):
            item = d.to_dict()
        elif isinstance(d, dict):
            item = d.copy()
        else:
            item = {}
        equip = getattr(d, "equipment", None) or item.get("equipment") or ""
        defect_area = getattr(d, "defect_area", None) or item.get("defect_area") or ""
        remarks = getattr(d, "additional_remarks", None) or item.get("additional_remarks") or ""
        item["equipment"] = equip
        item["defect_area"] = defect_area
        item["remarks"] = remarks
        item["additional_remarks"] = remarks
        item["description"] = defect_area
        item["remark"] = remarks
        formatted_defects.append(item)

    context = pe_info.copy()
    context["defects"] = formatted_defects
    return context


def generate_vi_summary(
    pe_info: dict,
    defects: Sequence[ViDefectRecord],
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
