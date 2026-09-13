"""Core Scan Page Renderer & Dynamic Shading Engine for Full Report (Ticket #30 / T4.2a).

Renders transparent Jinja2 scanning templates under templates/FULL REPORT/NORMAL IR US TEV/
via docxtpl and dynamically applies OpenXML cell shading per D30 and D32:
- Technology severity cells (IR, US, TEV): Green 00B050 (healthy) or Red EE0000 (defective), clearing text.
- Analysis & Recommendation banner: Green 00B050 for 'No Anomaly.' or Red EE0000 for defect forwarding prose.
"""

from __future__ import annotations

import copy
import gc
import logging
from pathlib import Path
import re
from typing import Any, Sequence

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from PIL import Image as PILImage

from src.quick_report.cbm_render import (
    _build_jinja_env,
    _preserve_blank_render_values,
    _process_inline_images,
)
from src.quick_report.utils import clear_cell_text, set_cell_shading

logger = logging.getLogger(__name__)

# Canonical color hex codes
COLOR_HEALTHY: str = "00B050"  # Green
COLOR_DEFECT: str = "EE0000"   # Red
COLOR_NORMAL: str = "00B050"   # Alias for healthy

# Canonical banner texts per D30
BANNER_HEALTHY_ANALYSIS: str = "No Anomaly."
BANNER_HEALTHY_RECOMMENDATION: str = "-"
BANNER_DEFECT_FORWARDING: str = "Please refer to the following page for details defect."
BANNER_DEFECT_FORWARDING_ANALYSIS: str = "Please refer to the following page for details defect."
BANNER_DEFECT_FORWARDING_RECOMMENDATION: str = "Please refer to the following page for details defect."

# Sentinels for Jinja severity placeholders
SEVERITY_MARKER_IR: str = "__SEVERITY_IR__"
SEVERITY_MARKER_US: str = "__SEVERITY_US__"
SEVERITY_MARKER_TEV: str = "__SEVERITY_TEV__"


# Sentinels representing absence of defect or empty values
_NEGATIVE_SENTINELS: frozenset[str] = frozenset({
    "",
    "-",
    "--",
    "NONE",
    "NORMAL",
    "HEALTHY",
    "NO DEFECT",
    "NO ANOMALY",
    "NO_DEFECT",
    "NO_ANOMALY",
    "N/A",
    "NA",
    "TIADA",
    "TIADA ANOMALI",
    "TIADA DEFECT",
    "NIL",
    "EMPTY",
    "FALSE",
    "0",
})

_VALID_TECHNOLOGY_MAP: dict[str, str] = {
    "IR": "IR",
    "INFRARED": "IR",
    "THERMAL": "IR",
    "US": "US",
    "ULTRASOUND": "US",
    "TEV": "TEV",
    "TRANSIENT": "TEV",
}


def _normalize_technologies(techs: set[str] | list[str] | tuple[str, ...] | str | None) -> set[str]:
    """Normalize defective technologies specification into a set of uppercase strings.

    Filters out negative/empty sentinels (e.g. '-', 'NONE', 'NORMAL', 'N/A') and
    normalizes recognized modalities ('IR', 'US', 'TEV').
    """
    if techs is None:
        return set()
    if isinstance(techs, str):
        raw_items = [techs]
    else:
        raw_items = [str(t) for t in techs]

    tokens: list[str] = []
    for item in raw_items:
        trimmed = str(item).strip()
        if not trimmed or trimmed.upper() in _NEGATIVE_SENTINELS:
            continue
        # Pre-normalize U/S variants before delimiter splitting to prevent U / S token fracturing
        subbed = re.sub(r"(?i)\bu\s*/\s*s\b", "US", trimmed)
        cleaned = subbed.replace(",", " ").replace("+", " ").replace("/", " ")
        tokens.extend(cleaned.split())

    res = set()
    for tok in tokens:
        clean_tok = tok.strip().upper().replace("/", "")
        if clean_tok in _NEGATIVE_SENTINELS or not clean_tok:
            continue
        if clean_tok in _VALID_TECHNOLOGY_MAP:
            res.add(_VALID_TECHNOLOGY_MAP[clean_tok])
        elif clean_tok not in _NEGATIVE_SENTINELS:
            res.add(clean_tok)
    return res


