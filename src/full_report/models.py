"""Domain scan models and compartment matrix logic for Full Report (Ticket #26 / T2.3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Sequence

from src.testsheet.models import (
    BatteryBankSpec,
    LVDBFeederSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


class SwitchgearCategory(str, Enum):
    """Categorization of switchgear equipment driving compartment layout and page counts."""

    INDKOM = "INDKOM"
    TAMCO_LUCY = "TAMCO_LUCY"
    OTHER_RMU = "OTHER_RMU"
    VCB = "VCB"


# Standard 5 compartments for VCB switchgear per D26
VCB_STANDARD_COMPARTMENTS: tuple[str, ...] = (
    "BREAKER COMPARTMENT",
    "CABLE COMPARTMENT",
    "BUSBAR COMPARTMENT",
    "PT COMPARTMENT",
    "SECONDARY COMPARTMENT",
)

# Transition 5 compartments for VCB switchgear transition panels
VCB_TRANSITION_COMPARTMENTS: tuple[str, ...] = (
    "FRONT COMPARTMENT",
    "REAR COMPARTMENT",
    "BUSBAR COMPARTMENT",
    "PT COMPARTMENT",
    "SECONDARY COMPARTMENT",
)

# Standard 7 components for distribution transformers per D31 / ADR 0004
TRANSFORMER_STANDARD_COMPONENTS: tuple[str, ...] = (
    "OVERVIEW",
    "OVERVIEW TOP",
    "HV BUSHING",
    "HV CABLE",
    "HV CABLE SPLIT",
    "LV BUSHING",
    "LV CABLE",
)


def classify_switchgear(
    switchgear_type: str = "",
    manufacturer: str = "",
) -> SwitchgearCategory:
    """Classify switchgear into one of 4 canonical categories per D26/D29."""
    combined = f"{switchgear_type or ''} {manufacturer or ''}".upper()

    # VCB check takes highest precedence (even if made by TAMCO/EPE)
    if "VCB" in combined:
        return SwitchgearCategory.VCB

    # INDKOM RMU
    if "INDKOM" in combined:
        return SwitchgearCategory.INDKOM

    # TAMCO / LUCY / SSE LUCY
    if any(k in combined for k in ("TAMCO", "LUCY", "SSE LUCY")):
        return SwitchgearCategory.TAMCO_LUCY

    # Other RMUs (SIEMENS, ABB, generic RMU SF6 / RMU OIL)
    return SwitchgearCategory.OTHER_RMU


def is_tx_feeder(
    panel_or_name: SwitchgearPanelSpec | SwitchgearPanelScanSpec | dict | str | None = "",
) -> bool:
    """Determine if a switchgear panel/bay is a transformer (TX) feeder."""
    if panel_or_name is None:
        return False
    if isinstance(panel_or_name, str):
        combined = panel_or_name.upper()
    elif isinstance(panel_or_name, dict):
        name = panel_or_name.get("name", "") or ""
        feeder = panel_or_name.get("panel_feeder_no", "") or panel_or_name.get("feeder_no", "") or ""
        p_type = panel_or_name.get("panel_type", "") or ""
        combined = f"{name} {feeder} {p_type}".upper()
    else:
        name = getattr(panel_or_name, "name", "") or ""
        feeder = getattr(panel_or_name, "panel_feeder_no", "") or ""
        p_type = getattr(panel_or_name, "panel_type", "") or ""
        combined = f"{name} {feeder} {p_type}".upper()

    if any(
        k in combined
        for k in (
            "TRANSFORMER",
            "ALATUBAH",
            "TEE-OFF",
            "TEE OFF",
            "FUSE",
            "100KVA",
            "300KVA",
            "500KVA",
            "750KVA",
            "1000KVA",
            "KVA",
        )
    ):
        return True
    return bool(re.search(r"\bTX\d*\b", combined))


def is_transition_panel(
    panel_or_name: SwitchgearPanelSpec | SwitchgearPanelScanSpec | dict | str | None = "",
) -> bool:
    """Determine if a switchgear panel/bay is a transition panel."""
    if panel_or_name is None:
        return False
    if isinstance(panel_or_name, str):
        combined = panel_or_name.upper()
    elif isinstance(panel_or_name, dict):
        name = panel_or_name.get("name", "") or ""
        feeder = panel_or_name.get("panel_feeder_no", "") or panel_or_name.get("feeder_no", "") or ""
        p_type = panel_or_name.get("panel_type", "") or ""
        combined = f"{name} {feeder} {p_type}".upper()
    else:
        name = getattr(panel_or_name, "name", "") or ""
        feeder = getattr(panel_or_name, "panel_feeder_no", "") or ""
        p_type = getattr(panel_or_name, "panel_type", "") or ""
        combined = f"{name} {feeder} {p_type}".upper()

    return any(
        k in combined
        for k in ("TRANSITION", "PERALIHAN", "TRANSISYEN", "TOOLS", "TOOL")
    )


OVERVIEW_COMPARTMENTS_MAP: dict[SwitchgearCategory, tuple[str, ...]] = {
    SwitchgearCategory.TAMCO_LUCY: ("OVERVIEW", "OVERVIEW BOTTOM"),
    SwitchgearCategory.VCB: ("OVERVIEW",),
    SwitchgearCategory.INDKOM: ("OVERVIEW",),
    SwitchgearCategory.OTHER_RMU: ("OVERVIEW",),
}


def resolve_overview_compartments(category: SwitchgearCategory) -> tuple[str, ...]:
    """Resolve overview scanning page compartments for switchgear category per D26."""
    return OVERVIEW_COMPARTMENTS_MAP.get(category, ("OVERVIEW",))


def resolve_switchgear_compartments(
    category: SwitchgearCategory,
    panel: SwitchgearPanelSpec | SwitchgearPanelScanSpec | str | None = None,
) -> tuple[str, ...]:
    """Resolve switchgear panel scanning compartments per D26.

    Panel scanning strictly covers panel-level compartments:
    - TAMCO / LUCY: ("CABLE COMPARTMENT", "CABLE ENTRY")
    - INDKOM: ("FUSE COMPARTMENT",) for TX feeder bays, ("CABLE COMPARTMENT",) for other bays
      (or ("FUSE COMPARTMENT", "CABLE COMPARTMENT") when panel is omitted)
    - VCB: 5 standard compartments (or 5 transition compartments for transition panels)
    - OTHER_RMU: ("CABLE COMPARTMENT",)

    Board-level overview scanning ('OVERVIEW', 'OVERVIEW BOTTOM' via swg-overview.docx) is cleanly
    decoupled from panel scanning and resolved via resolve_overview_compartments().
    """
    if category == SwitchgearCategory.TAMCO_LUCY:
        return ("CABLE COMPARTMENT", "CABLE ENTRY")

    if category == SwitchgearCategory.VCB:
        if panel is not None and is_transition_panel(panel):
            return VCB_TRANSITION_COMPARTMENTS
        return VCB_STANDARD_COMPARTMENTS

    if category == SwitchgearCategory.INDKOM:
        if panel is None:
            return ("FUSE COMPARTMENT", "CABLE COMPARTMENT")
        if is_tx_feeder(panel):
            return ("FUSE COMPARTMENT",)
        return ("CABLE COMPARTMENT",)

    # OTHER_RMU
    return ("CABLE COMPARTMENT",)


def resolve_panel_page_count(
    category: SwitchgearCategory,
    panel: SwitchgearPanelSpec | SwitchgearPanelScanSpec,
    active_compartments: Sequence[str] | None = None,
) -> int:
    """Resolve number of scanning pages for a panel per D29."""
    if active_compartments is not None and len(active_compartments) > 0:
        return len(active_compartments)
    return len(resolve_switchgear_compartments(category, panel))


def build_switchgear_panel_scan_spec(
    panel: SwitchgearPanelSpec,
    category: SwitchgearCategory,
    active_compartments: Sequence[str] | None = None,
) -> SwitchgearPanelScanSpec:
    """Construct strongly-typed SwitchgearPanelScanSpec applying D26 compartments and D29 page counts."""
    if active_compartments is not None and len(active_compartments) > 0:
        compartments = tuple(active_compartments)
    else:
        compartments = resolve_switchgear_compartments(category, panel)

    return SwitchgearPanelScanSpec(
        panel_no=panel.panel_no,
        panel_feeder_no=panel.panel_feeder_no,
        name=panel.name,
        panel_type=panel.panel_type,
        serial_no=panel.serial_no,
        status=panel.status,
        load_amp=panel.load_amp,
        heater_amp=panel.heater_amp,
        cable_type=panel.cable_type,
        us_reading=panel.us_reading,
        us_char=panel.us_char,
        tev_reading=panel.tev_reading,
        tev_ppc=panel.tev_ppc,
        tev_char=panel.tev_char,
        photo_numbers=panel.photo_numbers,
        compartments=compartments,
    )


def build_switchgear_scan_spec(
    swg: SwitchgearSpec,
) -> SwitchgearScanSpec:
    """Construct strongly-typed SwitchgearScanSpec from SwitchgearSpec."""
    category = classify_switchgear(swg.switchgear_type, swg.manufacturer)
    overview = resolve_overview_compartments(category)
    panels = tuple(
        build_switchgear_panel_scan_spec(p, category)
        for p in swg.panels
    )

    return SwitchgearScanSpec(
        switchgear_type=swg.switchgear_type,
        manufacturer=swg.manufacturer,
        model=swg.model,
        manufactured_year=swg.manufactured_year,
        rating=swg.rating,
        serial_no=swg.serial_no,
        category=category,
        overview_compartments=overview,
        panels=panels,
        photo_numbers=swg.photo_numbers,
    )


def has_hv_cable_split(tx: TransformerSpec | TransformerScanSpec | None = None) -> bool:
    """Domain predicate stub for Transformer HV Cable Split per ADR 0004.

    Always returns True under unconditional generation policy.
    Future PCE revisions with structured checkbox will evaluate that coordinate.
    """
    return True


def build_transformer_scan_spec(tx: TransformerSpec) -> TransformerScanSpec:
    """Construct strongly-typed TransformerScanSpec from TransformerSpec per D31 / ADR 0004."""
    components = TRANSFORMER_STANDARD_COMPONENTS
    if not has_hv_cable_split(tx):
        components = tuple(c for c in components if c != "HV CABLE SPLIT")

    return TransformerScanSpec(
        tx_id=tx.tx_id,
        rating_kva=tx.rating_kva,
        construction_year=tx.construction_year,
        manufacturer=tx.manufacturer,
        serial_no=tx.serial_no,
        type=tx.type,
        us_reading=tx.us_reading,
        us_char=tx.us_char,
        hv_cable_type=tx.hv_cable_type,
        lv_cable_type=tx.lv_cable_type,
        photo_numbers=tx.photo_numbers,
        components=components,
    )


def build_lvdb_scan_spec(lvdb: LVDBSpec) -> LVDBScanSpec:
    """Construct strongly-typed LVDBScanSpec from LVDBSpec."""
    return LVDBScanSpec(
        name=lvdb.name,
        label=lvdb.label,
        source=lvdb.source,
        manufacturer=lvdb.manufacturer,
        serial_no=lvdb.serial_no,
        rating=lvdb.rating,
        cable_type=lvdb.cable_type,
        photo_numbers=lvdb.photo_numbers,
        feeders=lvdb.feeders,
    )


def build_battery_bank_scan_spec(bb: BatteryBankSpec) -> BatteryBankScanSpec:
    """Construct strongly-typed BatteryBankScanSpec from BatteryBankSpec."""
    return BatteryBankScanSpec(
        name=bb.name,
        manufacturer=bb.manufacturer,
        model=bb.model,
        serial_no=bb.serial_no,
        photo_numbers=bb.photo_numbers,
    )


def has_battery_bank(equipment: SubstationEquipmentPackage) -> bool:
    """Evaluate battery bank presence strictly via len(equipment.battery_banks) > 0 per D49."""
    return len(equipment.battery_banks) > 0


def build_full_report_scan_package(
    equipment: SubstationEquipmentPackage,
    substation_number: int = 0,
    station_name: str = "",
) -> FullReportScanPackage:
    """Construct complete FullReportScanPackage from extracted SubstationEquipmentPackage."""
    swgs = tuple(build_switchgear_scan_spec(s) for s in equipment.switchgears)
    txs = tuple(build_transformer_scan_spec(t) for t in equipment.transformers)
    lvdb_specs = tuple(build_lvdb_scan_spec(l) for l in equipment.lvdb_specs)

    # D49: Evaluates battery bank presence strictly via len(equipment.battery_banks) > 0
    if has_battery_bank(equipment):
        bbs = tuple(build_battery_bank_scan_spec(b) for b in equipment.battery_banks)
    else:
        bbs = ()

    return FullReportScanPackage(
        substation_number=substation_number,
        station_name=station_name,
        switchgears=swgs,
        transformers=txs,
        lvdb_specs=lvdb_specs,
        battery_banks=bbs,
    )


@dataclass(frozen=True)
class SwitchgearPanelScanSpec:
    """Strongly-typed scan specification for an individual switchgear panel/bay."""

    panel_no: int = 1
    panel_feeder_no: str = ""
    name: str = ""
    panel_type: str = ""
    serial_no: str = ""
    status: str = ""
    load_amp: str = ""
    heater_amp: str = ""
    cable_type: str = ""
    us_reading: str = ""
    us_char: str = ""
    tev_reading: str = ""
    tev_ppc: str = ""
    tev_char: str = ""
    photo_numbers: tuple[int, ...] = ()
    compartments: tuple[str, ...] = ()

    @property
    def page_count(self) -> int:
        """Derived scanning page count equal to number of active compartments."""
        return len(self.compartments)

    @property
    def is_tx_feeder(self) -> bool:
        """Return True if this panel is a transformer (TX) feeder."""
        return is_tx_feeder(self)

    @property
    def is_transition_panel(self) -> bool:
        """Return True if this panel is a transition panel."""
        return is_transition_panel(self)


@dataclass(frozen=True)
class SwitchgearScanSpec:
    """Strongly-typed scan specification for a switchgear lineup and its panels."""

    switchgear_type: str = ""
    manufacturer: str = ""
    model: str = ""
    manufactured_year: str = ""
    rating: str = ""
    serial_no: str = ""
    category: SwitchgearCategory = SwitchgearCategory.OTHER_RMU
    overview_compartments: tuple[str, ...] = ()
    panels: tuple[SwitchgearPanelScanSpec, ...] = ()
    photo_numbers: tuple[int, ...] = ()

    @property
    def panel_count(self) -> int:
        """Return the number of panels attached to the switchgear."""
        return len(self.panels)

    @property
    def total_page_count(self) -> int:
        """Return the total scanning pages for switchgear overview and panels."""
        overview_pages = len(self.overview_compartments)
        panel_pages = sum(p.page_count for p in self.panels)
        return overview_pages + panel_pages


@dataclass(frozen=True)
class TransformerScanSpec:
    """Strongly-typed scan specification for a distribution transformer."""

    tx_id: str = "Tx 1"
    rating_kva: str = ""
    construction_year: str = ""
    manufacturer: str = ""
    serial_no: str = ""
    type: str = ""
    us_reading: str = ""
    us_char: str = ""
    hv_cable_type: str = ""
    lv_cable_type: str = ""
    photo_numbers: tuple[int, ...] = ()
    components: tuple[str, ...] = TRANSFORMER_STANDARD_COMPONENTS

    @property
    def page_count(self) -> int:
        """Derived scanning page count equal to number of components."""
        return len(self.components)


# Feeder scan spec directly aliases LVDBFeederSpec to eliminate duplicated DTO code
LVDBFeederScanSpec = LVDBFeederSpec


@dataclass(frozen=True)
class LVDBScanSpec(LVDBSpec):
    """Strongly-typed scan specification for an LVDB or Feeder Pillar."""

    @property
    def page_count(self) -> int:
        """Return scanning page count for LVDB."""
        return 1


@dataclass(frozen=True)
class BatteryBankScanSpec(BatteryBankSpec):
    """Strongly-typed scan specification for a DC battery bank."""

    @property
    def page_count(self) -> int:
        """Return scanning page count for battery bank."""
        return 1


@dataclass(frozen=True)
class FullReportScanPackage:
    """Composite package containing scan specifications across all equipment in a substation."""

    substation_number: int = 0
    station_name: str = ""
    switchgears: tuple[SwitchgearScanSpec, ...] = ()
    transformers: tuple[TransformerScanSpec, ...] = ()
    lvdb_specs: tuple[LVDBScanSpec, ...] = ()
    battery_banks: tuple[BatteryBankScanSpec, ...] = ()

    @property
    def has_switchgear(self) -> bool:
        """Return True if at least one switchgear is present."""
        return len(self.switchgears) > 0

    @property
    def switchgear(self) -> SwitchgearScanSpec:
        """Return the primary switchgear or a default SwitchgearScanSpec."""
        return self.switchgears[0] if self.switchgears else SwitchgearScanSpec()

    @property
    def transformer_count(self) -> int:
        """Return total number of transformers."""
        return len(self.transformers)

    @property
    def lvdb_count(self) -> int:
        """Return total number of LVDB / Feeder Pillar units."""
        return len(self.lvdb_specs)

    @property
    def has_battery_bank(self) -> bool:
        """Evaluate battery bank presence strictly via len(self.battery_banks) > 0 per D49."""
        return len(self.battery_banks) > 0

    @property
    def total_page_count(self) -> int:
        """Calculate total scanning pages across all equipment in the package."""
        swg_pages = sum(s.total_page_count for s in self.switchgears)
        tx_pages = sum(t.page_count for t in self.transformers)
        lvdb_pages = sum(l.page_count for l in self.lvdb_specs)
        bb_pages = sum(b.page_count for b in self.battery_banks)
        return swg_pages + tx_pages + lvdb_pages + bb_pages
