# Map 061: Quick Report Engine Unstubbing & Photo Integration Map

Labels: wayfinder:map

## Destination

Fully unstub the Quick Report Generation engine in `src/quick_report/`, implementing dynamic substation condition equipment pair extraction, real QR03/testsheet CBA & VI defect data fetching, raw IR/DG/US/TEV photo discovery and range matching from `RAW MATERIAL/`, cell-constrained `InlineImage` embedding, and resilient multi-station batch compilation in `pahang-cli`.

## Notes

- **Target Domain**: `src/quick_report/` (`composer.py`, `utils.py`, `cbm_render.py`, `visual_render.py`, `cbm_family.py`)
- **Dependencies**: `src/testsheet/` (`models.py`, `extractor.py`), `src/master/` (`qr02.py`)
- **Photo Source Structure**: `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/` (`IR/`, `DG/`, `US+TEV/`)
- **Canonical Suffix**: `(IR+US+TEV+VI)`
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/research`, `/grilling`

## Decisions so far

- [Ticket 062: Substation Condition Equipment Extraction & Pair Building Engine](file:///.issues/062-substation-condition-equipment-extraction.md) — Implemented dynamic 2-column equipment pair extraction in `QuickReportComposer._build_substation_condition_pairs(pkg)` in `src/quick_report/composer.py`, dynamically populating canonical pair sequence based on substation package metadata.
- [Ticket 063: CBA & VI Defect Data Extraction & Suffix Calculation](file:///.issues/063-cba-vi-defect-extraction-and-suffix.md) — Implemented `MasterQr03DefectRepository` in `src/quick_report/defects.py` to extract CBM and VI defects from master Excel workbooks (`QR03 CBA.xlsx` and `QR03 VI.xlsx`), wired into `QuickReportComposer._process_station()`, driving dynamic canonical suffix `(IR+US+TEV+VI)` and page composition.
- [Ticket 067: Quick Report Batch Execution Summary & Failure Reporting UI](file:///.issues/067-batch-execution-summary-and-failure-reporting-ui.md) — Implemented `_print_quick_report_batch_summary` in `src/project_workflow_actions.py` to output a formatted CLI box with totals (Processed, Succeeded, Failed, Warnings), output file links, and concise 1-line failure messages.

## Open Tickets (Frontier)

- [Ticket 064: Raw Photo Discovery & Numerical Range Matching (IR, DG, US, TEV)](file:///.issues/064-photo-discovery-and-range-matching.md) — Unblocked (Stubbed / Deferred)
- [Ticket 065: Photo Resizing, InlineImage Binding & Fallback Placeholders](file:///.issues/065-photo-resizing-and-inline-image-binding.md) — Blocked by Ticket 064
- [Ticket 066: Quick Report Composer Integration & End-to-End Verification](file:///.issues/066-quick-report-composer-integration-and-verification.md) — Blocked by Tickets 065

## Not yet specified

- Direct PDF conversion pipeline for compiled Quick Report DOCX output.

## Out of scope

- Direct modification of master ENGR files (handled by Update QR02 CBA workflow).
- Hardcoded date strings in Quick Report file stems (`<DDMMYYYY>`).
