"""Part 2: CBM Technical Summary Generator"""

from __future__ import annotations

import gc
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from docxtpl import DocxTemplate

from src.core.normalizers import format_temperature_float, normalize_us_characteristic
from src.quick_report.cbm_render import _build_jinja_env
from src.quick_report.models import CbmSummaryRow

if TYPE_CHECKING:
    from src.quick_report.defects import CbmDefectRecord


def format_temperature_reading(value: Any) -> str:
    """Format temperature reading as 1-decimal float string with ' °C' suffix.

    Returns '-' if empty/None.

    Examples:
        "50"      → "50.0 °C"
        "50.5"    → "50.5 °C"
        "50 °C"   → "50.0 °C"
        "50.5°C"  → "50.5 °C"
        None / "" / "-"  → "-"
    """
    formatted = format_temperature_float(value)
    if formatted == "-":
        return "-"
    return f"{formatted} °C"


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


def format_summary_equipment(
    record: CbmDefectRecord,
    pe_info: dict[str, Any] | None = None,
) -> str:
    """Format Part 2 Summary EQUIPMENT column with enriched multi-line equipment details."""
    equip = (record.equipment or "").strip()
    raw_id = (record.equipment_id or "").strip()
    eq_upper = equip.upper()

    # 1. Switchgear family (RMU SF6, RMU OIL, VCB, MRMU, CABLE SWG, EARTHING, SWITCHGEAR, GIS)
    if any(k in eq_upper for k in ("RMU", "VCB", "SWG", "SWITCHGEAR", "GIS", "MRMU", "EARTHING")):
        equipment_pkg = None
        if pe_info:
            for key in ("equipment_specs", "equipment_package", "equipment"):
                val = pe_info.get(key)
                if val is not None and hasattr(val, "switchgears"):
                    equipment_pkg = val
                    break

        swg_spec = None
        matched_panel = None
        if equipment_pkg and equipment_pkg.switchgears:
            from src.quick_report.cbm_render import _find_matching_switchgear_panel

            all_panels = [p for s in equipment_pkg.switchgears for p in s.panels]
            if raw_id:
                matched_panel = _find_matching_switchgear_panel(all_panels, raw_id)
            if matched_panel:
                for s in equipment_pkg.switchgears:
                    if matched_panel in s.panels:
                        swg_spec = s
                        break
            if not swg_spec:
                target_str = f"{equip} {raw_id} {record.hv_lv}".upper()
                for s in equipment_pkg.switchgears:
                    s_str = f"{s.switchgear_type} {s.model} {s.rating}".upper()
                    if ("33KV" in target_str or "33" in target_str) and (
                        "33KV" in s_str
                        or "33" in s_str
                        or any("3P" in p.panel_feeder_no.upper() for p in s.panels)
                    ):
                        swg_spec = s
                        break
                    elif ("11KV" in target_str or "11" in target_str) and (
                        "11KV" in s_str
                        or "11" in s_str
                        or any("1K" in p.panel_feeder_no.upper() for p in s.panels)
                    ):
                        swg_spec = s
                        break

        if swg_spec and swg_spec.switchgear_type:
            if equip.upper() in ("SWITCHGEAR", "SWG", "GIS", "VCB"):
                equip = swg_spec.switchgear_type

        if raw_id:
            if " - " in raw_id:
                parts = raw_id.split(" - ", 1)
                if parts[0].strip().upper().startswith(("GIS", "VCB", "SWG", "SWITCHGEAR", "RMU")):
                    p_feeder = parts[1].strip()
                    p_name = matched_panel.name if matched_panel and matched_panel.name else parts[1].strip()
                else:
                    p_feeder = parts[0].strip()
                    p_name = parts[1].strip()
                p_feeder_line = p_feeder if p_feeder.upper().startswith("PANEL") else f"PANEL {p_feeder}"
                return f"{equip}\n{p_feeder_line}\n{p_name}"
            else:
                p_feeder_line = raw_id if raw_id.upper().startswith("PANEL") else f"PANEL {raw_id}"
                if matched_panel and matched_panel.name:
                    return f"{equip}\n{p_feeder_line}\n{matched_panel.name}"
                return f"{equip}\n{p_feeder_line}"
        return equip

    # 2. Transformer family (CABLE LTX/DTX, LTX/DTX, PTX, CABLE PTX, TRANSFORMER)
    if any(k in eq_upper for k in ("TX", "TRANSFORMER")):
        equipment_pkg = None
        if pe_info:
            for key in ("equipment_specs", "equipment_package", "equipment"):
                val = pe_info.get(key)
                if val is not None and hasattr(val, "transformers"):
                    equipment_pkg = val
                    break
        transformers = equipment_pkg.transformers if equipment_pkg else ()
        matched_tx = None
        if transformers:
            if raw_id:
                for tx in transformers:
                    if tx.tx_id and tx.tx_id.strip().upper() == raw_id.strip().upper():
                        matched_tx = tx
                        break
            if not matched_tx:
                matched_tx = transformers[0]

        tx_label = raw_id or (matched_tx.tx_id if matched_tx else "")
        mfg = matched_tx.manufacturer if (matched_tx and matched_tx.manufacturer) else (record.brand or "")
        rating = matched_tx.rating_kva if (matched_tx and matched_tx.rating_kva) else (record.rating or "")
        spec_str = f"{mfg} {rating}".strip()

        if "CABLE" in eq_upper:
            if spec_str and tx_label:
                return f"{equip}\n{tx_label} - {spec_str}"
            elif tx_label:
                return f"{equip}\n{tx_label}"
            elif spec_str:
                return f"{equip}\n{spec_str}"
            return equip
        else:
            if spec_str and tx_label:
                return f"{tx_label} – {spec_str}"
            elif tx_label:
                return tx_label
            elif spec_str:
                return f"{equip} – {spec_str}"
            return equip

    # 3. LVDB / Feeder Pillar family
    if any(k in eq_upper for k in ("LVDB", "FP", "PILLAR")):
        if raw_id:
            return raw_id.replace(" - ", " – ")
        return equip

    # 4. Battery / Black Box / Other
    if raw_id and raw_id.upper() not in eq_upper:
        return f"{equip} {raw_id}"
    return equip


