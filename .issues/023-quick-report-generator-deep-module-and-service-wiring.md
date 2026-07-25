# Quick Report Generator Deep Module and Service Wiring

Labels: wayfinder:task
Parent: [Map: Quick Report Generation Workflow (Pahang CLI)](file:///.issues/019-quick-report-generation-map.md)
Blocks: [Quick Report Templates and Docxtpl Binding Schema](file:///.issues/020-quick-report-templates-and-docxtpl-binding-schema.md), [Quick Report Defect Data Extraction and Suffix Lookup](file:///.issues/021-quick-report-defect-data-extraction-and-suffix-lookup.md), [Quick Report Photo Embedding and Layout Rules](file:///.issues/022-quick-report-photo-embedding-and-layout.md)

## Question

How should the core Quick Report generation engine be structured into deep module components (e.g. `src/quick_report/builder.py`, `src/quick_report/template_engine.py`), wired to `WorkflowService.run_quick_report`, and exposed via `QuickReportAction` in the CLI presentation layer with full support for Auto, Folder, and FL modes?
