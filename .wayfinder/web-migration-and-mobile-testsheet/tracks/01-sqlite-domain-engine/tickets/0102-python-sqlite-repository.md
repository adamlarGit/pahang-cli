<!-- status: open -->
Part of Track 1: .wayfinder/web-migration-and-mobile-testsheet/tracks/01-sqlite-domain-engine/map.md

# 0102: feat(db): python sqlite repository & project storage

**What to build:**
The Python SQLite repository module in `src/db/` managing database connections, transactions, and typed CRUD operations against `<base_path>/pahang_project.db`.

**Blocked by:** 0101

**Status:** Open

## Acceptance Criteria
- [ ] Implement `InspectionRepository` in `src/db/repository.py` backed by Python standard library `sqlite3`.
- [ ] Integrate with `ProjectEnvironment.storage`: automatically resolve and create `<base_path>/pahang_project.db` on initial access.
- [ ] Implement typed domain dataclasses / models in `src/db/models.py` matching the schema tables.
- [ ] Implement query methods: `get_inspection(id)`, `find_inspections(station, date)`, `list_inspections(limit, offset)`, `upsert_inspection(record)`.
- [ ] Add automated tests in `tests/db/test_repository.py` verifying transactions, constraints, and data integrity.
