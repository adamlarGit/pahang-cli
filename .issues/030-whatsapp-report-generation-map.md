# Map: WhatsApp Report Generation Workflow (Pahang CLI)

Labels: wayfinder:map

## Destination

Implement and verify the end-to-end WhatsApp Report Generation workflow in `pahang-cli` (`src/whatsapp/` deep module + `src/whatsapp_report_workflow.py` orchestrator), including interactive Quick Report batch selection (`select_directory_tree`), qualifying PDF filename parsing (`QUALIFYING_PDF_PATTERN`), `TOTAL PE.xlsx` / metadata lookup, docx template binding (`templates/WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx`), save directory resolution (`PYTHON/WHATSAPP/`), and CLI action integration (`WhatsAppReportAction`).

## Notes

- **Input Source**: Selectable batch directory under `QUICK REPORT/` containing output PE PDF reports (e.g. `001. SSU CHEROH (VI).pdf`).
- **Template Path**: `templates/WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx` (resolved via `config.py` and `WorkspaceStorage.get_whatsapp_template()`).
- **Output Path**: `PYTHON/WHATSAPP/` (resolved via `WorkspaceStorage.get_whatsapp_dir()`).
- **Data Lookup**: Scans `TOTAL PE.xlsx` (`DataCycle1` sheet) for station name, ERMS FL code, date of inspection, and defect findings matching extracted PE numbers.
- **Reference Implementation**: `C:\Users\ADAM\Desktop\tnb\src\whatsapp_report_workflow.py` and `src\docx_ops.py` (`generate_whatsapp_report`).
- **Skills**: `/codebase-design`, `/domain-modeling`, `/research`, `/grilling`

## Decisions so far

- [WhatsApp Report Architecture and Data Flow](file:///.issues/031-whatsapp-report-architecture-and-data-flow.md) — Standardized on **Deep Module + Orchestrator** pattern: `src/whatsapp/` package (`generator.py` for rendering & Excel lookup, `models.py` for schemas) + `src/whatsapp_report_workflow.py` lean orchestrator.
- [Qualifying PDF Parsing and PE Metadata Lookup](file:///.issues/032-qualifying-pdf-parsing-and-pe-metadata-lookup.md) — PDF regex matching `^(\d+)\.?\s*(.*?)\s*(?:\((.*?)\))?\.pdf$`; defect indicators extracted **strictly** from PDF filename suffix `(...)` (`"-"` if missing); `TOTAL PE.xlsx` queried strictly for substation metadata (`WO`/MSMS, inspection date, station mapping).
- [WhatsApp Docx Template Binding and Summary Formatting](file:///.issues/033-whatsapp-docx-template-binding-and-formatting.md) — `docxtpl` Jinja context binding using `templates/WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx`; strictly output `.docx` file in `PYTHON/WHATSAPP/` named `{next_num:02d}. {station_name} {clean_date}.docx` (e.g. `01. MARAN 25-07-2026.docx`).
- [WhatsApp Service Wiring and CLI Adapter Integration](file:///.issues/034-whatsapp-service-wiring-and-cli-adapter.md) — Reuses `cli_selectors.select_directory_tree` starting at `QUICK REPORT/` for tree navigation; connects `WhatsAppReportAction` and `WorkflowService.run_whatsapp`.
- [Refactor Legacy Workflows to Deep Module + Orchestrator Architecture](file:///.issues/035-refactor-workflows-to-deep-module-architecture.md) — Standardized workflow orchestrators in `src/workflows/`, extracted `ProcessingHistoryStore` with `qr02_processed_folders.json`, and decoupled domain persistence into `src/master/` deep modules.


## Not yet specified

- Batch output PDF validation for missing or corrupted PDF files.

## Out of scope

- Direct WhatsApp Web API / Automated message sending (out of scope; docx summary report generation only).
- Formatted plain text summary output / clipboard copying.
- Modifying Quick Report PDF contents.
