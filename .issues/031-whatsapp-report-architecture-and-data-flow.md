# WhatsApp Report Architecture and Data Flow

Labels: wayfinder:research
Status: Closed
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

What is the deep module architecture, data flow, and directory structure for the WhatsApp Report Generation workflow in `pahang-cli`, and how do input Quick Report batch folders (`QUICK REPORT/<STATION>/...`), `TOTAL PE.xlsx`, template resources (`WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx`), and output files (`PYTHON/WHATSAPP/`) interact?

## Resolution

1. **Deep Module + Orchestrator Architecture**:
   - **Deep Module (`src/whatsapp/`)**:
     - `src/whatsapp/models.py`: Data schemas (`WhatsAppReportResources`, `WhatsAppReportItem`, `WhatsAppReportSummary`).
     - `src/whatsapp/generator.py`: Core domain logic for parsing PDF filenames, querying `TOTAL PE.xlsx` (`DataCycle1` sheet), binding Jinja2 context to `docxtpl.DocxTemplate`, and outputting `.docx` files to `PYTHON/WHATSAPP/`.
   - **Lean Workflow Orchestrator (`src/whatsapp_report_workflow.py`)**:
     - Coordinates `ProjectEnvironment`, calls `src/cli_selectors.py` (`select_directory_tree`) for interactive batch selection, and dispatches generation to `src/whatsapp/generator.py`.
   - **Service & CLI Presentation Layer**:
     - `src/workflows/service.py` (`WorkflowService.run_whatsapp`) and `src/project_workflow_actions.py` (`WhatsAppReportAction`).

2. **System-Wide Alignment**:
   - Locked the requirement that **all** workflow modules in `pahang-cli` (including `update_qr02_cba` and `populate_total_pe` tracked in ticket [035-refactor-workflows-to-deep-module-architecture.md](file:///.issues/035-refactor-workflows-to-deep-module-architecture.md)) strictly follow the `deep module + orchestrator` philosophy.
