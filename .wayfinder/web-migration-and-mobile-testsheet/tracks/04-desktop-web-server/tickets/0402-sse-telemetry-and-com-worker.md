<!-- status: open -->
Part of Track 4: .wayfinder/web-migration-and-mobile-testsheet/tracks/04-desktop-web-server/map.md

# 0402: feat(web): sse telemetry stream & com worker thread

**What to build:**
Real-time telemetry and COM thread isolation for background jobs:
1. Server-Sent Events (SSE) route `/api/events` broadcasting task progress, percent complete, step names, and warnings to connected browser clients.
2. Background task executor running long batch workflows on a dedicated thread initialized with `pythoncom.CoInitialize()` and cleaned up with `pythoncom.CoUninitialize()` to prevent Windows COM apartment threading failures.

**Blocked by:** 0401

**Status:** Open

## Acceptance Criteria
- [ ] Implement SSE event generator streaming messages produced by `progress_sink`.
- [ ] Implement `ComTaskRunner` handling COM initialization/uninitialization safely per task.
- [ ] Gracefully handle client disconnection without killing the background job.
- [ ] Add integration test verifying SSE output format against mock workflow runs.
