<!-- status: open -->
Part of Track 3: .wayfinder/web-migration-and-mobile-testsheet/tracks/03-mobile-offline-pwa/map.md

# 0301: feat(pwa): sqlite wasm + opfs storage layer

**What to build:**
The offline storage and PWA foundation for the mobile inspection app:
1. PWA Manifest and Service Worker providing 100% offline asset caching.
2. Web Worker running official `@sqlite.org/sqlite-wasm` storing the database inside the browser Origin Private File System (OPFS).
3. Schema initialization running Track 1 `schema.sql` on startup if tables do not exist.

**Blocked by:** Track 1 (0101)

**Status:** Open

## Acceptance Criteria
- [ ] Set up mobile webapp root in `src/mobile_pwa/` (or dedicated static bundle).
- [ ] Configure `manifest.json` and service worker with offline cache strategy.
- [ ] Initialize SQLite Wasm worker using OPFS VFS.
- [ ] Verify database persists data across tab closes and device restarts.
- [ ] Test offline behavior in Chrome (Android) and Safari (iOS 17+).
