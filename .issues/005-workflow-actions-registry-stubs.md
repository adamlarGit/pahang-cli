# Ticket: Port Action Registries and Workflow Stubs

**Labels**: `wayfinder:grilling`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed
**Blocked By**: [CLI Menu and Session Port](file:///.issues/004-cli-menu-and-session-port.md)
**Blocks**: [CLI Entrypoint and Verification](file:///.issues/006-cli-entrypoint-and-verification.md)

## Question

How should workflow actions and utility actions be registered and stubbed in Pahang CLI?

## Resolution

- **Project Workflow Action Registry (`src/project_workflow_actions.py`)**: Registered `PopulateTotalPeAction`, `RawMaterialAction`, `UpdateQr02CbaAction`, `QuickReportAction`, `PostProcessingPipelineAction`, and `WhatsAppReportAction`.
- **Utility Actions (`src/utility_actions.py`)**: Registered standalone utility actions for raw material creation, file renaming, PDF extraction/combining, docx conversion, diagonal formatting, signature replacement, and WhatsApp report generation.
- **Workflow Service & Models (`src/workflows/`)**: Created request/response dataclasses and `WorkflowService` orchestration layer.
- **Settings Actions (`src/settings_actions.py`)**: Ported git rollback version menu.
