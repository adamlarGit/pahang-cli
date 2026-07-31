"""Part 2: CBM Technical Summary Generator"""
from dataclasses import dataclass
from pathlib import Path

import docx

from src.quick_report.utils import format_table_cell


def _text_or_empty(value) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except Exception:
        pass
    return str(value)


def _format_db(val: str) -> str:
    if not val or val == "-":
        return "-"
    if "dB" in val:
        return val
    try:
        f = float(val)
        if f.is_integer():
            return f"{int(f)}dB"
        return f"{f}dB"
    except Exception:
        return f"{val}dB"


@dataclass
class PreparedTechSummaryRow:
    equipment: str
    brand: str
    model: str
    rating: str
    defect_area: str
    remarks: str
    ir_reading: str
    us_reading: str
    tev_reading: str
    ir_abs: str = "-"
    ir_delta: str = "-"
    us_dB: str = "-"
    tev_dB: str = "-"
    status: str = "PENDING"


def prepare_tech_summary_rows(defects: list[dict]) -> list[PreparedTechSummaryRow]:
    """Prepare summary rows pairing IR, US, and TEV defect readings."""
    paired: dict[tuple[str, str, str], PreparedTechSummaryRow] = {}

    for defect in defects:
        equip = _text_or_empty(defect.get("equipment")).strip()
        area = _text_or_empty(defect.get("defect_area")).strip()
        remarks = _text_or_empty(defect.get("additional_remarks") or defect.get("remarks")).strip()
        key = (equip, area, remarks)

        tech = _text_or_empty(defect.get("technology")).upper()
        raw_val = defect.get("reading") or defect.get("temperature") or defect.get("us_value") or defect.get("tev_value") or ""
        val_str = str(raw_val).strip()

        ir_read_str = f"{val_str} °C" if (tech == "IR" and val_str and "°C" not in val_str) else (val_str if tech == "IR" else "-")
        us_read_str = _format_db(val_str) if tech == "US" else "-"
        tev_read_str = _format_db(val_str) if tech == "TEV" else "-"

        if key not in paired:
            paired[key] = PreparedTechSummaryRow(
                equipment=equip,
                brand=_text_or_empty(defect.get("brand")),
                model=_text_or_empty(defect.get("model")),
                rating=_text_or_empty(defect.get("rating")),
                defect_area=area,
                remarks=remarks,
                ir_reading=ir_read_str,
                us_reading=us_read_str,
                tev_reading=tev_read_str,
                ir_abs=f"{val_str} °C" if (tech == "IR" and val_str) else "-",
                ir_delta=str(defect.get("ir_delta") or "-"),
                us_dB=_format_db(val_str) if tech == "US" else "-",
                tev_dB=_format_db(val_str) if tech == "TEV" else "-",
                status=str(defect.get("status") or "PENDING"),
            )
        else:
            row = paired[key]
            if tech == "IR":
                row.ir_reading = ir_read_str
                row.ir_abs = f"{val_str} °C" if val_str else "-"
            elif tech == "US":
                row.us_reading = us_read_str
                row.us_dB = _format_db(val_str)
            elif tech == "TEV":
                row.tev_reading = tev_read_str
                row.tev_dB = _format_db(val_str)

    return list(paired.values())


def build_cbm_summary_context(pe_info: dict, defects: list[dict]) -> dict:
    """Pure context builder for CBM Technical Summary."""
    rows = prepare_tech_summary_rows(defects)
    context = pe_info.copy()
    context["defects"] = [row.__dict__ for row in rows]
    return context


def _get_field(row: PreparedTechSummaryRow | dict, field: str, default: str = "-") -> str:
    if isinstance(row, dict):
        val = row.get(field, default)
    else:
        val = getattr(row, field, default)
    return str(val) if val is not None and str(val).strip() != "" else default


def generate_cbm_tech_summary(
    pe_info: dict,
    defects: list[dict],
    template_path: str | Path,
    output_dir: str | Path,
    substation_number: int,
) -> Path:
    """Generate CBM technical summary page joining IR, US, and TEV."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    prepared_rows = prepare_tech_summary_rows(defects)

    doc = docx.Document(str(template_path))
    table = doc.tables[0]

    # Clear template placeholder loop rows after row 0
    while len(table.rows) > 1:
        tr = table.rows[-1]._tr
        table._tbl.remove(tr)

    # Format header row 0
    header_row = table.rows[0]
    for cell in header_row.cells:
        format_table_cell(cell, cell.text.strip(), font_size_pt=10, bold=True, fill="D9D9D9")

    num_cols = len(header_row.cells)

    for idx, r in enumerate(prepared_rows, start=1):
        new_row = table.add_row()
        equip = _get_field(r, "equipment", "")
        area = _get_field(r, "defect_area", "")
        ir_abs = _get_field(r, "ir_abs", "-")
        if ir_abs == "-":
            ir_abs = _get_field(r, "ir_reading", "-")
        ir_delta = _get_field(r, "ir_delta", "-")
        us_dB = _get_field(r, "us_dB", "-")
        if us_dB == "-":
            us_dB = _get_field(r, "us_reading", "-")
        tev_dB = _get_field(r, "tev_dB", "-")
        if tev_dB == "-":
            tev_dB = _get_field(r, "tev_reading", "-")
        status = _get_field(r, "status", "PENDING")

        if num_cols == 6:
            values = [str(idx), equip, area, ir_abs, ir_delta, status]
        elif num_cols == 8:
            values = [str(idx), equip, area, ir_abs, ir_delta, us_dB, tev_dB, status]
        else:
            # Dynamic fallback for other column configurations
            values = [str(idx), equip, area, ir_abs, ir_delta]
            if num_cols >= 7:
                values.append(us_dB)
            if num_cols >= 8:
                values.append(tev_dB)
            while len(values) < num_cols:
                values.append(status if len(values) == num_cols - 1 else "-")

        for j, val in enumerate(values[:num_cols]):
            format_table_cell(new_row.cells[j], str(val), font_size_pt=10, bold=False, fill=None)

    sub_num_int = int(substation_number) if str(substation_number).isdigit() else substation_number
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sub_num_int:03d}_2 CBM SUMMARY.docx"
    doc.save(out_path)
    return out_path
