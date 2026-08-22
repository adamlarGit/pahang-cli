# Ticket 083: Testsheet Equipment Package OpenPyXL Extractor

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](map.md)
Status: Closed

## Question

How should `TestsheetExtractor` in `src/testsheet/extractor.py` be enhanced to parse openpyxl worksheets (`PCE VI` and `PCE Testsheet`) into `SubstationEquipmentPackage` adhering to Stage 2 (Read Phase) of `docs/etl_pipeline_refactoring_methodology.md` with zero silent fallbacks and reusable sub-helper methods?

## Resolution

Specified single-responsibility extractor helper methods in `TestsheetExtractor` (`src/testsheet/extractor.py`):
1. **Switchgear & Panels (`_extract_switchgear_specs`)**:
   - Switchgear 1 from `PCE VI` Rows 11–13: Row 11 checkboxes (`RMU OIL`, `RMU SF6`, `MRMU`, `VCB`, `OCB`, `OTHER`), `C12` manufacturer, `F12`/`G12` model, `C13` year, `J13` rating, `O13` serial no.
   - Switchgear 2 from `PCE VI` Rows 14–16: Row 14 checkboxes (`RMU OIL`, `RMU SF6`, `MRMU`, `VCB`, `OCB`, `OTHER`), `C15` manufacturer, `F15`/`G15` model, `C16` year, `J16` rating, `O16` serial no. (parsed if active checkbox or non-empty manufacturer/serial).
   - Panel slots across `PCE Testsheet` & rollover sheets (`(2)`, `(3)`): extracts `panel_no`, `panel_feeder_no` (SCADA), `name`, `panel_type`, `status` (`CLOSE`/`TRIP`), `load_amp`, `cable_type`, `heater_amp`, `serial_no`. Non-empty name/feeder rule filters out inactive slots.
2. **Transformers (`_extract_transformer_specs`)**:
   - `C17` on `PCE VI` is authoritative quantity (`1..4`). Returns `()` for `0`, `N/A`, or `NOT ACCESSIBLE`.
   - Rows 18–21: Column `D` (`type`), Column `F` (`rating_kva`), Column `I` (`construction_year`), Column `K` (`manufacturer`), Column `O` (`serial_no`).
3. **LVDB / Feeder Pillar (`_extract_lvdb_specs`)**:
   - `PCE Testsheet` Slot 1 (rows 48–51): `R48` label (`FP`/`LVDB`), `T48` source (`TX1`), `S49` IR photo number, `V49` manufacturer, `V50` serial_no, `V51` rating.
   - `PCE Testsheet` Slot 2 (rows 52–55): `R52` label (`FP`/`LVDB`), `T52` source (`TX2`), `S53` IR photo number, `V53` manufacturer, `V54` serial_no, `V55` rating.
   - Active detection: Valid IR photo number in `S49`/`S53` or non-empty manufacturer/serial/rating.
4. **Battery Bank (`_extract_battery_banks`)**:
   - `PCE Testsheet` rows 59–65: Scans Column `B` for `"Battery Bank"` labels, parses Column `J` for manufacturer, model, and serial number.
5. **Fire Extinguisher (`_extract_fire_extinguisher_spec`)**:
   - `building_type == "OUTDOOR"` $\to$ `has_fire_extinguisher = False`.
   - Indoor/Attach/Compact $\to$ `has_fire_extinguisher = True`, extracts `D42`/`E42` (Valid), `F42`/`G42` (Expired), `I42` (expiry date).
6. **Auxiliary Flags (`_extract_auxiliary_flags`)**:
   - `has_efi`: `PCE VI` Row 25 (`E25` `✅` vs `I25` `N/A`).
   - `has_sf6`: `PCE VI` Row 29 (`E29` `✅`) and Row 11 SF6/MRMU.
   - `has_battery_charger`, `has_rtu`.
7. **Missing Value Presentation Policy**: Missing/corrupted cells normalize to `""` in extracted domain dataclasses. Dash `"-"` is only injected during document presentation (Stage 4/5).

