"""VI quick-report rendering engine and context builders."""

from __future__ import annotations

import gc
from pathlib import Path

from docxtpl import DocxTemplate

from src.quick_report.cbm_render import _build_jinja_env, _preserve_blank_render_values

# Constants
DEFECTS_PER_PAGE = 6


import warnings

def _remove_empty_cell_borders(docx_path: Path, active_count: int) -> None:
    """Clear borders for unused VI defect card cells to clean up the page. (DEPRECATED)"""
    warnings.warn("_remove_empty_cell_borders is deprecated, use src.quick_report.vi_defect_pages instead", DeprecationWarning, stacklevel=2)
    from src.quick_report.vi_defect_pages import _remove_empty_cell_borders as _new_func
    _new_func(docx_path, active_count)


def generate_vi_summary(pe_info: dict, defects: list[dict], template_path: str, output_dir: str, substation_number: int) -> Path:
    """Generate VI defect summary page. (DEPRECATED)"""
    warnings.warn("generate_vi_summary is deprecated, use src.quick_report.vi_summary instead", DeprecationWarning, stacklevel=2)
    from src.quick_report.vi_summary import generate_vi_summary as _new_func
    return _new_func(pe_info, defects, template_path, output_dir, substation_number)



def generate_vi_defect_page(defects: list[dict], template_path: str, output_dir: str, substation_number: int, pe_info: dict) -> list[Path]:
    """Generate VI defect pages dynamically with automatic pagination. (DEPRECATED)"""
    warnings.warn("generate_vi_defect_page is deprecated, use src.quick_report.vi_defect_pages instead", DeprecationWarning, stacklevel=2)
    from src.quick_report.vi_defect_pages import generate_vi_defect_pages as _new_func
    return _new_func(defects, template_path, output_dir, substation_number, pe_info)
