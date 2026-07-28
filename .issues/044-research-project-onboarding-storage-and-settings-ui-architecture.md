# Ticket 044: Research Project Onboarding, Storage, and Settings UI Architecture

Labels: `wayfinder:research`
Status: `Closed`

## Question

How does `pahang-cli` currently handle project onboarding, configuration persistence, active project selection, and settings actions? What facts and architectural Seams exist in `src/project/`, `src/cli_session.py`, `src/settings_actions.py`, `src/workflow_cli.py`, and `src/cli_menu.py`? Based on these facts, what modular, DRY, project-centric recommendation should be implemented so non-technical users can view project settings, switch active projects, and register new project paths anytime directly from the CLI?

## Resolution

- **Onboarding Flow**: Handled in `src/workflow_cli.py` via `_select_active_project()` and `_add_new_project_wizard()`. Saves catalog to `.cli_config.json` via `JsonFileProjectRepository` and activates key in `.active_project.json`. Automatically bootstraps workspace subfolders and template files via `LocalWorkspaceStorage._initialize_project_workspace()`.
- **Architectural Gap**: `src/cli_menu.py` Settings menu lacks options to view current project details, switch projects, add new projects, or update project directory paths. Project switching was buried only in the `Project Workflow` submenu.
- **Repository Gap**: `ProjectRepository` lacks `update_base_path(key, new_path)` and `delete(key)` CRUD methods and workspace health validation.
- **Recommendation**:
  1. Extend `ProjectRepository` and `LocalWorkspaceStorage` with path editing, project deletion, and folder health checks.
  2. Extract onboarding and management logic from `workflow_cli.py` into `src/project/management.py`.
  3. Create `src/project_settings_actions.py` to handle project detail inspection, project switching, registration, and directory path updating.
  4. Wire a user-friendly "Manage Projects & Workspace Storage" menu into `src/cli_menu.py` and `src/workflow_cli.py` with visual status badges (`[ACTIVE]`, `[OK]`) designed for non-technical users.

