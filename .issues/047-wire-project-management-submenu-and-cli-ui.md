# Ticket 047: Wire Project & Storage Management Submenu and CLI UI

Labels: `wayfinder:task`
Status: `Closed`
Blocked by: `[Ticket 046: Extract Project Management and Implement Project Settings Actions](file:///.issues/046-extract-project-management-and-settings-actions.md)`

## Question

How should `src/cli_menu.py` and `src/workflow_cli.py` be updated to add a "Manage Projects & Workspace Storage" entrypoint under the main Settings menu, displaying visual status badges (`[ACTIVE]`, `[OK]`) and self-explanatory prompts tailored for non-technical site inspectors?

## Resolution

- **Submenu Interface (`src/cli_menu.py`)**: Added `select_project_management_action()` with 5 options: View Info, Switch Project, Add Project, Update Path, Unregister Project + Back. Added `"📁 Manage Projects & Workspace Storage"` as Option 1 under `select_settings_action()`.
- **CLI Submenu Router (`src/workflow_cli.py`)**: Added `_run_project_management_menu(session)` to handle selection loops and dispatch actions to `src.project_settings_actions`. Refactored all internal project activation calls to use `select_active_project_wizard()`.
- **Tests & Code Review**: Added unit tests in `tests/test_cli_menu.py` and updated `tests/test_project_management.py`. Verified by independent Code Reviewer subagent (Status: `PASSED`, all 69 unit tests passing cleanly).

