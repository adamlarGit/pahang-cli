<!-- label: wayfinder:task -->
<!-- status: open -->
<!-- blocked-by: 003 -->
# 004: CLI Presentation Adapter & Audit Summary Box

## Question

How should the interactive CLI presentation adapter prompt the operator and display real-time execution feedback and audit metrics?

## Context

1. **Adapter Class**: `PostProcessingPipelineAction` in `src/project_workflow_actions.py`.
2. **Prompts**:
   - Scope selection: `by_date` (select target date folder) vs `by_fl` (multi-select specific substations).
   - Signatures prompt:
     - `Yes`: Prompt vendor signature person and TNB signature person from `env.get_sign_dir()`.
     - `No`: Configure request with `apply_signatures=False` (triggers `mode="none"` placeholder stripping).
   - WhatsApp prompt: Prompted **only** if `by_date` is selected.
3. **Real-time Step Feedback**:
   - Stream progress per substation with distinct progress markers.
4. **Final Summary Box**:
   - Render structured summary box showing total queued, succeeded, failed, warnings, generated deliverable paths, and total elapsed runtime.

## TDD Plan

1. **Red**: Unit tests in `tests/test_postprocessing_cli_adapter.py` verifying:
   - CLI adapter builds correct `PostProcessingRequest` based on user inputs.
   - WhatsApp prompt is suppressed when `by_fl` is selected.
   - Summary formatter outputs expected structure.
2. **Green**: Update `PostProcessingPipelineAction` and formatting helpers.
3. **Refactor**: Ensure all outputs conform to project UI standards.
