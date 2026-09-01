# Map 092: CBM Defect and Summary Redesign Map

Labels: wayfinder:map

## Destination

Re-architect and implement the end-to-end CBM defect extraction, multi-technology planning, summary rendering, and detail rendering pipeline in `src/quick_report/` (`defects.py`, `cbm_family.py`, `cbm_defect_planner.py`, `cbm_summary.py`, `cbm_defect_pages.py`, `cbm_render.py`, `composer.py`), ensuring complete fidelity with real ENGR workbooks, multi-tech project configuration, testsheet bay matching, clean Word COM assembly, and complete post-refactoring codebase hygiene / dead code removal.

## Notes

- **Target Domain**: `src/quick_report/`, `src/project/`
- **Methodology**: `docs/etl_pipeline_refactoring_methodology.md`
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/grilling`, `/tdd`, `/code-review`

## Decisions so far

- [Ticket 093: Dynamic Multi-Technology Template Resolution & Project Environment Integration](file:///.issues/093-dynamic-multi-technology-template-resolution.md) — Dynamically resolve `DEFECT IR`, `DEFECT IR US`, `DEFECT IR US TEV` based on `ProjectMetadata.technologies` with fail-fast `FileNotFoundError` semantics.
- [Ticket 094: CBM Defect Record Ingestion & Extraction Alignment](file:///.issues/094-cbm-defect-record-ingestion-alignment.md) — Aligned `CbmDefectRecord` dataclass and repository to explicitly capture `equipment_id`, `criticality`, `us_char`, `tev_char`, and exact measurements from `QR03 CBA`.
- [Ticket 095: Equipment Taxonomy Aliasing & Multi-Tech Defect Planner](file:///.issues/095-equipment-taxonomy-and-multitech-planner.md) — Canonical aliasing for 5 core families with multi-tech support, grouping by `item_key`, merging by `(item_key, defect_area)`, and smart routing for TX HV/LV sides.
- [Ticket 096: Part 2 CBM Technical Summary Table Redesign](file:///.issues/096-part2-cbm-technical-summary-redesign.md) — 7-column Part 2 CBM Technical Summary table with single IR temp column, unit formatting (`°C`, `dB`), and US characteristic `SEVERITY`.
- [Ticket 097: Part 4 CBM Defect Detail Pages & Namespace Context Builders](file:///.issues/097-part4-cbm-defect-pages-and-context-builders.md) — Clean context builders for all 5 families with testsheet bay matching, verbatim `f"{defect_area}/ {additional_remarks}"` formatting, and clean `"-"` fallbacks with zero raw Jinja leaks.
- [Ticket 098: Loader Stage Part Ordering & End-to-End Test Verification](file:///.issues/098-loader-stage-ordering-and-verification.md) — Strictly indexed 2-digit prefixes in `temp_parts/` (`001_01_` through `001_07_`) with full end-to-end integration and lifecycle verification.
- [Ticket 099: Codebase Hygiene, Dead Code Removal & Unused Stub Cleanup](file:///.issues/099-codebase-hygiene-and-dead-code-cleanup.md) — Complete codebase hygiene, removal of dead helper functions and obsolete template keys, top-level imports cleanup, and clean `/code-review` verification.

## Open Tickets (Frontier)

*(None — all tickets closed)*

## Not yet specified

- Visual image embedding & photo discovery when photo directories are wired.

## Out of scope

- Direct alteration of master templates in `templates/` other than user-managed additions.
