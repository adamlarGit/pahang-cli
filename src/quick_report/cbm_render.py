"""CBM quick-report rendering engine and context builders."""

from __future__ import annotations

import gc
from pathlib import Path
import re
from typing import Any

from docxtpl import DocxTemplate
from jinja2 import Environment, Undefined

from src.quick_report.cbm_family import QuickReportFamilySpec
from src.quick_report.defects import CbmDefectRecord
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    TransformerSpec,
)


class PreservingUndefined(Undefined):
    """Render undefined quick-report Jinja placeholders as '-'."""

    def __str__(self) -> str:
        return "-"

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return self

    def __getitem__(self, name):
        return self

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __len__(self):
        return 0


class QuickReportContext(dict):
    """Dict wrapper that renders missing/empty values as clean '-'."""

    def __init__(self, value: dict | None = None, path: str = ""):
        super().__init__()
        self._path = path
        if value:
            for key, item in value.items():
                super().__setitem__(key, self._wrap_value(item, self._child_path(key)))

    def _child_path(self, key: str) -> str:
        return f"{self._path}.{key}" if self._path else str(key)

    def _wrap_value(self, value, path: str):
        if isinstance(value, dict):
            return QuickReportContext(value, path)
        if isinstance(value, list):
            return [self._wrap_value(item, path) for item in value]
        if value is None:
            return "-"
        if isinstance(value, str) and not value.strip():
            return "-"
        return value

    def __missing__(self, key):
        return "-"

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            return "-"


def _build_jinja_env() -> Environment:
    """Create a Jinja environment that renders undefined placeholders as '-'."""
    return Environment(undefined=PreservingUndefined, autoescape=True)



def _preserve_blank_render_values(value):
    """Wrap quick-report render data so missing keys render as clean '-'."""
    if isinstance(value, dict):
        return QuickReportContext(value)
    if isinstance(value, list):
        return [QuickReportContext(item) if isinstance(item, dict) else item for item in value]
    return value


def _render_docx_template(template_path: str | Path, output_path: Path, context: dict) -> Path:
    """Render a DocxTemplate with quick-report placeholder semantics."""
    doc = DocxTemplate(str(template_path))
    doc.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env(), autoescape=True)
    doc.save(output_path)
    del doc
    gc.collect()
    return output_path


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except Exception:
        pass
    return str(value).strip()


def _fallback_dash(value: Any) -> str:
    s = _text_or_empty(value)
    return s if s else "-"


def _format_detail_area(defect_area: Any, additional_remarks: Any, *, overview: bool = False) -> str:
    if overview:
        return "OVERVIEW"
    defect_area_text = _text_or_empty(defect_area)
    remarks_text = _text_or_empty(additional_remarks)
    if remarks_text:
        return f"{defect_area_text}/ {remarks_text}" if defect_area_text else remarks_text
    return defect_area_text if defect_area_text else "-"


def _extract_equipment_package(pe_info: dict[str, Any] | None) -> SubstationEquipmentPackage | None:
    if not pe_info:
        return None
    for key in ("equipment_specs", "equipment_package", "equipment"):
        val = pe_info.get(key)
        if isinstance(val, SubstationEquipmentPackage):
            return val
    return None


def _find_matching_switchgear_panel(
    panels: list[SwitchgearPanelSpec] | tuple[SwitchgearPanelSpec, ...],
    target_id: str,
) -> SwitchgearPanelSpec | None:
    if not panels or not target_id:
        return None
    t = target_id.strip().upper()
    if not t:
        return None

    # 1. Exact match on panel_feeder_no or name
    for p in panels:
        if p.panel_feeder_no and p.panel_feeder_no.strip().upper() == t:
            return p
        if p.name and p.name.strip().upper() == t:
            return p

    # 2. Canonical panel naming match (e.g. PANEL 1, P1)
    for p in panels:
        p_no_str = str(p.panel_no)
        p_feeder = p.panel_feeder_no.strip().upper()
        if t in (f"PANEL {p_no_str}", f"P{p_no_str}", f"PANEL {p_feeder}", f"P{p_feeder}"):
            return p

    # 3. Numeric digit extraction matching
    t_digits = re.findall(r"\d+", t)
    if t_digits:
        t_num = t_digits[0]
        for p in panels:
            if str(p.panel_no) == t_num or p.panel_feeder_no.strip() == t_num:
                return p

    # 4. Substring containment if name has >= 2 chars
    for p in panels:
        p_name = p.name.strip().upper()
        if len(p_name) >= 2 and (p_name in t or t in p_name):
            return p

    return None


