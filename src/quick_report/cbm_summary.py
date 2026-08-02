"""Part 2: CBM Technical Summary Generator"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.quick_report.cbm_render import _render_docx_template

if TYPE_CHECKING:
    from src.quick_report.defects import CbmDefectRecord


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
    status: str = ""


def _get_field(defect: object, key: str, default: str = "") -> str:
    if isinstance(defect, dict):
        val = defect.get(key, default)
        return str(val) if val is not None else default
    val = getattr(defect, key, default)
    return str(val) if val is not None else default


def prepare_tech_summary_rows(defects: Sequence[CbmDefectRecord | dict]) -> list[PreparedTechSummaryRow]:
    """Prepare summary rows pairing IR, US, and TEV defect readings."""
    paired: dict[tuple[str, str, str], PreparedTechSummaryRow] = {}

    for defect in defects:
        equip = _text_or_empty(_get_field(defect, "equipment")).strip()
        area = _text_or_empty(_get_field(defect, "defect_area")).strip()
        remarks = _text_or_empty(_get_field(defect, "additional_remarks")).strip()
        key = (equip, area, remarks)

        tech = _text_or_empty(_get_field(defect, "technology")).upper()
        raw_val = _get_field(defect, "raw_measurement")
        val_str = str(raw_val).strip()

        ir_read_str = f"{val_str} °C" if (tech == "IR" and val_str and "°C" not in val_str) else (val_str if tech == "IR" else "-")
        us_read_str = _format_db(val_str) if tech == "US" else "-"
        tev_read_str = _format_db(val_str) if tech == "TEV" else "-"

        if key not in paired:
            paired[key] = PreparedTechSummaryRow(
                equipment=equip,
                brand=_text_or_empty(_get_field(defect, "brand")),
                model=_text_or_empty(_get_field(defect, "model")),
                rating=_text_or_empty(_get_field(defect, "rating")),
                defect_area=area,
                remarks=remarks,
                ir_reading=ir_read_str,
                us_reading=us_read_str,
                tev_reading=tev_read_str,
                ir_abs=f"{val_str} °C" if (tech == "IR" and val_str) else "-",
                ir_delta=str(_get_field(defect, "ir_delta", "-") or "-"),
                us_dB=_format_db(val_str) if tech == "US" else "-",
                tev_dB=_format_db(val_str) if tech == "TEV" else "-",
                status=str(_get_field(defect, "status", "") or ""),
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


def build_cbm_summary_context(pe_info: dict, defects: Sequence[CbmDefectRecord | dict]) -> dict:
    """Pure context builder for CBM Technical Summary."""
    rows = prepare_tech_summary_rows(defects)
    context = pe_info.copy()
    context["defects"] = [row.__dict__ for row in rows]
    return context


def generate_cbm_tech_summary(
    pe_info: dict,
    defects: Sequence[CbmDefectRecord | dict],
    template_path: str | Path,
    output_dir: str | Path,
    substation_number: int,
) -> Path:
    """Generate CBM technical summary page joining IR, US, and TEV via DocxTemplate."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    context = build_cbm_summary_context(pe_info, defects)

    sub_num_int = int(substation_number) if str(substation_number).isdigit() else substation_number
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sub_num_int:03d}_2 CBM SUMMARY.docx"

    return _render_docx_template(template_p, out_path, context)
