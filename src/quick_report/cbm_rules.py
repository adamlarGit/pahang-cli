"""Pure domain CBM Defect Analysis and Recommendation rule engine.

Strictly adheres to the empirical standards of PO 42360565 - AZZAD.
Zero docx, OpenXML, or COM dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import TYPE_CHECKING, Any

from src.core.normalizers import normalize_us_characteristic
from src.quick_report.defects import CbmDefectRecord
from src.testsheet.feeder_thermal import resolve_feeder_channel

if TYPE_CHECKING:
    from src.testsheet.models import SubstationEquipmentPackage, SwitchgearPanelSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CbmPhraseTemplate:
    """Pair of analysis and recommendation phrasing templates."""

    analysis: str
    recommendation: str

    def format(self, **kwargs: Any) -> tuple[str, str]:
        """Format dynamic variables into analysis and recommendation pair."""
        return (
            self.analysis.format(**kwargs),
            self.recommendation.format(**kwargs),
        )


# ─── Structured Domain Phrase Registry ───────────────────────────────────────
# Organized by Equipment Family and Diagnostic Pattern.
# Extensible for dynamic per-station or per-technology phrase loading in future cycles.
CBM_PHRASE_REGISTRY: dict[str, dict[str, CbmPhraseTemplate]] = {
    "fp_lvdb": {
        "din_fuse": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at FUSE COMPARTMENT. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "lug": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {phase_prefix}CABLE LUG CONNECTION. "
                "The anomaly is due to bad contact or high resistive joint at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface, re-crimp and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "link": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {direction} LINK CONNECTION. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "fuse": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {direction} FUSE CONNECTION. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "din_link": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at LINK COMPARTMENT. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "contact_finger": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {direction} CONTACT FINGER. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "busbar": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at BUSBAR CONNECTION. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "cut_out_fuse": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at CUT OUT FUSE. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
        "ct": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at CT CONNECTION. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
    },
    "swg": {
        "pilc": CbmPhraseTemplate(
            analysis="Thermal image above indicates hotspot detected at CABLE SWG – CABLE PILC.",
            recommendation="To inspect and replace PILC with XLPE cable.",
        ),
        "xlpe_termination": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hotspot detected at CABLE TERMINATION/CABLE XLPE. "
                "The anomaly is due to void, insulation material deterioration or defective cable."
            ),
            recommendation="To inspect and make a new termination or replace defective parts if necessary.",
        ),
        "tag": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hotspot detected at SECONDARY COMPARTMENT – CABLE CONNECTION{tag_str}. "
                "The anomaly is due to loose or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface, re-tighten the connection points or replace defective parts if necessary."
            ),
        ),
        "us_pd": CbmPhraseTemplate(
            analysis="Electrical {char_key} partial discharge sound detected at {comp}.",
            recommendation=(
                "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. "
                "If any parts are found to be in poor condition, replacement is necessary."
            ),
        ),
        "us_vibration": CbmPhraseTemplate(
            analysis="Audible mechanical vibration sound detected at {comp}.",
            recommendation=(
                "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. "
                "If any parts are found to be in poor condition, replacement is necessary."
            ),
        ),
        "tev_internal": CbmPhraseTemplate(
            analysis=(
                "High TEV reading detected at {comp}. Based on the phase-resolved partial discharge, "
                "graph indicates internal electrical partial discharge."
            ),
            recommendation=(
                "To inspect the bushing, cable termination and cable for sign of internal electrical partial discharge. "
                "If parts in poor condition, parts replacement are necessary. Before any rectification work is being carried out, "
                "please conduct test using TEV locater or sequence switching to find the source of high TEV reading. "
                "It is recommended to plan shutdown with CBM team."
            ),
        ),
    },
    "tx": {
        "hv_termination": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at HV CABLE TERMINATION – {phase_suffix}. "
                "The anomaly is due to void, insulation material deterioration or defective cable."
            ),
            recommendation="To inspect and make a new termination or replace defective parts if necessary.",
        ),
        "lv_bushing": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {phase_prefix}BUSHING CONNECTION. "
                "The anomaly is due to bad contact or high resistive joint at the connection point."
            ),
            recommendation=(
                "To inspect bushing condition especially at its internal rod, perform proper cleaning "
                "and re-tighten the connection point or replace defective parts if necessary."
            ),
        ),
        "hv_bushing": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {phase_prefix}HV BUSHING CONNECTION. "
                "The anomaly is due to bad contact or high resistive joint at the connection point."
            ),
            recommendation=(
                "To inspect bushing condition, perform proper cleaning and re-tighten the connection point "
                "or replace defective parts if necessary."
            ),
        ),
        "lv_lug": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {phase_prefix}CABLE LUG CONNECTION. "
                "The anomaly is due to bad contact or high resistive joint at the connection point."
            ),
            recommendation=(
                "To inspect, perform proper cleaning, re-crimp and re-tighten the connection point "
                "or replace defective parts if necessary."
            ),
        ),
        "tank_body": CbmPhraseTemplate(
            analysis="Thermal image above indicates hot spot detected at OVERVIEW TOP / TANK BODY.",
            recommendation=(
                "To inspect and perform dissolve gas analysis (DGA) testing and winding resistance test to pinpoint "
                "the exact cause of the thermal pattern and check for winding related heating issues. "
                "It is recommended to plan shutdown with CBM team to properly address the rectification work."
            ),
        ),
        "us_pd": CbmPhraseTemplate(
            analysis="Electrical {char_key} partial discharge sound detected at {comp}.",
            recommendation=(
                "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. "
                "If any parts are found to be in poor condition, replacement is necessary."
            ),
        ),
        "us_vibration": CbmPhraseTemplate(
            analysis="Audible mechanical vibration sound detected at {comp}.",
            recommendation=(
                "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. "
                "If any parts are found to be in poor condition, replacement is necessary."
            ),
        ),
    },
    "battery": {
        "connection": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at BATTERY CONNECTION. "
                "The anomaly is due to bad contact, oxidation or high resistive joint at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface, apply anti-corrosion grease and re-tighten the connection point. "
                "Replace defective battery cells if necessary."
            ),
        ),
    },
    "blackbox": {
        "terminal": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at CONTROL / JUNCTION BOX TERMINAL CONNECTION. "
                "The anomaly is due to loose or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
    },
    "overview": {
        "defect": CbmPhraseTemplate(
            analysis="Please refer to the following page for details defect.",
            recommendation="Please refer to the following page for details defect.",
        ),
        "normal": CbmPhraseTemplate(
            analysis="No Anomaly.",
            recommendation="-",
        ),
    },
    "fallback": {
        "connection": CbmPhraseTemplate(
            analysis=(
                "Thermal image above indicates hot spot detected at {component}. "
                "The anomaly is due to loosen or bad contact at the connection point."
            ),
            recommendation=(
                "To inspect, clean the contact surface and re-tighten the connection point. "
                "Replace defective parts if necessary."
            ),
        ),
    },
}


def _extract_phase(text: str) -> str:
    """Extract phase string (e.g. 'RED PHASE', 'YELLOW PHASE', 'BLUE PHASE', 'NEUTRAL PHASE')."""
    if not text:
        return ""
    t = text.upper()
    for p in ("RED", "YELLOW", "BLUE", "NEUTRAL"):
        if f"{p} PHASE" in t:
            return f"{p} PHASE"
    for p in ("RED", "YELLOW", "BLUE", "NEUTRAL"):
        if re.search(rf"\b{p}\b", t):
            return f"{p} PHASE"
    return ""


def _is_defective_record(record: CbmDefectRecord) -> bool:
    """Determine whether a CBM defect record represents a defective row or normal condition."""
    comb = f"{record.defect_area} {record.additional_remarks}".strip().upper()
    if any(sentinel in comb for sentinel in ("NO ANOMALY", "TIADA DEFECT", "TIADA ANOMALI")):
        return False
    if comb in ("-", "NONE", "TIADA", "NORMAL"):
        return False
    if not record.defect_area and not record.technology and not record.raw_measurement:
        if not record.ir_reading and not record.us_reading and not record.tev_reading:
            return False
    if record.defect_area in ("", "-", "NONE", "TIADA"):
        has_meas = any(
            bool(m and str(m).strip() not in ("", "-", "0", "0.0"))
            for m in (record.ir_reading, record.us_reading, record.tev_reading, record.raw_measurement)
        )
        if not has_meas:
            return False
    return True


def _generate_fp_lvdb_analysis_and_recommendation(
    record: CbmDefectRecord,
    *,
    equipment_pkg: SubstationEquipmentPackage | None = None,
) -> tuple[str, str]:
    """Rule 3.1: Feeder Pillar & LVDB Analysis & Recommendation generation."""
    record_equip = record.equipment.strip().upper()
    record_model = record.model.strip().upper()
    defect_area_upper = record.defect_area.strip().upper().replace("CONECCTION", "CONNECTION")
    comb_area = f"{defect_area_upper} {record.additional_remarks}".strip().upper()
    phase = _extract_phase(comb_area)
    phase_prefix = f"{phase} " if phase else ""

    # 1. Cable Lug / Cable Termination (applies to both DIN and J-Slot / LVDB)
    if any(k in comb_area for k in ("LUG", "CABLE TERMINATION", "CABLE XLPE")):
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["lug"].format(phase_prefix=phase_prefix)

    # 2. Explicit DIN-specific compartments
    if "FUSE COMPARTMENT" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["din_fuse"].format()
    if "LINK COMPARTMENT" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["din_link"].format()

    # 3. Explicit Busbar, CT, Cut Out Fuse
    if "BUSBAR" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["busbar"].format()
    if re.search(r"\bCT\b", defect_area_upper):
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["ct"].format()
    if "CUT OUT" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["cut_out_fuse"].format()

    # 4. Check if equipment is DIN Type Feeder Pillar (FP (D)) without explicit J-slot markers
    is_din = False
    if any(k in record_equip for k in ("FP (D)", "FP(D)", "/DIN", "-DIN", " DIN")):
        is_din = True
    elif any(k in record_model for k in ("FP (D)", "FP(D)", "(D)", "DIN")):
        is_din = True
    elif equipment_pkg and equipment_pkg.lvdb_specs:
        for spec in equipment_pkg.lvdb_specs:
            if spec.label and any(k in spec.label.upper() for k in ("DIN", "(D)")):
                is_din = True
                break

    if is_din and not any(k in defect_area_upper for k in ("INCOMING", "OUTGOING")):
        if "LINK" in comb_area:
            return CBM_PHRASE_REGISTRY["fp_lvdb"]["din_link"].format()
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["din_fuse"].format()

    # 5. J-Slot Feeder Pillar & LVDB: Resolve direction (INCOMING vs OUTGOING)
    # Priority A: Check record.defect_area directly (master droplist token)
    direction = ""
    if "INCOMING" in defect_area_upper or "INC " in defect_area_upper:
        direction = "INCOMING"
    elif "OUTGOING" in defect_area_upper or "OUT " in defect_area_upper:
        direction = "OUTGOING"

    # Priority B: Fall back to equipment_id / resolve_feeder_channel if defect_area didn't specify
    if not direction:
        raw_target = record.equipment_id or record.equipment
        ch_res = resolve_feeder_channel(raw_target)
        if not ch_res:
            ch_res = resolve_feeder_channel(f"{raw_target} {record.defect_area}")
        if ch_res:
            if ch_res.channel.startswith("IN"):
                direction = "INCOMING"
            elif ch_res.channel.startswith("OT"):
                direction = "OUTGOING"

    # Priority C: Keyword fallback in equipment_id or remarks
    if not direction:
        comb_id = f"{record.equipment_id} {record.additional_remarks}".upper()
        if any(k in comb_id for k in ("INCOMING", "INC")):
            direction = "INCOMING"
        elif any(k in comb_id for k in ("OUTGOING", "OUT", "OT", "FEEDER", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10")):
            direction = "OUTGOING"
        else:
            direction = "OUTGOING"

    # 6. Specific J-slot / LVDB component phrase
    if "CONTACT FINGER" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["contact_finger"].format(direction=direction)

    if "LINK" in defect_area_upper:
        return CBM_PHRASE_REGISTRY["fp_lvdb"]["link"].format(direction=direction)

    # Default for J-slot / LVDB: FUSE CONNECTION
    return CBM_PHRASE_REGISTRY["fp_lvdb"]["fuse"].format(direction=direction)


def _generate_swg_analysis_and_recommendation(
    record: CbmDefectRecord,
    *,
    panel_spec: SwitchgearPanelSpec | None = None,
) -> tuple[str, str]:
    """Rule 3.2: Switchgear Panels Analysis & Recommendation generation (with compound multi-tech)."""
    comb_area = f"{record.defect_area} {record.additional_remarks}".strip().upper()
    tech = record.technology.upper()

    has_ir = False
    has_us = False
    has_tev = False

    # Strict defect technology detection
    if "IR" in tech:
        has_ir = True
    if "US" in tech:
        has_us = True
    if "TEV" in tech:
        has_tev = True

    # Check for active US abnormal characteristic if not strictly in technology string
    if not has_us and record.us_char:
        norm_char = normalize_us_characteristic(record.us_char).upper()
        if norm_char in ("CORONA", "TRACKING", "ARCING", "MECHANICAL VIBRATION", "CORONA DISCHARGE"):
            has_us = True

    # Check for active TEV reading if not strictly in technology string
    if not has_tev and record.tev_reading and record.tev_reading not in ("", "-", "0", "0.0"):
        has_tev = True

    # Fallback to IR if no tech is identified
    if not has_ir and not has_us and not has_tev:
        has_ir = True

    analyses: list[str] = []
    recommendations: list[str] = []

    # 1. Thermal (IR) Evaluation
    if has_ir:
        # Rule 3.2.1: PILC Cable
        cable_type_swg = (panel_spec.cable_type if panel_spec and panel_spec.cable_type else "").upper()
        if any("PILC" in s for s in (comb_area, record.equipment_id.upper(), record.equipment.upper(), cable_type_swg)):
            a, r = CBM_PHRASE_REGISTRY["swg"]["pilc"].format()
            analyses.append(a)
            recommendations.append(r)
        # Rule 3.2.3: Secondary Compartment / Cable Tag
        elif "SECONDARY" in comb_area or "TAG" in comb_area:
            m = re.search(r"(?:CABLE\s+)?TAG\s*[:\-]?\s*([A-Za-z0-9_:\-]+)", comb_area)
            tag_str = f" (CABLE TAG {m.group(1).strip()})" if m else ""
            a, r = CBM_PHRASE_REGISTRY["swg"]["tag"].format(tag_str=tag_str)
            analyses.append(a)
            recommendations.append(r)
        else:
            # Rule 3.2.2: XLPE Cable Termination (Standard Cable IR)
            a, r = CBM_PHRASE_REGISTRY["swg"]["xlpe_termination"].format()
            analyses.append(a)
            recommendations.append(r)

    # 2. Airborne Ultrasound (US) Evaluation (Rule 3.2.4)
    if has_us:
        norm_char = normalize_us_characteristic(record.us_char).upper()
        if "TRACKING" in norm_char:
            char_key = "tracking"
        elif "ARCING" in norm_char:
            char_key = "arcing"
        elif "MECHANICAL" in norm_char or "VIBRATION" in norm_char:
            char_key = "mechanical vibration"
        else:
            char_key = "corona"

        comp = "CABLE COMPARTMENT"
        if record.defect_area and any(k in record.defect_area.upper() for k in ("COMPARTMENT", "BUSBAR", "SPOUT", "CHAMBER", "BREAKER")):
            comp = record.defect_area.strip().upper()

        if char_key == "mechanical vibration":
            a, r = CBM_PHRASE_REGISTRY["swg"]["us_vibration"].format(comp=comp)
        else:
            a, r = CBM_PHRASE_REGISTRY["swg"]["us_pd"].format(char_key=char_key, comp=comp)
        analyses.append(a)
        recommendations.append(r)

    # 3. Transient Earth Voltage (TEV) Evaluation (Rule 3.2.5)
    if has_tev:
        comp = "CABLE COMPARTMENT"
        if record.defect_area and any(k in record.defect_area.upper() for k in ("COMPARTMENT", "BUSBAR", "SPOUT", "CHAMBER", "BREAKER")):
            comp = record.defect_area.strip().upper()

        a, r = CBM_PHRASE_REGISTRY["swg"]["tev_internal"].format(comp=comp)
        analyses.append(a)
        recommendations.append(r)

    # Multi-paragraph concatenation (Rule 3.2.6)
    return "\n\n".join(analyses), "\n\n".join(recommendations)


def _generate_tx_analysis_and_recommendation(
    record: CbmDefectRecord,
) -> tuple[str, str]:
    """Rule 3.3: Transformer Analysis & Recommendation generation.

    Strictly aligned with QR03 master Excel dropdown options.
    """
    comb_area = f"{record.defect_area} {record.additional_remarks}".strip().upper()
    tech = record.technology.upper()

    # Airborne Ultrasound on Transformer (Rule 3.3.5)
    has_us_defect = False
    if "US" in tech:
        has_us_defect = True
    elif record.us_char:
        norm_char = normalize_us_characteristic(record.us_char).upper()
        if norm_char in ("CORONA", "TRACKING", "ARCING", "MECHANICAL VIBRATION", "CORONA DISCHARGE"):
            has_us_defect = True

    if has_us_defect:
        comp = record.defect_area.strip().upper() if record.defect_area.strip() else "HV CABLE TERMINATION"
        norm_char = normalize_us_characteristic(record.us_char).upper()
        if "TRACKING" in norm_char:
            char_key = "tracking"
        elif "ARCING" in norm_char:
            char_key = "arcing"
        elif "MECHANICAL" in norm_char or "VIBRATION" in norm_char:
            char_key = "mechanical vibration"
        else:
            char_key = "corona"

        if char_key == "mechanical vibration":
            return CBM_PHRASE_REGISTRY["tx"]["us_vibration"].format(comp=comp)
        return CBM_PHRASE_REGISTRY["tx"]["us_pd"].format(char_key=char_key, comp=comp)

    phase = _extract_phase(comb_area)
    phase_prefix = f"{phase} " if phase else ""

    # Rule 3.3.1: HV Cable Termination / Cable Box / XLPE / PILC
    if any(k in comb_area for k in ("HV CABLE TERMINATION", "HV TERMINATION", "HV CABLE XLPE", "HV CABLE PILC", "HV CABLE BOX")):
        phase_suffix = phase if phase else "-"
        return CBM_PHRASE_REGISTRY["tx"]["hv_termination"].format(phase_suffix=phase_suffix)

    # Rule 3.3.2: Bushing Connections (LV vs. HV)
    if "LV BUSHING" in comb_area:
        return CBM_PHRASE_REGISTRY["tx"]["lv_bushing"].format(phase_prefix=phase_prefix)
    if "HV BUSHING" in comb_area:
        return CBM_PHRASE_REGISTRY["tx"]["hv_bushing"].format(phase_prefix=phase_prefix)
    if "BUSHING" in comb_area:
        # If general BUSHING and Column K or comb_area indicates HV
        if getattr(record, "hv_lv", "") == "HV" and "LV" not in comb_area:
            return CBM_PHRASE_REGISTRY["tx"]["hv_bushing"].format(phase_prefix=phase_prefix)
        return CBM_PHRASE_REGISTRY["tx"]["lv_bushing"].format(phase_prefix=phase_prefix)

    # Rule 3.3.3: LV Cable Lug Connection
    if "LUG" in comb_area:
        return CBM_PHRASE_REGISTRY["tx"]["lv_lug"].format(phase_prefix=phase_prefix)

    # Rule 3.3.4: Tank Body / Radiator / Conservator
    if any(k in comb_area for k in ("TANK", "BODY", "RADIATOR", "FIN", "CONSERVATOR", "OVERVIEW")):
        return CBM_PHRASE_REGISTRY["tx"]["tank_body"].format()

    # Default fallback for unclassified transformer connection
    comp_name = record.defect_area or "CONNECTION POINT"
    return CBM_PHRASE_REGISTRY["fallback"]["connection"].format(component=comp_name)


def _generate_blackbox_rules(record: CbmDefectRecord, *, overview: bool = False) -> tuple[str, str]:
    """Rule 3.4: Black Box Analysis & Recommendation generation."""
    if overview:
        if _is_defective_record(record):
            return CBM_PHRASE_REGISTRY["overview"]["defect"].format()
        return CBM_PHRASE_REGISTRY["overview"]["normal"].format()
    return CBM_PHRASE_REGISTRY["blackbox"]["terminal"].format()


def _generate_battery_rules(record: CbmDefectRecord, *, overview: bool = False) -> tuple[str, str]:
    """Rule 3.4: Battery Bank Analysis & Recommendation generation."""
    if overview:
        if _is_defective_record(record):
            return CBM_PHRASE_REGISTRY["overview"]["defect"].format()
        return CBM_PHRASE_REGISTRY["overview"]["normal"].format()
    return CBM_PHRASE_REGISTRY["battery"]["connection"].format()


def generate_cbm_analysis_and_recommendation(
    record: CbmDefectRecord,
    *,
    equipment_type: str,
    equipment_pkg: SubstationEquipmentPackage | None = None,
    panel_spec: SwitchgearPanelSpec | None = None,
    is_overview: bool = False,
) -> tuple[str, str]:
    """Generate programmatic Analysis and Recommendation text for a CBM defect record.

    Parameters:
        record: The CbmDefectRecord populated from QR03 CBA Excel.
        equipment_type: Family identifier ('fp_lvdb', 'swg', 'tx', 'blackbox', 'battery').
        equipment_pkg: Optional SubstationEquipmentPackage for equipment metadata resolution.
        panel_spec: Optional SwitchgearPanelSpec for switchgear panel-level specs.
        is_overview: True if generating status text for an overview sheet row.

    Returns:
        tuple[str, str]: (analysis_text, recommendation_text)
    """
    equip_type = equipment_type.strip().lower()

    # Rule 3.5: Overview Table Handling
    if is_overview:
        if _is_defective_record(record):
            return CBM_PHRASE_REGISTRY["overview"]["defect"].format()
        return CBM_PHRASE_REGISTRY["overview"]["normal"].format()

    # Route by equipment family
    if equip_type in ("fp_lvdb", "fp", "lvdb"):
        return _generate_fp_lvdb_analysis_and_recommendation(record, equipment_pkg=equipment_pkg)
    elif equip_type in ("swg", "switchgear", "panel"):
        return _generate_swg_analysis_and_recommendation(record, panel_spec=panel_spec)
    elif equip_type in ("tx", "transformer"):
        return _generate_tx_analysis_and_recommendation(record)
    elif equip_type in ("blackbox", "bbox"):
        return _generate_blackbox_rules(record, overview=False)
    elif equip_type in ("battery", "batt"):
        return _generate_battery_rules(record, overview=False)

    # Rule 3.6: General Safe Fallback
    logger.warning("Unclassified CBM equipment type '%s' for defect '%s'", equipment_type, record.defect_area)
    comp_name = record.defect_area or "THE CONNECTION POINT"
    return CBM_PHRASE_REGISTRY["fallback"]["connection"].format(component=comp_name)
