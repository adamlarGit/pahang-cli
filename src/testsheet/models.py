"""Domain models for testsheets and photo ranges in Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PhotoRange:
    """Numerical bounds (start and end photo numbers) for raw photo matching."""

    start_num: int | None = None
    end_num: int | None = None

    def contains(self, photo_num: int) -> bool:
        """Return True if photo_num is within bounds inclusive (supporting single photos)."""
        if self.start_num is None and self.end_num is None:
            return False
        start = self.start_num if self.start_num is not None else self.end_num
        end = self.end_num if self.end_num is not None else self.start_num
        if start is None or end is None:
            return False
        min_val = min(start, end)
        max_val = max(start, end)
        return min_val <= photo_num <= max_val

    @property
    def is_valid(self) -> bool:
        """Return True if at least start_num or end_num is specified."""
        return self.start_num is not None or self.end_num is not None


@dataclass(frozen=True)
class RawPhotoRanges:
    """Container for IR (Infrared) and DG (Digital) photo range bounds."""

    ir: PhotoRange = PhotoRange()
    dg: PhotoRange = PhotoRange()


@dataclass(frozen=True)
class SwitchgearPanelSpec:
    """Specification for an individual switchgear panel/bay."""

    panel_no: int = 1
    panel_feeder_no: str = ""
    name: str = ""
    panel_type: str = ""
    serial_no: str = ""
    status: str = ""
    load_amp: str = ""
    cable_type: str = ""
    heater_amp: str = ""
    us_reading: str = ""
    us_char: str = ""
    tev_reading: str = ""
    tev_ppc: str = ""
    tev_char: str = ""


@dataclass(frozen=True)
class SwitchgearSpec:
    """Specification for a switchgear board/tank and its associated panels."""

    switchgear_type: str = ""
    manufacturer: str = ""
    model: str = ""
    manufactured_year: str = ""
    rating: str = ""
    serial_no: str = ""
    panels: tuple[SwitchgearPanelSpec, ...] = ()


@dataclass(frozen=True)
class LVDBFeederSpec:
    """Specification for an individual LVDB / Feeder Pillar circuit way."""

    channel: str = ""       # e.g. "IN1", "IN2", "IN3", "OT1".."OT10"
    cable_type: str = ""    # e.g. "XLPE", "PILC"


@dataclass(frozen=True)
class ThermalReadingSpec:
    """Thermal measurement readings for an equipment component."""

    tmin: str = ""       # Reference / minimum temperature
    tmax: str = ""       # Maximum temperature
    delta_t: str = ""    # Temperature rise / difference
    avg: str = ""        # Average temperature


@dataclass(frozen=True)
class TransformerSpec:
    """Specification for a power distribution transformer."""

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
    hv_cable_thermal: ThermalReadingSpec = ThermalReadingSpec()
    hv_bushing_thermal: ThermalReadingSpec = ThermalReadingSpec()
    lv_cable_thermal: ThermalReadingSpec = ThermalReadingSpec()
    lv_bushing_thermal: ThermalReadingSpec = ThermalReadingSpec()
    body_thermal: ThermalReadingSpec = ThermalReadingSpec()


@dataclass(frozen=True)
class LVDBSpec:
    """Specification for a Low Voltage Distribution Board (LVDB) or Feeder Pillar (FP)."""

    name: str = "LVDB 1"
    label: str = "LVDB"
    source: str = "TX1"
    manufacturer: str = ""
    serial_no: str = ""
    rating: str = ""
    cable_type: str = ""
    feeders: tuple[LVDBFeederSpec, ...] = ()

    def get_feeder_cable(self, feeder_channel_or_id: str) -> str:
        """Resolve cable type for a given feeder channel or identifier, falling back to board cable_type."""
        if not feeder_channel_or_id or feeder_channel_or_id.strip() in ("", "-", "--"):
            return self.cable_type
        target = feeder_channel_or_id.strip().upper()
        # 1. Exact match on channel
        for f in self.feeders:
            if f.channel and f.channel.upper() == target:
                if f.cable_type:
                    return f.cable_type
        # 2. Universal feeder channel resolution (handles MSMS meters, CBM defect IDs, bay labels)
        from src.testsheet.feeder_thermal import resolve_feeder_channel

        ch_res = resolve_feeder_channel(target)
        if ch_res:
            for f in self.feeders:
                if f.channel and f.channel.upper() == ch_res.channel.upper():
                    if f.cable_type:
                        return f.cable_type
        # 3. Substring / fuzzy match on channel
        for f in self.feeders:
            if f.channel and (f.channel.upper() in target or target in f.channel.upper()):
                if f.cable_type:
                    return f.cable_type
        return self.cable_type


@dataclass(frozen=True)
class BatteryBankSpec:
    """Specification for a DC battery bank system."""

    name: str = "BATTERY BANK 1"
    manufacturer: str = ""
    model: str = ""
    serial_no: str = ""


@dataclass(frozen=True)
class FireExtinguisherSpec:
    """Specification for substation fire safety equipment."""

    has_fire_extinguisher: bool = False
    expiry_date: str = ""
    status: str = ""


@dataclass(frozen=True)
class SubstationEquipmentPackage:
    """Composite container bundling equipment specifications across all 5 domain categories."""

    switchgears: tuple[SwitchgearSpec, ...] = ()
    transformers: tuple[TransformerSpec, ...] = ()
    lvdb_specs: tuple[LVDBSpec, ...] = ()
    battery_banks: tuple[BatteryBankSpec, ...] = ()
    fire_extinguisher: FireExtinguisherSpec = FireExtinguisherSpec()
    has_battery_charger: bool = False
    has_rtu: bool = False
    has_sf6: bool = False
    has_efi: bool = False

    @property
    def switchgear(self) -> SwitchgearSpec:
        """Return the primary switchgear unit or a default SwitchgearSpec."""
        return self.switchgears[0] if self.switchgears else SwitchgearSpec()

    @property
    def transformer_count(self) -> int:
        """Return the total number of transformers."""
        return len(self.transformers)

    @property
    def lvdb_count(self) -> int:
        """Return the total number of LVDB / Feeder Pillar units."""
        return len(self.lvdb_specs)

    @property
    def has_switchgear(self) -> bool:
        """Return True if at least one switchgear is configured."""
        return len(self.switchgears) > 0


@dataclass(frozen=True)
class TestsheetData:
    """Extracted data from a substation testsheet Excel workbook."""

    __test__ = False

    substation_number: int
    substation_name_erms: str
    station_name: str = ""
    date_str: str = ""
    fl_erms: str = ""
    fl_site: str = ""
    wo_number: str = ""
    photo_ranges: RawPhotoRanges = RawPhotoRanges()
    substation_name_site: str = ""
    gps_coordinate: str = ""
    substation_type: str = ""
    building_type: str | None = None
    ambient: str = "-"
    humidity: str = "-"
    time: str = "-"
    tev_background: str = "-"
    cycle_1: datetime | None = None
    equipment: SubstationEquipmentPackage = SubstationEquipmentPackage()


@dataclass(frozen=True)
class SubstationTestsheetPackage:
    """Discovered testsheet workbook and unsorted raw data context package."""

    __test__ = False

    testsheet_path: Path
    unsorted_raw_data_dir: Path
    station: str
    month: str
    date_str: str
    substation_number: int
    data: TestsheetData | None = None


@dataclass(frozen=True)
class SubstationPackage:
    """Discovered pair of testsheet (.xlsx) and quick report (.docx) for a substation."""

    __test__ = False

    testsheet_xlsx: Path
    quick_report_docx: Path
    date_folder: str = ""
    station_name: str = ""
    fl_erms: str = ""
    substation_number: int = 0

