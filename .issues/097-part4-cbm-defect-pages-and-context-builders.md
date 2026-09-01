# Ticket 097: Part 4 CBM Defect Detail Pages & Namespace Context Builders

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed
Blocks: [Ticket 098](file:///.issues/098-loader-stage-ordering-and-verification.md)
Blocked-by: [Ticket 096](file:///.issues/096-part2-cbm-technical-summary-redesign.md)

## Question

How should `src/quick_report/cbm_defect_pages.py` and `src/quick_report/cbm_render.py` build clean namespaces for `swg.*`, `panel.*`, `tx.*`, `fp.*`, `batt.*`, `bbox.*`, integrating testsheet operational values and ensuring unresolved placeholders render as clean `"-"` without raw Jinja tag leaks?

## Scope

- Build context builders for SWG, TX, FP/LVDB, Battery, and Black Box per agreed field mappings.
- Fix dictionary pruning so missing/empty values render as `"-"` instead of raw `{{ undefined }}` tags.
- Verbatim `f"{defect_area}/ {additional_remarks}"` formatting.
- Unit tests for all 5 family context builders and page plan generation.

## Resolution

- Built context builders for all 5 families in `cbm_render.py` with testsheet bay matching and verbatim `f"{defect_area}/ {additional_remarks}"` formatting.
- Fixed `QuickReportContext` and `PreservingUndefined` to render missing/empty placeholders as clean `"-"` without raw Jinja leaks.
- Updated `transformer.py` to expose `pkg.data.equipment` to context builders.
- Added comprehensive unit tests in `tests/test_quick_report_components.py`.
