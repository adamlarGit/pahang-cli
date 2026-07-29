# Ticket 057: MSMS CLI Action Registration & Standalone Execution

## Parent Map

[Map 054: MSMS Workflow Porting & Domain Architecture Map](file:///.issues/054-msms-workflow-and-domain-map.md)

## Type

`grilling` (HITL)

## Status

`CLOSED`

## Question

Should `Update DATA_MSMS` be registered under Project Workflows, Utility Actions, or both?

## Resolution

Decided on **Option A**: Register `UpdateDataMsmsAction` in both `PROJECT_WORKFLOW_ACTIONS` (`src/project_workflow_actions.py`) and `UTILITY_ACTIONS` (`src/utility_actions.py`) using `get_or_create_utility_environment()` for standalone fallback.
