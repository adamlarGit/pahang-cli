# Ticket 084: Dynamic Substation Condition Pairs Transformer

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](file:///.issues/081-dynamic-substation-equipment-condition-map.md)
Status: Open (Blocked by Ticket 082, Ticket 083)

## Question

How should `QuickReportTransformer._build_substation_condition_pairs()` in `src/quick_report/transformer.py` (and `src/quick_report/substation_condition.py`) be refactored as a pure ETL Stage 4 Transformer stage to dynamically construct 2-column condition pairs from `pkg.data.equipment` instead of returning hardcoded static pairs?

## Objectives

1. Apply ETL Stage 4 Pure Transformation principles:
   - Always include `("SUBSTATION OVERVIEW", "SIGNBOARD")`.
   - Add Switchgear card `("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE")` if switchgear is present.
   - Dynamically loop for `1..transformer_count`: add `("TRANSFORMER {i}", "TRANSFORMER {i} NAMEPLATE")`. Skip if `transformer_count == 0` (e.g. SSU switching station).
   - Dynamically loop for `1..lvdb_count`: add `("FEEDER PILLAR {i}", "FEEDER PILLAR {i} NAMEPLATE")`. Skip if no LVDB/0 TX.
   - Conditionally add `("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE")` if `has_battery_charger` is True.
   - Conditionally add `("RTU", "RTU NAMEPLATE")` if `has_rtu` is True.
   - Conditionally add `("EFI", "SF6 GAS INDICATOR")` if `has_sf6` or `has_efi` is True.
   - Conditionally add `("FIRE EXTINGUISHER", "FIRE EXTINGUISHER EXPIRY DATE")` ONLY if `fire_extinguisher.has_fire_extinguisher` is True (Indoor/Attach/Compact, skipped for Outdoor).
   - Conditionally add `("TRANSFORMER OIL LEVEL INDICATOR", "TRANSFORMER OIL LEVEL INDICATOR")` ONLY if `transformer_count > 0`.
2. Ensure `generate_substation_condition_pages()` seamlessly receives the dynamic pair count and handles multi-page chunking (3 pairs per page) and last-page border stripping.
