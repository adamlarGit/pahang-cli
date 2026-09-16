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
    
    out_path = Path(output_dir) / f"{substation_number:03d}_01_front_page.docx"
    context = build_front_page_context(pe_info)
    # Front page is a metadata cover page (substation info, date, crew, equipment tools).
    # Suppress scan post-processing to prevent Table 1 "TEV" labels (under SCANNED BY and
    # EQUIPMENT/TOOLS) from being falsely detected as severity cells and wiped/shaded green.
    _render_docx_template(template_path, out_path, context, scan_post_process=False)
    return out_path
