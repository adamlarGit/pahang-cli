"""Pure planner for CBM defect family page rendering plans."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Sequence

from src.quick_report.cbm_family import (
    QUICK_REPORT_FAMILY_SPECS,
    QuickReportDetailRoleSpec,
    QuickReportFamilySpec,
)
from src.quick_report.defects import CbmDefectRecord
from src.quick_report.models import CbmDefectDetailGroup, CbmDefectFamilyPlan, CbmDefectGroup

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)

_PHASE_PATTERN = re.compile(
    r"\b(RED\s*PHASE|YELLOW\s*PHASE|BLUE\s*PHASE|R\s*PHASE|Y\s*PHASE|B\s*PHASE|RED|YELLOW|BLUE|NEUTRAL)\b",
    re.IGNORECASE,
)


def _extract_phase(text: str) -> str:
    """Extract canonical electrical phase from text (RED, YELLOW, BLUE, NEUTRAL, or '')."""
    m = _PHASE_PATTERN.search(text or "")
    if m:
        token = m.group(1).upper()
        if "RED" in token or token.startswith("R"):
            return "RED"
        if "YELLOW" in token or token.startswith("Y"):
            return "YELLOW"
        if "BLUE" in token or token.startswith("B"):
            return "BLUE"
        if "NEUTRAL" in token:
            return "NEUTRAL"
    return ""


class CbmDefectPlanner:
    """Pure planner: matches CBM defects to family specs and template files."""

    def plan(
        self,
        cbm_defects: Sequence[CbmDefectRecord],
        environment: ProjectEnvironment,
    ) -> tuple[CbmDefectFamilyPlan, ...]:
        """Construct CbmDefectFamilyPlan tuples for all matching families with valid templates."""
        if not cbm_defects:
            return ()

        # Log skipped defects that do not match any CBM family spec
        for d in cbm_defects:
            if not any(self._defect_matches_family(d, spec) for spec in QUICK_REPORT_FAMILY_SPECS):
                logger.info(
                    "Skipping non-matching defect for Part 4 detail pages: equipment='%s', equipment_id='%s', defect_area='%s'",
                    d.equipment,
                    d.equipment_id,
                    d.defect_area,
                )

        family_plans: list[CbmDefectFamilyPlan] = []

        for spec in QUICK_REPORT_FAMILY_SPECS:
            family_defects = [
                d for d in cbm_defects if self._defect_matches_family(d, spec)
            ]
            if not family_defects:
                continue

            # Check overview template
            overview_tmpl = environment.get_template(spec.overview_template_key)
            if not overview_tmpl or not Path(overview_tmpl).exists():
                raise FileNotFoundError(
                    f"Missing CBM template '{spec.overview_template_key}' for family '{spec.id}'"
                )

            # Check all detail role templates
            detail_templates: list[tuple[str, Path]] = []
            for role in spec.detail_roles:
                tmpl = environment.get_template(role.template_key)
                if not tmpl or not Path(tmpl).exists():
                    raise FileNotFoundError(
                        f"Missing CBM template '{role.template_key}' for family '{spec.id}'"
                    )
                detail_templates.append((role.id, Path(tmpl)))

            # Group defects by equipment family key (e.g. FP TX1, LVDB TX1, TX1, SWG)
            family_groups: dict[str, list[CbmDefectRecord]] = {}
            family_keys: dict[str, str] = {}
            for d in family_defects:
                ikey = self._derive_family_group_key(d, spec)
                norm_key = ikey.upper()
                if norm_key not in family_groups:
                    family_groups[norm_key] = []
                    family_keys[norm_key] = ikey
                family_groups[norm_key].append(d)

            groups: list[CbmDefectGroup] = []
            for norm_key, raw_group_defects in family_groups.items():
                item_key = family_keys[norm_key]
                # Multi-technology merging on (equipment_id, defect_area, phase)
                merged_defects = self._merge_defects_by_area(raw_group_defects)
                if not merged_defects:
                    continue

                overview = merged_defects[0]

                detail_groups: list[CbmDefectDetailGroup] = []
                for role in spec.detail_roles:
                    if spec.id == "tx":
                        matched_defects = [
                            d for d in merged_defects if self._route_tx_defect_role(d) == role.id
                        ]
                    else:
                        matched_defects = [
                            d for d in merged_defects if self._defect_matches_role(d, role)
                        ]
                    detail_groups.append(
                        CbmDefectDetailGroup(
                            role_id=role.id,
                            defects=tuple(matched_defects),
                        )
                    )

                groups.append(
                    CbmDefectGroup(
                        item_key=item_key,
                        item_suffix="",
                        defects=tuple(merged_defects),
                        overview=overview,
                        detail_groups=tuple(detail_groups),
                    )
                )

            family_plans.append(
                CbmDefectFamilyPlan(
                    spec=spec,
                    overview_template=Path(overview_tmpl),
                    detail_templates=tuple(detail_templates),
                    groups=tuple(groups),
                )
            )

        return tuple(family_plans)

    @classmethod
    def _derive_family_group_key(
        cls, defect: CbmDefectRecord, spec: QuickReportFamilySpec
    ) -> str:
        """Derive equipment family group key (e.g. 'FP TX1', 'LVDB TX1', 'TX1', 'SWG')."""
        raw_id = (defect.equipment_id or "").strip()
        raw_eq = (defect.equipment or "").strip()
        raw_area = (defect.defect_area or "").strip()
        combined = f"{raw_eq} {raw_id} {raw_area}".upper()

        if spec.id == "fp_lvdb":
            # 1. Hyphen separator split (e.g. 'FP TX1 - OUTGOING F1' -> 'FP TX1')
            split_match = re.split(r"\s*[-–—]\s*", raw_id, maxsplit=1)
            if len(split_match) > 1 and any(k in split_match[0].upper() for k in ("FP", "LVDB", "FEEDER")):
                return split_match[0].strip()
            # 2. Match canonical equipment family + TX/number patterns (e.g. 'LVDB TX1', 'FP TX2')
            m = re.search(r"(?:FP|LVDB|FEEDER\s*PILLAR)\s*(?:TX\s*[1-9]|\d+)", combined)
            if m:
                return m.group(0).upper()
            # 3. Explicit TX reference in feeder pillar / LVDB
            if "TX2" in combined or "TX 2" in combined:
                return "FP TX2" if "LVDB" not in raw_eq.upper() else "LVDB TX2"
            if "TX1" in combined or "TX 1" in combined:
                return "FP TX1" if "LVDB" not in raw_eq.upper() else "LVDB TX1"
            # 4. Fallback: equipment name or 'FP LVDB'
            return raw_eq if raw_eq else "FP LVDB"

        if spec.id == "tx":
            split_match = re.split(r"\s*[-–—]\s*", raw_id, maxsplit=1)
            if len(split_match) > 1 and re.match(r"^(?:TX|T)\s*\d+", split_match[0].strip(), re.I):
                return split_match[0].strip()
            m = re.search(r"\b(?:TX|T)\s*([1-9])\b", combined)
            if m and not raw_id:
                return f"TX{m.group(1)}"
            return raw_id or raw_eq or "TX1"

        if spec.id == "swg":
            if "SWG 2" in combined or "SWITCHGEAR 2" in combined or "SWG2" in combined:
                return "SWG 2"
            return raw_eq or "SWG"

        if spec.id == "battery":
            if "BATTERY 2" in combined or "CHARGER 2" in combined or "BANK 2" in combined:
                return "BATTERY 2"
            return raw_id or raw_eq or "BATTERY"

        if spec.id == "blackbox":
            if "BLACK BOX 2" in combined or "BLACKBOX 2" in combined or "BOX 2" in combined:
                return "BLACK BOX 2"
            return raw_id or raw_eq or "BLACK BOX"

        return raw_id or raw_eq or "DEFAULT"

    @classmethod
    def _derive_item_key(
        cls, defect: CbmDefectRecord, spec: QuickReportFamilySpec | None = None
    ) -> str:
        """Derive equipment item_key from equipment_id if present, else equipment."""
        if spec is not None:
            return cls._derive_family_group_key(defect, spec)
        if defect.equipment_id and defect.equipment_id.strip():
            return defect.equipment_id.strip()
        return (defect.equipment or "").strip()

    @classmethod
    def _merge_defects_by_area(
        cls, defects: Sequence[CbmDefectRecord]
    ) -> list[CbmDefectRecord]:
        """Merge multi-technology defects sharing the same equipment_id, area, and phase."""
        if not defects:
            return []

        buckets: dict[tuple[str, str, str], list[CbmDefectRecord]] = {}
        for d in defects:
            item_id = (d.equipment_id or d.equipment or "").strip().upper()
            area = (d.defect_area or "").strip().upper()
            phase = _extract_phase(f"{d.defect_area} {d.additional_remarks}")
            buckets.setdefault((item_id, area, phase), []).append(d)

        merged: list[CbmDefectRecord] = []
        for records in buckets.values():
            if len(records) == 1:
                merged.append(records[0])
            else:
                techs = [r.technology.strip().upper() for r in records if r.technology]
                if len(techs) == len(set(techs)):
                    merged.append(cls._merge_records(records))
                else:
                    merged.extend(records)

        return merged

    @staticmethod
    def _merge_records(records: Sequence[CbmDefectRecord]) -> CbmDefectRecord:
        """Merge multiple CbmDefectRecords sharing the same equipment_id and area into a unified record."""
        def _first_non_empty(*values: str) -> str:
            for v in values:
                if v and str(v).strip() and str(v).strip() != "-":
                    return str(v).strip()
            return ""

        equipment = _first_non_empty(*(d.equipment for d in records))
        equipment_id = _first_non_empty(*(d.equipment_id for d in records))
        brand = _first_non_empty(*(d.brand for d in records))
        model = _first_non_empty(*(d.model for d in records))
        rating = _first_non_empty(*(d.rating for d in records))
        defect_area = _first_non_empty(*(d.defect_area for d in records))

        # Combine unique additional remarks
        unique_remarks = list(
            dict.fromkeys(
                r for d in records if (r := (d.additional_remarks or "").strip()) and r != "-"
            )
        )
        additional_remarks = "; ".join(unique_remarks)

        # Combine unique technologies
        unique_techs = list(
            dict.fromkeys(
                t for d in records if (t := (d.technology or "").strip().upper())
            )
        )
        technology = "+".join(unique_techs)

        # Readings
        ir_reading = _first_non_empty(*(d.ir_reading for d in records))
        us_reading = _first_non_empty(*(d.us_reading for d in records))
        us_char = _first_non_empty(*(d.us_char for d in records))
        tev_reading = _first_non_empty(*(d.tev_reading for d in records))
        tev_char = _first_non_empty(*(d.tev_char for d in records))
        raw_measurement = _first_non_empty(*(d.raw_measurement for d in records))

        # Earliest source order
        source_orders = [d.source_order for d in records if d.source_order > 0]
        source_order = min(source_orders) if source_orders else 0

        return CbmDefectRecord(
            equipment=equipment,
            technology=technology,
            brand=brand,
            model=model,
            rating=rating,
            defect_area=defect_area,
            additional_remarks=additional_remarks,
            ir_reading=ir_reading,
            us_reading=us_reading,
            us_char=us_char,
            tev_reading=tev_reading,
            tev_char=tev_char,
            raw_measurement=raw_measurement,
            equipment_id=equipment_id,
            source_order=source_order,
        )

    @staticmethod
    def _route_tx_defect_role(defect: CbmDefectRecord) -> str:
        """Route TX defect to tx_hv_side or tx_lv_side based on area, equipment_id, and equipment."""
        combined_text = f"{defect.defect_area or ''} {defect.equipment_id or ''}".upper()

        # 1. HV keywords in defect_area or equipment_id
        if any(kw in combined_text for kw in ("HV", "11KV", "33KV")):
            return "tx_hv_side"

        # 2. LV keywords in defect_area or equipment_id
        if any(kw in combined_text for kw in ("LV", "415V")):
            return "tx_lv_side"

        # 3. Fallback based on equipment name
        if "CABLE" in (defect.equipment or "").upper():
            return "tx_hv_side"

        return "tx_lv_side"

    @staticmethod
    def _defect_matches_family(defect: CbmDefectRecord, spec: QuickReportFamilySpec) -> bool:
        """Check if defect matches family equipment_values and technologies (case-insensitive)."""
        if spec.equipment_values:
            eq_upper = (defect.equipment or "").upper()
            if eq_upper not in [ev.upper() for ev in spec.equipment_values]:
                return False
        if spec.technologies and defect.technology:
            tech_upper = defect.technology.upper()
            tech_tokens = [t.strip() for t in tech_upper.replace("+", " ").replace("/", " ").split() if t.strip()]
            spec_techs = [t.upper() for t in spec.technologies]
            if not any(token in spec_techs for token in tech_tokens):
                return False
        return True

    @staticmethod
    def _defect_matches_role(defect: CbmDefectRecord, role: QuickReportDetailRoleSpec) -> bool:
        """Check if defect matches detail role equipment_values and technologies (case-insensitive)."""
        if role.equipment_values:
            eq_upper = (defect.equipment or "").upper()
            if eq_upper not in [ev.upper() for ev in role.equipment_values]:
                return False
        if role.technologies and defect.technology:
            tech_upper = defect.technology.upper()
            tech_tokens = [t.strip() for t in tech_upper.replace("+", " ").replace("/", " ").split() if t.strip()]
            role_techs = [t.upper() for t in role.technologies]
            if not any(token in role_techs for token in tech_tokens):
                return False
        return True

