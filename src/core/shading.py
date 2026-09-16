"""Unified cell shading and post-render styling engine.

Single source of truth for:
- Canonical color hex codes (COLOR_DEFECT, COLOR_HEALTHY, COLOR_NORMAL, COLOR_WHITE)
- Technology severity placeholder markers (__SEVERITY_IR__, __SEVERITY_US__, __SEVERITY_TEV__)
- Technology normalization supporting composite '+', ',', '/' delimiters
- Cell technology detection and banner text identification
- OpenXML table cell shading, border, and text clearing operations
- Dynamic technology severity shading and analysis/recommendation banner shading
- Dash measurement unit cleanup ('-dB', '-°C', etc.)
- apply_scan_post_processing() pipeline for Quick Report and Full Report
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# ─── Canonical Color Hex Codes ───────────────────────────────────────────────
COLOR_DEFECT: str = "EE0000"   # Red
COLOR_HEALTHY: str = "00B050"  # Green
COLOR_NORMAL: str = "00B050"   # Alias for healthy
COLOR_WHITE: str = "FFFFFF"    # White

# ─── Canonical Banner Texts ──────────────────────────────────────────────────
BANNER_HEALTHY_ANALYSIS: str = "No Anomaly."
BANNER_HEALTHY_RECOMMENDATION: str = "-"
BANNER_DEFECT_FORWARDING: str = "Please refer to the following page for details defect."
BANNER_DEFECT_FORWARDING_ANALYSIS: str = "Please refer to the following page for details defect."
BANNER_DEFECT_FORWARDING_RECOMMENDATION: str = "Please refer to the following page for details defect."

# ─── Sentinels for Jinja Severity Placeholders ────────────────────────────────
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
    normalizes recognized modalities ('IR', 'US', 'TEV'). Supports composite
    delimiters ('+', ',', '/').
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


def clear_cell_text(cell: Any) -> None:
    """Clear paragraph text and run text in a python-docx table cell."""
    for paragraph in getattr(cell, "paragraphs", ()):
        for run in getattr(paragraph, "runs", ()):
            run.text = ""
        paragraph.text = ""


def set_cell_shading(cell: Any, hex_color: str) -> None:
    """Set background fill color on a python-docx table cell (e.g. 'EE0000' or '00B050')."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color.lstrip("#").upper())


def get_cell_shading(cell: Any) -> str | None:
    """Read w:fill hex color attribute from a table cell's tcPr/w:shd XML element."""
    if not hasattr(cell, "_tc"):
        return None
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        return None
    return shd.attrib.get(qn("w:fill"))


def clear_cell_shading(cell: Any) -> None:
    """Remove background shading (<w:shd>) from a table cell."""
    if not hasattr(cell, "_tc"):
        return
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is not None:
        tcPr.remove(shd)


def _set_tc_border_nil(cell: Any, border_name: str) -> None:
    """Set a specific border on a cell to nil."""
    if not hasattr(cell, "_tc"):
        return
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)
    border = tcBorders.find(qn(f"w:{border_name}"))
    if border is None:
        border = OxmlElement(f"w:{border_name}")
        tcBorders.append(border)
    border.set(qn("w:val"), "nil")


