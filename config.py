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

# ─── CBM Defect Templates (filename mapping within technology folder) ───
CBM_DEFECT_TEMPLATES: dict[str, str] = {
    "fp_overview": "fp-overview.docx",
    "fp_individual_defect": "fp-individual-defect.docx",
    "swg_overview": "swg-overview.docx",
    "swg_panel": "swg-panel.docx",
    "tx_overview": "tx-overview.docx",
    "tx_hv_sides": "tx-hv-sides.docx",
    "tx_lv_sides": "tx-lv-sides.docx",
    "blackbox_overview": "blackbox-overview.docx",
    "battery_overview": "battery-overview.docx",
}

# ─── Template Paths (relative to global package templates directory) ───
TEMPLATES: dict[str, str] = {
    "whatsapp_template": r"WHATSAPP\TEMPLATE WHATSAPP PYTHON.docx",
    "vi_front_page_ir": r"QUICK REPORT\1. FRONT PAGE TEMPLATE IR BOX Jinja2 updated.docx",
    "vi_front_page_ir_us": r"QUICK REPORT\1. FRONT PAGE TEMPLATE IR US BOX Jinja2 updated.docx",
    "vi_front_page_ir_us_tev": r"QUICK REPORT\1. FRONT PAGE TEMPLATE IR US TEV BOX Jinja2 updated.docx",
    "vi_summary": r"QUICK REPORT\2. VI SUMMARY TEMPLATE Jinja2 DYNAMIC.docx",
    "vi_defect": r"QUICK REPORT\10. VISUAL DEFECT Jinja2 DYNAMIC.docx",
    "cbm_summary_ir": r"QUICK REPORT\CBM DEFECT IR SUMMARY.docx",
    "cbm_summary_ir_us": r"QUICK REPORT\CBM DEFECT IR+US SUMMARY.docx",
    "cbm_summary_ir_us_tev": r"QUICK REPORT\CBM DEFECT IR+US+TEV SUMMARY.docx",
    "sub_cond_dir": r"QUICK REPORT\SUBSTATION CONFIGURATION",
    "sub_cond_master": r"QUICK REPORT\SUBSTATION CONFIGURATION\MASTER_SUBSTATION_CONDITION.docx",
    "sticker_page": r"QUICK REPORT\SUBSTATION CONFIGURATION\11. STICKER PAGE.docx",
    
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
    "separator_sheet": r"TESTSHEET SEPARATOR\separator_sheet.pdf",

    # Full Report Templates
    "full_report_census": r"FULL REPORT\executive_summary_census.docx",
    "full_report_normal_dir": r"FULL REPORT\NORMAL IR US TEV",
    "full_report_battery_overview": r"FULL REPORT\NORMAL IR US TEV\battery-overview.docx",
    "full_report_fp_overview": r"FULL REPORT\NORMAL IR US TEV\fp-overview.docx",
    "full_report_swg_overview": r"FULL REPORT\NORMAL IR US TEV\swg-overview.docx",
    "full_report_swg_panel": r"FULL REPORT\NORMAL IR US TEV\swg-panel.docx",
    "full_report_tx_hv_sides": r"FULL REPORT\NORMAL IR US TEV\tx-hv-sides.docx",
    "full_report_tx_lv_sides": r"FULL REPORT\NORMAL IR US TEV\tx-lv-sides.docx",
    "full_report_tx_overview": r"FULL REPORT\NORMAL IR US TEV\tx-overview.docx",
}

FULL_REPORT_TEMPLATES: dict[str, str] = {
    "census": "executive_summary_census.docx",
    "battery_overview": "battery-overview.docx",
    "fp_overview": "fp-overview.docx",
    "swg_overview": "swg-overview.docx",
    "swg_panel": "swg-panel.docx",
    "tx_hv_sides": "tx-hv-sides.docx",
    "tx_lv_sides": "tx-lv-sides.docx",
    "tx_overview": "tx-overview.docx",
}

# ─── Seed Files for Onboarding (source relative to GLOBAL_TEMPLATES_DIR -> target relative to base_path) ───
SEED_FILES: dict[str, str] = {
    r"DATA MSMS.xlsx": r"PYTHON\DATA MSMS.xlsx",
    r"TOTAL PE.xlsx": r"PYTHON\TOTAL PE.xlsx",
}

# ─── File Patterns ───
# ─── Station-to-ENGR Code Mapping (for per-station ENGR workbook resolution) ───
ENGR_STATION_CODES: dict[str, str] = {
    "MARAN": "MRN",
    "KUANTAN": "KTN",
    "JENGKA": "JEN",
    "MUADZAM SHAH": "BMS",
    "BENTONG": "BTG",
    "GEBENG": "GBG",
    "ROMPIN": "ROM",
    "TEMERLOH": "TML",
    "PEKAN": "PEK",
    "TRIANG": "TRI",
    "KUALA LIPIS": "KLS",
    "CAMERON HIGHLAND": "CHL",
    "RAUB": "RAU",
    "JERANTUT": "JRT",
}

ENGR_FILE_PATTERN: str = r"PYTHON\ENGR FROM DRIVE\ENGR-*.xlsx"

# ─── Project-specific Constants ───
PROJECT_CONSTANTS: dict[str, int] = {
    "total_plan": 300,
    "defects_per_page": 6,
}
