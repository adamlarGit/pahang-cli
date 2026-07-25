# Quick Report CLI Action and Service Wiring

Labels: wayfinder:task
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md), [Digital Testsheet Data Extraction and Context Mapping Schema](file:///.issues/026-digital-testsheet-data-extraction-schema.md), [Substation Condition Template Auto-Detection Rules](file:///.issues/027-substation-condition-template-auto-detection.md), [Photo Retrieval, Aspect Ratio Resizing, and Fallback Placeholders](file:///.issues/028-photo-retrieval-resizing-and-placeholders.md)
Completed At: 2026-07-25T15:23:00+08:00

## Question

How should `QuickReportComposer` be wired into `WorkflowService.run_quick_report` and exposed via `QuickReportAction` in the CLI presentation layer with full support for Auto station batch, Date folder, and FL modes?

## Answer

1. **CLI Selection Modes in `QuickReportAction`**:
   - Offers 2 interactive selection modes:
     1. `Select Date Folder` (`QuickReportMode.FOLDER`)
     2. `Manual FL Input` (`QuickReportMode.FL`)
   - Omits auto workstation scan in favor of targeted folder/FL execution.

2. **Substation Condition Template Path Handling**:
   - Automatically uses `MASTER_SUBSTATION_CONDITION.docx` from `environment.get_sub_cond_dir()` without prompting the user.

3. **Service Layer & Error Isolation (`WorkflowService.run_quick_report`)**:
   - Follows the Johor reference pattern (`quick_report_workflow.py`):
     - Individual station processing is wrapped in `try...except` to isolate errors and prevent batch aborts.
     - Progress is emitted via `progress_sink` (`[current/total] Generating quick report for {station}...`).
     - Returns a `QuickReportResult` carrying `reports_generated`, `generated_paths`, `warnings`, and `errors`.
     - The CLI presentation layer displays a summary of generated files and reports any skipped or failed stations with error reasons.