def detect_cell_technology(cell: Any) -> str | None:
    """Detect if a table cell represents a technology severity cell (IR, US, TEV).

    Returns 'IR', 'US', 'TEV', or None.
    """
    text = cell.text.strip() if hasattr(cell, "text") else ""
    if not text:
        return None

    text_upper = text.upper()

    # 1. Exact or marker substring matches
    if SEVERITY_MARKER_IR in text_upper or "{{ IR.SEVERITY }}" in text_upper or "{{IR.SEVERITY}}" in text_upper:
        return "IR"
    if SEVERITY_MARKER_US in text_upper or "{{ US.SEVERITY }}" in text_upper or "{{US.SEVERITY}}" in text_upper:
        return "US"
    if SEVERITY_MARKER_TEV in text_upper or "{{ TEV.SEVERITY }}" in text_upper or "{{TEV.SEVERITY}}" in text_upper:
        return "TEV"

    # 2. Jinja variable pattern
    if re.search(r"\{\{\s*ir\.severity\s*\}\}", text, re.I):
        return "IR"
    if re.search(r"\{\{\s*us\.severity\s*\}\}", text, re.I):
        return "US"
    if re.search(r"\{\{\s*tev\.severity\s*\}\}", text, re.I):
        return "TEV"

    # 3. Simple token patterns
    if text_upper in ("IR", "IR_SEVERITY", "[IR_SEVERITY]", "IR.SEVERITY", "IR SEVERITY"):
        return "IR"
    if text_upper in ("US", "US_SEVERITY", "[US_SEVERITY]", "US.SEVERITY", "US SEVERITY", "U/S", "U/S_SEVERITY", "U/S.SEVERITY", "U/S SEVERITY"):
        return "US"
    if text_upper in ("TEV", "TEV_SEVERITY", "[TEV_SEVERITY]", "TEV.SEVERITY", "TEV SEVERITY"):
        return "TEV"

    # 4. Heading + technology patterns
    tokens = set(re.findall(r"\b[A-Z0-9/]+\b", text_upper))
    if "SEVERITY" in tokens:
        if "IR" in tokens:
            return "IR"
        if "US" in tokens or "U/S" in tokens:
            return "US"
        if "TEV" in tokens:
            return "TEV"

    return None


def is_defect_forwarding_text(text: str) -> bool:
    """Check if cell text corresponds to downstream defect forwarding prose per D30."""
    lower = text.lower()
    return (
        "please refer to the following page for detail" in lower
        or "please refer to the following page for details" in lower
        or "refer to the following page" in lower
        or "following page for details defect" in lower
        or "following page for detail defect" in lower
    )


def is_healthy_banner_text(text: str) -> bool:
    """Check if cell text corresponds to healthy Analysis / Recommendation prose per D30."""
    lower = text.lower().strip()
    if not lower:
        return False
    if (
        "no anomaly" in lower
        or "tiada anomaly" in lower
        or "tiada anomali" in lower
        or "tiada defect" in lower
        or "no defect" in lower
    ):
        return True
    # Strip common prefixes and evaluate residual prose
    clean = re.sub(r"^(?:recommendation|cadangan|analysis|analisis)\s*:\s*", "", lower).strip()
    if clean in ("-", "tiada", "none", "n/a", "nil", "normal") or not clean:
        return True
    return False


def get_cell_shading(cell: Any) -> str | None:
    """Read w:fill hex color attribute from a table cell's tcPr/w:shd XML element."""
    if not hasattr(cell, "_tc"):
        return None
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.attrib.get(qn("w:fill"))


def _get_cell_tc(cell: Any) -> Any:
    """Extract underlying XML _tc element from a cell or wrapper."""
    if hasattr(cell, "_tc"):
        return cell._tc
    return cell


def _is_cell(target: Any) -> bool:
    """Check if target represents a single table cell."""
    return hasattr(target, "paragraphs") and hasattr(target, "_tc") and not hasattr(target, "rows")


def _iter_unique_cells(target: Any) -> list[Any]:
    """Extract a deduplicated list of table cells from various containers.

    Accepts a single _Cell, _Row, Table, Document, DocxTemplate, or sequence thereof.
    Ensures merged cells sharing the same underlying XML _tc element are only yielded once.
    """
    cells: list[Any] = []
    seen_tcs: set[Any] = set()

    def _collect(obj: Any) -> None:
        if obj is None:
            return
        if _is_cell(obj):
            tc = _get_cell_tc(obj)
            if tc not in seen_tcs:
                seen_tcs.add(tc)
                cells.append(obj)
            return
        if hasattr(obj, "cells"):  # Table row (_Row)
            for c in obj.cells:
                _collect(c)
            return
        if hasattr(obj, "rows"):  # Table
            for r in obj.rows:
                for c in r.cells:
                    _collect(c)
            return
        if hasattr(obj, "docx") and hasattr(obj.docx, "tables"):  # DocxTemplate
            for t in obj.docx.tables:
                _collect(t)
            return
        if hasattr(obj, "tables"):  # docx.Document
            for t in obj.tables:
                _collect(t)
            return
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                _collect(item)

    _collect(target)
    return cells


