# Map 054: MSMS Workflow Porting & Domain Architecture Map

## Destination

Port the `DATA_MSMS` update workflow into `pahang-cli`, establish the MSMS domain architecture (`src/msms`), update `TOTAL_PE` Work Order (WO) columns, and lay the foundation for multi-source MSMS client Excel population.

## Notes

- **Domain**: MSMS (Management System / Work Order Integration)
- **Relevant Skills**: `/wayfinder`, `/grilling`, `/domain-modeling`, `/codebase-design`
- **Source Reference**: `C:\Users\ADAM\Desktop\tnb\src\update_data_msms_workflow.py` & `excel_ops.py`
- **Target Integration**: `TOTAL_PE.xlsx` (`DataCycle1` WO column update)

## Decisions so far

- [Ticket 055: Determine MSMS Domain Location (src/master vs src/msms)](file:///.issues/055-msms-domain-location-decision.md) — Decided on dedicated top-level domain package `src/msms/`.
- [Ticket 056: MSMS Workflow Structure & TOTAL PE Integration](file:///.issues/056-msms-workflow-structure-and-total-pe-integration.md) — `src/msms/` handles `DATA_MSMS.xlsx` repo operations, and `src/workflows/update_data_msms.py` uses `TotalPeRepository` to update `TOTAL_PE.xlsx` WO columns.
- [Ticket 057: MSMS CLI Action Registration & Standalone Execution](file:///.issues/057-msms-cli-action-registration.md) — Register `UpdateDataMsmsAction` in both `PROJECT_WORKFLOW_ACTIONS` (`src/project_workflow_actions.py`) and `UTILITY_ACTIONS` (`src/utility_actions.py`).
- [Ticket 058: Implement MSMS Domain Package](file:///.issues/058-implement-msms-domain-package.md) — Created `src/msms/` (`models.py`, `repository.py`, `__init__.py`).
- [Ticket 059: Implement MSMS Workflow & Service Integration](file:///.issues/059-implement-msms-workflow-and-service.md) — Implemented `src/workflows/update_data_msms.py` and registered `run_update_data_msms` in `WorkflowService`.
- [Ticket 060: Register MSMS CLI Actions & Unit Test Suite](file:///.issues/060-register-msms-actions-and-add-tests.md) — Registered CLI actions in project and utility registries, wrote unit tests, and confirmed all 73 tests pass.

## Open Tickets (Frontier)

*(All tickets closed — Destination Reached)*

## Not yet specified

- Extracting MSMS client data from multi-file sources (testsheets, TOTAL PE, ENGR files) into custom client templates

## Out of scope

- Porting non-MSMS legacy features from `C:\Users\ADAM\Desktop\tnb`