def _find_matching_transformer(
    transformers: tuple[TransformerSpec, ...],
    target_id: str,
) -> TransformerSpec | None:
    if not transformers:
        return None
    t = target_id.strip().upper()
    if t:
        for tx in transformers:
            if tx.tx_id and tx.tx_id.strip().upper() == t:
                return tx
        t_digits = re.findall(r"\d+", t)
        if t_digits:
            t_num = t_digits[0]
            for tx in transformers:
                tx_digits = re.findall(r"\d+", tx.tx_id)
                if tx_digits and tx_digits[0] == t_num:
                    return tx
    if len(transformers) == 1:
        return transformers[0]
    return None


def _find_matching_lvdb(
    lvdb_specs: tuple[LVDBSpec, ...],
    target_id: str,
) -> LVDBSpec | None:
    if not lvdb_specs:
        return None
    t = target_id.strip().upper()
    if t:
        for lv in lvdb_specs:
            if lv.name and lv.name.strip().upper() == t:
                return lv
            if lv.source and lv.source.strip().upper() in t:
                return lv
            combined = f"{lv.label} {lv.source}".strip().upper()
            if combined and combined in t:
                return lv
        t_digits = re.findall(r"\d+", t)
        if t_digits:
            t_num = t_digits[0]
            for lv in lvdb_specs:
                lv_digits = re.findall(r"\d+", lv.name)
                if lv_digits and lv_digits[0] == t_num:
                    return lv
    if len(lvdb_specs) == 1:
        return lvdb_specs[0]
    return None


def _find_matching_battery(
    battery_banks: tuple[BatteryBankSpec, ...],
    target_id: str,
) -> BatteryBankSpec | None:
    if not battery_banks:
        return None
    t = target_id.strip().upper()
    if t:
        for b in battery_banks:
            if b.name and (b.name.strip().upper() == t or t in b.name.strip().upper()):
                return b
        t_digits = re.findall(r"\d+", t)
        if t_digits:
            t_num = t_digits[0]
            for b in battery_banks:
                b_digits = re.findall(r"\d+", b.name)
                if b_digits and b_digits[0] == t_num:
                    return b
    if len(battery_banks) == 1:
        return battery_banks[0]
    return None


