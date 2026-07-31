# Map 068: Quick Report Workflow Service Call Alignment Map

Labels: wayfinder:map

## Destination

Align `WorkflowService.run_quick_report` and Quick Report execution with `pahang-cli`'s standardized 6-stage ETL workflow architecture (`src/workflows/quick_report.py`), establishing a clean entry seam (`QuickReportWorkflow.execute(environment, request)`) in `src/workflows/` that orchestrates the underlying `src/quick_report/` domain engine.

## Notes

- **Target Domain**: `src/workflows/service.py`, `src/workflows/quick_report.py`, `src/quick_report/`
- **Methodology**: `docs/etl_pipeline_refactoring_methodology.md`
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/research`, `/grilling`

## Decisions so far

- [Ticket 069: Research Quick Report Workflow Service Call Architecture](file:///.issues/069-research-quick-report-workflow-service-architecture.md) — Standardize Quick Report on `src/workflows/quick_report.py` 6-stage ETL orchestrator, treating `src/quick_report/` as a deep domain rendering engine.
- [Ticket 070: Align WorkflowService and Create QuickReportWorkflow Orchestrator](file:///.issues/070-align-workflow-service-call.md) — Created `QuickReportWorkflow` in `src/workflows/quick_report.py` and updated `WorkflowService.run_quick_report` in `src/workflows/service.py` to instantiate and execute `QuickReportWorkflow`.

## Open Tickets (Frontier)

- None (All tickets closed for Map 068).

## Not yet specified

- Alignment of CLI action handlers in `src/project_workflow_actions.py` to consume `WorkflowService.run_quick_report` via standardized request object.

## Out of scope

- Refactoring internal sub-rendering modules in `src/quick_report/` (handled in Map 071).
