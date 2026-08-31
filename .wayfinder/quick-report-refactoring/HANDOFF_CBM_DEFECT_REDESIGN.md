# Handoff: CBM Defect and CBM Defect Summary Quick Report Redesign

## Goal
Redesign and strengthen end-to-end extraction, transformation, and rendering for CBM defects and the CBM tech summary page in Quick Report generation (`src/quick_report/`).

## Context and Files
- Wayfinder Map: `.wayfinder/quick-report-refactoring/071-quick-report-etl-pipeline-refactoring-map.md`
- Interactive Architecture Visualization: `.wayfinder/quick-report-refactoring/cbm_e2e_dataflow.html`
- Source Data: Master ENGR workbook sheet `QR03 CBA` in `PYTHON/ENGR FROM DRIVE/ENGR-*.xlsx`
- Core Modules:
  - `src/quick_report/defects.py`: `MasterQr03DefectRepository` and `CbmDefectRecord`
  - `src/quick_report/transformer.py`: `QuickReportTransformer` and suffix calculation
  - `src/quick_report/cbm_family.py`: `QUICK_REPORT_FAMILY_SPECS` and equipment categorization
  - `src/quick_report/cbm_defect_planner.py`: `CbmDefectPlanner` (overview and detail card grouping)
  - `src/quick_report/cbm_summary.py`: Part 2 CBM Tech Summary page generation
  - `src/quick_report/cbm_defect_pages.py`: Part 4 CBM Defect Detail pages generation
  - `src/quick_report/cbm_render.py`: Jinja context builders (`swg.*`, `tx.*`, `fp.*`, `panel.*`)
  - `src/quick_report/composer.py`: Multi-part orchestrator and Word COM document compilation

## Current Decisions and Agreed Scope
1. Photo discovery and image embedding (`_find_dg_photo`, `_find_ir_photo`, `_find_us_photo` in `utils.py`): Keep as stubbed for now.
2. Dedicated `IR+US` templates: Work in progress, keep as known gap for now.
3. Priority focus: Redesign how end-to-end CBM defect data gets extracted, transformed, and parsed into the output document.

## 5 Processes to Work Through
1. Process 1: Ingestion and Extraction (`src/quick_report/defects.py`)
   - Raw column parsing from `QR03 CBA`.
   - Functional Location normalization and row filtering.
   - Clean data contracts on `CbmDefectRecord`.

2. Process 2: Equipment Taxonomy and Planning (`src/quick_report/cbm_family.py`, `src/quick_report/cbm_defect_planner.py`)
   - Fix rigid string matching in `QUICK_REPORT_FAMILY_SPECS`.
   - Handle freeform equipment entries (e.g. `SWITCHGEAR`, `TRANSFORMER`, `FP` instead of exact `RMU SF6`, `LVDB`, `LTX/DTX`).
   - Grouping logic for overview cards versus detail cards.

3. Process 3: Part 2 CBM Tech Summary Page (`src/quick_report/cbm_summary.py`)
   - Pairing multi-technology readings (`IR`, `US`, `TEV`) for the same defect area.
   - Calculating temperature differences against ambient temperature.
   - Replacing hardcoded `status = "MAJOR"` and `ir_delta = "-"` with explicit classification rules.

4. Process 4: Part 4 CBM Defect Detail Pages (`src/quick_report/cbm_defect_pages.py`, `src/quick_report/cbm_render.py`)
   - Jinja context building for each equipment family.
   - Preserving missing values cleanly without template errors.

5. Process 5: Loader Stage and Word COM Assembly (`src/quick_report/composer.py`)
   - Part naming conventions in `temp_parts/` to resolve prefix collisions.
   - Clean document stitching and COM process reliability.

## Instructions for the New Session
1. Review the interactive flow in `.wayfinder/quick-report-refactoring/cbm_e2e_dataflow.html`.
2. Do not run any codebase changes without explicit operator confirmation.
3. Ask the operator which of the 5 processes to pick first, or present the concrete options to begin.
