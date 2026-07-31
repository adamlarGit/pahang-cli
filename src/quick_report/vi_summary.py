"""Part 3: VI Defect Summary Generator"""
from pathlib import Path

import docx

from src.quick_report.utils import format_table_cell


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
    """Generate VI defect summary page."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_vi_summary_context(pe_info, defects)
    formatted_defects = context.get("defects", [])

    doc = docx.Document(str(template_path))
    table = doc.tables[0]

    # Clear template placeholder / loop rows after row 0
    while len(table.rows) > 1:
        tr = table.rows[-1]._tr
        table._tbl.remove(tr)

    headers = ["NO.", "EQUIPMENT", "DEFECT DESCRIPTION", "REMARKS"]
    header_row = table.rows[0]
    for j, h in enumerate(headers):
        format_table_cell(header_row.cells[j], h, font_size_pt=10, bold=True, fill="D9D9D9")

    for idx, d in enumerate(formatted_defects, start=1):
        row = table.add_row()
        values = [
            str(idx),
            str(d.get("equipment") or ""),
            str(d.get("defect_area") or ""),
            str(d.get("remarks") or ""),
        ]
        for j, val in enumerate(values):
            format_table_cell(row.cells[j], val, font_size_pt=10, bold=False, fill=None)

    sub_num_int = int(substation_number) if str(substation_number).isdigit() else substation_number
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sub_num_int:03d}_2 VI SUMMARY.docx"
    doc.save(out_path)
    return out_path