def _build_fp_lvdb_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    equipment = _text_or_empty(record.equipment).strip()
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)

    raw_id = record.equipment_id or resolved_item_key or resolved_item_suffix
    if " - " in raw_id:
        parts = raw_id.split(" - ", 1)
        labelsource = parts[0].strip()
        feederno = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "-"
    else:
        labelsource = raw_id.strip()
        feederno = "-"

    equipment_pkg = _extract_equipment_package(pe_info)
    lvdb_specs = equipment_pkg.lvdb_specs if equipment_pkg else ()
    matched_lv = _find_matching_lvdb(lvdb_specs, labelsource or raw_id)

    fp_mfg = (matched_lv.manufacturer if matched_lv and matched_lv.manufacturer else "") or _text_or_empty(record.brand)
    
    combined_model = f"{equipment} {record.model}".upper()
    if any(k in combined_model for k in ("(J)", "J-SLOTTED", "J SLOTTED", "J-SLOT", "LVDB")):
        fp_model = "J-SLOTTED"
    elif any(k in combined_model for k in ("(D)", " DIN", "DIN ", "-DIN", "/DIN")):
        fp_model = "DIN"
    elif record.model:
        fp_model = _text_or_empty(record.model)
    elif matched_lv and matched_lv.label:
        fp_model = matched_lv.label
    else:
        fp_model = ""

    fp_rating = _text_or_empty(record.rating) or (matched_lv.rating if matched_lv else "")
    fp_serial = matched_lv.serial_no if matched_lv else ""
    
    fp_cable = ""
    if equipment_pkg:
        for swg in equipment_pkg.switchgears:
            for p in swg.panels:
                if p.cable_type:
                    fp_cable = p.cable_type
                    break
            if fp_cable:
                break
    if not fp_cable and "CABLE" in equipment.upper():
        fp_cable = equipment

    return {
        "fp": {
            "labelsource": _fallback_dash(labelsource),
            "feederno": _fallback_dash(feederno),
            "area": area,
            "manufacturer": _fallback_dash(fp_mfg),
            "model": _fallback_dash(fp_model),
            "rating": _fallback_dash(fp_rating),
            "serialnumber": _fallback_dash(fp_serial),
            "cabletype": _fallback_dash(fp_cable),
            "ir": {"reading": _fallback_dash(record.ir_reading)},
            "us": {
                "reading": _fallback_dash(record.us_reading),
                "char": _fallback_dash(record.us_char),
            },
            "tev": {
                "reading": _fallback_dash(record.tev_reading),
                "char": _fallback_dash(record.tev_char),
            },
        }
    }


def _build_swg_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    equipment = _text_or_empty(record.equipment).strip()
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)

    equipment_pkg = _extract_equipment_package(pe_info)
    swg_spec = equipment_pkg.switchgear if equipment_pkg and equipment_pkg.switchgears else None

    # SWG header fields
    swg_manufacturer = (swg_spec.manufacturer if swg_spec and swg_spec.manufacturer else "") or _text_or_empty(record.brand)
    swg_model = _text_or_empty(record.model) or (swg_spec.model if swg_spec else "")
    swg_rating = _text_or_empty(record.rating) or (swg_spec.rating if swg_spec else "")
    swg_serial = swg_spec.serial_no if swg_spec else ""
    swg_type = equipment or (swg_spec.switchgear_type if swg_spec else "")

    # Match panel in testsheet
    all_panels = [p for swg in (equipment_pkg.switchgears if equipment_pkg else ()) for p in swg.panels]
    panel_match_target = record.equipment_id or resolved_item_suffix or resolved_item_key
    matched_panel = _find_matching_switchgear_panel(all_panels, panel_match_target)

    if matched_panel:
        panel_loadamp = matched_panel.load_amp
        panel_heateramp = matched_panel.heater_amp
        panel_breakerstatus = matched_panel.status
        panel_cabletype = matched_panel.cable_type or (equipment if "CABLE" in equipment.upper() else "")
        panel_serialnumber = matched_panel.serial_no
    else:
        panel_loadamp = ""
        panel_heateramp = ""
        panel_breakerstatus = ""
        panel_cabletype = equipment if "CABLE" in equipment.upper() else ""
        panel_serialnumber = ""

    if " - " in panel_match_target:
        parts = panel_match_target.split(" - ", 1)
        panel_linknumber = parts[0].strip()
        panel_name = parts[1].strip()
    else:
        panel_name = panel_match_target
        panel_linknumber = panel_match_target

    return {
        "swg": {
            "area": area,
            "manufacturer": _fallback_dash(swg_manufacturer),
            "model": _fallback_dash(swg_model),
            "rating": _fallback_dash(swg_rating),
            "serialnumber": _fallback_dash(swg_serial),
            "type": _fallback_dash(swg_type),
        },
        "panel": {
            "name": _fallback_dash(panel_name),
            "linknumber": _fallback_dash(panel_linknumber),
            "area": area,
            "breakerstatus": _fallback_dash(panel_breakerstatus),
            "busbarposition": "-",
            "cabletype": _fallback_dash(panel_cabletype),
            "heateramp": _fallback_dash(panel_heateramp),
            "loadamp": _fallback_dash(panel_loadamp),
            "serialnumber": _fallback_dash(panel_serialnumber),
            "ir": {"reading": _fallback_dash(record.ir_reading)},
            "us": {
                "reading": _fallback_dash(record.us_reading),
                "char": _fallback_dash(record.us_char),
            },
            "tev": {
                "reading": _fallback_dash(record.tev_reading),
                "char": _fallback_dash(record.tev_char),
            },
        },
    }


