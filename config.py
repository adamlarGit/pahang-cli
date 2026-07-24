"""Centralized configuration for the Pahang CLI."""
from __future__ import annotations

from pathlib import Path

_CONFIG_FILE = Path(__file__).parent / ".cli_config.json"

# ─── Station Mapping (global, shared across Pahang area projects) ───
STATION_MAPPING: dict[str, str] = {
    "CMRN": "MARAN",
    "CKTN": "KUANTAN",
    "CJEN": "JENGKA",
    "CBMS": "MUADZAM SHAH",
    "CBTG": "BENTONG",
    "CBGB": "GEBENG",
    "CROM": "ROMPIN",
    "CTML": "TEMERLOH",
    "CPEK": "PEKAN",
    "CTRI": "TRIANG",
    "CKLS": "KUALA LIPIS",
    "CCHL": "CAMERON HIGHLAND",
    "CRAU": "RAUB",
    "CJRT": "JERANTUT",
}

GLOBAL_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"

# ─── Template Paths (relative to global package templates directory) ───
TEMPLATES: dict[str, str] = {
    "whatsapp_template": r"WHATSAPP\TEMPLATE WHATSAPP.docx",
    "vi_front_page": r"QUICK REPORT\1. FRONT PAGE TEMPLATE IR BOX Jinja2 updated.docx",
    "vi_front_page_ir_us_tev": r"QUICK REPORT\1. FRONT PAGE TEMPLATE IR US TEV BOX Jinja2 updated.docx",
    "vi_summary": r"QUICK REPORT\2. VI SUMMARY TEMPLATE Jinja2.docx",
    "vi_defect": r"QUICK REPORT\10. VISUAL DEFECT Jinja2.docx",
    "cbm_summary": r"QUICK REPORT\CBM DEFECT SUMMARY.docx",
    "cbm_defect": r"QUICK REPORT\SUBSTATION CONFIGURATION\2B CBM DEFECT.docx",
    "sub_cond_dir": r"QUICK REPORT\SUBSTATION CONFIGURATION",
    
    # CBM Defect Pages (IR/US/TEV)
    "fp_overview": r"QUICK REPORT\DEFECT IR\fp-overview.docx",
    "fp_individual_defect": r"QUICK REPORT\DEFECT IR\fp-individual-defect.docx",
    "swg_overview": r"QUICK REPORT\DEFECT IR\swg-overview.docx",
    "swg_panel": r"QUICK REPORT\DEFECT IR\swg-panel.docx",
    "tx_overview": r"QUICK REPORT\DEFECT IR\tx-overview.docx",
    "tx_hv_sides": r"QUICK REPORT\DEFECT IR\tx-hv-sides.docx",
    "tx_lv_sides": r"QUICK REPORT\DEFECT IR\tx-lv-sides.docx",
    "blackbox_overview": r"QUICK REPORT\DEFECT IR\blackbox-overview.docx",
    "battery_overview": r"QUICK REPORT\DEFECT IR\battery-overview.docx",
}

# ─── Seed Files for Onboarding (source relative to GLOBAL_TEMPLATES_DIR -> target relative to base_path) ───
SEED_FILES: dict[str, str] = {
    r"DATA MSMS.xlsx": r"PYTHON\DATA MSMS.xlsx",
    r"TOTAL PE.xlsx": r"PYTHON\TOTAL PE.xlsx",
}

# ─── File Patterns ───
ENGR_FILE_PATTERN: str = r"PYTHON\ENGR FROM DRIVE\ENGR-*.xlsx"

# ─── Project-specific Constants ───
PROJECT_CONSTANTS: dict[str, int] = {
    "total_plan": 300,
    "defects_per_page": 6,
}
