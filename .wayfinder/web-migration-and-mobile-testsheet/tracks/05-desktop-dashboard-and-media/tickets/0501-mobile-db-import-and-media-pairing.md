<!-- status: open -->
Part of Track 5: .wayfinder/web-migration-and-mobile-testsheet/tracks/05-desktop-dashboard-and-media/map.md

# 0501: feat(web): mobile db import & raw media pairing assistant

**What to build:**
A dedicated import and media linking screen on the desktop web interface:
1. File dropzone accepting one or more exported `.db` files from technicians' mobile phones.
2. Invokes Track 1's `DatabaseMergeService` using `ATTACH DATABASE` with clean-child replace (`D-MASTER.17`) to import the records into `<base_path>/pahang_project.db`.
3. Media pairing assistant: scans `TESTSHEET/<STATION>/<MONTH>/<DATE>/UNSORTED RAW DATA/` where SD cards were dumped (`D-MASTER.19`), detects photo bounds (`PhotoRange`), displays a visual confirmation matrix, and non-destructively copies matched photo sets into canonical `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<PE>/RAW DATA/` while extracting UltraTEV archives.

**Blocked by:** Tracks 1, 3, 4

**Status:** Open

## Acceptance Criteria
- [ ] Build drag-and-drop file upload UI for mobile `.db` inspection files.
- [ ] Connect upload endpoint to `DatabaseMergeService` (with clean-child merge semantics).
- [ ] Auto-scan `TESTSHEET/<STATION>/<MONTH>/<DATE>/UNSORTED RAW DATA/` for camera photo dumps (`IR/`, `DG/`) and UltraTEV archives (`D-MASTER.19`).
- [ ] Display visual confirmation matrix of matched substations, photo counts, and status badges.
- [ ] Execute non-destructive copy into `RAW MATERIAL/<PE>/RAW DATA/` with idempotent re-sort capability.
- [ ] Integration tests in `tests/web/test_media_import.py`.
