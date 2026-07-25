# Map: Quick Report Generation for Pahang

Labels: wayfinder:map

## Destination

Implement and verify the end-to-end Quick Report Generation engine in `pahang-cli` (`src/quick_report/`), including testsheet data extraction, docx template binding (`docxtpl` & `docxcompose`), IR/DG photo range matching, defect suffix calculation, and CLI integration (`QuickReportAction`) operating across Pahang's workstation directory structure (`TESTSHEET/`, `RAW MATERIAL/`, `QUICK REPORT/`).

## Notes

- **Baseline Codebase**: Johor implementation in `PO 42234207 - JOHOR - JBU - 400 PE IR US TEV/src/report_composer/`
- **Pahang Trial References**: `C:\Users\ADAM\Desktop\tnb\src\` (`quick_report_workflow.py`, `quick_report_render.py`, `quick_report_specs.py`, `quick_report_utils.py`)
- **Core Module Location**: `src/quick_report/composer.py` (`QuickReportComposer`), `src/quick_report/render.py`, `src/quick_report/specs.py`, `src/quick_report/utils.py`
- **Front Page Selection**: Determined strictly by substation technology rating (`IR` vs `IR+US` vs `IR+US+TEV`), not defect findings.
- **Output Filename**: Omits date string (`{pe_number:03d}. {name_erms} {suffix}.docx`).
- **Defect Suffix**: Canonical order `(IR+US+TEV+VI)`.
- **Undefined Handling**: Uses `PreservingUndefined` to preserve unpopulated Jinja tags (`{{ placeholder }}`) and convert empty values to `"-"`.
- **Skills**: `/codebase-design`, `/domain-modeling`, `/research`, `/grilling`

## Decisions so far

- [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md) — Specified 6-module structure (`__init__.py`, `composer.py`, `cbm_family.py`, `cbm_render.py`, `visual_render.py`, `utils.py`), 7-part docx assembly sequence with mandatory Sticker Page, canonical suffix `(IR+US+TEV+VI)`, and date-omitting output filename `{pe_number:03d}. {name_erms}{suffix}.docx`.

## Not yet specified

- Batch generation error recovery and partial failure reporting across multi-station runs.
- PDF export or conversion options (if required in future scope).

## Out of scope

- Direct modification of master ENGR files (handled by Update QR02 CBA workflow).
- Hardcoded 8-digit date strings in Quick Report output file stems (`<DDMMYYYY>`).
