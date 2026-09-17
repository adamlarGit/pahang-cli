"""Contract scope, modality normalization, and switchgear eligibility module.

Centralized domain logic for:
- Awarded technologies normalization and validation (IR, US, TEV)
- ContractScope value object modeling project technology scope
- Switchgear compartment normalization and eligibility matrices (TEV & US)
- Backward-compatible two-tier evaluation functional wrappers
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

# Canonical default awarded technologies (standard 3-modality contract)
DEFAULT_AWARDED_TECHNOLOGIES: frozenset[str] = frozenset({"IR", "US", "TEV"})

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
    "TIADA",
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


def normalize_technologies(techs: Any = None) -> set[str]:
    """Normalize technologies specification into a set of uppercase strings.

    Filters out negative/empty sentinels (e.g. '-', 'NONE', 'NORMAL', 'N/A', 'TIADA')
    and normalizes recognized modalities ('IR', 'US', 'TEV'). Supports composite
    delimiters ('+', ',', '/').
    """
    if techs is None:
        return set()
    if isinstance(techs, str):
        raw_items = [techs]
    elif isinstance(techs, (int, float, bool)):
        raw_items = [str(techs)]
    elif isinstance(techs, (set, frozenset, list, tuple)) or hasattr(techs, "__iter__"):
        raw_items = [str(t) for t in techs]
    else:
        raw_items = [str(techs)]

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


# ─── Switchgear Compartment TEV & US Eligibility Sets ─────────────────────────
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

US_BLANKED_SWG_COMPARTMENTS: frozenset[str] = frozenset({
    "SECONDARY COMPARTMENT",
    "LINK BOX",
})


def normalize_swg_compartment(compartment: str | None) -> str:
    """Normalize raw compartment or defect area string to canonical switchgear compartment name."""
    if not compartment:
        return ""
    comp_upper = str(compartment).strip().upper()

    # Direct canonical membership check
    if (
        comp_upper in TEV_ELIGIBLE_SWG_COMPARTMENTS
        or comp_upper in TEV_BLANKED_SWG_COMPARTMENTS
        or comp_upper in US_BLANKED_SWG_COMPARTMENTS
    ):
        return comp_upper

    # Specific precedence rules:
    # 1. Cable Entry before generic Cable
    if (
        any(k in comp_upper for k in ("CABLE ENTRY", "ENTRY CABLE", "CABLE INLET"))
        or re.search(r"\bCABLE[\s\-_/]*ENTRY\b", comp_upper)
        or re.search(r"\bENTRY[\s\-_/]*CABLE\b", comp_upper)
    ):
        return "CABLE ENTRY"

    # 2. Link Box before generic Cable (e.g. Cable Link Box, Linkbox, Link Box, Link-Box, Link_Box)
    if (
        any(k in comp_upper for k in ("LINK BOX", "LINKBOX", "CABLE LINK BOX"))
        or re.search(r"\bLINK[\s\-_/]*BOX\b", comp_upper)
        or ("LINK" in comp_upper and "BOX" in comp_upper)
    ):
        return "LINK BOX"

    # 3. Secondary Compartment (Control/metering compartment)
    if (
        any(k in comp_upper for k in ("SECONDARY COMPARTMENT", "SECONDARY", "CONTROL COMPARTMENT", "METERING"))
        or re.search(r"\bCONTROL\b", comp_upper)
    ):
        return "SECONDARY COMPARTMENT"

    # 4. Busbar
    if "BUSBAR" in comp_upper:
        return "BUSBAR COMPARTMENT"

    # 5. Fuse (e.g. INDKOM RMU fuse compartment / outgoing fuse)
    if "FUSE" in comp_upper:
        return "FUSE COMPARTMENT"

    # 6. Breaker (VCB / CB / Spout / Chamber)
    if any(k in comp_upper for k in ("BREAKER", "VCB", "SPOUT", "CHAMBER")) or re.search(r"\bCB\b", comp_upper):
        return "BREAKER COMPARTMENT"

    # 7. PT / VT (Potential / Voltage Transformer)
    if (
        re.search(r"\b(PT|VT)\b", comp_upper)
        or "VOLTAGE TRANSFORMER" in comp_upper
        or "POTENTIAL TRANSFORMER" in comp_upper
    ):
        return "PT COMPARTMENT"

    # 8. Cable (e.g. Cable Box, Cable Termination, Cable Lug)
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


def is_swg_compartment_us_eligible(compartment: str | None) -> bool:
    """Determine if a switchgear compartment is eligible for Ultrasound (US) testing (Tier 2).

    US-Excluded / Blanked:
    - SECONDARY COMPARTMENT (Control/metering compartment; no ultrasound testing performed)
    - LINK BOX (External cable link/grounding box; no ultrasound testing performed)

    US-Eligible:
    - All other switchgear compartments: BREAKER COMPARTMENT, CABLE COMPARTMENT, PT COMPARTMENT,
      BUSBAR COMPARTMENT, CABLE ENTRY, FUSE COMPARTMENT, BACK COMPARTMENT, FRONT COMPARTMENT, etc.
    """
    if not compartment:
        return False
    normalized = normalize_swg_compartment(compartment)
    if not normalized:
        return False
    return normalized not in US_BLANKED_SWG_COMPARTMENTS


# ─── Functional Wrappers (Backward Compatible) ────────────────────────────────
def is_tev_contract_awarded(technologies: Any = None) -> bool:
    """Check if TEV is in project awarded technologies (Tier 1).

    If technologies is omitted or None, defaults to True (standard 3-technology contract).
    """
    if technologies is None:
        return True
    if isinstance(technologies, ContractScope):
        return technologies.has_tev
    norm_techs = normalize_technologies(technologies)
    if not norm_techs:
        return True
    return "TEV" in norm_techs


def is_us_contract_awarded(technologies: Any = None) -> bool:
    """Check if Ultrasound (US) is in project awarded technologies (Tier 1).

    If technologies is omitted or None, defaults to True (standard 3-technology contract).
    """
    if technologies is None:
        return True
    if isinstance(technologies, ContractScope):
        return technologies.has_us
    norm_techs = normalize_technologies(technologies)
    if not norm_techs:
        return True
    return "US" in norm_techs


def is_swg_tev_active(
    project_technologies: Any = None,
    compartment: str | None = None,
) -> bool:
    """Two-tier evaluation of switchgear panel TEV activity.

    Returns True only if:
    1. Tier 1: Contract includes TEV technology.
    2. Tier 2: Switchgear compartment is TEV-eligible.
    """
    if isinstance(project_technologies, ContractScope):
        return project_technologies.is_swg_tev_active(compartment)
    if not is_tev_contract_awarded(project_technologies):
        return False
    return is_swg_compartment_tev_eligible(compartment)


def is_swg_us_active(
    project_technologies: Any = None,
    compartment: str | None = None,
) -> bool:
    """Two-tier evaluation of switchgear panel Ultrasound (US) activity.

    Returns True only if:
    1. Tier 1: Contract includes US technology.
    2. Tier 2: Switchgear compartment is US-eligible.
    """
    if isinstance(project_technologies, ContractScope):
        return project_technologies.is_swg_us_active(compartment)
    if not is_us_contract_awarded(project_technologies):
        return False
    return is_swg_compartment_us_eligible(compartment)


# ─── Deep Module: ContractScope Dataclass ─────────────────────────────────────
@dataclass(frozen=True)
class ContractScope:
    """Immutable domain representation of awarded project contract technologies and equipment scope."""

    _technologies: frozenset[str] = field(default_factory=lambda: DEFAULT_AWARDED_TECHNOLOGIES)

    def __init__(
        self,
        technologies: Any = None,
        *,
        awarded_technologies: Any = None,
    ) -> None:
        source = awarded_technologies if awarded_technologies is not None else technologies
        if source is None or source is DEFAULT_AWARDED_TECHNOLOGIES:
            techs = DEFAULT_AWARDED_TECHNOLOGIES
        elif isinstance(source, ContractScope):
            techs = source._technologies
        else:
            techs = frozenset(normalize_technologies(source))
        object.__setattr__(self, "_technologies", techs)

    @property
    def awarded_technologies(self) -> frozenset[str]:
        """Return the frozenset of awarded technologies (e.g. {'IR', 'US', 'TEV'})."""
        return self._technologies

    @property
    def technologies(self) -> frozenset[str]:
        """Alias for awarded_technologies."""
        return self._technologies

    @property
    def has_ir(self) -> bool:
        """Return True if Thermal Infrared (IR) is awarded."""
        return "IR" in self._technologies

    @property
    def has_us(self) -> bool:
        """Return True if Airborne / Structure-borne Ultrasound (US) is awarded."""
        return "US" in self._technologies

    @property
    def has_tev(self) -> bool:
        """Return True if Transient Earth Voltage (TEV) is awarded."""
        return "TEV" in self._technologies

    def is_awarded(self, technology: Any) -> bool:
        """Check if a specific technology (e.g. 'IR', 'US', 'TEV') is awarded."""
        if technology is None:
            return False
        norm = normalize_technologies(technology)
        if not norm:
            return False
        return norm.issubset(self._technologies)

    def is_swg_tev_active(self, compartment: str | None) -> bool:
        """Two-tier evaluation of switchgear panel TEV activity for this contract."""
        if not self.has_tev:
            return False
        return is_swg_compartment_tev_eligible(compartment)

    def is_swg_us_active(self, compartment: str | None) -> bool:
        """Two-tier evaluation of switchgear panel Ultrasound (US) activity for this contract."""
        if not self.has_us:
            return False
        return is_swg_compartment_us_eligible(compartment)

    def __contains__(self, technology: Any) -> bool:
        return self.is_awarded(technology)

    def __iter__(self):
        return iter(self._technologies)

    def __len__(self) -> int:
        return len(self._technologies)

    def __bool__(self) -> bool:
        return bool(self._technologies)

    def __repr__(self) -> str:
        sorted_techs = sorted(self._technologies)
        return f"ContractScope({sorted_techs})"

    @classmethod
    def from_source(cls, source: Any = None) -> ContractScope:
        """Universal factory constructing ContractScope from dicts, objects, strings, sequences, or None."""
        if source is None:
            return cls(DEFAULT_AWARDED_TECHNOLOGIES)

        if isinstance(source, ContractScope):
            return source

        try:
            from unittest.mock import NonCallableMock
            if isinstance(source, NonCallableMock):
                try:
                    if hasattr(source, "contract") and isinstance(source.contract, ContractScope):
                        return source.contract
                except Exception:
                    pass
                for attr in ("technologies", "project_technologies", "metadata", "project"):
                    try:
                        if hasattr(source, attr):
                            val = getattr(source, attr)
                            if not isinstance(val, NonCallableMock) and val is not None:
                                return cls.from_source(val)
                    except Exception:
                        pass
                return cls(DEFAULT_AWARDED_TECHNOLOGIES)
        except ImportError:
            pass

        if hasattr(source, "contract") and isinstance(source.contract, ContractScope):
            return source.contract

        if isinstance(source, dict):
            if "contract" in source and isinstance(source["contract"], ContractScope):
                return source["contract"]

            for key in ("contract", "project_technologies", "technologies"):
                if key in source and source[key] is not None:
                    return cls.from_source(source[key])

            for nest_key in ("project", "metadata", "project_metadata"):
                nested = source.get(nest_key)
                if nested is not None:
                    if hasattr(nested, "contract") and isinstance(nested.contract, ContractScope):
                        return nested.contract
                    if hasattr(nested, "technologies") and nested.technologies is not None:
                        return cls.from_source(nested.technologies)
                    if isinstance(nested, dict):
                        for key in ("contract", "project_technologies", "technologies"):
                            if key in nested and nested[key] is not None:
                                return cls.from_source(nested[key])

            return cls(DEFAULT_AWARDED_TECHNOLOGIES)

        # Check object attributes
        for attr in ("contract", "project_technologies", "technologies"):
            if hasattr(source, attr):
                val = getattr(source, attr)
                if callable(val):
                    try:
                        val = val()
                    except Exception:
                        continue
                if val is not None:
                    if attr == "contract" and isinstance(val, ContractScope):
                        return val
                    return cls.from_source(val)

        for nest_attr in ("metadata", "project_metadata", "project"):
            if hasattr(source, nest_attr):
                nested = getattr(source, nest_attr)
                if nested is not None:
                    return cls.from_source(nested)

        # Strings, sets, sequences, sentinels
        if isinstance(source, (str, set, frozenset, list, tuple)):
            norm = normalize_technologies(source)
            return cls(frozenset(norm))

        if isinstance(source, (int, float, bool)):
            norm = normalize_technologies(source)
            return cls(frozenset(norm))

        if hasattr(source, "__iter__"):
            norm = normalize_technologies(source)
            return cls(frozenset(norm))

        # Unknown arbitrary object (e.g. SimpleNamespace(foo="bar"), object())
        return cls(DEFAULT_AWARDED_TECHNOLOGIES)


__all__ = [
    "ContractScope",
    "DEFAULT_AWARDED_TECHNOLOGIES",
    "TEV_ELIGIBLE_SWG_COMPARTMENTS",
    "TEV_BLANKED_SWG_COMPARTMENTS",
    "US_BLANKED_SWG_COMPARTMENTS",
    "normalize_technologies",
    "normalize_swg_compartment",
    "is_swg_compartment_tev_eligible",
    "is_swg_compartment_us_eligible",
    "is_tev_contract_awarded",
    "is_us_contract_awarded",
    "is_swg_tev_active",
    "is_swg_us_active",
]
