# Ticket: Port CLI Entrypoint and Run End-to-End Verification

**Labels**: `wayfinder:grilling`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed
**Blocked By**: [Workflow Actions Registry Stubs](file:///.issues/005-workflow-actions-registry-stubs.md)

## Question

How should `src/workflow_cli.py` and `main.py` be set up and verified for `pahang-cli`?

## Resolution

- **CLI Entrypoint (`src/workflow_cli.py`)**: Implemented CLI runner with `_add_new_project_wizard` for dynamic project onboarding (prompts for project name, PO number, 11kV/33kV rating, inspection year, cycle, and root folder). Initialized folder hierarchy and seed files.
- **Main Runner (`main.py`)**: Created `main.py` entry script cleanly calling `run_cli()`.
- **Empirical Verification**: Executed `python main.py --help` confirming clean execution banner `⚡ PAHANG AUTOMATION CLI — Version 1.0.0` and help output without errors.
