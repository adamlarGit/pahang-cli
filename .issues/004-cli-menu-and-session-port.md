# Ticket: Port CLI Selectors, Menu, and Session Management

**Labels**: `wayfinder:grilling`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed
**Blocked By**: [Domain Model Port](file:///.issues/003-domain-model-port.md)
**Blocks**: [Workflow Actions Registry Stubs](file:///.issues/005-workflow-actions-registry-stubs.md)

## Question

How to port the interactive menu selection components (`cli_selectors.py`, `cli_menu.py`, `cli_session.py`) into `src/`?

## Resolution

- **CLI Selectors (`src/cli_selectors.py`)**: Ported interactive single/multi selection module supporting arrow keys, vim keys (`j`/`k`), numeric shortcuts, confirmation prompts, and directory tree navigation with fallback handling.
- **CLI Menu (`src/cli_menu.py`)**: Updated menu headers and banners for Pahang CLI (`MAIN MENU - Pahang CLI (v{__version__})`) and added project action navigation.
- **Session State (`src/cli_session.py`)**: Ported `CliSession` maintaining active project state in memory and persisting key in `.active_project.json`.