def prepare_tech_summary_rows(
    defects: Sequence[CbmDefectRecord],
    pe_info: dict[str, Any] | None = None,
) -> list[CbmSummaryRow]:
    """Prepare summary rows pairing IR, US, and TEV defect readings."""
    paired: dict[tuple[str, str, str], dict[str, str]] = {}

    for record in defects:
        equip = format_summary_equipment(record, pe_info=pe_info)
        raw_area = (record.defect_area or "").strip()
        remarks = (record.additional_remarks or "").strip()
        area_combined = f"{raw_area}/ {remarks}" if (raw_area and remarks) else (raw_area or remarks)
        key = (
            (record.equipment_id or record.equipment or "").strip().upper(),
            raw_area.upper(),
            remarks.upper(),
        )

        # Determine IR reading
        ir_raw = (record.ir_reading or "").strip()
        if not ir_raw and record.technology == "IR":
            ir_raw = (record.raw_measurement or "").strip()
        ir_read_str = format_temperature_reading(ir_raw) if (ir_raw and ir_raw != "-") else "-"

        # Determine US reading
        us_raw = (record.us_reading or "").strip()
        if not us_raw and record.technology == "US":
            us_raw = (record.raw_measurement or "").strip()
        us_read_str = format_db_reading(us_raw) if (us_raw and us_raw != "-") else "-"

        # Determine TEV reading
        tev_raw = (record.tev_reading or "").strip()
        if not tev_raw and record.technology == "TEV":
            tev_raw = (record.raw_measurement or "").strip()
        tev_read_str = format_db_reading(tev_raw) if (tev_raw and tev_raw != "-") else "-"

        # Determine severity: US defect characteristic (CORONA DISCHARGE, TRACKING, ARCING, etc.)
        severity = ""
        if record.technology == "US" or record.us_char:
            norm_char = normalize_us_characteristic(record.us_char)
            if norm_char not in ("-", "NORMAL"):
                severity = norm_char

        brand_val = (record.brand or "").strip()
        model_val = (record.model or "").strip()
        rating_val = (record.rating or "").strip()

        # Attribute missing brand/model/rating from matched equipment
        equipment_pkg = None
        if pe_info:
            for ep_key in ("equipment_specs", "equipment_package", "equipment"):
                val = pe_info.get(ep_key)
                if val is not None and hasattr(val, "switchgears"):
                    equipment_pkg = val
                    break

        if equipment_pkg and any(
            k in record.equipment.upper()
            for k in ("RMU", "VCB", "SWG", "SWITCHGEAR", "GIS", "MRMU", "EARTHING")
        ):
            from src.quick_report.cbm_render import _find_matching_switchgear_panel

            all_panels = [p for s in equipment_pkg.switchgears for p in s.panels]
            matched_panel = _find_matching_switchgear_panel(
                all_panels, record.equipment_id or record.equipment
            )
            swg_spec = None
            if matched_panel:
                for s in equipment_pkg.switchgears:
                    if matched_panel in s.panels:
                        swg_spec = s
                        break
            if not swg_spec:
                target_str = f"{record.equipment} {record.equipment_id} {record.hv_lv}".upper()
                for s in equipment_pkg.switchgears:
                    s_str = f"{s.switchgear_type} {s.model} {s.rating}".upper()
                    if ("33KV" in target_str or "33" in target_str) and (
                        "33KV" in s_str
                        or "33" in s_str
                        or any("3P" in p.panel_feeder_no.upper() for p in s.panels)
                    ):
                        swg_spec = s
                        break
                    elif ("11KV" in target_str or "11" in target_str) and (
                        "11KV" in s_str
                        or "11" in s_str
                        or any("1K" in p.panel_feeder_no.upper() for p in s.panels)
                    ):
                        swg_spec = s
                        break
            if swg_spec:
                if not brand_val and swg_spec.manufacturer:
                    brand_val = swg_spec.manufacturer.strip()
                if not model_val and swg_spec.model:
                    model_val = swg_spec.model.strip()
                if not rating_val and swg_spec.rating:
                    rating_val = swg_spec.rating.strip()

        if key not in paired:
            paired[key] = {
                "equipment": equip,
                "brand": brand_val,
                "model": model_val,
                "rating": rating_val,
                "defect_area": area_combined,
                "remarks": remarks,
                "ir_abs": ir_read_str,
                "us_dB": us_read_str,
                "tev_dB": tev_read_str,
                "severity": severity,
            }
        else:
            row_dict = paired[key]
            if not row_dict["equipment"] and equip:
                row_dict["equipment"] = equip
            if not row_dict["defect_area"] and area_combined:
                row_dict["defect_area"] = area_combined
            if not row_dict["remarks"] and remarks:
                row_dict["remarks"] = remarks
            if record.brand and not row_dict["brand"]:
                row_dict["brand"] = record.brand.strip()
            if record.model and not row_dict["model"]:
                row_dict["model"] = record.model.strip()
            if record.rating and not row_dict["rating"]:
                row_dict["rating"] = record.rating.strip()
            if ir_read_str != "-":
                row_dict["ir_abs"] = ir_read_str
            if us_read_str != "-":
                row_dict["us_dB"] = us_read_str
            if tev_read_str != "-":
                row_dict["tev_dB"] = tev_read_str
            if severity and not row_dict["severity"]:
                row_dict["severity"] = severity

    return [
        CbmSummaryRow(
            equipment=d["equipment"],
            brand=d["brand"],
            model=d["model"],
            rating=d["rating"],
            defect_area=d["defect_area"],
            remarks=d["remarks"],
            ir_reading=d["ir_abs"],
            us_reading=d["us_dB"],
            tev_reading=d["tev_dB"],
            ir_abs=d["ir_abs"],
            ir_delta="-",
            us_dB=d["us_dB"],
            tev_dB=d["tev_dB"],
            severity=d["severity"],
            status=d["severity"],
        )
        for d in paired.values()
    ]


def build_cbm_summary_context(
    pe_info: dict[str, Any],
    defects: Sequence[CbmDefectRecord],
) -> dict[str, Any]:
    """Pure context builder for CBM Technical Summary."""
    rows = prepare_tech_summary_rows(defects, pe_info=pe_info)
    context = pe_info.copy()
    context["defects"] = [
        {
            "equipment": r.equipment,
            "brand": r.brand,
            "model": r.model,
            "rating": r.rating,
            "defect_area": r.defect_area,
            "remarks": r.remarks,
            "ir_reading": r.ir_reading,
            "us_reading": r.us_reading,
            "tev_reading": r.tev_reading,
            "ir_abs": r.ir_abs,
            "ir_delta": r.ir_delta,
            "us_dB": r.us_dB,
            "tev_dB": r.tev_dB,
            "severity": r.severity,
            "status": r.status,
        }
        for r in rows
    ]
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
    out_path = out_dir / f"{sub_num_int:03d}_02_cbm_summary.docx"

    doc = DocxTemplate(str(template_p))
    doc.render(context, jinja_env=_build_jinja_env(), autoescape=True)
    doc.save(str(out_path))
    del doc
    gc.collect()
    return out_path
