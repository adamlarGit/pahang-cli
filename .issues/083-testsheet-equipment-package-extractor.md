# Ticket 083: Testsheet Equipment Package OpenPyXL Extractor

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](file:///.issues/081-dynamic-substation-equipment-condition-map.md)
Status: Open (Blocked by Ticket 082)

## Question

How should `TestsheetExtractor` in `src/testsheet/extractor.py` be enhanced to parse openpyxl worksheets (`PCE VI` and `PCE Testsheet`) into `SubstationEquipmentPackage` adhering to Stage 2 (Read Phase) of `docs/etl_pipeline_refactoring_methodology.md` with zero silent fallbacks and reusable sub-helper methods?

## Objectives

1. Follow ETL Stage 2 Single Responsibility Principle:
   - Implement `_extract_switchgear_spec(ws_vi, ws_pce) -> SwitchgearSpec` (parse `PCE VI` row 11 checkboxes, `C12` manufacturer, `G12` model, `E13` year, `K13` rating, `O13` serial no, and CBA switchgear rows 14-17 across pages for panel count).
   - Implement `_extract_transformer_specs(ws_vi) -> tuple[TransformerSpec, ...]` (read `E17` for count, rows 18-21 for Tx 1..4 specs).
   - Implement `_extract_lvdb_specs(ws_pce) -> tuple[LVDBSpec, ...]` (read `Z37` fuse type, `W38-W40` LVDB1 specs, `W42-W44` LVDB2 specs).
   - Implement `_extract_battery_banks(ws_pce) -> tuple[BatteryBankSpec, ...]` (read CBA rows 47-48).
   - Implement `_extract_fire_extinguisher_spec(ws_vi, building_type) -> FireExtinguisherSpec`:
     - If `building_type` == `"OUTDOOR"` -> `has_fire_extinguisher = False`.
     - If `building_type` in `("INDOOR", "ATTACH BUILDING", "COMPACT")` -> `has_fire_extinguisher = True`, parse row 41 (`G41`/`H41`) for expiry date and status.
   - Implement `_extract_feature_flags(ws_vi, ws_pce)`: parse `has_sf6` (Row 11 SF6 checkbox / Gas pressure row 28), `has_efi` (Row 24 EFI functioning), `has_rtu`, `has_battery_charger`.
2. Populate `TestsheetData.equipment` cleanly within `extract_testsheet_data()`.
