<!-- status: open -->
Part of Track 5: .wayfinder/web-migration-and-mobile-testsheet/tracks/05-desktop-dashboard-and-media/map.md

# 0501: feat(web): mobile db import & raw media pairing assistant

**What to build:**
A dedicated import and media linking screen on the desktop web interface:
1. File dropzone accepting one or more exported `.db` files from technicians' mobile phones.
2. Invokes Track 1's `DatabaseMergeService` using `ATTACH DATABASE` to import the records into `<base_path>/pahang_project.db`.
3. Media pairing assistant: scans `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/` where SD cards were dumped, detects photo bounds (`PhotoRange`), and links IR/DG photo sets and UltraTEV archives to the imported inspection records.

**Blocked by:** Tracks 1, 3, 4

**Status:** Open

## Acceptance Criteria
- [ ] Build drag-and-drop file upload UI.
- [ ] Connect upload endpoint to `DatabaseMergeService`.
- [ ] Scan and display discovered raw photo ranges and UltraTEV archives.
- [ ] Display visual confirmation matrix of matched substations and photos before locking.
- [ ] Integration tests in `tests/web/test_media_import.py`.
