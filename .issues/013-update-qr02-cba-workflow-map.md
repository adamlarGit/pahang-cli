# Map: Update QR02 CBA Workflow (Pahang CLI)

Labels: wayfinder:map

## Destination

Implement the Update QR02 CBA workflow for Pahang CLI: extract substation metadata from testsheet workbooks (`PCE Testsheet`, `PCE VI` sheets) and upsert records into per-station ENGR `QR02 CBA` worksheets. Deep module architecture following Johor reference patterns — repository/transaction abstraction, atomic saves, ghost cell cleanup, per-station ENGR file resolution.

## Notes

- **Data Flow**: Testsheet → per-station ENGR `QR02 CBA` sheet (one ENGR file per station)
- **Fields Written**: GPS Coordinate (Col L), Type (Col M), Building Type (Col N), Cycle 1 date (Col O), Vendor (Col P = `"EET"`)
- **Lookup Key**: FL (ERMS) in Col I — match only, never written
- **ENGR File Pattern**: `ENGR-750-36-CBA-<STATION_CODE>-<YEAR>.xlsx` in `PYTHON/ENGR FROM DRIVE/`
- **Testsheet Location**: `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/*.xlsx`
- **Testsheet Format**: Same as Johor — `PCE Testsheet` (W5 FL, C5 name, P4 date), `PCE VI` (C7 site name, C8 GPS, N1 type, row 9 building type checkboxes)
- **Reference Codebase**: `C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV`
- **Sample ENGR Data**: `C:\Users\ADAM\Documents\PO 42289580 - PAHANG - 11kV SECOND CYCLE AZZAD 2026\PYTHON\ENGR FROM DRIVE`
- **Skills**: `/codebase-design`, `/domain-modeling`
- **Design**: Follow deep module principles — `src/master/qr02.py` (repository + UoW), `src/testsheet/extractor.py` (fixed-cell extraction), `src/update_qr02_cba_workflow.py` (orchestration)

## Decisions so far

- [Data Flow Direction](file:///.issues/013-update-qr02-cba-workflow-map.md) — Testsheet data feeds into per-station ENGR QR02 CBA sheets; FL (ERMS) is lookup key only (not written); only GPS, Type, Building Type, Cycle 1 date, and Vendor (`"EET"`) are written.
- [Station ENGR Code Mapping](file:///.issues/013-update-qr02-cba-workflow-map.md) — 14 stations mapped: MRN, KTN, JEN, BMS, BTG, GBG, ROM, TML, PEK, TRI, KLS, CHL, RAU, JRT. Filename year derived from `ProjectMetadata.year`.
- [Testsheet Folder Scanning](file:///.issues/013-update-qr02-cba-workflow-map.md) — Reuse `SubstationTestsheetRepository.discover_packages()`, group by station, one ENGR transaction per station group.
- [TestsheetExtractor Rewrite](file:///.issues/013-update-qr02-cba-workflow-map.md) — Replace generic keyword scanning with Johor's fixed-cell approach (`PCE Testsheet` W5/C5/P4, `PCE VI` C7/C8/N1/row 9). Expand `TestsheetData` model. Keep RAW DATA photo range extraction.
- [Master Repository Module](file:///.issues/013-update-qr02-cba-workflow-map.md) — Create `src/master/qr02.py` following Johor's `Qr02Repository`/`LocalExcelQr02Transaction` architecture with per-station ENGR resolution.
- [ENGR Filename Year](file:///.issues/013-update-qr02-cba-workflow-map.md) — Derived from `ProjectMetadata.year`, not hardcoded.
- [History Tracking Key](file:///.issues/013-update-qr02-cba-workflow-map.md) — Keyed by `<STATION>/<MONTH>/<DD-MM-YYYY>` in `PYTHON/processed_folders.json`.

## Not yet specified

- Pahang-specific `warn_missing_fields()` audit (which fields are essential for Pahang vs Johor's equipment-heavy checks).
- Row matching edge cases when ENGR file has no pre-populated FL for a substation (append vs skip policy).

## Out of scope

- Equipment columns (switchgear, transformer, feeder pillar) — Pahang ENGR has no equipment columns (stops at Col Q).
- QR03 CBA or QR03 VI sheet updates — separate workflow.