def apply_technology_severity_shading(
    target: Any,
    *,
    defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
    technology: str | None = None,
    is_defective: bool | None = None,
) -> Any:
    """Dynamically shade technology severity cells (IR, US, TEV) Green or Red, clearing text.

    - Healthy cell: Green '00B050', text cleared.
    - Defective cell: Red 'EE0000', text cleared.

    Can operate on a single _Cell, a _Row, a Table, a Document, a DocxTemplate, or an iterable thereof.
    """
    def_techs = _normalize_technologies(defective_technologies)
    cells = _iter_unique_cells(target)
    single_cell_mode = len(cells) == 1 and _is_cell(target)

    for cell in cells:
        detected_tech = detect_cell_technology(cell)
        tech = (technology or detected_tech or "").upper()

        if not tech:
            if single_cell_mode and is_defective is not None:
                cell_defective = is_defective
            else:
                continue
        else:
            if is_defective is not None:
                cell_defective = is_defective
            else:
                cell_defective = tech in def_techs

        clear_cell_text(cell)
        set_cell_shading(cell, COLOR_DEFECT if cell_defective else COLOR_HEALTHY)

    return target


def apply_banner_shading(
    target: Any,
    *,
    is_defective: bool | None = None,
) -> Any:
    """Dynamically shade Analysis & Recommendation banner cells per D30 and D32.

    - Healthy ('No Anomaly.'): Green '00B050'.
    - Defect Forwarding prose: Red 'EE0000'.

    Can operate on a single _Cell, a _Row, a Table, a Document, a DocxTemplate, or an iterable thereof.
    """
    cells = _iter_unique_cells(target)
    single_cell_mode = len(cells) == 1 and _is_cell(target)

    for cell in cells:
        text = cell.text.strip()
        lower = text.lower()
        is_header = lower.rstrip(":").strip() in ("analysis & recommendations", "analysis & recommendation")
        if is_header:
            continue

        if is_defective is True:
            if (
                single_cell_mode
                or is_defect_forwarding_text(text)
                or lower.startswith("analysis:")
                or lower.startswith("recommendation:")
            ):
                set_cell_shading(cell, COLOR_DEFECT)
        elif is_defective is False:
            if (
                single_cell_mode
                or is_healthy_banner_text(text)
                or (lower.startswith("analysis:") and "defect" not in lower)
                or (lower.startswith("recommendation:") and "defect" not in lower)
            ):
                set_cell_shading(cell, COLOR_HEALTHY)
        else:  # is_defective is None
            if is_defect_forwarding_text(text):
                set_cell_shading(cell, COLOR_DEFECT)
            elif is_healthy_banner_text(text):
                set_cell_shading(cell, COLOR_HEALTHY)

    return target


