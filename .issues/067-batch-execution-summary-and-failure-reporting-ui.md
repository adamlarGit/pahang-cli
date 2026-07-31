# Ticket 067: Quick Report Batch Execution Summary & Failure Reporting UI

## Parent Map

[Map 061: Quick Report Engine Unstubbing & Photo Integration Map](file:///.issues/061-quick-report-engine-unstubbing-map.md)

## Type

`task` (HITL)

## Status

`CLOSED`

## Blocked-By

*(None — Frontier Ticket)*

## Question

How should `QuickReportAction` format and display batch execution summaries, success statistics, warning logs, and partial failure tracebacks in the CLI UI after multi-station batch quick report composition runs?

## Resolution

Implemented formatted CLI summary box printer `_print_quick_report_batch_summary` in `src/project_workflow_actions.py`. Displays total processed, succeeded, failed, and warning counts, lists generated DOCX files with full output paths, and provides concise 1-line failure messages e.g. `[FAILED] substation_number. substation_name_erms: Reason` for failed stations. Added unit test `test_print_quick_report_batch_summary` in `tests/test_workflow_actions.py`.
