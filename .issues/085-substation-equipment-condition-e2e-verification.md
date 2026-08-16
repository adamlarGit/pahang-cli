# Ticket 085: Substation Equipment Condition E2E Verification & Test Suite

Labels: wayfinder:task
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](file:///.issues/081-dynamic-substation-equipment-condition-map.md)
Status: Open (Blocked by Ticket 084)

## Question

How can we verify end-to-end that the new equipment extractor and dynamic condition page generator correctly handle all real-world substation types (1 TX PCE, 2 TX PCE, CS Compact Substation, SSU 0 TX Switching Station) without layout or data regression?

## Objectives

1. Add unit tests for `TestsheetExtractor` using real or mock testsheet data across different substation variants (1 TX, 2 TX, SSU, CS).
2. Add unit/integration tests for `_build_substation_condition_pairs()` ensuring correct pair lists generated for each equipment package structure.
3. Test DOCX page generation with `generate_substation_condition_pages()` for arbitrary pair counts (e.g. 5 pairs -> 2 pages, 9 pairs -> 3 pages, 3 pairs -> 1 page) and verify clean cell border removal on incomplete final pages.
4. Execute `pytest` suite to ensure 100% pass rate.
