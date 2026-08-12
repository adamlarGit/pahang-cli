"""Part 2: CBM Technical Summary Generator"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from src.quick_report.cbm_render import _render_docx_template
from src.quick_report.models import CbmSummaryRow

if TYPE_CHECKING:
    from src.quick_report.defects import CbmDefectRecord


def format_temperature_reading(value: str) -> str:
    """Format temperature reading string with ' °C' suffix if non-empty, or '-' if empty/None."""
    if value is None:
        return "-"
    val_str = str(value).strip()
    if not val_str or val_str == "-":
        return "-"
    if "°C" in val_str:
        if val_str.endswith("°C") and not val_str.endswith(" °C"):
            return val_str[:-2].strip() + " °C"
        return val_str
    return f"{val_str} °C"


def format_db_reading(value: str) -> str:
    """Format dB reading string with 'dB' suffix if non-empty, or '-' if empty/None."""
    if value is None:
        return "-"
    val_str = str(value).strip()
    if not val_str or val_str == "-":
        return "-"
    if "dB" in val_str:
        return val_str
    try:
        f = float(val_str)
        if f.is_integer():
            return f"{int(f)}dB"
        return f"{f}dB"
    except Exception:
        return f"{val_str}dB"


def prepare_tech_summary_rows(
    defects: Sequence[CbmDefectRecord],
) -> list[CbmSummaryRow]:
    """Prepare summary rows pairing IR, US, and TEV defect readings."""
    paired: dict[tuple[str, str, str], dict[str, str]] = {}

    for record in defects:
        equip = (record.equipment or "").strip()
        area = (record.defect_area or "").strip()
        remarks = (record.additional_remarks or "").strip()
        key = (equip, area, remarks)

        # Determine IR reading strictly from record.ir_reading
        ir_raw = (record.ir_reading or "").strip()
        ir_read_str = format_temperature_reading(ir_raw) if (ir_raw and ir_raw != "-") else "-"

        # Determine US reading strictly from record.us_reading
        us_raw = (record.us_reading or "").strip()
        us_read_str = format_db_reading(us_raw) if (us_raw and us_raw != "-") else "-"

        # Determine TEV reading strictly from record.tev_reading
        tev_raw = (record.tev_reading or "").strip()
        tev_read_str = format_db_reading(tev_raw) if (tev_raw and tev_raw != "-") else "-"

        if key not in paired:
            paired[key] = {
                "equipment": equip,
                "brand": (record.brand or "").strip(),
                "model": (record.model or "").strip(),
                "rating": (record.rating or "").strip(),
                "defect_area": area,
                "remarks": remarks,
                "ir_reading": ir_read_str,
                "us_reading": us_read_str,
                "tev_reading": tev_read_str,
            }
        else:
            row_dict = paired[key]
            if ir_read_str != "-":
                row_dict["ir_reading"] = ir_read_str
            if us_read_str != "-":
                row_dict["us_reading"] = us_read_str
            if tev_read_str != "-":
                row_dict["tev_reading"] = tev_read_str
            if record.brand and not row_dict["brand"]:
                row_dict["brand"] = record.brand.strip()
            if record.model and not row_dict["model"]:
                row_dict["model"] = record.model.strip()
            if record.rating and not row_dict["rating"]:
                row_dict["rating"] = record.rating.strip()

    return [
        CbmSummaryRow(
            equipment=d["equipment"],
            brand=d["brand"],
            model=d["model"],
            rating=d["rating"],
            defect_area=d["defect_area"],
            remarks=d["remarks"],
            ir_reading=d["ir_reading"],
            us_reading=d["us_reading"],
            tev_reading=d["tev_reading"],
            ir_abs=d["ir_reading"],
            ir_delta="-",
            us_dB=d["us_reading"],
            tev_dB=d["tev_reading"],
            status="MAJOR",
        )
        for d in paired.values()
    ]


def build_cbm_summary_context(
    pe_info: dict[str, Any],
    defects: Sequence[CbmDefectRecord],
) -> dict[str, Any]:
    """Pure context builder for CBM Technical Summary."""
    rows = prepare_tech_summary_rows(defects)
    context = pe_info.copy()
    context["defects"] = [row.__dict__ for row in rows]
    return context


def generate_cbm_tech_summary(
    pe_info: dict[str, Any],
    defects: Sequence[CbmDefectRecord],
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
