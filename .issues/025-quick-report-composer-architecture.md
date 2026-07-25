# Quick Report Composer Architecture and Template Engine

Labels: wayfinder:grilling
Assignee: antigravity
Status: Closed
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)

## Question

How should `src/quick_report/composer.py` (`QuickReportComposer`), `render.py`, `specs.py`, and `utils.py` be structured to orchestrate the 7-part docx document assembly sequence (`docxcompose.Composer`), front page technology selection (`IR`, `IR+US`, `IR+US+TEV`), `PreservingUndefined` Jinja rendering, and canonical defect status suffix calculation `(IR+US+TEV+VI)` without date strings in filenames?

## Resolution

The architecture and template engine for `src/quick_report/` is specified as follows:

1. **Module Decomposition (Deep Module Facade)**:
   - `src/quick_report/__init__.py`: Public package facade exporting `QuickReportComposer`.
   - `src/quick_report/composer.py`: Main orchestrator class `QuickReportComposer` managing the 7-part assembly sequence via `docxcompose.Composer`, dynamic suffix calculation `(IR+US+TEV+VI)`, front page technology mapping, output filename formatting, and temporary sub-document cleanup.
   - `src/quick_report/cbm_family.py`: Declarative specs (`QUICK_REPORT_FAMILY_SPECS`) matching defects to 5 equipment families (`fp_lvdb`, `swg`, `tx`, `blackbox`, `battery`) and overview/detail role matching.
   - `src/quick_report/cbm_render.py`: Context builders for CBM Technical Summary tables (1-to-1 IR/US pairing) and CBM detail pages.
   - `src/quick_report/visual_render.py`: Context builders for VI Summary tables, 6-card defect pages, and empty cell border cleanup.
   - `src/quick_report/utils.py`: Shared helper utilities for FL normalization, filename sanitization, and job sorting.

2. **7-Part Document Assembly Sequence**:
   - **Part 1 (Front Page)**: Always rendered. Template chosen by substation technology rating (`IR`, `IR+US`, `IR+US+TEV`).
   - **Part 2A (CBM Tech Summary)**: Rendered conditionally if CBM defects exist.
   - **Part 2 (VI Defect Summary)**: Rendered conditionally if VI defects exist.
   - **Part 2B (CBM Defect Family Pages)**: Rendered conditionally if CBM defects exist.
   - **Part 5 (Substation Condition Page)**: Always rendered using selected condition template.
   - **Part 6 (VI Defect Pages)**: Rendered conditionally if VI defects exist (max 6 cards per page).
   - **Part 7 (Sticker Page)**: Mandatory, always rendered as the final section (`11. STICKER PAGE.docx`).

3. **Pahang Naming Rule & Suffix Calculation**:
   - Output filename pattern: `{pe_number:03d}. {sanitized_name_erms}{suffix}.docx` (omits `<DDMMYYYY>` date string).
   - Suffix calculated in canonical order `(IR+US+TEV+VI)` based on active defects.

