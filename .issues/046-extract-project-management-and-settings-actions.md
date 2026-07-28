# Ticket 046: Extract Project Management and Implement Project Settings Actions

Labels: `wayfinder:task`
Status: `Closed`
Blocked by: `[Ticket 045: Extend ProjectRepository with Path Updating, Deletion, and Workspace Health Checking](file:///.issues/045-extend-project-repository-and-workspace-health.md)`

## Question

How should project onboarding logic be extracted into `src/project/management.py` and dedicated action handlers implemented in `src/project_settings_actions.py` to support viewing active project details, switching active projects, registering new project paths, and re-binding existing workspace directories?

## Resolution

- **Module Extraction (`src/project/management.py`)**: Extracted onboarding, project creation wizard, project key prompting, and active project selection wizard out of `workflow_cli.py` into a clean, reusable domain management module.
- **Action Handlers (`src/project_settings_actions.py`)**: Implemented dedicated action handlers:
  - `handle_view_project_info()`: Renders active project metadata details and workspace folder status health badges (`[OK]`, `[MISSING]`).
  - `handle_switch_project()`: Interactively switches active project session.
  - `handle_add_project()`: Launches the project registration wizard.
  - `handle_update_project_path()`: Allows re-binding a project's workspace directory path and auto-bootstraps subfolders.
  - `handle_unregister_project()`: Removes a project and clears session state if active.
- **Refactored Entrypoint (`src/workflow_cli.py`)**: Updated `src/workflow_cli.py` to delegate project onboarding and selection to `src.project.management`.
- **Tests**: Added unit test suite in `tests/test_project_management.py` (all 65 tests passing).

