"""Core Scan Page Renderer & Dynamic Shading Engine for Full Report (Ticket #30 / T4.2a).

Renders transparent Jinja2 scanning templates under templates/FULL REPORT/NORMAL IR US TEV/
via docxtpl and dynamically applies OpenXML cell shading per D30 and D32:
- Technology severity cells (IR, US, TEV): Green 00B050 (healthy) or Red EE0000 (defective), clearing text.
- Analysis & Recommendation banner: Green 00B050 for 'No Anomaly.' or Red EE0000 for defect forwarding prose.
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Any

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

from src.quick_report.prpd import is_blank_or_invalid_image

from src.quick_report.cbm_render import (
    _build_jinja_env,
    _preserve_blank_render_values,
)
from src.core.shading import (
    COLOR_DEFECT,
    COLOR_HEALTHY,
    COLOR_NORMAL,
    BANNER_HEALTHY_ANALYSIS,
    BANNER_HEALTHY_RECOMMENDATION,
    BANNER_DEFECT_FORWARDING,
    BANNER_DEFECT_FORWARDING_ANALYSIS,
    BANNER_DEFECT_FORWARDING_RECOMMENDATION,
    SEVERITY_MARKER_IR,
    SEVERITY_MARKER_US,
    SEVERITY_MARKER_TEV,
    _normalize_technologies,
    get_cell_shading,
    detect_cell_technology,
    is_defect_forwarding_text,
    is_healthy_banner_text,
    apply_technology_severity_shading,
    apply_banner_shading,
    cleanup_dash_measurement_units,
    apply_scan_post_processing,
)

logger = logging.getLogger(__name__)



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
                            if is_blank_or_invalid_image(v_path):
                                logger.warning(
                                    "Blank, invalid, or corrupt image at %s; falling back to blank",
                                    v_path,
                                )
                                obj[k] = ""
                            else:
                                try:
                                    obj[k] = InlineImage(doc, str(v_path), width=Mm(image_width_mm))
                                except Exception as exc:
                                    logger.warning(
                                        "Failed to bind InlineImage at %s: %s; falling back to blank",
                                        v_path,
                                        exc,
                                    )
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
        blank_tev: bool | None = None,
        blank_us: bool | None = None,
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

        # Resolve whether switchgear TEV/US cells should be blanked
        should_blank_tev = (
            blank_tev
            if blank_tev is not None
            else bool(
                render_ctx.get("__blank_tev__")
                or render_ctx.get("blank_tev")
                or (render_ctx.get("is_tev_active") is False)
            )
        )
        should_blank_us = (
            blank_us
            if blank_us is not None
            else bool(
                render_ctx.get("__blank_us__")
                or render_ctx.get("blank_us")
                or (render_ctx.get("is_us_active") is False)
            )
        )

        # Apply dynamic post-render OpenXML DOM shading
        apply_scan_post_processing(
            doc,
            defective_technologies=def_techs,
            is_defective=has_defect,
            is_overview=overview,
            blank_tev=should_blank_tev,
            blank_us=should_blank_us,
        )

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
        blank_tev: bool | None = None,
        blank_us: bool | None = None,
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
            blank_tev=blank_tev,
            blank_us=blank_us,
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
    blank_tev: bool | None = None,
    blank_us: bool | None = None,
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
        blank_tev=blank_tev,
        blank_us=blank_us,
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
    "cleanup_dash_measurement_units",
    "get_cell_shading",
    # Core Renderer
    "FullReportScanPageRendererCore",
    "render_scan_page",
]
