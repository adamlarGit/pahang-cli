# Ticket 053: Wire Post-Processing Pipeline Action in Project Workflows

## Parent Map

[Map 048: Standalone Utility Actions Deep Dive & Implementation](file:///.issues/048-standalone-utility-actions-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Question

How should `PostProcessingPipelineAction` in `src/project_workflow_actions.py` and `WorkflowService.run_postprocessing_pipeline` be implemented using the ported utility workflows?

## Resolution

Ported `postprocessing_pipeline_workflow.py` into `src/workflows/postprocessing_pipeline.py`. Registered `run_postprocessing_pipeline` within `WorkflowService` (`src/workflows/service.py`) and connected `PostProcessingPipelineAction.execute` inside `src/project_workflow_actions.py` to dispatch to the service. Verified all 70 pytest test cases pass cleanly.
