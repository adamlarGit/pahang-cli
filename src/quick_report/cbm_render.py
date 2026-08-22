"""CBM quick-report rendering engine and context builders."""

from __future__ import annotations

import gc
from pathlib import Path

from docxtpl import DocxTemplate
from jinja2 import Environment, Undefined

from src.quick_report.cbm_family import QuickReportFamilySpec
from src.quick_report.defects import CbmDefectRecord

_MISSING = object()


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


def _build_fp_lvdb_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    return _prune_unset_detail_payload({
        "fp": {
            "labelsource": resolved_item_key,
            "area": _format_detail_area(record.defect_area, record.additional_remarks, overview=overview),
            "manufacturer": _text_or_empty(record.brand),
            "model": _text_or_empty(record.model),
            "rating": _text_or_empty(record.rating),
            "serialnumber": "",
            "cabletype": "",
        }
    }) or {}


def _build_swg_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    equipment = _text_or_empty(record.equipment).strip()
    area = _format_detail_area(record.defect_area, record.additional_remarks, overview=overview)
    return _prune_unset_detail_payload({
        "swg": {
            "area": area,
            "manufacturer": _text_or_empty(record.brand),
            "model": _text_or_empty(record.model),
            "rating": _text_or_empty(record.rating),
            "serialnumber": "",
            "type": equipment,
        },
        "panel": {
            "name": resolved_item_suffix or resolved_item_key,
            "area": area,
            "breakerstatus": "",
            "busbarposition": "",
            "cabletype": equipment if "CABLE" in equipment.upper() else "",
            "heateramp": "",
            "linknumber": resolved_item_key,
            "loadamp": "",
            "serialnumber": "",
            "ir": {"reading": _text_or_empty(record.ir_reading)},
            "us": {
                "reading": _text_or_empty(record.us_reading),
                "char": _text_or_empty(record.us_char),
            },
            "tev": {
                "reading": _text_or_empty(record.tev_reading),
                "char": _text_or_empty(record.tev_char),
            },
        },
    }) or {}


def _build_tx_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    return _prune_unset_detail_payload({
        "tx": {
            "area": _format_detail_area(record.defect_area, record.additional_remarks, overview=overview),
            "cabletype": _text_or_empty(record.equipment),
            "location": resolved_item_suffix,
            "manufacturer": _text_or_empty(record.brand),
            "model": _text_or_empty(record.model),
            "number": resolved_item_key,
            "rating": _text_or_empty(record.rating),
            "serialnumber": "",
            "ir": {"reading": _text_or_empty(record.ir_reading)},
            "us": {
                "reading": _text_or_empty(record.us_reading),
                "char": _text_or_empty(record.us_char),
            },
        },
    }) or {}


def _build_blackbox_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    resolved_item_suffix = _text_or_empty(item_suffix)
    return _prune_unset_detail_payload({
        "bbox": {
            "location": resolved_item_suffix or resolved_item_key,
            "number": resolved_item_key,
        }
    }) or {}


def _build_battery_render_context(
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    resolved_item_key = _text_or_empty(item_key)
    return _prune_unset_detail_payload({
        "batt": {
            "manufacturer": _text_or_empty(record.brand),
            "model": _text_or_empty(record.model),
            "number": resolved_item_key,
            "serialnumber": "",
        }
    }) or {}


def _build_family_render_context(
    family_spec: QuickReportFamilySpec,
    record: CbmDefectRecord,
    *,
    overview: bool,
    item_key: str = "",
    item_suffix: str = "",
) -> dict:
    if family_spec.id == "fp_lvdb":
        return _build_fp_lvdb_render_context(record, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "swg":
        return _build_swg_render_context(record, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "tx":
        return _build_tx_render_context(record, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "blackbox":
        return _build_blackbox_render_context(record, overview=overview, item_key=item_key, item_suffix=item_suffix)
    if family_spec.id == "battery":
        return _build_battery_render_context(record, overview=overview, item_key=item_key, item_suffix=item_suffix)
    return {}

