<!-- status: open -->
Part of Track 1: .wayfinder/web-migration-and-mobile-testsheet/tracks/01-sqlite-domain-engine/map.md

# 0101: feat(db): canonical sql schema & dual-target ddl

**What to build:**
The canonical relational SQL schema for substation inspection records. The schema must run identically in standard Python `sqlite3` and mobile browser `sqlite3.wasm`.

Captures all domain attributes currently parsed from `PCE Testsheet` and `PCE VI`:
1. `inspections`: `id`, `project_key`, `station`, `pe_num`, `substation_name`, `inspection_date`, `po_number`, `voltage_rating`, `status`, `tester_name`, `tnb_rep_name`, timestamps.
2. `switchgear_spec`: switchgear type (VCB/GIS/RMU), model, serial_number, mfg_year, rated_current, breaking_capacity, gas_pressure.
3. `switchgear_panels`: panel order, panel_name, feeder_id, panel_type, breaker_serial.
4. `switchgear_readings`: contact resistance, insulation resistance (incoming/outgoing), UltraTEV readings (background, max, level, classification).
5. `transformer_records`: TX serial, rating, oil temp, winding temp, condition.
6. `feeder_pillar_records`: FP type, fuse ratings, condition status.
7. `visual_checklist_items`: item code, category, description, status (Pass/Fail/NA), remarks.
8. `defect_records`: technology (IR/US/TEV/VI), description, severity, status.
9. `calibration_equipment`: instrument type, serial, calibration date, expiry.

**Blocked by:** None (Frontier)

**Status:** Open

## Acceptance Criteria
- [ ] Create `src/db/schema.sql` containing the DDL with proper primary keys, foreign keys, and indexes.
- [ ] Ensure SQLite compatibility (no vendor-specific types, valid for SQLite 3.40+).
- [ ] Add migration versioning support (`PRAGMA user_version = 1`).
- [ ] Add unit test verifying schema executes cleanly against an in-memory SQLite database.