def set_cell_no_borders(cell: Any) -> None:
    """Set all borders on a python-docx table cell to nil (invisible)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)

    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tcBorders.find(qn(f"w:{border_name}"))
        if border is None:
            border = OxmlElement(f"w:{border_name}")
            tcBorders.append(border)
        border.set(qn("w:val"), "nil")


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
    """Check if cell text corresponds to downstream defect forwarding prose."""
    lower = text.lower()
    return (
        "please refer to the following page for detail" in lower
        or "please refer to the following page for details" in lower
        or "refer to the following page" in lower
        or "following page for details defect" in lower
        or "following page for detail defect" in lower
    )


def is_healthy_banner_text(text: str) -> bool:
    """Check if cell text corresponds to healthy Analysis / Recommendation prose."""
    lower = text.lower().strip()
    if not lower:
        return False
    if is_defect_forwarding_text(lower):
        return False

    # Check for explicit English phrases
    if "no anomaly" in lower or "no defect" in lower:
        return True

    # Require explicit prefix: 'analysis:' or 'recommendation:'
    m = re.match(r"^(?:analysis|recommendation)\s*:\s*(.*)$", lower)
    if m:
        clean = m.group(1).strip()
        if not clean or clean in ("-", "--", "none", "n/a", "na", "nil", "normal"):
            return True
        if "no anomaly" in clean or "no defect" in clean:
            return True

    return False


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
    is_overview: bool = False,
) -> Any:
    """Dynamically shade technology severity cells (IR, US, TEV) Green or Red, clearing text.

    - Healthy cell: Green '00B050', text cleared.
    - Defective cell: Red 'EE0000', text cleared.
    - On overview pages (is_overview=True): cell text is cleared and set to '-'.

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
        if is_overview:
            if getattr(cell, "paragraphs", None):
                cell.paragraphs[0].text = "-"
        else:
            set_cell_shading(cell, COLOR_DEFECT if cell_defective else COLOR_HEALTHY)

    return target


def _sanitize_healthy_banner_cell(cell: Any) -> None:
    """Sanitize leftover defect forwarding prose in a healthy banner cell."""
    text = cell.text.strip()
    lower = text.lower()
    if lower.startswith("analysis:"):
        clear_cell_text(cell)
        p = cell.paragraphs[0] if getattr(cell, "paragraphs", None) else cell.add_paragraph()
        r0 = p.add_run("Analysis: ")
        r0.bold = True
        r0.italic = True
        r1 = p.add_run(" ")
        r2 = p.add_run("No Anomaly.")
    elif lower.startswith("recommendation:"):
        clear_cell_text(cell)
        p = cell.paragraphs[0] if getattr(cell, "paragraphs", None) else cell.add_paragraph()
        r0 = p.add_run("Recommendation: ")
        r0.bold = True
        r0.italic = True
        r1 = p.add_run(" ")
        r2 = p.add_run("-")
    elif is_defect_forwarding_text(text):
        clear_cell_text(cell)
        p = cell.paragraphs[0] if getattr(cell, "paragraphs", None) else cell.add_paragraph()
        p.add_run("No Anomaly.")


