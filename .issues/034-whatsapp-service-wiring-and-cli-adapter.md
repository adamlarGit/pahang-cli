# WhatsApp Service Wiring and CLI Adapter Integration

Labels: wayfinder:research
Status: Closed
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

How should `WorkflowService.run_whatsapp` and `WhatsAppReportAction` be implemented to integrate interactive directory selection tree (`select_directory_tree`), batch confirmation summary prompts, progress reporting sinks, and CLI execution flow?

## Resolution

1. **Tree Directory Selection (`src/cli_selectors.py`)**:
   - Reuses standard `select_directory_tree(root_path=storage.get_quick_report_dir(), ...)` with `is_selectable=is_selectable_quick_report_batch`.
   - Generates batch confirmation summary showing relative path, qualifying PDF count, first PE, and last PE numbers.

2. **Workflow Service Integration (`src/workflows/service.py`)**:
   - Updates `WorkflowService.run_whatsapp(environment, request)` to delegate execution to `run_whatsapp_report(environment, report_dir=...)` in `src/whatsapp_report_workflow.py`.

3. **CLI Presentation Adapter (`src/project_workflow_actions.py`)**:
   - `WhatsAppReportAction.execute` invokes `select_quick_report_batch(storage.get_quick_report_dir())`, verifies selection, dispatches `WhatsAppReportRequest`, and outputs final `.docx` path to console.
