# Map 048: Standalone Utility Actions Deep Dive & Implementation

## Destination

Enable all 11 Utility Actions in `pahang-cli` to be invokable as standalone workflows/scripts without requiring an active project, connecting stubbed runners to domain services or standalone utility handlers, and consolidating them with the 1-Click Project Post-Processing Pipeline.

## Notes

- **Domain**: CLI Utility Workflows & Standalone Automation
- **Relevant Skills**: `/grilling`, `/domain-modeling`, `/research`, `/codebase-design`
- **Primary Registry**: `src/utility_actions.py` & `src/project_workflow_actions.py`
- **Documentation Reference**: `docs/workflows/utility_actions.md`
- **Source Reference CLI**: `C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV\src\`

## Decisions so far

- [Ticket 049: Research Standalone Utility Actions Architecture & Implementations](file:///.issues/049-research-standalone-utility-actions.md) — Audited 11 utility actions, established `get_or_create_utility_environment` fallback pattern, agreed to port core workflow modules into `src/workflows/` from reference CLI, un-stub `src/utility_actions.py`, and consolidate with `PostProcessingPipelineAction`.
- [Ticket 050: Implement Standalone Utility Environment Helper](file:///.issues/050-implement-standalone-utility-environment-helper.md) — Implemented `get_or_create_utility_environment` in `src/project/environment.py`.
- [Ticket 051: Port Converters & Core Utility Workflows](file:///.issues/051-port-converters-and-utility-workflows.md) — Ported `converters.py` and 8 core utility workflow modules into `src/workflows/`.
- [Ticket 052: Un-stub Utility Actions Registry](file:///.issues/052-unstub-utility-actions-registry.md) — Un-stubbed all 11 runners in `src/utility_actions.py` with lazy loading and standalone fallback.
- [Ticket 053: Wire Post-Processing Pipeline Action in Project Workflows](file:///.issues/053-wire-postprocessing-pipeline-action.md) — Ported `src/workflows/postprocessing_pipeline.py`, updated `WorkflowService`, and wired `PostProcessingPipelineAction`.

## Open Tickets (Frontier)

*(All tickets closed — Destination Reached)*

## Out of scope

- Rewriting core domain logic for project workflows (only exposing standalone execution wrappers and reusing shared modules)
- Non-Windows COM automation for Excel/Word features on non-Windows OS (fallback behavior is sufficient)
