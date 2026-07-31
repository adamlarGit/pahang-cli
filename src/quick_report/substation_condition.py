"""Substation condition page generation for Quick Reports (Part 5)."""

from __future__ import annotations

import logging
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docxtpl import DocxTemplate

from src.testsheet.models import SubstationTestsheetPackage


def build_substation_condition_pairs(pkg: SubstationTestsheetPackage | None = None) -> list[tuple[str, str]]:
    """
    Build active 2-column pairs for the substation condition page based on
    substation technology and equipment inventory.
    """
    pairs: list[tuple[str, str]] = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD")
    ]

    if not pkg or not pkg.data:
        return pairs

    substation_type = (pkg.data.substation_type or "").upper()

    # Switchgear
    pairs.append(("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE"))

    # Transformer
    pairs.append(("TRANSFORMER 1", "TRANSFORMER 1 NAMEPLATE"))

    # Feeder Pillar / LVDB
    fp_label = "LVDB" if "LVDB" in substation_type else "FEEDER PILLAR 1"
    pairs.append((fp_label, f"{fp_label} NAMEPLATE"))

    # Battery Charger
    pairs.append(("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE"))

    # RTU (if MRMU or RTU)
    if "MRMU" in substation_type or "RTU" in substation_type:
        pairs.append(("RTU", "RTU NAMEPLATE"))

    # EFI / SF6 Gas Indicator (if SF6 or MRMU)
    if "SF6" in substation_type or "MRMU" in substation_type:
        pairs.append(("EFI", "SF6 GAS INDICATOR"))

    # Fire Extinguisher
    pairs.append(("FIRE EXTINGUISHER", "FIRE EXTINGUISHER EXPIRY DATE"))

    # Transformer Oil Level Indicator
    pairs.append(("TRANSFORMER OIL LEVEL INDICATOR", "TRANSFORMER OIL LEVEL INDICATOR"))

    return pairs


def _clear_cell_text(cell) -> None:
    """Clear paragraph text and run text in cell."""
    for paragraph in cell.paragraphs:
        for run in paragraph.runs:
            run.text = ""
        paragraph.text = ""


def _set_cell_no_borders(cell) -> None:
    """Construct/update <w:tcBorders> XML element on cell tcPr with w:val='nil'."""
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


def _remove_empty_cell_borders_sub_cond(docx_path: Path, active_count: int) -> None:
    """Clear borders and text for unused substation condition cells safely using python-docx oxml."""
    if active_count >= 3:
        return

    try:
        doc = Document(docx_path)
        if len(doc.tables) >= 3:
            for i in range(active_count, len(doc.tables)):
                table = doc.tables[i]
                for row in table.rows:
                    for cell in row.cells:
                        _clear_cell_text(cell)
                        _set_cell_no_borders(cell)
        elif len(doc.tables) == 1:
            table = doc.tables[0]
            for slot_idx in range(active_count, 3):
                row_indices = (slot_idx * 2, slot_idx * 2 + 1)
                for r_idx in row_indices:
                    if r_idx < len(table.rows):
                        for cell in table.rows[r_idx].cells:
                            _clear_cell_text(cell)
                            _set_cell_no_borders(cell)

        doc.save(docx_path)
    except Exception as exc:
        logging.warning(f"Failed to remove empty cell borders for {docx_path}: {exc}")


def generate_substation_condition_pages(
    pe_info: dict,
    pkg: SubstationTestsheetPackage | None,
    template_path: Path | str,
    output_dir: Path | str,
    substation_number: int
) -> list[Path]:
    """Generate substation condition pages."""
    t_path = Path(template_path)
    if not t_path.exists():
        raise FileNotFoundError(f"Template path does not exist: {t_path}")
        
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    pairs = build_substation_condition_pairs(pkg)
    chunks = [pairs[i:i + 3] for i in range(0, len(pairs), 3)]
    if not chunks:
        chunks = [[]]
        
    parts: list[Path] = []
    
    for idx, chunk in enumerate(chunks, start=1):
        cond_out = out_dir / f"{substation_number:03d}_5 SUBSTATION CONDITION part{idx}.docx"
        
        padded_chunk = list(chunk)
        while len(padded_chunk) < 3:
            padded_chunk.append(("", ""))
            
        context = {
            "pairs": [
                {
                    "header_left": p[0],
                    "header_right": p[1],
                    "photo_left": "",
                    "photo_right": "",
                }
                for p in padded_chunk
            ]
        }
        context.update(pe_info)
        
        doc = DocxTemplate(str(t_path))
        doc.render(context)
        doc.save(cond_out)
        
        if idx == len(chunks) and len(chunk) < 3:
            _remove_empty_cell_borders_sub_cond(cond_out, len(chunk))
            
        parts.append(cond_out)
        
    return parts
