# Map: Quick Report Generation Workflow (Pahang CLI)

Labels: wayfinder:map

## Destination

Design and specify the deep module architecture, Jinja2/docx template bindings, defect data extraction schemas, photo embedding rules, and service seams for the Quick Report (Visual & CBM Report) Generation workflow in `pahang-cli`.

## Notes

- **Input Data Sources**:
  - Testsheets: `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/*.xlsx` (`PCE Testsheet`, `PCE VI` sheets).
  - Raw Photos: `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/` (`IR/`, `DG/`, `US+TEV/`).
- **Templates**: Located in `templates/QUICK REPORT/`
  - Front Page: `1. FRONT PAGE TEMPLATE IR BOX Jinja2 updated.docx`, `1. FRONT PAGE TEMPLATE IR US TEV BOX Jinja2 updated.docx`
  - Substation Configuration: `templates/QUICK REPORT/SUBSTATION CONFIGURATION/*.docx` (10 configuration templates)
  - VI Summary & Defect: `2. VI SUMMARY TEMPLATE Jinja2.docx`, `10. VISUAL DEFECT Jinja2.docx`
  - CBM Defect Summary: `CBM DEFECT SUMMARY.docx`
- **Output Destination**: `QUICK REPORT/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>).docx`
- **Pahang Naming Rule**: Omits `<DDMMYYYY>` date string from document and folder stems.
- **Domain Context**: [CONTEXT.md](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md)
- **Skills**: `/codebase-design`, `/domain-modeling`, `/research`

## Decisions so far

- [Quick Report Templates and Docxtpl Binding Schema](file:///.issues/020-quick-report-templates-and-docxtpl-binding-schema.md) — Categorized 24 templates in `templates/QUICK REPORT/`; defined Jinja2 schema for metadata, photo bindings, equipment lists, and defect summaries; specified sequential composition using `docxcompose.Composer` with 6-item page chunking.
- [Quick Report Defect Data Extraction and Suffix Lookup](file:///.issues/021-quick-report-defect-data-extraction-and-suffix-lookup.md) — Extract visual defect rows from `QR03 VI` and diagnostic rows from `QR03 CBA`; calculate Pahang `DefectStatusSuffix` in canonical order `(IR+US+TEV+VI)` omitting date string; populate summary tables chunked into 6-item pages.
- [Quick Report Photo Embedding and Layout Rules](file:///.issues/022-quick-report-photo-embedding-and-layout.md) — Range-match IR/DG photos from RAW MATERIAL using `_extract_photo_number`; embed with `docxtpl.InlineImage` passing explicit width (e.g. `width=Mm(120)` front page, `width=Mm(68)` defect table) to auto-preserve aspect ratio; use fallback placeholders for missing photos.


## Not yet specified

- Batch generation error recovery and partial failure reporting across multi-station runs.
- PDF export or conversion options (if required in future scope).

## Out of scope

- Single-folder flat paths without `WorkspaceStorage` resolution.
- Hardcoded date strings in Quick Report file stems (`<DDMMYYYY>`).
- Direct modification of master ENGR files (handled by Update QR02 CBA workflow).
