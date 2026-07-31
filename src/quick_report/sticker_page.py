"""Part 7: Sticker Page Generator."""

from __future__ import annotations

import gc
from pathlib import Path

from docxtpl import DocxTemplate

from src.quick_report.cbm_render import _build_jinja_env, _preserve_blank_render_values


def build_sticker_page_context(pe_info: dict) -> dict:
    """Build context for the sticker page."""
    return pe_info.copy()


def generate_sticker_page(pe_info: dict, template_path: str | Path, output_dir: str | Path, substation_number: int) -> Path:
    """Generate sticker page."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    doc = DocxTemplate(template_p)
    context = build_sticker_page_context(pe_info)
    doc.render(_preserve_blank_render_values(context), jinja_env=_build_jinja_env(), autoescape=True)
    
    out_path = Path(output_dir) / f"{substation_number:03d}_7 STICKER PAGE.docx"
    doc.save(out_path)
    
    return out_path
