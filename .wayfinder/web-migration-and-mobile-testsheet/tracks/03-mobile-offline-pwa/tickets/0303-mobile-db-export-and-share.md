<!-- status: open -->
Part of Track 3: .wayfinder/web-migration-and-mobile-testsheet/tracks/03-mobile-offline-pwa/map.md

# 0303: feat(pwa): database export & web share integration

**What to build:**
Export and sharing mechanism on mobile:
1. "Export Database" action that reads the SQLite file from OPFS into a downloadable/shareable binary `.db` blob.
2. Integration with `navigator.share({ files: [dbBlob] })` enabling immediate sharing via WhatsApp, AirDrop, or Telegram directly from the mobile browser.
3. Fallback direct browser download for devices where the Web Share API is unavailable.
4. Inspection history list showing draft, completed, and exported inspection records.

**Blocked by:** 0301, 0302

**Status:** Open

## Acceptance Criteria
- [ ] Implement OPFS file reader exporting `.db` binary payload.
- [ ] Connect Web Share API for iOS Safari and Android Chrome.
- [ ] Implement fallback file download `<a download="inspection.db">`.
- [ ] Add inspection status dashboard in the PWA listing stored inspections with export status badges.
- [ ] Verify exported `.db` file opens cleanly in standard desktop `sqlite3`.
