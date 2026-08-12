from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from src.quick_report.cbm_render import _render_docx_template
from src.quick_report.models import ViSummaryRow

if TYPE_CHECKING:
    from src.quick_report.defects import ViDefectRecord


def prepare_vi_summary_rows(defects: Sequence[ViDefectRecord]) -> list[ViSummaryRow]:
    """Prepare strongly-typed VI summary rows from VI defect records."""
    return [
        ViSummaryRow(
            equipment=record.equipment,
            defect_area=record.defect_area,
            remarks=record.additional_remarks,
        )
        for record in defects
    ]


def build_vi_summary_context(pe_info: dict[str, Any], defects: Sequence[ViDefectRecord]) -> dict[str, Any]:
    """Pure context builder for VI Defect Summary."""
    rows = prepare_vi_summary_rows(defects)
    formatted_defects = [
        {
            "equipment": r.equipment,
            "defect_area": r.defect_area,
            "remarks": r.remarks,
            "additional_remarks": r.remarks,
            "description": r.defect_area,
            "remark": r.remarks,
        }
        for r in rows
    ]

    context = pe_info.copy()
    context["defects"] = formatted_defects
    return context


def generate_vi_summary(
    pe_info: dict[str, Any],
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

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{substation_number:03d}_2 VI SUMMARY.docx"

    return _render_docx_template(template_p, out_path, context)