def _build_tx_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    equipment = _text_or_empty(record.equipment).strip()
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)

    equipment_pkg = _extract_equipment_package(pe_info)
    transformers = equipment_pkg.transformers if equipment_pkg else ()
    tx_match_target = record.equipment_id or resolved_item_key
    matched_tx = _find_matching_transformer(transformers, tx_match_target)

    # Location from substation building_type (overview) or HV/LV side (detail)
    if overview:
        tx_location = ""
        if pe_info and isinstance(pe_info.get("substation"), dict):
            tx_location = pe_info["substation"].get("building_type", "")
        if not tx_location and resolved_item_suffix:
            tx_location = resolved_item_suffix
    else:
        search_loc = f"{record.defect_area} {record.additional_remarks} {record.equipment_id} {equipment}".upper()
        if any(k in search_loc for k in ("HV", "11KV", "33KV")):
            tx_location = "HV - SIDE"
        elif any(k in search_loc for k in ("LV", "415V")):
            tx_location = "LV - SIDE"
        else:
            tx_location = ""
            if pe_info and isinstance(pe_info.get("substation"), dict):
                tx_location = pe_info["substation"].get("building_type", "")
            if not tx_location and resolved_item_suffix:
                tx_location = resolved_item_suffix

    tx_mfg = (matched_tx.manufacturer if matched_tx and matched_tx.manufacturer else "") or _text_or_empty(record.brand)
    
    raw_model = (matched_tx.type if matched_tx and matched_tx.type else "") or _text_or_empty(record.model)
    if raw_model.upper() in ("H/S", "HERMETICALLY SEALED", "HERMETICALLY SEAL"):
        tx_model = "HERMETICALLY SEAL"
    else:
        tx_model = raw_model

    tx_rating = (matched_tx.rating_kva if matched_tx and matched_tx.rating_kva else "") or _text_or_empty(record.rating)
    tx_serial = matched_tx.serial_no if matched_tx else ""

    tx_cable = ""
    if equipment_pkg:
        for swg in equipment_pkg.switchgears:
            for p in swg.panels:
                if "TX" in p.name.upper() and p.cable_type:
                    tx_cable = p.cable_type
                    break
            if tx_cable:
                break
        if not tx_cable:
            for swg in equipment_pkg.switchgears:
                for p in swg.panels:
                    if p.cable_type:
                        tx_cable = p.cable_type
                        break
                if tx_cable:
                    break
    if not tx_cable and "CABLE" in equipment.upper():
        tx_cable = equipment

    tx_number = record.equipment_id or resolved_item_key

    return {
        "tx": {
            "number": _fallback_dash(tx_number),
            "location": _fallback_dash(tx_location),
            "area": area,
            "manufacturer": _fallback_dash(tx_mfg),
            "model": _fallback_dash(tx_model),
            "rating": _fallback_dash(tx_rating),
            "serialnumber": _fallback_dash(tx_serial),
            "cabletype": _fallback_dash(tx_cable),
            "ir": {"reading": _fallback_dash(record.ir_reading)},
            "us": {
                "reading": _fallback_dash(record.us_reading),
                "char": _fallback_dash(record.us_char),
            },
            "tev": {
                "reading": _fallback_dash(record.tev_reading),
                "char": _fallback_dash(record.tev_char),
            },
        }
    }


