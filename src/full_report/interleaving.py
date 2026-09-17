"""Defect Interleaving Rules for Full Report (Ticket #32 / T5.1).

Matches sliced CBM defect pages (from temp_parts/cbm_defects/) to physical equipment
components using D37 grammar and Table 1 metadata, implementing replacement and
insertion sequencing rules per D34, D35, D36, D37, D38:
- SWG IR Hotspot: Sliced defect page replaces swg-panel.docx (D34).
- SWG TEV / US: swg-panel.docx retained, followed immediately by inline TEV detail page (D34).
- Transformer: Defect detail pages inserted immediately behind specific component scan page (D35).
- Feeder Pillar: Defect detail pages sequenced immediately after fp-overview.docx in
  left-to-right channel order (IN1..IN3, OT1..OT10) (D36).
- Unmatched Orphans: Safely appended at the end of the equipment scanning stream before
  Substation Condition with prominent warning (D38).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from pathlib import Path
import re
from typing import Sequence

from src.full_report.attribution import verify_cbm_defect_attribution
from src.full_report.defect_parser import (
    CbmDefectHeaderParser,
    CbmDefectSliceMetadata,
    normalize_defect_area,
    normalize_equipment_id,
    parse_d37_filename,
)
from src.full_report.models import is_tx_feeder
from src.full_report.scan_adapters import ScanAdapterResult, ScanRenderItem
from src.quick_report.defects import CbmDefectRecord

logger = logging.getLogger(__name__)


class InterleavingActionType(str, Enum):
    """Action taken during defect interleaving."""

    REPLACE = "REPLACE"
    APPEND_AFTER = "APPEND_AFTER"
    INSERT_BEHIND = "INSERT_BEHIND"
    ORPHAN_APPEND = "ORPHAN_APPEND"
    FOREIGN_DISCARD = "FOREIGN_DISCARD"


@dataclass
class InterleavingAction:
    """Detailed record of an interleaving decision made by the policy."""

    action_type: InterleavingActionType
    target_sequence: str
    target_component: str
    defect_filename: str
    reason: str
    defect_metadata: CbmDefectSliceMetadata | None = None
    target_item: ScanRenderItem | None = None


@dataclass
class InterleavedPart:
    """Represents a component scan page or interleaved defect page in the document stream."""

    part_name: str
    is_defect: bool
    equipment_category: str
    sequence: str
    component_name: str
    action_type: InterleavingActionType | None = None
    scan_item: ScanRenderItem | None = None
    defect_metadata: CbmDefectSliceMetadata | None = None
    file_path: Path | None = None

    @property
    def is_sliced(self) -> bool:
        """Whether this part originates from a pre-sliced document on disk."""
        if self.file_path is not None:
            return True
        if self.defect_metadata is not None and self.defect_metadata.slice_path is not None:
            return True
        if self.scan_item is not None:
            return self.scan_item.is_sliced
        return self.is_defect


@dataclass
class InterleavingResult:
    """Comprehensive result of executing DefectInterleavingPolicy."""

    parts: tuple[InterleavedPart, ...]
    actions: tuple[InterleavingAction, ...]
    orphans: tuple[InterleavedPart, ...]
    replaced_items: tuple[ScanRenderItem, ...]

    def __len__(self) -> int:
        return len(self.parts)

    def __iter__(self):
        return iter(self.parts)

    def __getitem__(self, index: int) -> InterleavedPart:
        return self.parts[index]


# ==============================================================================
# Helper Functions
# ==============================================================================

def get_feeder_channel_sort_key(seq: str, eq_id: str = "") -> tuple[int, int, str]:
    """Calculate sorting key for Feeder Pillar defect channels per D36.

    Ensures left-to-right sequencing:
    - Overview first (-1, 0, clean_seq)
    - Incomers next (IN01..IN03 -> group 0, channel_num)
    - Outgoings next (OT01..OT10, F01..F10 -> group 1, channel_num)
    - Other (group 2)
    """
    clean_seq = seq.lower().strip()
    clean_id = eq_id.upper().strip()

    # Check for IN channel (incomings)
    in_match = re.search(r"in(\d+)", clean_seq) or re.search(r"IN\s*(\d+)", clean_id)
    if in_match:
        return (0, int(in_match.group(1)), clean_seq)

    # Check for OT / F channel (outgoings)
    ot_match = re.search(r"ot(\d+)", clean_seq) or re.search(r"OT\s*(\d+)", clean_id)
    if ot_match:
        return (1, int(ot_match.group(1)), clean_seq)

    f_match = re.search(r"f(\d+)", clean_seq) or re.search(r"F\s*(\d+)", clean_id)
    if f_match:
        num = int(f_match.group(1))
        if num == 0:
            return (-1, 0, clean_seq)
        return (1, num, clean_seq)

    digits = re.findall(r"\d+", clean_seq) or re.findall(r"\d+", clean_id)
    num = int(digits[0]) if digits else 99
    return (2, num, clean_seq)


def _infer_cbm_record_category(equipment_str: str) -> str:
    """Infer equipment category string from CbmDefectRecord equipment."""
    eq = (equipment_str or "").upper()
    if any(k in eq for k in ("RMU", "VCB", "SWG", "SWITCHGEAR", "AIS", "GIS")):
        return "swg"
    if any(k in eq for k in ("TRANSFORMER", "TX")):
        return "tx"
    if any(k in eq for k in ("FEEDER PILLAR", "FP", "LVDB")):
        return "fp"
    if "BATT" in eq:
        return "battery"
    return ""


def _resolve_defect_technology(
    meta: CbmDefectSliceMetadata,
    records: Sequence[CbmDefectRecord] | None = None,
) -> str:
    """Resolve defect technology ('IR', 'TEV', 'US') using dual-layer inspection."""
    # 1. Check explicit metadata technology
    if meta.technology:
        return meta.technology.upper()

    # 2. Match against QR03 CbmDefectRecord list (gated by equipment category)
    if records:
        meta_cat = meta.equipment_category.lower()
        meta_id_clean = re.sub(r"[^A-Za-z0-9]", "", meta.equipment_id).upper()
        meta_seq_clean = meta.sequence.lower()
        meta_area_norm = normalize_defect_area(meta.defect_area)

        for rec in records:
            rec_cat = _infer_cbm_record_category(rec.equipment)
            # Only match if categories are compatible
            if rec_cat and meta_cat and rec_cat != meta_cat:
                continue

            rec_id_clean = re.sub(r"[^A-Za-z0-9]", "", rec.equipment_id).upper()
            rec_area_norm = normalize_defect_area(rec.defect_area)

            # Match on ID or sequence or area
            id_matched = (meta_id_clean and meta_id_clean == rec_id_clean) or (
                rec_id_clean and rec_id_clean in meta_id_clean
            )
            area_matched = meta_area_norm == rec_area_norm

            # Sequence match (e.g. p04 vs 4, f02 vs F2)
            seq_digits = re.findall(r"\d+", meta_seq_clean)
            rec_digits = re.findall(r"\d+", rec.equipment_id)
            seq_matched = bool(seq_digits and rec_digits and seq_digits[0].lstrip("0") == rec_digits[0].lstrip("0"))

            if (id_matched and area_matched) or id_matched or (seq_matched and area_matched) or seq_matched:
                if rec.technology:
                    return rec.technology.upper()

    # 3. Check filename tokens (token-based to avoid false positives like 'US' in 'FUSE')
    name_upper = (meta.filename or "").upper()
    tokens = set(re.split(r"[^A-Za-z0-9]+", name_upper))
    if any(k in tokens for k in ("TEV", "PRPD")) or "PARTIAL_DISCHARGE" in name_upper:
        return "TEV"
    if any(k in tokens for k in ("US", "ULTRASOUND", "ACOUSTIC")):
        return "US"
    if any(k in tokens for k in ("IR", "HOTSPOT", "THERMAL")):
        return "IR"

    # Default for switchgear and general CBM defects
    return "IR"


# ==============================================================================
# DefectInterleavingPolicy Deep Policy Class
# ==============================================================================

class DefectInterleavingPolicy:
    """Deep policy module implementing deterministic defect interleaving rules.

    Matches sliced CBM defect pages to physical equipment scanning components
    and produces an ordered Bill of Materials adhering strictly to D34, D35, D36, D38.
    """

    def __init__(self, parser: CbmDefectHeaderParser | None = None) -> None:
        self.parser = parser or CbmDefectHeaderParser()

    def interleave(
        self,
        scan_items: Sequence[ScanRenderItem | ScanAdapterResult],
        sliced_defects: Sequence[Path | str | CbmDefectSliceMetadata] | Path | str | None = None,
        cbm_records: Sequence[CbmDefectRecord] | None = None,
        target_substation: str = "",
    ) -> InterleavingResult:
        """Interleave sliced CBM defect pages into the component scanning stream.

        Args:
            scan_items: Baseline component scan items from equipment scan adapters.
            sliced_defects: Sliced defect documents or metadata from temp_parts/cbm_defects/.
            cbm_records: Optional QR03 CBA defect records for dual-layer technology resolution.
            target_substation: Optional target substation name for attribution assertion.

        Returns:
            InterleavingResult containing the final ordered parts, actions, orphans, and replaced items.
        """
        flattened_items = self._flatten_scan_items(scan_items)
        defect_metas = self._resolve_defect_metadata_list(sliced_defects)

        actions: list[InterleavingAction] = []
        orphans: list[InterleavedPart] = []
        replaced_items: list[ScanRenderItem] = []

        # Attribution check: discard foreign defect slices (Ticket #44 / Seam 2)
        valid_defect_metas: list[CbmDefectSliceMetadata] = []
        for d in defect_metas:
            if target_substation and not verify_cbm_defect_attribution(d, target_substation):
                logger.error(
                    "FOREIGN_DISCARD: Sliced defect '%s' (category=%s, substation='%s') explicitly conflicts with target substation '%s'. Discarding from equipment stream and orphan list.",
                    d.filename,
                    d.equipment_category,
                    d.substation,
                    target_substation,
                )
                action_discard = InterleavingAction(
                    action_type=InterleavingActionType.FOREIGN_DISCARD,
                    target_sequence=d.sequence,
                    target_component=d.defect_area,
                    defect_filename=d.filename,
                    reason=f"Foreign defect slice with substation '{d.substation}' explicitly conflicts with target '{target_substation}'",
                    defect_metadata=d,
                )
                actions.append(action_discard)
                continue
            valid_defect_metas.append(d)

        # If no defects, return all scan items directly as parts
        if not valid_defect_metas:
            parts = tuple(
                InterleavedPart(
                    part_name=item.page_name,
                    is_defect=False,
                    equipment_category=item.equipment_category,
                    sequence=item.sequence,
                    component_name=item.component_name,
                    scan_item=item,
                    file_path=item.sliced_path if item.is_sliced else None,
                )
                for item in flattened_items
            )
            return InterleavingResult(
                parts=parts,
                actions=tuple(actions),
                orphans=(),
                replaced_items=(),
            )

        # Categorize defect metadata
        swg_defects: list[CbmDefectSliceMetadata] = []
        tx_defects: list[CbmDefectSliceMetadata] = []
        fp_defects: list[CbmDefectSliceMetadata] = []
        batt_defects: list[CbmDefectSliceMetadata] = []
        raw_orphans: list[CbmDefectSliceMetadata] = []

        for d in valid_defect_metas:
            cat = d.equipment_category.lower()
            if cat in ("swg", "switchgear"):
                swg_defects.append(d)
            elif cat in ("tx", "transformer"):
                tx_defects.append(d)
            elif cat in ("fp", "lvdb", "feeder_pillar"):
                fp_defects.append(d)
            elif cat in ("battery", "batt"):
                batt_defects.append(d)
            else:
                raw_orphans.append(d)

        # Build plan item by item
        result_parts: list[InterleavedPart] = []

        # Track which defects have been consumed
        consumed_defects: set[str] = set()
        for item in flattened_items:
            if item.is_sliced and item.sliced_path:
                consumed_defects.add(Path(item.sliced_path).name)

        for item in flattened_items:
            cat = item.equipment_category.lower()

            # ------------------------------------------------------------------
            # 1. SWITCHGEAR INTERLEAVING (D34)
            # ------------------------------------------------------------------
            if cat in ("swg", "switchgear"):
                if item.is_overview:
                    part = self._substitute_overview_part(
                        item, swg_defects, consumed_defects, actions, replaced_items, "SWG"
                    )
                    result_parts.append(part)
                    for swg_d in swg_defects:
                        if swg_d.sequence == "p00" or swg_d.defect_area == "OVERVIEW":
                            consumed_defects.add(swg_d.filename)
                    continue

                # Panel item: look for matching panel defects
                matching_defects = self._find_swg_panel_defects(item, swg_defects, consumed_defects)

                if not matching_defects:
                    result_parts.append(self._item_to_part(item))
                    continue

                # Check technology of matching defects
                ir_defects: list[CbmDefectSliceMetadata] = []
                tev_us_defects: list[CbmDefectSliceMetadata] = []

                for md in matching_defects:
                    tech = _resolve_defect_technology(md, cbm_records)
                    if tech == "IR":
                        ir_defects.append(md)
                    else:
                        tev_us_defects.append(md)

                # D34 Rule: IR defect directly replaces the panel page
                if ir_defects:
                    primary_ir = ir_defects[0]
                    consumed_defects.add(primary_ir.filename)
                    action = InterleavingAction(
                        action_type=InterleavingActionType.REPLACE,
                        target_sequence=item.sequence,
                        target_component=item.component_name,
                        defect_filename=primary_ir.filename,
                        reason=f"SWG IR defect replaces {item.template_name} per D34",
                        defect_metadata=primary_ir,
                        target_item=item,
                    )
                    actions.append(action)
                    replaced_items.append(item)
                    result_parts.append(
                        InterleavedPart(
                            part_name=primary_ir.filename,
                            is_defect=True,
                            equipment_category=cat,
                            sequence=item.sequence,
                            component_name=item.component_name,
                            action_type=InterleavingActionType.REPLACE,
                            defect_metadata=primary_ir,
                            file_path=primary_ir.slice_path,
                        )
                    )

                    # Any secondary IR defects appended after
                    for sec_ir in ir_defects[1:]:
                        consumed_defects.add(sec_ir.filename)
                        action_sec = InterleavingAction(
                            action_type=InterleavingActionType.APPEND_AFTER,
                            target_sequence=item.sequence,
                            target_component=item.component_name,
                            defect_filename=sec_ir.filename,
                            reason="SWG secondary IR defect appended per D34",
                            defect_metadata=sec_ir,
                            target_item=item,
                        )
                        actions.append(action_sec)
                        result_parts.append(
                            InterleavedPart(
                                part_name=sec_ir.filename,
                                is_defect=True,
                                equipment_category=cat,
                                sequence=item.sequence,
                                component_name=item.component_name,
                                action_type=InterleavingActionType.APPEND_AFTER,
                                defect_metadata=sec_ir,
                                file_path=sec_ir.slice_path,
                            )
                        )
                else:
                    # No IR defect: keep the panel scan page (with red forwarding banner if TEV/US)
                    result_parts.append(self._item_to_part(item))

                # D34 Rule: TEV/US defect pages appended after the panel page
                for tev_d in tev_us_defects:
                    consumed_defects.add(tev_d.filename)
                    action_tev = InterleavingAction(
                        action_type=InterleavingActionType.APPEND_AFTER,
                        target_sequence=item.sequence,
                        target_component=item.component_name,
                        defect_filename=tev_d.filename,
                        reason=f"SWG TEV/US defect appended after {item.template_name} per D34",
                        defect_metadata=tev_d,
                        target_item=item,
                    )
                    actions.append(action_tev)
                    result_parts.append(
                        InterleavedPart(
                            part_name=tev_d.filename,
                            is_defect=True,
                            equipment_category=cat,
                            sequence=item.sequence,
                            component_name=item.component_name,
                            action_type=InterleavingActionType.APPEND_AFTER,
                            defect_metadata=tev_d,
                            file_path=tev_d.slice_path,
                        )
                    )

            # ------------------------------------------------------------------
            # 2. TRANSFORMER INTERLEAVING (D35)
            # ------------------------------------------------------------------
            elif cat in ("tx", "transformer"):
                if item.is_overview:
                    part = self._substitute_overview_part(
                        item, tx_defects, consumed_defects, actions, replaced_items, "Transformer"
                    )
                    result_parts.append(part)
                    for tx_d in tx_defects:
                        if tx_d.sequence == "s00" or tx_d.defect_area == "OVERVIEW":
                            consumed_defects.add(tx_d.filename)
                    continue

                # Transformer component scan page always retained
                result_parts.append(self._item_to_part(item))

                # Look for matching component defect (e.g. s02 HV BUSHING)
                matching_tx_defects = self._find_tx_component_defects(item, tx_defects, consumed_defects)
                for tx_d in matching_tx_defects:
                    consumed_defects.add(tx_d.filename)
                    action = InterleavingAction(
                        action_type=InterleavingActionType.INSERT_BEHIND,
                        target_sequence=item.sequence,
                        target_component=item.component_name,
                        defect_filename=tx_d.filename,
                        reason=f"Transformer defect inserted behind {item.component_name} per D35",
                        defect_metadata=tx_d,
                        target_item=item,
                    )
                    actions.append(action)
                    result_parts.append(
                        InterleavedPart(
                            part_name=tx_d.filename,
                            is_defect=True,
                            equipment_category=cat,
                            sequence=item.sequence,
                            component_name=item.component_name,
                            action_type=InterleavingActionType.INSERT_BEHIND,
                            defect_metadata=tx_d,
                            file_path=tx_d.slice_path,
                        )
                    )

            # ------------------------------------------------------------------
            # 3. FEEDER PILLAR INTERLEAVING (D36)
            # ------------------------------------------------------------------
            elif cat in ("fp", "lvdb", "feeder_pillar"):
                if item.is_overview:
                    part = self._substitute_overview_part(
                        item, fp_defects, consumed_defects, actions, replaced_items, "Feeder Pillar"
                    )
                    result_parts.append(part)
                    for fp_d in fp_defects:
                        if fp_d.sequence == "f00" or fp_d.defect_area == "OVERVIEW":
                            consumed_defects.add(fp_d.filename)

                    # Collect all defects for this Feeder Pillar
                    matching_fp_defects = self._find_fp_defects(item, fp_defects, consumed_defects)
                    # Sort strictly in channel order per D36 (IN1..IN3, OT1..OT10)
                    sorted_fp_defects = sorted(
                        matching_fp_defects,
                        key=lambda d: get_feeder_channel_sort_key(d.sequence, d.equipment_id),
                    )

                    for fp_d in sorted_fp_defects:
                        if fp_d.sequence == "f00" or fp_d.defect_area == "OVERVIEW":
                            continue

                        consumed_defects.add(fp_d.filename)
                        action = InterleavingAction(
                            action_type=InterleavingActionType.APPEND_AFTER,
                            target_sequence=item.sequence,
                            target_component=item.component_name,
                            defect_filename=fp_d.filename,
                            reason=f"Feeder Pillar defect sequenced after {item.page_name} in channel order per D36",
                            defect_metadata=fp_d,
                            target_item=item,
                        )
                        actions.append(action)
                        result_parts.append(
                            InterleavedPart(
                                part_name=fp_d.filename,
                                is_defect=True,
                                equipment_category=cat,
                                sequence=fp_d.sequence,
                                component_name=fp_d.defect_area,
                                action_type=InterleavingActionType.APPEND_AFTER,
                                defect_metadata=fp_d,
                                file_path=fp_d.slice_path,
                            )
                        )
                else:
                    result_parts.append(self._item_to_part(item))

            # ------------------------------------------------------------------
            # 4. BATTERY BANK INTERLEAVING
            # ------------------------------------------------------------------
            elif cat in ("battery", "batt"):
                result_parts.append(self._item_to_part(item))
                matching_batt_defects = [
                    d for d in batt_defects
                    if d.filename not in consumed_defects
                    and d.sequence != "b00" and d.defect_area != "OVERVIEW"
                ]
                for batt_d in matching_batt_defects:
                    consumed_defects.add(batt_d.filename)
                    action = InterleavingAction(
                        action_type=InterleavingActionType.APPEND_AFTER,
                        target_sequence=item.sequence,
                        target_component=item.component_name,
                        defect_filename=batt_d.filename,
                        reason="Battery Bank defect appended per policy",
                        defect_metadata=batt_d,
                        target_item=item,
                    )
                    actions.append(action)
                    result_parts.append(
                        InterleavedPart(
                            part_name=batt_d.filename,
                            is_defect=True,
                            equipment_category=cat,
                            sequence=batt_d.sequence,
                            component_name=batt_d.defect_area,
                            action_type=InterleavingActionType.APPEND_AFTER,
                            defect_metadata=batt_d,
                            file_path=batt_d.slice_path,
                        )
                    )

            else:
                result_parts.append(self._item_to_part(item))

        # ----------------------------------------------------------------------
        # 5. ORPHAN DEFECT SAFE APPEND (D38)
        # ----------------------------------------------------------------------
        # Check for any unconsumed defects across all categories (no silent drop!)
        all_unconsumed = [
            d for d in valid_defect_metas
            if d.filename not in consumed_defects
        ]

        for orphan_meta in all_unconsumed:
            logger.warning(
                "Unmatched orphan CBM defect page '%s' (category=%s, seq=%s, id=%s, area=%s) - "
                "safely appending before Substation Condition per D38",
                orphan_meta.filename,
                orphan_meta.equipment_category,
                orphan_meta.sequence,
                orphan_meta.equipment_id,
                orphan_meta.defect_area,
            )
            action = InterleavingAction(
                action_type=InterleavingActionType.ORPHAN_APPEND,
                target_sequence="stream_end",
                target_component="COMPONENT_STREAM_END",
                defect_filename=orphan_meta.filename,
                reason="Unmatched defect safely appended at end of scan stream per D38",
                defect_metadata=orphan_meta,
            )
            actions.append(action)

            orphan_part = InterleavedPart(
                part_name=orphan_meta.filename,
                is_defect=True,
                equipment_category="orphan",
                sequence=orphan_meta.sequence,
                component_name=orphan_meta.defect_area,
                action_type=InterleavingActionType.ORPHAN_APPEND,
                defect_metadata=orphan_meta,
                file_path=orphan_meta.slice_path,
            )
            orphans.append(orphan_part)
            result_parts.append(orphan_part)

        return InterleavingResult(
            parts=tuple(result_parts),
            actions=tuple(actions),
            orphans=tuple(orphans),
            replaced_items=tuple(replaced_items),
        )

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _flatten_scan_items(
        self,
        scan_items: Sequence[ScanRenderItem | ScanAdapterResult],
    ) -> list[ScanRenderItem]:
        """Flatten ScanAdapterResult or ScanRenderItem sequences into list[ScanRenderItem]."""
        items: list[ScanRenderItem] = []
        for elem in scan_items:
            if isinstance(elem, ScanAdapterResult):
                items.extend(elem.items)
            elif isinstance(elem, ScanRenderItem):
                items.append(elem)
            elif hasattr(elem, "items"):
                items.extend(getattr(elem, "items"))
        return items

    def _resolve_defect_metadata_list(
        self,
        sliced_defects: Sequence[Path | str | CbmDefectSliceMetadata] | Path | str | None,
    ) -> list[CbmDefectSliceMetadata]:
        """Resolve various inputs into list of CbmDefectSliceMetadata."""
        if not sliced_defects:
            return []

        if isinstance(sliced_defects, (str, Path)):
            p = Path(sliced_defects)
            if p.is_dir():
                target_files = sorted(p.glob("*.docx"))
                return self._resolve_defect_metadata_list(target_files)
            else:
                target_list = [p]
        else:
            target_list = list(sliced_defects)

        results: list[CbmDefectSliceMetadata] = []
        for item in target_list:
            if isinstance(item, CbmDefectSliceMetadata):
                results.append(item)
                continue

            file_path = Path(item)
            # Try Table 1 parsing if physical file exists
            if file_path.is_file():
                try:
                    meta = self.parser.parse(file_path, slice_path=file_path)
                    results.append(meta)
                    continue
                except Exception as exc:
                    logger.debug("Table 1 extraction failed on %s: %s; falling back to D37 regex", file_path, exc)

            # Fallback to D37 filename parsing
            parsed = parse_d37_filename(file_path)
            if parsed:
                if file_path.is_file():
                    parsed = CbmDefectSliceMetadata(
                        equipment_category=parsed.equipment_category,
                        equipment_instance=parsed.equipment_instance,
                        sequence=parsed.sequence,
                        equipment_id=parsed.equipment_id,
                        defect_area=parsed.defect_area,
                        severity=parsed.severity,
                        index=parsed.index,
                        substation=parsed.substation,
                        manufacturer=parsed.manufacturer,
                        model=parsed.model,
                        filename=parsed.filename,
                        slice_path=file_path,
                        technology=parsed.technology,
                    )
                results.append(parsed)
            else:
                # Unparseable filename -> create orphan metadata
                orphan_meta = CbmDefectSliceMetadata(
                    equipment_category="unknown",
                    equipment_instance="unknown",
                    sequence="unknown",
                    equipment_id="UNKNOWN",
                    defect_area="UNKNOWN",
                    filename=file_path.name,
                    slice_path=file_path if file_path.is_file() else None,
                )
                results.append(orphan_meta)

        return results

    def _item_to_part(self, item: ScanRenderItem) -> InterleavedPart:
        """Convert a standard ScanRenderItem into an InterleavedPart."""
        return InterleavedPart(
            part_name=item.page_name,
            is_defect=False,
            equipment_category=item.equipment_category,
            sequence=item.sequence,
            component_name=item.component_name,
            scan_item=item,
            file_path=item.sliced_path if item.is_sliced else None,
        )

    def _substitute_overview_part(
        self,
        item: ScanRenderItem,
        defects: Sequence[CbmDefectSliceMetadata],
        consumed_defects: set[str],
        actions: list[InterleavingAction],
        replaced_items: list[ScanRenderItem],
        reason_label: str,
    ) -> InterleavedPart:
        """Handle D47 overview replacement with sliced QR overview if available."""
        ov_match = self._find_overview_defect_match(item, defects, consumed_defects)
        if ov_match:
            consumed_defects.add(ov_match.filename)
            if not item.is_sliced:
                action = InterleavingAction(
                    action_type=InterleavingActionType.REPLACE,
                    target_sequence=item.sequence,
                    target_component=item.component_name,
                    defect_filename=ov_match.filename,
                    reason=f"{reason_label} Overview replaced by sliced overview per D47",
                    defect_metadata=ov_match,
                    target_item=item,
                )
                actions.append(action)
                replaced_items.append(item)
                return InterleavedPart(
                    part_name=ov_match.filename,
                    is_defect=False,
                    equipment_category=item.equipment_category,
                    sequence=item.sequence,
                    component_name=item.component_name,
                    action_type=InterleavingActionType.REPLACE,
                    defect_metadata=ov_match,
                    file_path=ov_match.slice_path,
                )
        return self._item_to_part(item)

    def _find_overview_defect_match(
        self,
        item: ScanRenderItem,
        defects: Sequence[CbmDefectSliceMetadata],
        consumed_defects: set[str],
    ) -> CbmDefectSliceMetadata | None:
        """Find matching sliced overview page for D47 overview substitution."""
        item_id_clean = re.sub(r"[^A-Za-z0-9]", "", str(item.equipment_id or "")).lower()
        for d in defects:
            if d.filename in consumed_defects:
                continue
            if d.sequence in ("p00", "f00", "s00", "b00") or d.defect_area == "OVERVIEW":
                if item_id_clean and d.equipment_instance:
                    d_inst_clean = re.sub(r"[^A-Za-z0-9]", "", str(d.equipment_instance)).lower()
                    if item_id_clean == d_inst_clean:
                        return d
                else:
                    return d
        return None

    def _find_swg_panel_defects(
        self,
        item: ScanRenderItem,
        defects: Sequence[CbmDefectSliceMetadata],
        consumed_defects: set[str],
    ) -> list[CbmDefectSliceMetadata]:
        """Find matching defect pages for a switchgear panel scan item."""
        matches: list[CbmDefectSliceMetadata] = []
        item_seq = item.sequence.lower()
        item_panel_no = item.panel_no
        item_comp = normalize_defect_area(item.component_name)

        panel_ctx = item.context.get("panel", {}) if isinstance(item.context, dict) else {}
        item_feeder_no = normalize_equipment_id(
            str(
                panel_ctx.get("feeder_no")
                or panel_ctx.get("panel_feeder_no")
                or panel_ctx.get("linknumber")
                or ""
            )
        )
        panel_is_tx = is_tx_feeder(f"{panel_ctx.get('name', '')} {item_feeder_no}")

        for d in defects:
            if d.filename in consumed_defects:
                continue
            if d.sequence == "p00" or d.defect_area == "OVERVIEW":
                continue

            d_seq = d.sequence.lower()
            d_id = normalize_equipment_id(d.equipment_id)
            d_area = normalize_defect_area(d.defect_area)

            # Sequence match: e.g. p04 == p04
            seq_matched = item_seq == d_seq

            # Panel number match: e.g. item.panel_no == 4 and d_seq == "p04"
            panel_no_matched = False
            if item_panel_no is not None:
                d_digits = re.findall(r"\d+", d_seq)
                if d_digits and int(d_digits[0]) == item_panel_no:
                    panel_no_matched = True

            # Feeder ID match: e.g. CKN01309 == CKN01309
            id_matched = bool(item_feeder_no and d_id and (item_feeder_no == d_id or d_id in item_feeder_no))

            # TX Feeder match for fuse compartment defects
            tx_fuse_matched = bool(panel_is_tx and d_area == "FUSE_COMPARTMENT" and (panel_no_matched or id_matched))

            if seq_matched or panel_no_matched or id_matched or tx_fuse_matched:
                # If panel has multiple compartments (e.g. CABLE COMPARTMENT and CABLE ENTRY),
                # check compartment match:
                if d_area and d_area != "OVERVIEW":
                    if d_area in item_comp or item_comp in d_area:
                        matches.append(d)
                        continue
                    # For multi-compartment panels, do not duplicate on CABLE ENTRY unless matched
                    if item_comp == "CABLE_ENTRY":
                        continue
                matches.append(d)

        return matches

    def _find_tx_component_defects(
        self,
        item: ScanRenderItem,
        defects: Sequence[CbmDefectSliceMetadata],
        consumed_defects: set[str],
    ) -> list[CbmDefectSliceMetadata]:
        """Find matching defect pages for a transformer component scan item."""
        matches: list[CbmDefectSliceMetadata] = []
        item_seq = item.sequence.lower()
        item_comp = normalize_defect_area(item.component_name)

        for d in defects:
            if d.filename in consumed_defects:
                continue

            d_seq = d.sequence.lower()
            d_area = normalize_defect_area(d.defect_area)
            if d_seq in ("s00", "p00", "f00", "b00") or d_area == "OVERVIEW":
                continue

            # Check TX instance (e.g. tx1 vs tx2) if item has equipment_id
            if item.equipment_id and d.equipment_instance:
                item_digits = re.findall(r"\d+", item.equipment_id)
                d_digits = re.findall(r"\d+", d.equipment_instance)
                if item_digits and d_digits and item_digits[0] != d_digits[0]:
                    continue

            # Match on sequence (s02 == s02) or area (HV_BUSHING == HV_BUSHING)
            if item_seq == d_seq or (item_comp and item_comp == d_area):
                matches.append(d)

        return matches

    def _find_fp_defects(
        self,
        item: ScanRenderItem,
        defects: Sequence[CbmDefectSliceMetadata],
        consumed_defects: set[str],
    ) -> list[CbmDefectSliceMetadata]:
        """Find all unconsumed defect pages belonging to a Feeder Pillar."""
        matches: list[CbmDefectSliceMetadata] = []
        for d in defects:
            if d.filename in consumed_defects:
                continue
            if item.equipment_id and d.equipment_instance:
                item_digits = re.findall(r"\d+", item.equipment_id)
                d_digits = re.findall(r"\d+", d.equipment_instance)
                if item_digits and d_digits and item_digits[0] != d_digits[0]:
                    continue
            matches.append(d)
        return matches
