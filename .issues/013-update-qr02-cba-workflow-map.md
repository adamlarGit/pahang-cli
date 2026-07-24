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
- [Station ENGR Code Mapping](file:///.issues/014-station-engr-code-mapping.md) — 14 stations mapped: MRN, KTN, JEN, BMS, BTG, GBG, ROM, TML, PEK, TRI, KLS, CHL, RAU, JRT. Filename year derived from `ProjectMetadata.year`.
- [TestsheetExtractor Rewrite](file:///.issues/015-rewrite-testsheet-extractor.md) — Fixed-cell extraction for `PCE Testsheet` (W5/C5/P4) and `PCE VI` (C7/C8/N1/row 9).
- [Master Repository Module](file:///.issues/016-master-qr02-repository.md) — `src/master/qr02.py` with `LocalExcelQr02Repository`, exact FL matching, fallback append, atomic saves, and ghost cell cleanup.
- [Workflow Orchestrator](file:///.issues/017-update-qr02-cba-workflow.md) — `src/update_qr02_cba_workflow.py` with AUTO, ALL, and SPECIFIC mode filtering and history tracking in `processed_folders.json`.
- [Service & CLI Wiring](file:///.issues/018-wire-service-and-cli-adapter.md) — `WorkflowService.run_update_qr02_cba` and `UpdateQr02CbaAction` with 3-tier date folder navigation.

## Not yet specified

- None (Map fully resolved).

## Out of scope

- Equipment columns (switchgear, transformer, feeder pillar) — Pahang ENGR has no equipment columns (stops at Col Q).
- QR03 CBA or QR03 VI sheet updates — separate workflow.