def _build_blackbox_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)

    raw_target = record.equipment_id or resolved_item_key or resolved_item_suffix
    digits = re.findall(r"\d+", raw_target)
    if digits:
        bbox_number = digits[0]
    elif raw_target.strip():
        bbox_number = raw_target.strip()
    else:
        bbox_number = "-"

    search_text = f"{record.defect_area} {record.additional_remarks} {record.equipment_id} {resolved_item_suffix} {resolved_item_key}".upper()
    if "LEFT" in search_text:
        bbox_location = "LEFT"
    elif "RIGHT" in search_text:
        bbox_location = "RIGHT"
    elif "FRONT" in search_text:
        bbox_location = "FRONT"
    elif "REAR" in search_text:
        bbox_location = "REAR"
    else:
        bbox_location = "-"

    return {
        "bbox": {
            "number": _fallback_dash(bbox_number),
            "location": _fallback_dash(bbox_location),
            "area": area,
            "ir": {"reading": _fallback_dash(record.ir_reading)},
            "us": {
                "reading": _fallback_dash(record.us_reading),
                "char": _fallback_dash(record.us_char),
            },
            "tev": {
                "reading": _fallback_dash(record.tev_reading),
                "char": _fallback_dash(record.tev_char),
            },
        }
    }


def _build_battery_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)

    raw_target = record.equipment_id or resolved_item_key or resolved_item_suffix

    equipment_pkg = _extract_equipment_package(pe_info)
    battery_banks = equipment_pkg.battery_banks if equipment_pkg else ()
    matched_batt = _find_matching_battery(battery_banks, raw_target)

    batt_mfg = _text_or_empty(record.brand) or (matched_batt.manufacturer if matched_batt else "")
    batt_model = _text_or_empty(record.model) or (matched_batt.model if matched_batt else "")
    batt_serial = matched_batt.serial_no if matched_batt else ""
    batt_number = raw_target or (matched_batt.name if matched_batt else "")

    return {
        "batt": {
            "number": _fallback_dash(batt_number),
            "manufacturer": _fallback_dash(batt_mfg),
            "model": _fallback_dash(batt_model),
            "serialnumber": _fallback_dash(batt_serial),
            "area": area,
            "ir": {"reading": _fallback_dash(record.ir_reading)},
            "us": {
                "reading": _fallback_dash(record.us_reading),
                "char": _fallback_dash(record.us_char),
            },
            "tev": {
                "reading": _fallback_dash(record.tev_reading),
                "char": _fallback_dash(record.tev_char),
            },
        }
    }


def _build_family_render_context(
    family_spec: QuickReportFamilySpec,
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
    pe_info: dict[str, Any] | None = None,
) -> dict:
    if family_spec.id == "fp_lvdb":
        return _build_fp_lvdb_render_context(
            record,
            overview=overview,
            item_key=item_key,
            item_suffix=item_suffix,
            pe_info=pe_info,
        )
    if family_spec.id == "swg":
        return _build_swg_render_context(
            record,
            overview=overview,
            item_key=item_key,
            item_suffix=item_suffix,
            pe_info=pe_info,
        )
    if family_spec.id == "tx":
        return _build_tx_render_context(
            record,
            overview=overview,
            item_key=item_key,
            item_suffix=item_suffix,
            pe_info=pe_info,
        )
    if family_spec.id == "blackbox":
        return _build_blackbox_render_context(
            record,
            overview=overview,
            item_key=item_key,
            item_suffix=item_suffix,
            pe_info=pe_info,
        )
    if family_spec.id == "battery":
        return _build_battery_render_context(
            record,
            overview=overview,
            item_key=item_key,
            item_suffix=item_suffix,
            pe_info=pe_info,
        )
    return {}

