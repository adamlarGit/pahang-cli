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
  - Compare `updated_at` timestamps per substation inspection `(project_key, station, pe_num, inspection_date)`.
  - For newer incoming inspections, execute clean-child deletion on existing child records (`switchgear_panels`, `readings`, `defects`, etc.) in `main` to prevent ghost records (`D-MASTER.17`).
  - Insert or replace inspection header and re-insert child tables from `mobile`.
  - Execute within a single transaction and `DETACH DATABASE mobile`.
- [ ] Return structured `MergeResult` reporting total inspections imported, updated, conflicts resolved, and warnings.
- [ ] Add integration tests with mock mobile database files in `tests/db/test_merger.py` verifying ghost-row elimination on child deletions.
