"""CBM quick-report rendering engine and context builders."""

from __future__ import annotations

import gc
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
from jinja2 import Environment, Undefined

from src.quick_report.cbm_family import QuickReportFamilySpec, QUICK_REPORT_FAMILY_SPECS_BY_ID
from src.quick_report.utils import sanitize_filename

_MISSING = object()


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


class PreservingUndefined(Undefined):
    """Keep unresolved quick-report Jinja placeholders visible."""

    def __str__(self) -> str:
        return f"{{{{ {self._undefined_name} }}}}"

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        current = self._undefined_name or ""
        new_name = f"{current}.{name}" if current else name
        return type(self)(
            hint=self._undefined_hint,
            obj=self._undefined_obj,
            name=new_name,
            exc=self._undefined_exception,
        )

    def __getitem__(self, name):
        return self.__getattr__(str(name))

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __len__(self):
        return 0


class QuickReportContext(dict):
    """Dict wrapper that preserves full dotted paths for missing keys."""

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
        return _placeholder_literal(self._child_path(str(key)))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _build_jinja_env() -> Environment:
    """Create a Jinja environment that preserves unresolved placeholders."""
    return Environment(undefined=PreservingUndefined, autoescape=True)


def _placeholder_literal(path: str) -> str:
    """Format a placeholder literal that survives Jinja rendering."""
    return f"{{{{ {path} }}}}"


def _preserve_blank_render_values(value):
    """Wrap quick-report render data so missing keys keep their full paths."""
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


def _text_or_empty(value) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except Exception:
        pass
    return str(value)


def _format_detail_area(defect_area, additional_remarks, *, overview: bool = False) -> str:
    if overview:
        return "OVERVIEW"
    defect_area_text = _text_or_empty(defect_area).strip()
    remarks_text = _text_or_empty(additional_remarks).strip()
    if remarks_text:
        return f"{defect_area_text}/ {remarks_text}" if defect_area_text else remarks_text
    return defect_area_text


