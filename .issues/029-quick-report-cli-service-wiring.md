# Quick Report CLI Action and Service Wiring

Labels: wayfinder:task
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md), [Digital Testsheet Data Extraction and Context Mapping Schema](file:///.issues/026-digital-testsheet-data-extraction-schema.md), [Substation Condition Template Auto-Detection Rules](file:///.issues/027-substation-condition-template-auto-detection.md), [Photo Retrieval, Aspect Ratio Resizing, and Fallback Placeholders](file:///.issues/028-photo-retrieval-resizing-and-placeholders.md)

## Question

How should `QuickReportComposer` be wired into `WorkflowService.run_quick_report` and exposed via `QuickReportAction` in the CLI presentation layer with full support for Auto station batch, Date folder, and FL modes?