def _clone_context(val: Any) -> Any:
    """Recursively clone dicts and lists without deepcopying InlineImage or complex objects."""
    if isinstance(val, dict):
        return {k: _clone_context(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clone_context(v) for v in val]
    return val


def _bind_inline_images(doc: DocxTemplate, context: dict, image_width_mm: float = 80.0) -> None:
    """Recursively bind image file paths or rebind existing InlineImages to the active template."""
    def _convert(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                k_str = str(k).lower()
                if (
                    k_str in ("prpd", "image")
                    or k_str.endswith("_image")
                    or k_str.endswith(".image")
                    or k_str.endswith(".prpd")
                    or k_str.endswith("_prpd")
                ):
                    if isinstance(v, (str, Path)):
                        v_str = str(v).strip()
                        if not v_str or v_str == "-":
                            obj[k] = ""
                        else:
                            v_path = Path(v)
                            if v_path.is_file():
                                try:
                                    with PILImage.open(v_path) as img:
                                        img.verify()
                                    obj[k] = InlineImage(doc, str(v_path), width=Mm(image_width_mm))
                                except Exception as exc:
                                    logger.warning(
                                        "Invalid or corrupt image at %s: %s; falling back to blank",
                                        v_path,
                                        exc,
                                    )
                                    obj[k] = ""
                            else:
                                obj[k] = ""
                    elif isinstance(v, InlineImage):
                        v.tpl = doc
                    elif v is None:
                        obj[k] = ""
                elif isinstance(v, InlineImage):
                    v.tpl = doc
                else:
                    _convert(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, InlineImage):
                    item.tpl = doc
                else:
                    _convert(item)

    _convert(context)


class FullReportScanPageRendererCore:
    """Core scanning page renderer and OpenXML post-render shading engine.

    Wraps docxtpl.DocxTemplate to render component scanning templates and applies
    dynamic cell shading per D30 and D32:
    - Technology severity cells (IR, US, TEV): Green 00B050 (healthy) or Red EE0000 (defective), text cleared.
    - Analysis & Recommendation banner: Green 00B050 ('No Anomaly.') or Red EE0000 (defect forwarding prose).
    """

    def __init__(self, template_path: str | Path | None = None) -> None:
        self.template_path = Path(template_path) if template_path is not None else None

    def render(
        self,
        template_path_or_output: str | Path | None = None,
        output_path_or_context: Path | str | dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        *,
        template_path: str | Path | None = None,
        output_path: Path | str | None = None,
        defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
        is_defective: bool | None = None,
        overview: bool = False,
        image_width_mm: float = 80.0,
    ) -> Path:
        """Render scanning template with docxtpl and apply dynamic OpenXML cell shading.

        Supports flexible calling patterns:
        1. renderer = FullReportScanPageRendererCore(template_path)
           renderer.render(output_path, context)
           renderer.render(output_path, context=context)
           renderer.render(output_path=output_path, context=context)
        2. renderer = FullReportScanPageRendererCore()
           renderer.render(template_path, output_path, context)
           renderer.render(template_path, output_path, context=context)
           renderer.render(template_path=tpl, output_path=out, context=ctx)
        """
        actual_template = template_path or self.template_path
        actual_output = output_path
        raw_context = context

        pos_args: list[Any] = []
        if template_path_or_output is not None:
            pos_args.append(template_path_or_output)
        if output_path_or_context is not None:
            pos_args.append(output_path_or_context)

        if len(pos_args) == 2:
            arg0, arg1 = pos_args[0], pos_args[1]
            if isinstance(arg1, dict):
                actual_output = Path(arg0)
                if raw_context is None:
                    raw_context = arg1
            elif isinstance(arg1, (str, Path)):
                actual_template = Path(arg0)
                actual_output = Path(arg1)
            else:
                raise ValueError(f"Unrecognized second positional argument: {arg1!r}")
        elif len(pos_args) == 1:
            arg0 = pos_args[0]
            if isinstance(arg0, dict):
                if raw_context is None:
                    raw_context = arg0
            elif isinstance(arg0, (str, Path)):
                if actual_template is not None and actual_output is None:
                    actual_output = Path(arg0)
                else:
                    actual_template = Path(arg0)

        if raw_context is None:
            raw_context = {}

        if actual_template is None or not Path(actual_template).is_file():
            raise FileNotFoundError(f"Scanning template file not found: {actual_template}")
        if actual_output is None:
            raise ValueError("Output path must be provided")

        actual_template = Path(actual_template).resolve()
        actual_output = Path(actual_output).resolve()
        if actual_output.is_dir():
            raise ValueError(f"Output path cannot be an existing directory: {actual_output}")
        if actual_output == actual_template:
            raise ValueError(f"Output path cannot overwrite template path: {actual_output}")
        actual_output.parent.mkdir(parents=True, exist_ok=True)

        # Prepare context copy safely
        render_ctx = _clone_context(raw_context)

        # Resolve defective technologies set
        def_techs = _normalize_technologies(defective_technologies)
        if "__defective_technologies__" in render_ctx:
            def_techs.update(_normalize_technologies(render_ctx["__defective_technologies__"]))
        if "defective_technologies" in render_ctx:
            def_techs.update(_normalize_technologies(render_ctx["defective_technologies"]))

        # Inspect context severity flags
        for tech_key, tech_token in (("ir", "IR"), ("us", "US"), ("tev", "TEV")):
            val = render_ctx.get(tech_key)
            if isinstance(val, dict):
                sev_val = str(val.get("severity", "")).upper()
                if sev_val in ("DEFECT", "DEFECTIVE", "CRITICAL", "POOR", "ANOMALY"):
                    def_techs.add(tech_token)

        if is_defective is True and not def_techs and not overview:
            def_techs.add("IR")
        elif is_defective is False:
            def_techs.clear()

        # Inject severity sentinels so Jinja places markers into cells for post-processing
        for tech_key, marker in (
            ("ir", SEVERITY_MARKER_IR),
            ("us", SEVERITY_MARKER_US),
            ("tev", SEVERITY_MARKER_TEV),
        ):
            val = render_ctx.get(tech_key)
            if not isinstance(val, dict):
                render_ctx[tech_key] = {"severity": marker}
            elif val.get("severity") != "-":
                val["severity"] = marker

        # Inject banner analysis & recommendation per D30 if not already provided
        if is_defective is not None:
            has_defect = is_defective
        else:
            has_defect = len(def_techs) > 0

        if not has_defect and is_defective is not False:
            banner_val = render_ctx.get("banner")
            b_dict = banner_val if isinstance(banner_val, dict) else {}
            b_analysis = str(b_dict.get("analysis") or render_ctx.get("analysis") or "")
            b_rec = str(b_dict.get("recommendation") or render_ctx.get("recommendation") or "")
            if is_defect_forwarding_text(b_analysis) or is_defect_forwarding_text(b_rec):
                has_defect = True

        default_analysis = BANNER_DEFECT_FORWARDING if has_defect else BANNER_HEALTHY_ANALYSIS
        default_rec = BANNER_DEFECT_FORWARDING if has_defect else BANNER_HEALTHY_RECOMMENDATION

        if "banner" not in render_ctx or not isinstance(render_ctx["banner"], dict):
            render_ctx["banner"] = {
                "analysis": default_analysis,
                "recommendation": default_rec,
            }
        else:
            render_ctx["banner"].setdefault("analysis", default_analysis)
            render_ctx["banner"].setdefault("recommendation", default_rec)

        render_ctx.setdefault("analysis", render_ctx["banner"]["analysis"])
        render_ctx.setdefault("recommendation", render_ctx["banner"]["recommendation"])

        # Open template via docxtpl
        doc = DocxTemplate(str(actual_template))

        # Convert image paths and rebind InlineImages to the active template
        _bind_inline_images(doc, render_ctx, image_width_mm)

        # Render docxtpl template with PreservingUndefined Jinja environment
        doc.render(
            _preserve_blank_render_values(render_ctx),
            jinja_env=_build_jinja_env(),
            autoescape=True,
        )

        # Apply dynamic post-render OpenXML DOM shading
        apply_technology_severity_shading(doc, defective_technologies=def_techs)
        apply_banner_shading(doc, is_defective=has_defect)

        # Save rendered and shaded document
        doc.save(str(actual_output))
        del doc
        gc.collect()

        return actual_output

    @classmethod
    def render_page(
        cls,
        template_path: str | Path,
        output_path: Path | str,
        context: dict[str, Any],
        *,
        defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
        is_defective: bool | None = None,
        overview: bool = False,
        image_width_mm: float = 80.0,
    ) -> Path:
        """Convenience class method to render and shade a scan page."""
        renderer = cls()
        return renderer.render(
            template_path,
            output_path,
            context,
            defective_technologies=defective_technologies,
            is_defective=is_defective,
            overview=overview,
            image_width_mm=image_width_mm,
        )


def render_scan_page(
    template_path: str | Path,
    output_path: Path | str,
    context: dict[str, Any],
    *,
    defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
    is_defective: bool | None = None,
    overview: bool = False,
    image_width_mm: float = 80.0,
) -> Path:
    """Standalone helper function to render a scan page with dynamic OpenXML shading."""
    return FullReportScanPageRendererCore.render_page(
        template_path,
        output_path,
        context,
        defective_technologies=defective_technologies,
        is_defective=is_defective,
        overview=overview,
        image_width_mm=image_width_mm,
    )


__all__ = [
    # Color constants
    "COLOR_HEALTHY",
    "COLOR_DEFECT",
    "COLOR_NORMAL",
    # Banner constants
    "BANNER_HEALTHY_ANALYSIS",
    "BANNER_HEALTHY_RECOMMENDATION",
    "BANNER_DEFECT_FORWARDING",
    "BANNER_DEFECT_FORWARDING_ANALYSIS",
    "BANNER_DEFECT_FORWARDING_RECOMMENDATION",
    # Sentinels
    "SEVERITY_MARKER_IR",
    "SEVERITY_MARKER_US",
    "SEVERITY_MARKER_TEV",
    # Detection helpers
    "detect_cell_technology",
    "is_defect_forwarding_text",
    "is_healthy_banner_text",
    # DOM post-processors
    "apply_technology_severity_shading",
    "apply_banner_shading",
    "get_cell_shading",
    # Core Renderer
    "FullReportScanPageRendererCore",
    "render_scan_page",
]
