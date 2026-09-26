<!-- status: open -->
Part of Track 5: .wayfinder/web-migration-and-mobile-testsheet/tracks/05-desktop-dashboard-and-media/map.md

# 0502: feat(web): workflow card dashboard & live execution modal

**What to build:**
The primary desktop web dashboard replacing the terminal CLI:
- Project Top Bar: displays active project key, state, PO number, voltage type, and project switcher modal.
- Workflow Cards:
  - Generate Testsheet Folders.
  - Quick Report Generation (with interactive multi-date checklist and PRPD mode toggle).
  - Full Report Generation (with substation review checklist and COM status).
  - Update QR02 CBA.
  - WhatsApp Report Generator.
- Utility Action Panel: PDF separator merger, signature replacement.
- Live Task Execution Modal: shows SSE streaming logs, animated progress bar, and elapsed timer.

**Blocked by:** 0501, Track 2

**Status:** Open

## Acceptance Criteria
- [ ] Build desktop frontend dashboard with responsive card layout.
- [ ] Interactive station/month/date selectors powered by backend APIs.
- [ ] Real-time progress modal hooked up to SSE stream.
- [ ] Settings modal for camera config and PRPD style.
- [ ] Verified on Chrome and Edge.
