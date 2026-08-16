# Ticket 082: Reusable Substation Equipment Package Domain Models

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](file:///.issues/081-dynamic-substation-equipment-condition-map.md)
Status: Open (Unblocked)

## Question

How should the domain models in `src/testsheet/models.py` be expanded to represent substation equipment package specifications across all 5 categories (Environment, Switchgear, Transformer, LVDB, Auxiliary & Fire Safety) as canonical, reusable domain entities that can be shared across Quick Report, WhatsApp Report, MSMS, and future workflows without domain drift?

## Objectives

1. Define immutable, zero-dependency dataclasses covering the 5 domain categories:
   - **Category 1 (Environment)**: Integrated via `building_type` (`INDOOR`, `OUTDOOR`, `COMPACT`, `ATTACH BUILDING`) and `substation_type` (`PCE`, `CS`, `SSU > 8`, `RM`, `PPU`).
   - **Category 2 (Switchgear)**: `SwitchgearSpec`: `switchgear_type`, `manufacturer`, `model`, `manufactured_year`, `rating`, `serial_no`, `panel_count`, `feeders`.
   - **Category 3 (Transformer)**: `TransformerSpec`: `tx_id` (e.g. `"Tx 1"`), `rating_kva`, `construction_year`, `manufacturer`, `serial_no`, `type_hs`.
   - **Category 4 (LVDB)**: `LVDBSpec`: `manufacturer`, `serial_no`, `rating`, `fuse_type` (e.g. `"J-SLOTTED"` or `"DIN TYPE"`).
   - **Category 5 (Auxiliary & Fire Safety)**:
     - `BatteryBankSpec`: `name`, `details_str`.
     - `FireExtinguisherSpec`: `has_fire_extinguisher` (bool, False for Outdoor, True for Indoor/Attach/Compact), `expiry_date` (str), `status` (str, e.g. `"VALID"`, `"EXPIRED"`).
2. Construct top-level container `SubstationEquipmentPackage`:
   - `switchgear: SwitchgearSpec`
   - `transformer_count: int`
   - `transformers: tuple[TransformerSpec, ...]`
   - `lvdb_specs: tuple[LVDBSpec, ...]`
   - `battery_banks: tuple[BatteryBankSpec, ...]`
   - `fire_extinguisher: FireExtinguisherSpec`
   - `has_battery_charger: bool`
   - `has_rtu: bool`
   - `has_sf6: bool` (SF6 Gas Indicator presence / SF6 Switchgear type)
   - `has_efi: bool` (Earth Fault Indicator presence / functionality)
   - `findings_remarks: str`
3. Integrate `equipment: SubstationEquipmentPackage = SubstationEquipmentPackage()` onto `TestsheetData` with default initializers to maintain 1:1 backwards compatibility.
