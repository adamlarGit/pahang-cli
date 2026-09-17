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

    # 3. Strip leading number / dot sequences e.g. "005. " or "179. "
    text = re.sub(r"^\s*\d+\s*[\.\-]?\s*", " ", text)

    # 4. Strip leading electrical prefixes + possible PE numbers e.g. "PE 144 ", "SSU 2 "
    text = re.sub(r"^\s*\b(?:PE|SSU|PPU|PMU|SS)\b\s*(?:\d+[\.\-]?)?\s*", " ", text, flags=re.IGNORECASE)

    # Repeat strip in case of chained "005. PE TALAPIA"
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
        for row in table.rows:
            if len(row.cells) >= 2:
                label = row.cells[0].text.strip().upper()
                val = row.cells[-1].text.strip()
                if "SUBSTATION NAME (ERMS)" in label:
                    substation_erms = val
                elif "SUBSTATION NAME (SITE)" in label:
                    substation_site = val
                elif "SUBSTATION NAME" in label and not substation_erms:
                    substation_erms = val

    # Verify ERMS name if present
    if substation_erms and not is_substation_attribution_match(target_substation, substation_erms):
        return (
            False,
            f"Explicit foreign substation detected in front page ERMS field: '{substation_erms}' "
            f"(target: '{target_substation}')",
        )

    # Verify SITE name if present
    if substation_site and not is_substation_attribution_match(target_substation, substation_site):
        return (
            False,
            f"Explicit foreign substation detected in front page SITE field: '{substation_site}' "
            f"(target: '{target_substation}')",
        )

    return True, ""


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
    """Assert Table 1 row count matches expected visual defect count."""
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
    row_count = len(t.rows)

    # Table has 1 header row + N data rows (or N rows directly)
    if row_count != expected_count and (row_count - 1) != expected_count:
        return (
            False,
            f"vi_summary Table 1 row count {row_count} does not match expected defect count {expected_count}",
        )

    return True, ""


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
        "SUBSTATION NAME (ERMS)",
        "SUBSTATION NAME (SITE)",
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
        ["SUBSTATION", "NAME", "ERMS"],
        ["SUBSTATION", "NAME", "SITE"],
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

    Inspects all tables across the document searching for rows where header
    cells represent substation name fields (ignoring feeders, panels, etc.).
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
        for row_idx, row in enumerate(table.rows):
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

