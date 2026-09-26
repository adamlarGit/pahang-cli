<!-- status: open -->
Part of Track 1: .wayfinder/web-migration-and-mobile-testsheet/tracks/01-sqlite-domain-engine/map.md

# 0103: feat(db): sqlite attach database merge service

**What to build:**
A dedicated database merge service (`DatabaseMergeService`) that imports field inspection SQLite databases (exported from mobile PWAs) into the desktop project database using SQLite's native `ATTACH DATABASE` capability.

**Blocked by:** 0101, 0102

**Status:** Open

## Acceptance Criteria
- [ ] Implement `DatabaseMergeService` in `src/db/merger.py`.
- [ ] Validate uploaded database integrity (`PRAGMA quick_check` and schema version check).
- [ ] Execute atomic merge via `ATTACH DATABASE '<uploaded_path>' AS mobile`:
  - `INSERT OR REPLACE INTO main.inspections SELECT * FROM mobile.inspections;`
  - Upsert child tables (`switchgear_panels`, `readings`, `defects`, etc.).
  - Execute within a single transaction and `DETACH DATABASE mobile`.
- [ ] Return structured `MergeResult` reporting total inspections imported, updated, and warnings.
- [ ] Add integration tests with mock mobile database files in `tests/db/test_merger.py`.
