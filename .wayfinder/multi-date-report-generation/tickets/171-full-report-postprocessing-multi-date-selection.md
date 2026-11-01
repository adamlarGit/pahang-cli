<!-- status: closed -->
Part of #66
Specification: [spec.md](../spec.md)

# 171: feat(full-report): multi-date selection for post-processing matching Generate Full Reports

**What to build:** Bring workflow 14 (Post-Process Full Reports) in line with the MultiDateSelectionPolicy that workflow 13 follows. Both stages share one selection prompt (Manual FL / Browse Date Folders / Enter Target Date(s) / Cancel). In 14, Browse maps each ticked `TESTSHEET/<STATION>/<MONTH>/<DATE>/` to the same station's `FULL REPORT` date folder; typed dates match every station that has them; Manual FL looks FLs up in the testsheets and picks up all Parts. Discovery reads only the top level of each date folder, so `_superseded/` is never post-processed. 14's checklist and progress lines carry the date tag, and both preflights warn once per selected date that yields nothing.

**Blocked by:** None

**Status:** Closed

- [x] 13 and 14 show the same selection-mode menu, built from one shared prompt, and 13's existing tests still pass.
- [x] In 14, ticking several dates under one station in Browse processes only that station's Full Reports for those dates.
- [x] In 14, typed dates (single, list, range, combined) match Full Reports across all stations for those dates.
- [x] In 14, Manual FL finds the matching Full Report Parts, including multi-part reports, for every date the FL matches.
- [x] A `.docx` under a date folder's `_superseded/` subfolder is never discovered (regression test).
- [x] 14's checklist entries and progress messages carry the `[DD-MM-YYYY]` date tag.
- [x] 13's and 14's preflights print one warning line for each selected date that yields nothing, and the run continues with the remaining dates.
- [x] Tests are written first (red to green) for each behaviour above.
