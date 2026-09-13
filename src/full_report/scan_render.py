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


def _normalize_technologies(techs: set[str] | list[str] | tuple[str, ...] | str | None) -> set[str]:
    """Normalize defective technologies specification into a set of uppercase strings."""
    if techs is None:
        return set()
    if isinstance(techs, str):
        cleaned = techs.replace(",", " ").replace("+", " ").replace("/", " ")
        return {t.strip().upper() for t in cleaned.split() if t.strip()}
    return {str(t).strip().upper() for t in techs if str(t).strip()}


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
    lower = text.lower()
    return (
        "no anomaly" in lower
        or "tiada anomaly" in lower
        or "tiada anomali" in lower
        or "tiada defect" in lower
    )


def _get_cell_tc(cell: Any) -> Any:
    """Extract underlying XML _tc element from a cell or wrapper."""
    if hasattr(cell, "_tc"):
        return cell._tc
    return cell


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

    Can operate on a single _Cell, a Table, a Document, a DocxTemplate, or an iterable thereof.
    """
    def_techs = _normalize_technologies(defective_technologies)

    # 1. Single cell handling
    if hasattr(target, "paragraphs") and hasattr(target, "_tc") and not hasattr(target, "rows"):
        tech = (technology or detect_cell_technology(target) or "").upper()
        if is_defective is not None:
            cell_defective = is_defective
        elif tech:
            cell_defective = tech in def_techs
        else:
            cell_defective = False

        clear_cell_text(target)
        set_cell_shading(target, COLOR_DEFECT if cell_defective else COLOR_HEALTHY)
        return target

    # 2. Extract list of tables
    tables: list[Any] = []
    if hasattr(target, "docx") and hasattr(target.docx, "tables"):
        tables = list(target.docx.tables)
    elif hasattr(target, "tables"):
        tables = list(target.tables)
    elif hasattr(target, "rows"):
        tables = [target]
    elif isinstance(target, (list, tuple)):
        for item in target:
            if hasattr(item, "rows"):
                tables.append(item)
            elif hasattr(item, "paragraphs") and hasattr(item, "_tc"):
                apply_technology_severity_shading(
                    item,
                    defective_technologies=def_techs,
                    technology=technology,
                    is_defective=is_defective,
                )
        return target

    # 3. Process table cells
    for table in tables:
        seen_tcs: set[Any] = set()
        for row in table.rows:
            for cell in row.cells:
                tc = _get_cell_tc(cell)
                if tc in seen_tcs:
                    continue
                seen_tcs.add(tc)

                tech = detect_cell_technology(cell)
                if tech is not None:
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

    Can operate on a single _Cell, a Table, a Document, a DocxTemplate, or an iterable thereof.
    """
    # 1. Single cell handling
    if hasattr(target, "paragraphs") and hasattr(target, "_tc") and not hasattr(target, "rows"):
        if is_defective is True:
            set_cell_shading(target, COLOR_DEFECT)
        elif is_defective is False:
            set_cell_shading(target, COLOR_HEALTHY)
        else:
            text = target.text.strip()
            if is_defect_forwarding_text(text):
                set_cell_shading(target, COLOR_DEFECT)
            elif is_healthy_banner_text(text):
                set_cell_shading(target, COLOR_HEALTHY)
        return target

    # 2. Extract list of tables
    tables: list[Any] = []
    if hasattr(target, "docx") and hasattr(target.docx, "tables"):
        tables = list(target.docx.tables)
    elif hasattr(target, "tables"):
        tables = list(target.tables)
    elif hasattr(target, "rows"):
        tables = [target]
    elif isinstance(target, (list, tuple)):
        for item in target:
            if hasattr(item, "rows"):
                tables.append(item)
            elif hasattr(item, "paragraphs") and hasattr(item, "_tc"):
                apply_banner_shading(item, is_defective=is_defective)
        return target

    # 3. Process table cells
    for table in tables:
        seen_tcs: set[Any] = set()
        for row in table.rows:
            for cell in row.cells:
                tc = _get_cell_tc(cell)
                if tc in seen_tcs:
                    continue
                seen_tcs.add(tc)

                text = cell.text.strip()
                if is_defective is None:
                    if is_defect_forwarding_text(text):
                        set_cell_shading(cell, COLOR_DEFECT)
                    elif is_healthy_banner_text(text):
                        set_cell_shading(cell, COLOR_HEALTHY)
                elif is_defective is True:
                    if is_defect_forwarding_text(text) or "analysis" in text.lower() or "recommendation" in text.lower():
                        # Exclude pure header row 'Analysis & Recommendations:' if it's white/static
                        if text.strip().rstrip(":").lower() not in ("analysis & recommendations", "analysis & recommendation"):
                            set_cell_shading(cell, COLOR_DEFECT)
                else:  # is_defective is False
                    if is_healthy_banner_text(text) or (
                        "analysis:" in text.lower() and "defect" not in text.lower()
                    ):
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
                    if isinstance(v, (str, Path)) and str(v).strip() and str(v) != "-":
                        v_path = Path(v)
                        if v_path.is_file():
                            obj[k] = InlineImage(doc, str(v_path), width=Mm(image_width_mm))
                        else:
                            obj[k] = ""
                    elif isinstance(v, InlineImage):
                        v.tpl = doc
                    elif v is None or v == "-":
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
        template_path_or_output: str | Path,
        output_path_or_context: Path | str | dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        *,
        defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
        is_defective: bool | None = None,
        overview: bool = False,
        image_width_mm: float = 80.0,
    ) -> Path:
        """Render scanning template with docxtpl and apply dynamic OpenXML cell shading.

        Supports two calling patterns:
        1. renderer = FullReportScanPageRendererCore(template_path)
           renderer.render(output_path, context, ...)
        2. renderer = FullReportScanPageRendererCore()
           renderer.render(template_path, output_path, context, ...)
        """
        # Resolve positional arguments
        if self.template_path is not None and isinstance(output_path_or_context, dict) and context is None:
            actual_template = self.template_path
            actual_output = Path(template_path_or_output)
            raw_context = output_path_or_context
        else:
            actual_template = Path(template_path_or_output) if template_path_or_output else self.template_path
            actual_output = Path(output_path_or_context) if output_path_or_context is not None else None
            raw_context = context if context is not None else {}

        if actual_template is None or not actual_template.is_file():
            raise FileNotFoundError(f"Scanning template file not found: {actual_template}")
        if actual_output is None:
            raise ValueError("Output path must be provided")

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
            if tech_key in render_ctx and isinstance(render_ctx[tech_key], dict):
                sev_val = str(render_ctx[tech_key].get("severity", "")).upper()
                if sev_val in ("DEFECT", "DEFECTIVE"):
                    def_techs.add(tech_token)

        if is_defective is True and not def_techs:
            def_techs.add("IR")

        # Inject severity sentinels so Jinja places markers into cells for post-processing
        for tech_key, marker in (
            ("ir", SEVERITY_MARKER_IR),
            ("us", SEVERITY_MARKER_US),
            ("tev", SEVERITY_MARKER_TEV),
        ):
            if tech_key in render_ctx and isinstance(render_ctx[tech_key], dict):
                if render_ctx[tech_key].get("severity") != "-":
                    render_ctx[tech_key]["severity"] = marker
            else:
                render_ctx.setdefault(tech_key, {})["severity"] = marker

        # Inject banner analysis & recommendation per D30 if not already provided
        has_defect = (len(def_techs) > 0) or (is_defective is True)
        default_analysis = BANNER_DEFECT_FORWARDING if has_defect else BANNER_HEALTHY_ANALYSIS
        default_rec = BANNER_DEFECT_FORWARDING if has_defect else BANNER_HEALTHY_RECOMMENDATION

        if "banner" not in render_ctx:
            render_ctx["banner"] = {
                "analysis": default_analysis,
                "recommendation": default_rec,
            }
        elif isinstance(render_ctx["banner"], dict):
            render_ctx["banner"].setdefault("analysis", default_analysis)
            render_ctx["banner"].setdefault("recommendation", default_rec)

        render_ctx.setdefault(
            "analysis",
            render_ctx["banner"]["analysis"] if isinstance(render_ctx.get("banner"), dict) else default_analysis,
        )
        render_ctx.setdefault(
            "recommendation",
            render_ctx["banner"]["recommendation"] if isinstance(render_ctx.get("banner"), dict) else default_rec,
        )

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
        apply_banner_shading(doc)

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
    # Core Renderer
    "FullReportScanPageRendererCore",
    "render_scan_page",
]
