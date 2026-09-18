"""Substation Attribution & Structural Slicing Guards Core for Full Report (Ticket #44 / Seam 1 & 4)."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import shutil
from typing import Any

import docx

logger = logging.getLogger(__name__)

# Standard electrical prefixes to normalize and strip
ELECTRICAL_PREFIXES = frozenset({
    "PE",
    "SSU",
    "PPU",
    "PMU",
    "SS",
})


def normalize_substation_tokens(name: str | None) -> set[str]:
    """Normalize substation name into canonical uppercase alphanumeric stem tokens.

    Strips:
    - Leading PE numbers and dots (e.g. '005. ', 'PE 144 ', 'P/E 179 ')
    - Standard electrical prefixes ('P/E', 'PE', 'SSU', 'PPU', 'PMU', 'S/S')
    - Parenthesized suffixes: equipment '(VCB)', defect '(IR+VI)', '(IR+US+TEV)', etc.
    - Non-alphanumeric punctuation
    """
    if not name:
        return set()

    text = str(name).strip()
    if not text or text == "-":
        return set()

    # 1. Strip parenthesized suffixes e.g. (VCB), (IR+VI), (11kV)
    text = re.sub(r"\([^)]*\)", " ", text)

    # 2. Normalize common electrical slash notations before stripping
    text = re.sub(r"\bP/E\b", "PE", text, flags=re.IGNORECASE)
    text = re.sub(r"\bS/S\b", "SS", text, flags=re.IGNORECASE)

    # 3. Strip leading number / dot sequences and electrical prefixes (e.g. "005. PE TALAPIA")
    for _ in range(2):
        text = re.sub(r"^\s*\d+\s*[\.\-]?\s*", " ", text)
        text = re.sub(r"^\s*\b(?:PE|SSU|PPU|PMU|SS)\b\s*(?:\d+[\.\-]?)?\s*", " ", text, flags=re.IGNORECASE)

    # 5. Extract alphanumeric tokens
    raw_tokens = re.findall(r"[A-Za-z0-9]+", text.upper())

    # Filter out standalone electrical prefix tokens and purely single dot/hyphens
    filtered = {
        tok for tok in raw_tokens
        if tok not in ELECTRICAL_PREFIXES
    }

    return filtered


def is_substation_attribution_match(
    target_substation: str | None,
    candidate_substation: str | None,
) -> bool:
    """Determine whether candidate substation matches target or explicitly conflicts.

    Rules:
    - Blank, empty, or '-' candidate values are permitted (returns True).
    - If target has no tokens, returns True.
    - Matching requires target name tokens match or are a subset of candidate tokens
      (or candidate tokens are a subset of target tokens to handle benign suffix/district variations).
    - If non-empty tokens explicitly conflict, returns False.
    """
    if candidate_substation is None:
        return True

    candidate_str = str(candidate_substation).strip()
    if not candidate_str or candidate_str == "-":
        return True

    target_tokens = normalize_substation_tokens(target_substation)
    if not target_tokens:
        return True

    candidate_tokens = normalize_substation_tokens(candidate_substation)
    if not candidate_tokens:
        return True

    # Benign variations: target is subset of candidate or candidate is subset of target
    if target_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(target_tokens):
        return True

    return False


def verify_cbm_defect_attribution(
    defect_slice: Any,
    target_substation: str | None,
) -> bool:
    """Validate candidate CBM defect slice metadata against target substation name.

    Returns True if compatible, False if explicitly conflicting.
    """
    substation_name: str = ""
    if hasattr(defect_slice, "substation"):
        substation_name = str(getattr(defect_slice, "substation", "") or "")
    elif isinstance(defect_slice, str):
        substation_name = defect_slice

    if not substation_name.strip() or substation_name.strip() == "-":
        logger.debug("CBM defect slice has blank substation; allowing attribution with warning.")
        return True

    matched = is_substation_attribution_match(target_substation, substation_name)
    if not matched:
        logger.warning(
            "CBM defect slice rejected: explicit conflict between target '%s' and defect substation '%s'",
            target_substation,
            substation_name,
        )
    return matched


def _extract_label_value(row: Any, c_idx: int, cell: Any, cell_text: str) -> str:
    """Extract field value following a metadata label in the same cell or subsequent cells."""
    if ":" in cell_text:
        return cell_text.split(":", 1)[1].strip()
    for next_cell in row.cells[c_idx + 1:]:
        if next_cell._tc is cell._tc:
            continue
        val = next_cell.text.strip().lstrip(":").strip()
        if val:
            return val
    return ""


def _extract_front_page_substations(table: Any) -> tuple[bool, str, str]:
    """Check if table is a front page metadata table and extract ERMS and SITE values.

    Returns:
        (is_front_page, substation_erms, substation_site)
    """
    is_front_page = False
    for row in table.rows:
        for cell in row.cells:
            cell_text = cell.text.strip().upper()
            if "SUBSTATION NAME (ERMS)" in cell_text or "SUBSTATION NAME (SITE)" in cell_text:
                is_front_page = True
                break
        if is_front_page:
            break

    if not is_front_page:
        return False, "", ""

    substation_erms = ""
    substation_site = ""
    for row in table.rows:
        for c_idx, cell in enumerate(row.cells):
            cell_text = cell.text.strip()
            label_up = cell_text.upper()
            if "SUBSTATION NAME (ERMS)" in label_up:
                val = _extract_label_value(row, c_idx, cell, cell_text)
                if val and not substation_erms:
                    substation_erms = val
            elif "SUBSTATION NAME (SITE)" in label_up:
                val = _extract_label_value(row, c_idx, cell, cell_text)
                if val and not substation_site:
                    substation_site = val

    return True, substation_erms, substation_site


def _evaluate_dual_attribution(
    erms_name: str,
    site_name: str,
    target_substation: str | None,
    context_prefix: str = "front page",
) -> tuple[bool, str]:
    """Evaluate ERMS and SITE substation names against target substation with dual-name tolerance."""
    erms_val = erms_name.strip()
    site_val = site_name.strip()
    erms_present = bool(erms_val and erms_val != "-")
    site_present = bool(site_val and site_val != "-")

    if erms_present and site_present:
        erms_match = is_substation_attribution_match(target_substation, erms_val)
        site_match = is_substation_attribution_match(target_substation, site_val)
        if erms_match or site_match:
            return True, ""
        return (
            False,
            f"Explicit foreign substation detected in {context_prefix}: ERMS='{erms_val}', SITE='{site_val}' "
            f"(target: '{target_substation}')",
        )
    elif erms_present:
        if is_substation_attribution_match(target_substation, erms_val):
            return True, ""
        return (
            False,
            f"Explicit foreign substation detected in {context_prefix} ERMS field: '{erms_val}' "
            f"(target: '{target_substation}')",
        )
    elif site_present:
        if is_substation_attribution_match(target_substation, site_val):
            return True, ""
        return (
            False,
            f"Explicit foreign substation detected in {context_prefix} SITE field: '{site_val}' "
            f"(target: '{target_substation}')",
        )

    return True, ""


def verify_front_page_attribution(
    front_page_path: Path | str,
    target_substation: str | None,
) -> tuple[bool, str]:
    """Inspect Table 1 in sliced front_page.docx, validating SUBSTATION NAME (ERMS) & (SITE).

    Returns:
        (is_valid, error_reason)
    """
    path = Path(front_page_path).resolve()
    if not path.exists():
        return False, f"Front page file not found: {path}"

    try:
        doc = docx.Document(path)
    except Exception as exc:
        return False, f"Failed to load front page docx for attribution check: {exc}"

    if len(doc.tables) < 1:
        return False, f"Front page has no tables; cannot verify attribution: {path}"

    # Search tables for ERMS and SITE substation name fields
    substation_erms: str = ""
    substation_site: str = ""

    for table in doc.tables:
        is_fp, erms, site = _extract_front_page_substations(table)
        if is_fp:
            if erms and not substation_erms:
                substation_erms = erms
            if site and not substation_site:
                substation_site = site

    return _evaluate_dual_attribution(
        substation_erms,
        substation_site,
        target_substation,
        context_prefix="front page",
    )


def verify_condition_pages_structure(path: Path | str) -> tuple[bool, str]:
    """Assert valid docx with >= 1 table and >= 1 image shape."""
    p = Path(path).resolve()
    if not p.exists():
        return False, f"condition_pages file not found: {p}"

    try:
        doc = docx.Document(p)
    except Exception as exc:
        return False, f"Invalid docx in condition_pages: {exc}"

    if len(doc.tables) < 1:
        return False, f"condition_pages has {len(doc.tables)} tables (expected >= 1)"

    has_images = (
        len(doc.inline_shapes) > 0
        or len(doc.element.xpath(".//a:blip")) > 0
        or len(doc.element.xpath(".//w:drawing | .//w:pict")) > 0
    )
    if not has_images:
        return False, "condition_pages contains no image shapes"

    return True, ""


def verify_sticker_page_structure(path: Path | str) -> tuple[bool, str]:
    """Assert presence of 'NORMAL STICKER' or 'DEFECT STICKER'."""
    p = Path(path).resolve()
    if not p.exists():
        return False, f"sticker_page file not found: {p}"

    try:
        doc = docx.Document(p)
    except Exception as exc:
        return False, f"Invalid docx in sticker_page: {exc}"

    full_text_chunks = [p_el.text for p_el in doc.paragraphs]
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                full_text_chunks.append(c.text)

    full_text = " ".join(full_text_chunks).upper()
    if "NORMAL STICKER" not in full_text and "DEFECT STICKER" not in full_text:
        return False, "Neither 'NORMAL STICKER' nor 'DEFECT STICKER' found in sticker_page"

    return True, ""


def verify_vi_summary_structure(
    path: Path | str,
    expected_count: int,
) -> tuple[bool, str]:
    """Assert Table 1 non-empty defect row count matches expected visual defect count."""
    p = Path(path).resolve()
    if not p.exists():
        return False, f"vi_summary file not found: {p}"

    try:
        doc = docx.Document(p)
    except Exception as exc:
        return False, f"Invalid docx in vi_summary: {exc}"

    if len(doc.tables) < 1:
        return False, f"vi_summary has {len(doc.tables)} tables (expected >= 1)"

    t = doc.tables[0]
    data_rows = [r for r in t.rows[1:] if any(c.text.strip() for c in r.cells)]

    # Table has non-empty data rows matching expected defect count
    if len(data_rows) == expected_count:
        return True, ""

    return (
        False,
        f"vi_summary Table 1 non-empty defect row count ({len(data_rows)} data rows) "
        f"does not match expected defect count {expected_count}",
    )


def verify_vi_defect_pages_structure(path: Path | str) -> tuple[bool, str]:
    """Assert valid docx and contains image shapes."""
    p = Path(path).resolve()
    if not p.exists():
        return False, f"vi_defect_pages file not found: {p}"

    try:
        doc = docx.Document(p)
    except Exception as exc:
        return False, f"Invalid docx in vi_defect_pages: {exc}"

    has_images = (
        len(doc.inline_shapes) > 0
        or len(doc.element.xpath(".//a:blip")) > 0
        or len(doc.element.xpath(".//w:drawing | .//w:pict")) > 0
    )
    if not has_images:
        return False, "vi_defect_pages contains no image shapes"

    return True, ""


# Keywords identifying CBM measurement test sheets that may contain embedded images
CBM_MEASUREMENT_KEYWORDS = (
    "SPOT TEMP",
    "SPOT TEMPERATURE",
    "AMBIENT TEMP",
    "AMBIENT TEMPERATURE",
    "DELTA T",
    "DELTA-T",
    "DELTA_T",
    "ΔT",
    "LOAD",
    "HUMIDITY",
    "ULTRASOUND",
    "TRANSIENT EARTH",
    "TEV",
    "PRPD",
    "DATE:",
    "DATE :",
)


def _is_photo_grid_table(table: Any) -> bool:
    """Check if table is a photo grid (contains image shapes and lacks CBM measurement fields)."""
    try:
        has_images = len(table._tbl.xpath(".//a:blip | .//w:drawing | .//w:pict")) > 0
    except Exception:
        has_images = False

    if not has_images:
        return False

    table_text = " ".join(c.text for r in table.rows for c in r.cells).upper()
    is_cbm_measurement = any(kw in table_text for kw in CBM_MEASUREMENT_KEYWORDS)
    return not is_cbm_measurement


def _is_defect_summary_table(table: Any) -> bool:
    """Check if table is a visual defect summary grid (e.g. NO | EQUIPMENT | DEFECT DESCRIPTION)."""
    for row in table.rows[:4]:
        cells_upper = [c.text.strip().upper() for c in row.cells]
        row_text = " ".join(cells_upper)
        if "DEFECT DESCRIPTION" in row_text:
            return True
        if "EQUIPMENT" in row_text and any(k in row_text for k in ("REMARKS", "NO.", "NO ")):
            return True
        if "EQUIPMENT" in cells_upper and any(k in cells_upper for k in ("REMARKS", "ADDITIONAL REMARKS", "NO.", "NO")):
            return True
    return False


def _is_substation_name_label(text: str) -> bool:
    """Check if table cell text specifically represents a substation name label."""
    up = text.upper().strip().rstrip(":")
    if not up:
        return False

    if up in {
        "SUBSTATION",
        "SUBSTATION NAME",
        "STATION",
        "STATION NAME",
    }:
        return True

    clean = re.sub(r"[:\(\)\-_]+", " ", up)
    tokens = clean.split()
    if not tokens:
        return False
    if tokens == ["SUBSTATION"] or tokens == ["STATION"]:
        return True
    if tokens in [
        ["SUBSTATION", "NAME"],
        ["STATION", "NAME"],
        ["NAME", "OF", "SUBSTATION"],
        ["NAME", "OF", "STATION"],
    ]:
        return True
    return False


def inspect_deliverable_attribution(
    deliverable_path: Path | str,
    target_substation: str | None,
) -> tuple[bool, str]:
    """Execute fast headless OpenXML inspection on compiled deliverable.

    Inspects all tables across the document using table-level structural classification:
    1. Visual defect summary data grids are skipped.
    2. Front page metadata tables are validated with dual-name tolerance (ERMS/SITE).
    3. Photo grid tables (containing images and lacking CBM measurements) are skipped.
    4. CBM test sheet headers and metadata tables (first 4 rows) are inspected and validated.

    Returns (True, "") if all substation attribution checks pass, or (False, error_reason)
    if any explicit foreign substation name is detected.
    """
    path = Path(deliverable_path).resolve()
    if not path.exists():
        return False, f"Deliverable file not found: {path}"

    try:
        doc = docx.Document(path)
    except Exception as exc:
        logger.warning("Could not load deliverable docx for attribution check: %s", exc)
        return True, ""

    for table_idx, table in enumerate(doc.tables):
        # 1. Data Grids (Visual Defect Summary)
        if _is_defect_summary_table(table):
            continue

        # 2. Front Page Metadata Tables (Dual-name tolerance)
        is_front_page, erms_name, site_name = _extract_front_page_substations(table)
        if is_front_page:
            is_valid, reason = _evaluate_dual_attribution(
                erms_name,
                site_name,
                target_substation,
                context_prefix=f"deliverable table {table_idx + 1}",
            )
            if not is_valid:
                return False, reason
            continue

        # 3. Photo Grids
        if _is_photo_grid_table(table):
            continue

        # 4. CBM Test Sheet Header Tables & Metadata Tables (Inspect first 4 rows)
        for row_idx, row in enumerate(table.rows[:4]):
            for c_idx, cell in enumerate(row.cells):
                cell_text = cell.text.strip()
                if not cell_text:
                    continue

                candidate_val = ""
                # Check 1: cell contains inline "Substation: <Value>"
                if ":" in cell_text:
                    parts = cell_text.split(":", 1)
                    if _is_substation_name_label(parts[0]):
                        candidate_val = parts[1].strip()

                # Check 2: cell itself is label, value in subsequent cells
                if not candidate_val and _is_substation_name_label(cell_text):
                    for next_cell in row.cells[c_idx + 1:]:
                        if next_cell._tc is cell._tc or next_cell.text.strip() == cell_text:
                            continue
                        val = next_cell.text.strip().lstrip(":").strip()
                        if val:
                            candidate_val = val
                            break

                if candidate_val:
                    # Validate candidate value against target
                    if not is_substation_attribution_match(target_substation, candidate_val):
                        return (
                            False,
                            f"Explicit foreign substation detected in deliverable table {table_idx + 1}, "
                            f"row {row_idx + 1}: '{candidate_val}' (target: '{target_substation}')",
                        )

    return True, ""


def quarantine_deliverable(
    deliverable_path: Path | str,
    quarantine_dir: Path | str | None = None,
) -> Path:
    """Move compromised deliverable to quarantine directory and log critical error.

    Returns:
        Path to quarantined file.
    """
    src = Path(deliverable_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Deliverable to quarantine not found: {src}")

    if quarantine_dir is None:
        q_dir = src.parent / ".quarantine"
    else:
        q_dir = Path(quarantine_dir).resolve()

    q_dir.mkdir(parents=True, exist_ok=True)
    dest = q_dir / src.name

    if dest.exists():
        dest.unlink()

    shutil.move(str(src), str(dest))

    logger.critical(
        "QUARANTINE: Compromised deliverable '%s' moved to '%s' due to foreign substation leakage.",
        src,
        dest,
    )
    return dest

