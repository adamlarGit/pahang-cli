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
- [ ] Set up mobile webapp root in `web/pwa/` as a 100% static bundle.
- [ ] Configure `manifest.json` and service worker (`sw.js`) with offline cache-first strategy.
- [ ] Deploy static bundle to GitHub Pages over HTTPS with required COOP/COEP headers (`D-MASTER.16`).
- [ ] Initialize SQLite Wasm worker using OPFS VFS (`navigator.storage.getDirectory()`).
- [ ] Verify database persists data across tab closes, app terminations, and device restarts.
- [ ] Verify 'Add to Home Screen' standalone launch and offline operation on Android Chrome and iOS Safari 17+.
