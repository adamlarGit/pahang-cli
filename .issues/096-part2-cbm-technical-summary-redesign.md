# Ticket 096: Part 2 CBM Technical Summary Table Redesign

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed
Blocks: [Ticket 097](file:///.issues/097-part4-cbm-defect-pages-and-context-builders.md)
Blocked-by: [Ticket 095](file:///.issues/095-equipment-taxonomy-and-multitech-planner.md)

## Question

How should `src/quick_report/cbm_summary.py` generate the 7-column Part 2 CBM Technical Summary Table with single IR temperature column, unit suffixes (`°C`, `dB`), `"-"` fallbacks, and US defect characteristics (`CORONA`, `TRACKING`, `ARCING`) for `SEVERITY`?

## Scope

- Rewrite `prepare_tech_summary_rows` in `cbm_summary.py` to match the agreed 7-column schema.
- Wire `item.ir_abs`, `item.us_dB`, `item.tev_dB`, and `item.status` / `item.severity`.
- Fast unit test coverage for table rendering across single and multi-technology defects.

## Resolution

- Redesigned `prepare_tech_summary_rows` in `cbm_summary.py` to produce 7-column schema with `ir_abs` (`°C`), `ir_delta` (`"-"`), `us_dB` (`dB`), `tev_dB` (`dB`), and US characteristic `severity`/`status`.
- Updated `CbmSummaryRow` in `models.py`.
- Added unit tests in `tests/test_quick_report_components.py`.
