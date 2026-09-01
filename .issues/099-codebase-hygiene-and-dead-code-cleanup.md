# Ticket 099: Codebase Hygiene, Dead Code Removal & Unused Stub Cleanup

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed
Blocked-by: [Ticket 098](file:///.issues/098-loader-stage-ordering-and-verification.md)

## Question

How should obsolete/dead helper functions, legacy hardcoded fallback branches, unused imports, and redundant data structures across `src/quick_report/` and `src/project/` be identified and cleaned up after the CBM defect refactoring?

## Scope

- Audit all modules in `src/quick_report/` (`defects.py`, `cbm_family.py`, `cbm_defect_planner.py`, `cbm_summary.py`, `cbm_defect_pages.py`, `cbm_render.py`, `composer.py`, `utils.py`, `models.py`) for dead code, unused helpers, and obsolete legacy structures.
- Remove orphaned code while keeping interfaces clean and test suite passing at 100%.
- Ensure complete codebase hygiene without regressions.

## Resolution

- Purged dead functions (`sort_quick_report_detail_jobs`, `format_table_cell`, `_find_*_photo`) in `src/quick_report/utils.py` and `_placeholder_literal` in `src/quick_report/cbm_render.py`.
- Removed obsolete keys from `config.py` (`cbm_summary`, `cbm_defect`).
- Cleaned up mid-file imports across `extractor.py`, `filter.py`, `storage.py`, and `environment.py`.
- Conducted `/code-review` verifying standards and spec compliance (PASS Clean with 0 issues).
