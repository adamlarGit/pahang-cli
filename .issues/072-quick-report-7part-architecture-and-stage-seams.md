# Ticket 072: Quick Report 7-Part Architecture & Stage Seams

Labels: wayfinder:grilling
Status: Closed
Parent: [Map 071: Quick Report 7-Part ETL Pipeline Refactoring Map](file:///.issues/071-quick-report-etl-pipeline-refactoring-map.md)

## Question

How should the 6 ETL pipeline stages (`PreflightGuard`, `Extractor`, `Filter`, `Transformer`, `Loader`, `Auditor`) defined in `docs/etl_pipeline_refactoring_methodology.md` be mapped across the 7 dedicated rendering parts of Quick Report generation in `src/quick_report/`?

## Resolution

Achieved full shared understanding on the 7-part architecture and methodology enforcement:

### 1. File Structure (7 Parts + Composer)
- **Part 1**: `src/quick_report/front_page.py` (`generate_front_page`)
- **Part 2**: `src/quick_report/cbm_summary.py` (`generate_cbm_tech_summary`)
- **Part 3**: `src/quick_report/vi_summary.py` (`generate_vi_summary`)
- **Part 4**: `src/quick_report/cbm_defect_pages.py` (`generate_cbm_defect_pages`)
- **Part 5**: `src/quick_report/substation_condition.py` (`generate_substation_condition_pages`)
- **Part 6**: `src/quick_report/vi_defect_pages.py` (`generate_vi_defect_pages`)
- **Part 7**: `src/quick_report/sticker_page.py` (`generate_sticker_page`)
- **Part 8 / Composer Engine**: `src/quick_report/composer.py` (`QuickReportComposer` orchestrating Parts 1-7 and `docxcompose` document merging)

### 2. Master Excel Sheet Validation Contract
- Master workbook is the **ENGR file**.
- `QR03 CBA` and `QR03 VI` are sheet names inside the ENGR workbook.
- **Strict Rule**: Raise explicit `RuntimeError` immediately if `QR03 CBA` or `QR03 VI` sheets are missing. No silent fallbacks to `wb.active` or empty dataframes.

### 3. Verbose Domain Normalizers
- Normalizer functions in `src/core/normalizers.py` must have explicit, verbose names distinguishing domain-specific formatting (e.g. `format_front_page_date_str()` vs `format_cbm_defect_page_date_str()`) to eliminate cross-workflow confusion.

### 4. Pure Seam Context Builders & Fast Unit Testing
- Each part module decouples pure data context preparation (`build_[part]_context(...)`) from Word document rendering (`generate_[part](...)`).
- Component unit tests written in `tests/test_quick_report_components.py` for fast, in-memory validation without Word/Excel I/O.


Resolution: Refactored and implemented successfully.
