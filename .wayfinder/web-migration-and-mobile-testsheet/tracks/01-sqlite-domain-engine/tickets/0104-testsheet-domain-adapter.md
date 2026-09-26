<!-- status: open -->
Part of Track 1: .wayfinder/web-migration-and-mobile-testsheet/tracks/01-sqlite-domain-engine/map.md

# 0104: feat(db): in-memory testsheet domain adapter

**What to build:**
An authoritative domain adapter (`TestsheetDomainAdapter`) in `src/db/adapter.py` that translates relational SQLite inspection records into the existing `TestsheetData` domain model (`src/testsheet/models.py`) in memory.

This fulfills Master Decision **D-MASTER.15**: downstream report workflows (`QuickReportWorkflow`, `FullReportWorkflow`, `UpdateQr02CbaWorkflow`, `PopulateTotalPeWorkflow`, `WhatsAppReportWorkflow`) can consume SQLite inspection data directly without writing temporary files to disk or requiring any breaking changes to their report assembly pipelines.

**Capabilities:**
1. Queries `inspections` and child tables (`switchgear_spec`, `switchgear_panels`, `switchgear_readings`, `transformer_records`, `feeder_pillar_records`, `visual_checklist_items`, `defect_records`, `calibration_equipment`).
2. Reconstructs `TestsheetData` with full field fidelity:
   - Metadata (`pe_num`, `substation_name`, `station`, `inspection_date`, `voltage_rating`, etc.).
   - Switchgear specs and panel matrices.
   - Insulation and contact resistance readings.
   - UltraTEV survey readings and classifications.
   - Transformer and feeder pillar status records.
   - Visual inspection checklist items and defects.
   - Discovered camera and thermal photo ranges (`ir_photo_range`, `dg_photo_range`).
3. Provides batch adaptation: `get_testsheet_data_batch(station, date)` returning `list[TestsheetData]` matching the interface expected by workflow orchestrators.

**Blocked by:** 0101, 0102

**Status:** Open

## Acceptance Criteria
- [ ] Implement `TestsheetDomainAdapter` in `src/db/adapter.py`.
- [ ] Implement query and transformation logic mapping SQLite rows to immutable `TestsheetData` dataclasses.
- [ ] Verify 100% attribute parity against legacy `TestsheetExtractor` outputs for identical inspection fixtures.
- [ ] Add unit and integration tests in `tests/db/test_adapter.py`.
