"""Switchgear Topology Engine & Domain Models (Ticket #49 / ADR 0005).

Provides pure domain models, two-phase switchgear classification, and dynamic
compartment resolution for substation condition-based monitoring (CBM) inspection reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator


class SwitchgearArchetype(str, Enum):
    """Canonical physical hardware switchgear archetypes."""

    VCB_CUBICLE = "VCB_CUBICLE"
    GIS_CUBICLE = "GIS_CUBICLE"
    RMU_DUAL_CABLE_ENTRY = "RMU_DUAL_CABLE_ENTRY"
    RMU_FUSE_CANISTER = "RMU_FUSE_CANISTER"
    RMU_OIL = "RMU_OIL"
    RMU_STANDARD = "RMU_STANDARD"


class VoltageClass(str, Enum):
    """Standard electrical voltage operating classes."""

    LV = "LV"
    KV_6_6 = "6.6kV"
    KV_11 = "11kV"
    KV_22 = "22kV"
    KV_33 = "33kV"


class BayRole(str, Enum):
    """Functional bay / panel operational roles affecting physical compartment layout."""

    STANDARD = "STANDARD"
    TRANSFORMER = "TRANSFORMER"
    TRANSITION = "TRANSITION"
    BUS_SECTION = "BUS_SECTION"
    BUS_COUPLER = "BUS_COUPLER"


# Known model tokens extracted from co-mingled manufacturer strings
KNOWN_MODEL_TOKENS: tuple[str, ...] = ("INS24", "GR1", "FALCON", "JMW12", "VRN2A", "GV3")

# Canonical overview multi-views per archetype
OVERVIEW_COMPARTMENTS_MAP: dict[SwitchgearArchetype, tuple[str, ...]] = {
    SwitchgearArchetype.VCB_CUBICLE: ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP"),
    SwitchgearArchetype.GIS_CUBICLE: ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP"),
    SwitchgearArchetype.RMU_FUSE_CANISTER: ("OVERVIEW", "OVERVIEW TOP"),
    SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY: ("OVERVIEW", "OVERVIEW BOTTOM"),
    SwitchgearArchetype.RMU_OIL: ("OVERVIEW", "OVERVIEW BOTTOM"),
    SwitchgearArchetype.RMU_STANDARD: ("OVERVIEW",),
}


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to retrieve attribute from dict or object safely."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def classify_voltage_rating(rating: str | None = None) -> VoltageClass:
    """Normalize raw voltage rating strings to VoltageClass enum.

    Handles '11kV', '12kV', '12kV, 630A', blank/empty strings -> KV_11;
    '33kV' -> KV_33; '22kV' -> KV_22; '6.6kV' -> KV_6_6; 'LV'/'415V' -> LV.
    """
    if rating is None:
        return VoltageClass.KV_11

    clean = str(rating).strip().upper()
    if not clean:
        return VoltageClass.KV_11

    import re

    if re.search(r"(?:\b33\s*KV\b|^33$)", clean):
        return VoltageClass.KV_33
    if re.search(r"(?:\b22\s*KV\b|^22$)", clean):
        return VoltageClass.KV_22
    if re.search(r"(?:\b6\.6\s*KV\b|^6\.6$)", clean):
        return VoltageClass.KV_6_6
    if re.search(r"\b(LV|415\s*V)\b", clean):
        return VoltageClass.LV

    # Default distribution operating class in TNB Pahang is 11kV (covers 11kV, 12kV, 630A, etc.)
    return VoltageClass.KV_11


def extract_model_from_manufacturer(
    manufacturer: str | None = "",
    model: str | None = "",
) -> str:
    """Extract known model tokens from manufacturer string when model is blank.

    Recognizes tokens: INS24, GR1, FALCON, JMW12, VRN2A, GV3.
    """
    if model is not None and str(model).strip():
        return str(model).strip()

    if not manufacturer:
        return ""

    import re

    mfg = str(manufacturer).strip()
    match = re.search(r"\b(INS[-_]?24|GR1|FALCON|JMW12|VRN2A?|GV3)\b", mfg, re.IGNORECASE)
    if match:
        token = match.group(1).upper()
        if token.startswith("INS"):
            return "INS24"
        if token.startswith("VRN2"):
            return "VRN2A"
        return token

    return ""


def resolve_switchgear_archetype(
    switchgear_type: str = "",
    manufacturer: str = "",
    model: str = "",
) -> SwitchgearArchetype:
    """Resolve SwitchgearArchetype via strict precedence hierarchy.

    Precedence:
    1. VCB priority: type or manufacturer containing 'VCB' -> VCB_CUBICLE.
    2. GIS priority: type or manufacturer containing 'GIS' -> GIS_CUBICLE.
    3. MRMU (type or manufacturer containing 'MRMU') -> RMU_STANDARD.
    4. Oil / OCB: type/mfg containing 'OIL' or 'OCB', or model 'VRN2A' -> RMU_OIL.
    5. Lucy variants: all Lucy RMUs -> RMU_DUAL_CABLE_ENTRY.
    6. Tamco -> RMU_DUAL_CABLE_ENTRY.
    7. Indkom:
       - model containing 'INS24' (or token INS24 from mfg) -> RMU_FUSE_CANISTER.
       - model 'JMW12' or blank/unrecognized without 'INS24' -> RMU_STANDARD.
    8. Generic / unrecognized RMU fallback -> RMU_STANDARD.
    """
    type_upper = (switchgear_type or "").strip().upper()
    mfg_upper = (manufacturer or "").strip().upper()
    model_raw = (model or "").strip()

    # Model token fallback if model was not explicitly provided
    if not model_raw:
        model_raw = extract_model_from_manufacturer(mfg_upper, "")
    model_upper = model_raw.upper()

    # 1. VCB Priority
    if "VCB" in type_upper or "VCB" in mfg_upper:
        return SwitchgearArchetype.VCB_CUBICLE

    # 2. GIS Priority
    if "GIS" in type_upper or "GIS" in mfg_upper:
        return SwitchgearArchetype.GIS_CUBICLE

    # 3. MRMU Priority (Motorized RMU / Modular RMU)
    if "MRMU" in type_upper or "MRMU" in mfg_upper:
        return SwitchgearArchetype.RMU_STANDARD

    # 4. Oil / OCB (including Lucy VRN2a)
    if any(k in type_upper for k in ("OIL", "OCB")) or any(k in mfg_upper for k in ("OIL", "OCB")) or "VRN2A" in model_upper:
        return SwitchgearArchetype.RMU_OIL

    # 5. Lucy variants (Lucy SF6, Lucy Electric, etc.) or Falcon model
    if any(k in mfg_upper for k in ("LUCY", "SSE LUCY", "LUCY ELECTRIC", "LUCY SWITCHGEAR")) or "FALCON" in model_upper:
        return SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY

    # 6. Tamco or GR1 model
    if "TAMCO" in mfg_upper or "GR1" in model_upper:
        return SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY

    # 7. Indkom
    if "INDKOM" in mfg_upper or "INS24" in model_upper:
        if "INS24" in model_upper or "INS24" in mfg_upper:
            return SwitchgearArchetype.RMU_FUSE_CANISTER
        return SwitchgearArchetype.RMU_STANDARD

    # 8. Generic / unrecognized RMU fallback
    return SwitchgearArchetype.RMU_STANDARD


def resolve_overview_compartments(
    archetype: SwitchgearArchetype,
    voltage_class: VoltageClass = VoltageClass.KV_11,
) -> tuple[str, ...]:
    """Resolve overview scanning page compartments for switchgear archetype."""
    return OVERVIEW_COMPARTMENTS_MAP.get(archetype, ("OVERVIEW",))


def classify_bay_role(
    name: str = "",
    panel_feeder_no: str = "",
    panel_type: str = "",
    archetype: SwitchgearArchetype = SwitchgearArchetype.RMU_STANDARD,
) -> BayRole:
    """Classify functional operational role of a switchgear bay/panel.

    Keyword matching rules:
    - BUS_SECTION: 'BUS SECTION', 'BUS-SECTION', 'B/S', 'BUS SEC', 'SECTION', 'SEC'.
    - BUS_COUPLER: 'BUS COUPLER', 'BUS-COUPLER', 'B/C', 'COUPLER'.
    - TRANSITION: 'TRANSITION', 'PERALIHAN', 'TRANSISYEN', 'TOOLS', 'TOOL'.
    - TRANSFORMER: 'TX', 'TRANSFORMER', 'ALATUBAH', 'TEE-OFF' in name or panel_feeder_no.
    - STANDARD: default for outgoing feeders, incomers, spares, and regular line names.
    """
    import re

    combined = f"{name or ''} {panel_feeder_no or ''} {panel_type or ''}".strip().upper()
    name_feeder = f"{name or ''} {panel_feeder_no or ''}".strip().upper()

    # 1. Transition
    if re.search(r"\b(TRANSITION|PERALIHAN|TRANSISYEN|TOOLS?)\b", combined, re.IGNORECASE):
        return BayRole.TRANSITION

    # 2. Bus Section
    if re.search(r"(?:\bBUS[\s-]*(?:SECTION|SEC)\b|\bSECTION\b|\bSEC\b|\bB/S\b)", combined, re.IGNORECASE):
        return BayRole.BUS_SECTION

    # 3. Bus Coupler
    if re.search(r"(?:\bBUS[\s-]*COUPLER\b|\bCOUPLER\b|\bB/C\b)", combined, re.IGNORECASE):
        return BayRole.BUS_COUPLER

    # 4. Transformer (TX, TRANSFORMER, ALATUBAH, TEE-OFF) in name or panel_feeder_no per spec
    if re.search(r"(?:\bTX\d*\b|\bTRANSFORMER\b|\bALATUBAH\b|\bTEE[\s-]*OFF\b|\b\d*KVA\b)", name_feeder, re.IGNORECASE):
        return BayRole.TRANSFORMER

    # 5. Default Standard Feeder
    return BayRole.STANDARD


def eval_pt_gate(
    panel: Any = None,
    *,
    pt_photo: int | None = None,
    has_pt_measurement: bool = False,
) -> bool:
    """Evaluate empirical PT presence gate.

    Returns True iff sub-row r+3 has recorded photo evidence (pt_photo is not None)
    OR non-empty measurement data (has_pt_measurement is True).
    """
    p_photo = _get_attr_or_key(panel, "pt_photo", pt_photo)
    p_meas = bool(_get_attr_or_key(panel, "has_pt_measurement", has_pt_measurement))

    has_photo = p_photo is not None and str(p_photo).strip() not in ("", "-", "None")
    return bool(has_photo or p_meas)


def eval_secondary_gate(
    panel: Any = None,
    *,
    secondary_photo: int | None = None,
) -> bool:
    """Evaluate pure photo presence secondary gate for transition bays.

    Returns True iff Column P recorded an IR photo (secondary_photo is not None).
    Zero dependency on heater current.
    """
    s_photo = _get_attr_or_key(panel, "secondary_photo", secondary_photo)
    return s_photo is not None and str(s_photo).strip() not in ("", "-", "None")


def resolve_panel_compartments(
    archetype: SwitchgearArchetype,
    bay_role: BayRole | None = None,
    panel: Any = None,
    *,
    name: str = "",
    panel_feeder_no: str = "",
    panel_type: str = "",
    pt_photo: int | None = None,
    secondary_photo: int | None = None,
    has_pt_measurement: bool = False,
) -> tuple[str, ...]:
    """Resolve exact physical compartment name strings for a bay/panel.

    Pure domain resolution with zero COM or filesystem dependencies.
    """
    # Fall back to panel object attributes if provided
    if panel is not None:
        name = name or _get_attr_or_key(panel, "name", "") or ""
        panel_feeder_no = (
            panel_feeder_no
            or _get_attr_or_key(panel, "panel_feeder_no", "")
            or _get_attr_or_key(panel, "feeder_no", "")
            or ""
        )
        panel_type = panel_type or _get_attr_or_key(panel, "panel_type", "") or ""
        if pt_photo is None:
            pt_photo = _get_attr_or_key(panel, "pt_photo", None)
        if secondary_photo is None:
            secondary_photo = _get_attr_or_key(panel, "secondary_photo", None)
        if not has_pt_measurement:
            has_pt_measurement = bool(_get_attr_or_key(panel, "has_pt_measurement", False))


    if bay_role is None:
        bay_role = classify_bay_role(
            name=name,
            panel_feeder_no=panel_feeder_no,
            panel_type=panel_type,
            archetype=archetype,
        )

    # VCB / GIS Cubicle
    if archetype in (SwitchgearArchetype.VCB_CUBICLE, SwitchgearArchetype.GIS_CUBICLE):
        if bay_role == BayRole.TRANSITION:
            compartments = ["FRONT COMPARTMENT", "REAR COMPARTMENT", "BUSBAR COMPARTMENT"]
            if eval_secondary_gate(panel, secondary_photo=secondary_photo):
                compartments.append("SECONDARY COMPARTMENT")
            # Transition bays NEVER emit PT compartments
            return tuple(compartments)

        if bay_role in (BayRole.BUS_SECTION, BayRole.BUS_COUPLER):
            return (
                "BREAKER COMPARTMENT",
                "REAR COMPARTMENT",
                "BUSBAR COMPARTMENT",
                "SECONDARY COMPARTMENT",
            )

        # Standard Feeder or Transformer bay
        compartments = ["BREAKER COMPARTMENT", "CABLE COMPARTMENT", "BUSBAR COMPARTMENT"]
        if eval_pt_gate(panel, pt_photo=pt_photo, has_pt_measurement=has_pt_measurement):
            compartments.append("PT COMPARTMENT")
        compartments.append("SECONDARY COMPARTMENT")
        return tuple(compartments)

    # RMU Dual Cable Entry (Tamco, all Lucy)
    if archetype == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY:
        return ("CABLE COMPARTMENT", "CABLE ENTRY")

    # RMU Fuse Canister (Indkom INS24)
    if archetype == SwitchgearArchetype.RMU_FUSE_CANISTER:
        if bay_role == BayRole.TRANSFORMER:
            return ("FUSE COMPARTMENT",)
        return ("CABLE COMPARTMENT",)

    # RMU Oil (Lucy VRN2a, OCB)
    if archetype == SwitchgearArchetype.RMU_OIL:
        return ("CABLE COMPARTMENT", "CABLE ENTRY")

    # RMU Standard (Generic RMU, Indkom JMW12, MRMU)
    return ("CABLE COMPARTMENT",)


@dataclass(frozen=True)
class BoardClassification:
    """Classification result of a switchgear board lineup."""

    archetype: SwitchgearArchetype
    voltage_class: VoltageClass
    overview_compartments: tuple[str, ...]

    def __iter__(self) -> Iterator[Any]:
        """Allow tuple unpacking: archetype, voltage_class, overviews = board."""
        yield self.archetype
        yield self.voltage_class
        yield self.overview_compartments


class SwitchgearTopologyEngine:
    """Two-phase switchgear topology engine facade.

    Phase 1: Board-level macro archetype & voltage classification.
    Phase 2: Bay-level dynamic compartment resolution and presence gating.
    """

    @staticmethod
    def classify_board(
        switchgear_type: str = "",
        manufacturer: str = "",
        model: str = "",
        rating: str = "",
        swg: Any = None,
    ) -> BoardClassification:
        """Classify a switchboard lineup into macro archetype, voltage class, and overviews."""
        if swg is not None:
            switchgear_type = switchgear_type or _get_attr_or_key(swg, "switchgear_type", "") or ""
            manufacturer = manufacturer or _get_attr_or_key(swg, "manufacturer", "") or ""
            model = model or _get_attr_or_key(swg, "model", "") or ""
            rating = rating or _get_attr_or_key(swg, "rating", "") or ""

        model_resolved = extract_model_from_manufacturer(manufacturer, model)

        archetype = resolve_switchgear_archetype(switchgear_type, manufacturer, model_resolved)
        voltage_class = classify_voltage_rating(rating)
        overview_compartments = resolve_overview_compartments(archetype, voltage_class)

        return BoardClassification(
            archetype=archetype,
            voltage_class=voltage_class,
            overview_compartments=overview_compartments,
        )

    @staticmethod
    def resolve_panel_compartments(
        archetype: SwitchgearArchetype,
        bay_role: BayRole | None = None,
        panel: Any = None,
        *,
        name: str = "",
        panel_feeder_no: str = "",
        panel_type: str = "",
        pt_photo: int | None = None,
        secondary_photo: int | None = None,
        has_pt_measurement: bool = False,
    ) -> tuple[str, ...]:
        """Resolve panel compartment name strings applying dynamic presence gates."""
        return resolve_panel_compartments(
            archetype=archetype,
            bay_role=bay_role,
            panel=panel,
            name=name,
            panel_feeder_no=panel_feeder_no,
            panel_type=panel_type,
            pt_photo=pt_photo,
            secondary_photo=secondary_photo,
            has_pt_measurement=has_pt_measurement,
        )

    @staticmethod
    def resolve_overview_compartments(
        archetype: SwitchgearArchetype,
        voltage_class: VoltageClass = VoltageClass.KV_11,
    ) -> tuple[str, ...]:
        """Resolve overview scanning page compartments for switchgear archetype."""
        return resolve_overview_compartments(archetype, voltage_class)



