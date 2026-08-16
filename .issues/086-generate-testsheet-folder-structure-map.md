# Map 086: Generate TESTSHEET Folder Structure Workflow Map

Labels: wayfinder:map

## Destination

Design and implement a robust, 6-stage ETL compliant workflow (`GenerateTestsheetFolderStructureWorkflow`) positioned as Workflow #1 in the Project Workflow menu. It allows the operator to select a target Station and Month (from existing directories in `TESTSHEET/` or create new ones with incremental numbering `01.`, `02.`, etc.) and specify target inspection Date(s) (`DD-MM-YYYY`) to idempotently provision `<DATE>/UNSORTED RAW DATA/` with `DG/`, `IR/`, and `US+TEV/` subdirectories.

## Notes

- **Target Domain**: `src/workflows/generate_testsheet_folder.py`, `src/cli_selectors.py`, `src/project_workflow_actions.py`, `src/workflows/models.py`, `src/workflows/service.py`
- **Methodology Guidelines**:
  - `docs/etl_pipeline_refactoring_methodology.md`: 6-stage ETL pipeline (`GenerateTestsheetFolderPreflightGuard`, `GenerateTestsheetFolderExtractor`, `GenerateTestsheetFolderFilter`, `GenerateTestsheetFolderTransformer`, `GenerateTestsheetFolderLoader`, `GenerateTestsheetFolderAuditor`).
  - `docs/project_centric_architecture.md`: Strict workspace scoping (`environment.storage.get_testsheet_dir()`), zero CWD leakage.
- **Directory Hierarchy Standard**:
  ```text
  <base_path>/TESTSHEET/
  └── <STATION>/
      └── <MONTH (e.g. 01. AUGUST)>/
          └── <DATE (e.g. 10-08-2026)>/
              └── UNSORTED RAW DATA/
                  ├── DG/
                  ├── IR/
                  └── US+TEV/
  ```
- **Sequential Month Indexing Rule**: New month folders under a station receive sequential numbering starting from `01. <MONTH>` up to `N. <MONTH>` based on existing months count under that station.
- **Collision / Idempotency Rule**: Safely create missing subfolders without overwriting or deleting any existing files/directories (`mkdir(parents=True, exist_ok=True)`).
- **Skills**: `/wayfinder`, `/domain-modeling`, `/codebase-design`, `/tdd`, `/grilling`

## Decisions so far

- [Ticket 087: Domain Models & Request Schemas](file:///.issues/087-testsheet-folder-generation-domain-models-and-plan.md) — Defined immutable `GenerateTestsheetFolderRequest`, `DateFolderPlan`, `GenerateTestsheetFolderPlan`, and `GenerateTestsheetFolderResult` dataclasses.
- [Ticket 088: 6-Stage ETL Pipeline Implementation](file:///.issues/088-testsheet-folder-generation-6stage-etl-pipeline.md) — 6-stage architecture with best-effort multi-date filtering and verification-only auditor (no history.json pollution).
- [Ticket 089: Interactive Selectors](file:///.issues/089-cli-station-month-interactive-selectors.md) — Existing stations + `[+] Add New Station`, existing months + `[+] Add New Month` (with `01.`..`12.` incremental prefixing), normalized single/multi-date prompt with today's default.
- [Ticket 090: WorkflowService & Action #1](file:///.issues/090-wire-workflow-service-and-project-workflow-action.md) — Exposed `run_generate_testsheet_folder()`, registered action `"Generate TESTSHEET Folder Structure"` as item #1 in `PROJECT_WORKFLOW_ACTIONS`, minimal single-line console output summary.
- [Ticket 091: High-Level Integration Test Suite](file:///.issues/091-testsheet-folder-generation-unit-and-integration-tests.md) — Integration test suite covering single-date, multi-date, idempotency, best-effort filtering, and preflight guard.

## Open Tickets (Frontier)

None (All tickets 087-091 completed and implemented).

## Not yet specified

- **Template Testsheet Seeding (Optional Future Extension)**: Auto-copying blank station testsheet Excel templates into the newly created `<DATE>/` directory upon folder generation.
- **Batch Date Range Generation**: Creating multiple consecutive date folders via a calendar range selector (e.g., `10-08-2026` to `15-08-2026`).

## Out of scope

- Moving or importing camera raw photo files into `UNSORTED RAW DATA/` (handled separately by Raw Material workflow).
- Generating Word / Excel reports during folder structure initialization.
