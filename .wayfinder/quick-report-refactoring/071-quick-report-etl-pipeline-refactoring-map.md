# Map 071: Quick Report 7-Part ETL Pipeline Refactoring Map

Labels: wayfinder:map

## Destination

Enforce `docs/etl_pipeline_refactoring_methodology.md` on `src/quick_report/`, completely decoupling the 7 parts of Quick Report document generation into explicit, single-responsibility domain modules (`front_page.py`, `cbm_summary.py`, `vi_summary.py`, `cbm_defect_pages.py`, `substation_condition.py`, `vi_defect_pages.py`, `sticker_page.py`) assembled by `composer.py`, with clean seams, zero silent fallbacks, and fast unit test coverage.

## Notes

- **Target Domain**: `src/quick_report/`
- **Parts breakdown**:
  1. Part 1: `front_page.py`
  2. Part 2: `cbm_summary.py`
  3. Part 3: `vi_summary.py`
  4. Part 4: `cbm_defect_pages.py`
  5. Part 5: `substation_condition.py`
  6. Part 6: `vi_defect_pages.py`
  7. Part 7: `sticker_page.py`
  8. Composer: `composer.py`
- **Methodology**: `docs/etl_pipeline_refactoring_methodology.md`
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/grilling`, `/tdd`

## Decisions so far

- [Ticket 072: Quick Report 7-Part Architecture & Stage Seams](file:///.issues/072-quick-report-7part-architecture-and-stage-seams.md) — Defined 7-part file breakdown + composer, strict ENGR `QR03 CBA` and `QR03 VI` sheet validation (fail fast `RuntimeError`), verbose date normalizers, and pure context builder seams.
- [Ticket 073: Refactor Part 1 - Front Page Generator](file:///.issues/073-refactor-part1-front-page-generator.md) — Isolated Part 1 into `src/quick_report/front_page.py` with pure context preparation and template rendering.
- [Ticket 074: Refactor Part 2 - CBM Tech Summary Generator](file:///.issues/074-refactor-part2-cbm-tech-summary-generator.md) — Isolated Part 2 into `src/quick_report/cbm_summary.py` with pure defect pairing and table rendering.
- [Ticket 075: Refactor Part 3 - VI Defect Summary Generator](file:///.issues/075-refactor-part3-vi-defect-summary-generator.md) — Isolated Part 3 into `src/quick_report/vi_summary.py` with strongly-typed row structures and template rendering.
- [Ticket 076: Refactor Part 4 - CBM Defect Detail Pages Generator](file:///.issues/076-refactor-part4-cbm-defect-pages-generator.md) — Isolated Part 4 into `src/quick_report/cbm_defect_pages.py` using `cbm_family.py` specs and `cbm_render.py` context builders.
- [Ticket 077: Refactor Part 5 - Substation Condition Page Generator](file:///.issues/077-refactor-part5-substation-condition-page-generator.md) — Isolated Part 5 into `src/quick_report/substation_condition.py` with 3-pair chunking, oxml border clearing, paragraph height shrinking, and docxcompose multi-part merging.
- [Ticket 078: Refactor Part 6 - VI Defect Detail Pages Generator](file:///.issues/078-refactor-part6-vi-defect-pages-generator.md) — Isolated Part 6 into `src/quick_report/vi_defect_pages.py` with 6-slot pagination and border stripping.
- [Ticket 079: Refactor Part 7 - Sticker Page Generator](file:///.issues/079-refactor-part7-sticker-page-generator.md) — Isolated Part 7 into `src/quick_report/sticker_page.py` with pure context preparation.
- [Ticket 080: Refactor Part 8 - Quick Report Document Composer & Merger](file:///.issues/080-refactor-part8-quick-report-document-composer.md) — Implemented `src/quick_report/composer.py` orchestrating Parts 1-7 sequentially and merging into final document via Word COM with retry and table cell escaping.

## Open Tickets (Frontier)

None (All tickets 072-080 completed and verified).

## Not yet specified

- Automated visual regression testing for generated DOCX layout pages.

## Out of scope

- Direct alteration of template `.docx` files in `templates/`.
