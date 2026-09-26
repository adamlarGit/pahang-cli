# Track 1 Sub-Map: SQLite Domain Engine (Foundation)

Part of [Master Program Map](../../map.md)

---

## Destination

Establish the authoritative SQLite database layer used across both the Python desktop application and the mobile Wasm PWA. Delivers the unified relational schema capturing all substation inspection data, the Python repository for local project databases (`<base_path>/pahang_project.db`), and the `ATTACH DATABASE` merge engine that imports field inspection files into the main project database.

---

## Notes

- **Dual-Target DDL**: The SQL schema defined here must execute without modification in standard Python `sqlite3` and mobile browser `sqlite3.wasm`.
- **Project Scope**: The active database file is stored at `<base_path>/pahang_project.db` managed by `ProjectEnvironment`.
- **Relevant Skills**: `tdd`, `codebase-design`.

---

## Work Breakdown

```mermaid
graph TD
    T0101["0101: feat(db): canonical sql schema & dual-target ddl"]
    T0102["0102: feat(db): python sqlite repository & project storage"]
    T0103["0103: feat(db): sqlite attach database merge service"]

    T0101 --> T0102
    T0101 --> T0103
    T0102 --> T0103
```

---

## Tickets

### 0101: feat(db): canonical sql schema & dual-target ddl
- **Status**: Open (Frontier)
- **Ticket File**: [tickets/0101-canonical-sql-schema-and-ddl.md](./tickets/0101-canonical-sql-schema-and-ddl.md)
- **Delivers**: `schema.sql` defining relational tables for `inspections`, `switchgear_panels`, `panel_readings`, `transformers`, `feeder_pillars`, `visual_items`, `defects`, and `equipment_calibrations`. Tested against SQLite 3.40+.

### 0102: feat(db): python sqlite repository & project storage
- **Status**: Open
- **Blocked by**: 0101
- **Ticket File**: [tickets/0102-python-sqlite-repository.md](./tickets/0102-python-sqlite-repository.md)
- **Delivers**: `InspectionRepository` in `src/db/repository.py` managing connections, transactions, CRUD operations, and automatic table creation inside `<base_path>/pahang_project.db`.

### 0103: feat(db): sqlite attach database merge service
- **Status**: Open
- **Blocked by**: 0101, 0102
- **Ticket File**: [tickets/0103-sqlite-attach-database-merger.md](./tickets/0103-sqlite-attach-database-merger.md)
- **Delivers**: `DatabaseMergeService` that executes `ATTACH DATABASE` on an uploaded mobile `.db` file, merges inspection records into the main project database, and detects conflicts.
