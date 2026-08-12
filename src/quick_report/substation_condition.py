"""Substation condition page generation for Quick Reports (Part 5)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt
from docxcompose.composer import Composer as DocxComposer
from docxtpl import DocxTemplate

from src.quick_report.utils import clear_cell_text, set_cell_no_borders
from src.testsheet.models import SubstationTestsheetPackage


def build_substation_condition_pairs(pkg: SubstationTestsheetPackage | None = None) -> list[tuple[str, str]]:
    """
    Build active 2-column pairs for the substation condition page based on
    substation technology and equipment inventory.

    NOTE: Reserved for future dynamic pair builder. When substations have variable
    equipment configurations, this function will replace the hardcoded pairs
    in QuickReportTransformer._build_substation_condition_pairs().
    See: src/quick_report/transformer.py -> _build_substation_condition_pairs()
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
                        clear_cell_text(cell)
                        set_cell_no_borders(cell)
        elif len(doc.tables) == 1:
            table = doc.tables[0]
            for slot_idx in range(active_count, 3):
                row_indices = (slot_idx * 2, slot_idx * 2 + 1)
                for r_idx in row_indices:
                    if r_idx < len(table.rows):
                        for cell in table.rows[r_idx].cells:
                            clear_cell_text(cell)
                            set_cell_no_borders(cell)

        doc.save(docx_path)
    except Exception as exc:
        logging.warning(f"Failed to remove empty cell borders for {docx_path}: {exc}")


def generate_substation_condition_pages(
    pe_info: dict,
    condition_pairs_or_pkg: Sequence[tuple[str, str]] | SubstationTestsheetPackage | None,
    template_path: Path | str,
    output_dir: Path | str,
    substation_number: int,
) -> list[Path]:
    """Generate substation condition pages."""
    t_path = Path(template_path)
    if not t_path.exists():
        raise FileNotFoundError(f"Template path does not exist: {t_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(condition_pairs_or_pkg, (list, tuple)):
        pairs = list(condition_pairs_or_pkg)
    else:
        pairs = build_substation_condition_pairs(condition_pairs_or_pkg)
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

        # Shrink trailing paragraph to near-zero height to prevent overflow.
        # Word requires a mandatory <w:p> after every table; if the 3-pair
        # table fills the page, this paragraph spills onto page 2 and
        # causes blank pages during COM assembly.  Setting line_spacing_rule
        # to EXACTLY is critical — without it Word ignores the small size.
        if doc.paragraphs:
            last_para = doc.paragraphs[-1]
            pf = last_para.paragraph_format
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(0.5)
            for run in last_para.runs:
                run.font.size = Pt(0.5)
            if not last_para.runs:
                run = last_para.add_run()
                run.font.size = Pt(0.5)

        doc.save(cond_out)

        if idx == len(chunks) and len(chunk) < 3:
            _remove_empty_cell_borders_sub_cond(cond_out, len(chunk))

        parts.append(cond_out)

    # Merge all condition part files into a single docx so the COM
    # assembly stage pastes one file (no inter-part page breaks that
    # cause blank pages between full-page condition tables).
    if len(parts) > 1:
        merged_path = out_dir / f"{substation_number:03d}_5 SUBSTATION CONDITION.docx"
        base_doc = Document(str(parts[0]))
        composer = DocxComposer(base_doc)
        for part_path in parts[1:]:
            composer.append(Document(str(part_path)))
        composer.save(str(merged_path))

        # Post-merge: remove trailing section break and re-shrink the last paragraph.
        # docxcompose adds a trailing nextPage section break to the final paragraph
        # and may reset formatting during the merge process.
        merged_doc = Document(str(merged_path))
        if merged_doc.paragraphs:
            last_para = merged_doc.paragraphs[-1]

            # Remove trailing section break if present
            pPr = last_para._p.get_or_add_pPr()
            sectPr = pPr.find(qn("w:sectPr"))
            if sectPr is not None:
                pPr.remove(sectPr)

            # Remove trailing <w:br> page breaks injected by docxcompose
            for run in last_para.runs:
                r_elem = run._r
                for br in r_elem.findall(qn("w:br")):
                    r_elem.remove(br)
            for br in last_para._p.findall(qn("w:br")):
                last_para._p.remove(br)

            pf = last_para.paragraph_format
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(0.5)
            for run in last_para.runs:
                run.font.size = Pt(0.5)
            if not last_para.runs:
                run = last_para.add_run()
                run.font.size = Pt(0.5)
        merged_doc.save(str(merged_path))

        # Clean up individual part files.
        for p in parts:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        return [merged_path]

    return parts