def apply_banner_shading(
    target: Any,
    *,
    is_defective: bool | None = None,
) -> Any:
    """Dynamically shade Analysis & Recommendation banner cells.

    - Healthy ('No Anomaly.'): Green '00B050'. If cell text has leftover defect text,
      sanitizes it to 'Analysis:  No Anomaly.' / 'Recommendation:  -'.
    - Defect Forwarding prose or is_defective=True: Red 'EE0000'.

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

        if not single_cell_mode:
            is_banner_candidate = (
                lower.startswith("analysis:")
                or lower.startswith("recommendation:")
                or is_defect_forwarding_text(text)
            )
            if not is_banner_candidate:
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
                or lower.startswith("analysis:")
                or lower.startswith("recommendation:")
                or is_defect_forwarding_text(text)
            ):
                if is_defect_forwarding_text(text) or "defect" in lower:
                    _sanitize_healthy_banner_cell(cell)
                set_cell_shading(cell, COLOR_HEALTHY)
        else:  # is_defective is None
            if is_defect_forwarding_text(text):
                set_cell_shading(cell, COLOR_DEFECT)
            elif is_healthy_banner_text(text):
                set_cell_shading(cell, COLOR_HEALTHY)

    return target


def cleanup_dash_measurement_units(target: Any) -> Any:
    """Clean up '-dB', '- dB', '-°C', '- °C', '-%' artifacts produced when a measurement is '-'."""
    cells = _iter_unique_cells(target)
    for cell in cells:
        for p in getattr(cell, "paragraphs", ()):
            for run in getattr(p, "runs", ()):
                if run.text:
                    for bad in ("-dB", "- dB", "-°C", "- °C", "-%"):
                        if bad in run.text:
                            run.text = run.text.replace(bad, "-")
    return target


# ─── Switchgear Compartment TEV Eligibility (Two-Tier Model) ──────────────────
TEV_ELIGIBLE_SWG_COMPARTMENTS: frozenset[str] = frozenset({
    "BREAKER COMPARTMENT",
    "CABLE COMPARTMENT",
    "PT COMPARTMENT",
    "FUSE COMPARTMENT",
})

TEV_BLANKED_SWG_COMPARTMENTS: frozenset[str] = frozenset({
    "CABLE ENTRY",
    "BUSBAR COMPARTMENT",
})


def normalize_swg_compartment(compartment: str | None) -> str:
    """Normalize raw compartment or defect area string to canonical switchgear compartment name."""
    if not compartment:
        return ""
    comp_upper = str(compartment).strip().upper()

    # Direct canonical membership check
    if comp_upper in TEV_ELIGIBLE_SWG_COMPARTMENTS or comp_upper in TEV_BLANKED_SWG_COMPARTMENTS:
        return comp_upper

    # Specific precedence rules:
    # 1. Cable Entry before generic Cable
    if "CABLE ENTRY" in comp_upper:
        return "CABLE ENTRY"

    # 2. Busbar
    if "BUSBAR" in comp_upper:
        return "BUSBAR COMPARTMENT"

    # 3. Fuse (e.g. INDKOM RMU fuse compartment / outgoing fuse)
    if "FUSE" in comp_upper:
        return "FUSE COMPARTMENT"

    # 4. Breaker (VCB / Spout / Chamber)
    if any(k in comp_upper for k in ("BREAKER", "VCB", "SPOUT", "CHAMBER")):
        return "BREAKER COMPARTMENT"

    # 5. PT (Potential / Voltage Transformer)
    if re.search(r"\bPT\b", comp_upper) or "VOLTAGE TRANSFORMER" in comp_upper:
        return "PT COMPARTMENT"

    # 6. Cable (e.g. Cable Box, Cable Termination, Cable Lug)
    if "CABLE" in comp_upper:
        return "CABLE COMPARTMENT"

    return comp_upper


def is_swg_compartment_tev_eligible(compartment: str | None) -> bool:
    """Determine if a switchgear compartment is eligible for TEV testing (Tier 2).

    TEV-Eligible:
    - BREAKER COMPARTMENT
    - CABLE COMPARTMENT
    - PT COMPARTMENT
    - FUSE COMPARTMENT (e.g. INDKOM RMUs)

    Non-TEV / Blanked:
    - CABLE ENTRY
    - BUSBAR COMPARTMENT
    - Any other compartment not in the eligible set.
    """
    normalized = normalize_swg_compartment(compartment)
    return normalized in TEV_ELIGIBLE_SWG_COMPARTMENTS


def is_tev_contract_awarded(technologies: Sequence[str] | set[str] | None) -> bool:
    """Check if TEV is in project awarded technologies (Tier 1).

    If technologies is omitted or None, defaults to True (standard 3-technology contract).
    """
    if technologies is None:
        return True
    norm_techs = _normalize_technologies(technologies)
    if not norm_techs:
        return True
    return "TEV" in norm_techs


def is_swg_tev_active(
    project_technologies: Sequence[str] | set[str] | None = None,
    compartment: str | None = None,
) -> bool:
    """Two-tier evaluation of switchgear panel TEV activity.

    Returns True only if:
    1. Tier 1: Contract includes TEV technology.
    2. Tier 2: Switchgear compartment is TEV-eligible.
    """
    if not is_tev_contract_awarded(project_technologies):
        return False
    return is_swg_compartment_tev_eligible(compartment)


def blank_swg_tev_cells(target: Any) -> Any:
    """Blank TEV measurement cells in swg-panel.docx 37x24 table.

    Operates on rows 21–32 (indices 21..32 inclusive) and columns 11–22 (indices 11..22 inclusive).
    - Clears cell text
    - Removes background cell shading (<w:shd>)
    - Sets all borders to <w:val="nil"/>
    Also clears bordering spacer borders facing the TEV block to avoid ghost border artifacts.
    """
    tables = []
    if hasattr(target, "docx") and hasattr(target.docx, "tables"):
        tables = target.docx.tables
    elif hasattr(target, "tables"):
        tables = target.tables
    elif hasattr(target, "rows") and hasattr(target, "columns"):
        tables = [target]

    for table in tables:
        # Match swg-panel.docx 37x24 table layout
        if len(table.rows) >= 33 and len(table.columns) >= 23:
            seen_tcs = set()
            for r in range(21, 33):
                for c in range(11, 23):
                    cell = table.cell(r, c)
                    if cell._tc not in seen_tcs:
                        seen_tcs.add(cell._tc)
                        clear_cell_text(cell)
                        clear_cell_shading(cell)
                        set_cell_no_borders(cell)

            # Clear adjacent spacer borders facing the TEV block
            for r in range(21, 33):
                _set_tc_border_nil(table.cell(r, 10), "right")
                if len(table.columns) > 23:
                    _set_tc_border_nil(table.cell(r, 23), "left")
            for c in range(11, 23):
                _set_tc_border_nil(table.cell(20, c), "bottom")
                if len(table.rows) > 33:
                    _set_tc_border_nil(table.cell(33, c), "top")

    return target


def apply_scan_post_processing(
    target: Any,
    *,
    defective_technologies: set[str] | list[str] | tuple[str, ...] | str | None = None,
    is_defective: bool | None = None,
    is_overview: bool = False,
    blank_tev: bool = False,
) -> Any:
    """Unified post-render processing engine for scanning pages and CBM defect pages.

    1. If blank_tev is True, clears text, shading, and sets nil borders for TEV cells on swg-panel.docx.
    2. Applies technology severity shading (IR, US, TEV cells) Green/Red, clearing text.
       (If is_overview is True, clears text and sets to '-' if applicable).
    3. Applies banner shading (Analysis / Recommendation) Green ('00B050') or Red ('EE0000').
    4. Cleans up dash measurement unit artifacts ('-dB', '-°C', etc.).
    5. If blank_tev is True, re-verifies TEV cells remain strictly blanked, unshaded, and borderless.
    """
    if blank_tev:
        blank_swg_tev_cells(target)

    def_techs = _normalize_technologies(defective_technologies)
    if is_defective is True and not def_techs and not is_overview:
        def_techs.add("IR")

    if blank_tev and "TEV" in def_techs:
        def_techs.remove("TEV")

    apply_technology_severity_shading(
        target,
        defective_technologies=def_techs,
        is_overview=is_overview,
    )
    apply_banner_shading(target, is_defective=is_defective)
    cleanup_dash_measurement_units(target)

    if blank_tev:
        blank_swg_tev_cells(target)

    return target


__all__ = [
    "COLOR_DEFECT",
    "COLOR_HEALTHY",
    "COLOR_NORMAL",
    "COLOR_WHITE",
    "BANNER_HEALTHY_ANALYSIS",
    "BANNER_HEALTHY_RECOMMENDATION",
    "BANNER_DEFECT_FORWARDING",
    "BANNER_DEFECT_FORWARDING_ANALYSIS",
    "BANNER_DEFECT_FORWARDING_RECOMMENDATION",
    "SEVERITY_MARKER_IR",
    "SEVERITY_MARKER_US",
    "SEVERITY_MARKER_TEV",
    "TEV_ELIGIBLE_SWG_COMPARTMENTS",
    "TEV_BLANKED_SWG_COMPARTMENTS",
    "clear_cell_text",
    "set_cell_shading",
    "get_cell_shading",
    "clear_cell_shading",
    "set_cell_no_borders",
    "detect_cell_technology",
    "is_defect_forwarding_text",
    "is_healthy_banner_text",
    "normalize_swg_compartment",
    "is_swg_compartment_tev_eligible",
    "is_tev_contract_awarded",
    "is_swg_tev_active",
    "blank_swg_tev_cells",
    "apply_technology_severity_shading",
    "apply_banner_shading",
    "cleanup_dash_measurement_units",
    "apply_scan_post_processing",
]