def _payload_get(payload: object, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _lookup_family_value(payload: object, key: str, default: Any = None) -> Any:
    value = _payload_get(payload, key, _MISSING)
    if value is not _MISSING:
        return value
    for nested_key in ("defect", "tech_defect", "anchor_defect"):
        nested_payload = _payload_get(payload, nested_key, None)
        if nested_payload is None:
            continue
        value = _payload_get(nested_payload, key, _MISSING)
        if value is not _MISSING:
            return value
    return default


def _resolve_item_identity(payload: object, *, item_key: str = "", item_suffix: str = "") -> tuple[str, str]:
    resolved_item_key = _text_or_empty(item_key or _lookup_family_value(payload, "item_key", ""))
    resolved_item_suffix = _text_or_empty(item_suffix or _lookup_family_value(payload, "item_suffix", ""))
    return resolved_item_key, resolved_item_suffix


def _prune_unset_detail_payload(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = _prune_unset_detail_payload(item)
            if normalized is None:
                continue
            cleaned[key] = normalized
        return cleaned or None
    if isinstance(value, list):
        cleaned = []
        for item in value:
            normalized = _prune_unset_detail_payload(item)
            if normalized is not None:
                cleaned.append(normalized)
        return cleaned or None
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _build_fp_lvdb_render_context(payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    item_key, _ = _resolve_item_identity(payload, item_key=item_key, item_suffix=item_suffix)
    return _prune_unset_detail_payload({
        "fp": {
            "labelsource": item_key,
            "area": _format_detail_area(_lookup_family_value(payload, "defect_area"), _lookup_family_value(payload, "additional_remarks"), overview=overview),
            "manufacturer": _text_or_empty(_lookup_family_value(payload, "brand")),
            "model": _text_or_empty(_lookup_family_value(payload, "model")),
            "rating": _text_or_empty(_lookup_family_value(payload, "rating")),
            "serialnumber": "",
            "cabletype": "",
        }
    }) or {}


def _build_swg_render_context(payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    item_key, item_suffix = _resolve_item_identity(payload, item_key=item_key, item_suffix=item_suffix)
    equipment = _text_or_empty(_lookup_family_value(payload, "equipment")).strip()
    area = _format_detail_area(_lookup_family_value(payload, "defect_area"), _lookup_family_value(payload, "additional_remarks"), overview=overview)
    return _prune_unset_detail_payload({
        "swg": {
            "area": area,
            "manufacturer": _text_or_empty(_lookup_family_value(payload, "brand")),
            "model": _text_or_empty(_lookup_family_value(payload, "model")),
            "rating": _text_or_empty(_lookup_family_value(payload, "rating")),
            "serialnumber": "",
            "type": equipment,
        },
        "panel": {
            "name": item_suffix or item_key,
            "area": area,
            "breakerstatus": "",
            "busbarposition": "",
            "cabletype": equipment if "CABLE" in equipment.upper() else "",
            "heateramp": "",
            "linknumber": item_key,
            "loadamp": "",
            "serialnumber": "",
            "us": {"char": _text_or_empty(_lookup_family_value(payload, "defect_from"))},
        },
    }) or {}


def _build_tx_render_context(payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    item_key, item_suffix = _resolve_item_identity(payload, item_key=item_key, item_suffix=item_suffix)
    return _prune_unset_detail_payload({
        "tx": {
            "area": _format_detail_area(_lookup_family_value(payload, "defect_area"), _lookup_family_value(payload, "additional_remarks"), overview=overview),
            "cabletype": _text_or_empty(_lookup_family_value(payload, "equipment")),
            "location": item_suffix,
            "manufacturer": _text_or_empty(_lookup_family_value(payload, "brand")),
            "model": _text_or_empty(_lookup_family_value(payload, "model")),
            "number": item_key,
            "rating": _text_or_empty(_lookup_family_value(payload, "rating")),
            "serialnumber": "",
        },
        "panel": {
            "us": {"char": _text_or_empty(_lookup_family_value(payload, "defect_from"))},
        },
    }) or {}


def _build_blackbox_render_context(payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    item_key, item_suffix = _resolve_item_identity(payload, item_key=item_key, item_suffix=item_suffix)
    return _prune_unset_detail_payload({
        "bbox": {
            "location": item_suffix or item_key,
            "number": item_key,
        }
    }) or {}


def _build_battery_render_context(payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    item_key, _ = _resolve_item_identity(payload, item_key=item_key, item_suffix=item_suffix)
    return _prune_unset_detail_payload({
        "batt": {
            "manufacturer": _text_or_empty(_lookup_family_value(payload, "brand")),
            "model": _text_or_empty(_lookup_family_value(payload, "model")),
            "number": item_key,
            "serialnumber": "",
        }
    }) or {}


def _build_family_render_context(family_spec: QuickReportFamilySpec, payload: object, *, overview: bool, item_key: str = "", item_suffix: str = "") -> dict:
    if family_spec.id == "fp_lvdb":
        return _build_fp_lvdb_render_context(payload, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "swg":
        return _build_swg_render_context(payload, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "tx":
        return _build_tx_render_context(payload, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "blackbox":
        return _build_blackbox_render_context(payload, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "battery":
        return _build_battery_render_context(payload, overview=overview, item_key=item_key, item_suffix=item_suffix)
    return payload if isinstance(payload, dict) else {}


def generate_front_page(pe_info: dict, template_path: str, output_dir: str, pe_number: int) -> Path:
    """Generate the CBM quick report front page."""
    doc = DocxTemplate(template_path)
    doc.render(_preserve_blank_render_values(pe_info), jinja_env=_build_jinja_env(), autoescape=True)
    out_path = Path(output_dir) / f"{pe_number:03d}_1 FRONT PAGE.docx"
    doc.save(out_path)
    return out_path


def generate_quick_report_detail_pages(
    groups: list[object],
    family_spec: QuickReportFamilySpec,
    template_paths: dict[str, str | Path],
    output_dir: str | Path,
    pe_number: int,
    pe_info: dict,
) -> list[Path]:
    """Generate one quick-report family with overview and repeated detail pages."""
    if not groups:
        return []

    overview_template_path = template_paths.get(family_spec.overview_template_key)
    if not overview_template_path:
        return []

    overview_path = Path(overview_template_path)
    if not overview_path.exists():
        return []

    output_paths: list[Path] = []
    pe_num_str = f"{pe_number:03d}"
    output_dir_path = Path(output_dir)

    for group_index, group in enumerate(groups, start=1):
        group_item_key = _text_or_empty(_payload_get(group, "item_key", "")).strip()
        group_item_suffix = _text_or_empty(_payload_get(group, "item_suffix", "")).strip()
        item_key = sanitize_filename(group_item_key or f"GROUP {group_index}")
        
        overview_context = pe_info.copy()
        overview_context.update(_build_family_render_context(
            family_spec, _payload_get(group, "overview", {}), overview=True, item_key=group_item_key, item_suffix=group_item_suffix
        ))
        
        overview_output = output_dir_path / f"{pe_num_str}_2B {family_spec.output_label} OVERVIEW {item_key}.docx"
        _render_docx_template(overview_template_path, overview_output, overview_context)
        output_paths.append(overview_output)

        detail_groups = _payload_get(group, "detail_groups", {})
        for role_index, role_spec in enumerate(family_spec.detail_roles, start=1):
            role_template_path = template_paths.get(role_spec.template_key)
            if not role_template_path or not Path(role_template_path).exists():
                continue

            for defect_index, defect_context in enumerate(detail_groups.get(role_spec.id, []), start=1):
                render_context = pe_info.copy()
                render_context.update(_build_family_render_context(
                    family_spec, defect_context, overview=False, item_key=group_item_key, item_suffix=group_item_suffix
                ))
                defect_path = output_dir_path / f"{pe_num_str}_2B {role_spec.output_label} DEFECT {item_key} part{defect_index}.docx"
                _render_docx_template(role_template_path, defect_path, render_context)
                output_paths.append(defect_path)

    return output_paths


def prepare_tech_summary_rows(defects: list[dict]) -> list[PreparedTechSummaryRow]:
    """Prepare summary rows pairing IR, US, and TEV defect readings."""
    paired: dict[tuple[str, str, str], PreparedTechSummaryRow] = {}
    
    for defect in defects:
        equip = _text_or_empty(defect.get("equipment")).strip()
        area = _text_or_empty(defect.get("defect_area")).strip()
        remarks = _text_or_empty(defect.get("additional_remarks")).strip()
        key = (equip, area, remarks)
        
        if key not in paired:
            paired[key] = PreparedTechSummaryRow(
                equipment=equip,
                brand=_text_or_empty(defect.get("brand")),
                model=_text_or_empty(defect.get("model")),
                rating=_text_or_empty(defect.get("rating")),
                defect_area=area,
                remarks=remarks,
                ir_reading="-",
                us_reading="-",
                tev_reading="-",
            )
            
        tech = _text_or_empty(defect.get("technology")).upper()
        if tech == "IR":
            val = defect.get("temperature")
            paired[key].ir_reading = f"{float(val)} °C" if val else "-"
        elif tech == "US":
            val = defect.get("us_value")
            paired[key].us_reading = f"{int(float(val))}dB" if val else "-"
        elif tech == "TEV":
            val = defect.get("tev_value")
            paired[key].tev_reading = f"{int(float(val))}dB" if val else "-"
            
    return list(paired.values())


def generate_cbm_tech_summary(pe_info: dict, defects: list[dict], template_path: str, output_dir: str, pe_number: int) -> Path:
    """Generate CBM technical summary page joining IR, US, and TEV."""
    rows = prepare_tech_summary_rows(defects)
    context = pe_info.copy()
    context["defects"] = [row.__dict__ for row in rows]
    
    out_path = Path(output_dir) / f"{pe_number:03d}_2A CBM DEFECT SUMMARY.docx"
    _render_docx_template(template_path, out_path, context)
    return out_path
