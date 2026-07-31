"""Part 1: Front Page Generator"""
from pathlib import Path

from src.quick_report.cbm_render import _render_docx_template

def build_front_page_context(pe_info: dict) -> dict:
    """Pure context builder for the front page."""
    return pe_info.copy()

def generate_front_page(pe_info: dict, template_path: str | Path, output_dir: str | Path, substation_number: int) -> Path:
    """Generate the CBM quick report front page."""
    template_p = Path(template_path)
    if not template_p.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    
    out_path = Path(output_dir) / f"{substation_number:03d}_1 FRONT PAGE.docx"
    context = build_front_page_context(pe_info)
    _render_docx_template(template_path, out_path, context)
    return out_path
