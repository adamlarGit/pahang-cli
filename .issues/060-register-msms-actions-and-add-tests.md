# Ticket 060: Register MSMS CLI Actions & Unit Test Suite

## Parent Map

[Map 054: MSMS Workflow Porting & Domain Architecture Map](file:///.issues/054-msms-workflow-and-domain-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Question

How should `UpdateDataMsmsAction` be registered in project & utility action registries, and verified with unit tests?

## Resolution

Registered `UpdateDataMsmsAction` in `PROJECT_WORKFLOW_ACTIONS` (`src/project_workflow_actions.py`) delegating to `WorkflowService`. Registered `Update DATA_MSMS and TOTAL PE WO` in `UTILITY_ACTIONS` (`src/utility_actions.py`) using `get_or_create_utility_environment()` fallback. Created `tests/test_msms_workflow.py` and updated registry test cases. Verified all 73 pytest tests pass cleanly.
