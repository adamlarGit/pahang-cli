# Ticket 082: Reusable Substation Equipment Package Domain Models

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](map.md)
Status: Closed

## Question

How should the domain models in `src/testsheet/models.py` be expanded to represent substation equipment package specifications across all 5 categories (Environment, Switchgear, Transformer, LVDB, Auxiliary & Fire Safety) as canonical, reusable domain entities that can be shared across Quick Report, WhatsApp Report, MSMS, and future workflows without domain drift?

## Resolution

Defined immutable, zero-dependency dataclasses in `CONTEXT.md` and `src/testsheet/models.py`:
- `SwitchgearPanelSpec`: `panel_no`, `panel_feeder_no` (SCADA numbering), `name`, `panel_type`, `serial_no`, `status`, `load_amp`, `cable_type`, `heater_amp`.
- `SwitchgearSpec`: `switchgear_type`, `manufacturer`, `model`, `manufactured_year`, `rating` (board-level), `serial_no`, `panels: tuple[SwitchgearPanelSpec, ...]`.
- `TransformerSpec`: `tx_id`, `rating_kva`, `construction_year`, `manufacturer`, `serial_no`, `type`.
- `LVDBSpec`: `name`, `label` (`FP` or `LVDB`), `source` (`TX1`, `TX2`, etc.), `manufacturer`, `serial_no`, `rating`.
- `BatteryBankSpec`: `name`, `manufacturer`, `model`, `serial_no`.
- `FireExtinguisherSpec`: `has_fire_extinguisher`, `expiry_date`, `status`.
- `SubstationEquipmentPackage`: Composite container bundling all categories attached to `TestsheetData.equipment`, storing `switchgears: tuple[SwitchgearSpec, ...]`.

## Objectives

1. Define immutable, zero-dependency dataclasses covering the 5 domain categories:
   - **Category 1 (Environment)**: Integrated via `building_type` (`INDOOR`, `OUTDOOR`, `COMPACT`, `ATTACH BUILDING`) and `substation_type` (`PCE`, `CS`, `SSU > 8`, `RM`, `PPU`).
   - **Category 2 (Switchgear & Panels)**:
     - `SwitchgearPanelSpec`: `panel_no: int = 1`, `panel_feeder_no: str = ""` (SCADA numbering), `name: str = ""` (feeder/panel label), `panel_type: str = ""` (`VCB`, `LBS`, `SWITCH`, `TEE-OFF`), `serial_no: str = ""` (breaker serial number), `status: str = ""` (`CLOSE`, `TRIP`, `OPEN`), `load_amp: str = ""` (operating current), `cable_type: str = ""`, `heater_amp: str = ""`.
     - `SwitchgearSpec`: `switchgear_type: str = ""`, `manufacturer: str = ""`, `model: str = ""`, `manufactured_year: str = ""`, `rating: str = ""` (attached to switchgear), `serial_no: str = ""` (tank/board serial number), `panels: tuple[SwitchgearPanelSpec, ...] = ()`.
   - **Category 3 (Transformer)**: `TransformerSpec`: `tx_id: str = "Tx 1"`, `rating_kva: str = ""`, `construction_year: str = ""`, `manufacturer: str = ""`, `serial_no: str = ""`, `type: str = ""` (`HERMETICALLY SEALED`, `CONSERVATOR`, etc.).
   - **Category 4 (LVDB / FP)**: `LVDBSpec`: `name: str = "LVDB 1"`, `label: str = "LVDB"` (`FP` or `LVDB`), `source: str = "TX1"`, `manufacturer: str = ""`, `serial_no: str = ""`, `rating: str = ""`.
   - **Category 5 (Auxiliary & Fire Safety)**:
     - `BatteryBankSpec`: `name: str = "BATTERY BANK 1"`, `manufacturer: str = ""`, `model: str = ""`, `serial_no: str = ""`.
     - `FireExtinguisherSpec`: `has_fire_extinguisher: bool = False` (False for Outdoor, True for Indoor/Attach/Compact), `expiry_date: str = ""`, `status: str = ""` (`VALID`, `EXPIRED`, `-`).
2. Construct top-level container `SubstationEquipmentPackage`:
   - `switchgears: tuple[SwitchgearSpec, ...] = ()`
   - `transformers: tuple[TransformerSpec, ...] = ()`
   - `lvdb_specs: tuple[LVDBSpec, ...] = ()`
   - `battery_banks: tuple[BatteryBankSpec, ...] = ()`
   - `fire_extinguisher: FireExtinguisherSpec = FireExtinguisherSpec()`
   - `has_battery_charger: bool = False`
   - `has_rtu: bool = False`
   - `has_sf6: bool = False`
   - `has_efi: bool = False`
   - Properties: `switchgear: SwitchgearSpec` (returns first unit or default for backwards compatibility), `transformer_count: int`, `lvdb_count: int`, `has_switchgear: bool`.
3. Integrate `equipment: SubstationEquipmentPackage = SubstationEquipmentPackage()` onto `TestsheetData` with default initializers to maintain 1:1 backwards compatibility.

