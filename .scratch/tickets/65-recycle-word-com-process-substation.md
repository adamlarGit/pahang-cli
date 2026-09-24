<!-- status: closed -->
# 65: perf(lifecycle): recycle Word COM process per substation across batch report workflows

**What to build:**
Recycle the Microsoft Word COM application instance (`word_app`) per substation across batch runs in both `FullReportWorkflow` and `QuickReportWorkflow`. Holding a single `WINWORD.EXE` process alive over a 25+ minute batch with dozens of document opens/closes causes OLE handle degradation, memory bloat, and clipboard fatigue.

Recycling `word_app` per substation resets the COM server state, flushes lingering buffers, and isolates failures, with negligible (~1.5s) overhead per substation.

**Blocked by:** #63

**Status:** closed

- [x] In `src/workflows/full_report.py`, wrap each substation's slicing and compilation inside a fresh per-substation `BatchComSession` (or refresh the session if not provided externally via `com_session`), ensuring that Word COM terminates cleanly and re-spawns between stations.
- [x] In `src/workflows/quick_report.py`, ensure Word COM session recycling occurs cleanly per plan/substation when executing batch runs without an explicit injected session.
- [x] Unit tests verify that Word COM session recycling cleanly executes across multiple mock or headless stations without handle leaks or regressions.
- [x] Full existing test suite passes.
