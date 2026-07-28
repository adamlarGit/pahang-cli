# Map: Project Management & Settings Inspection in Pahang CLI

## Destination

Enable seamless multi-project management and settings inspection in `pahang-cli` by providing intuitive options to view active project settings, switch active projects, and add/register new project directories anytime from the CLI menu, adhering to modular, DRY principles and non-technical user ergonomics.

## Notes

- **Target CLI**: `pahang-cli` (`src/`)
- **Key Modules**: `src/project/repository.py`, `src/cli_session.py`, `src/settings_actions.py`, `src/workflow_cli.py`, `src/cli_menu.py`
- **User Persona**: Non-technical colleagues with zero coding background. Interactions must be bulletproof, self-explanatory, with clear menu prompts.
- **Key Skills**: `/wayfinder`, `/research`, `/domain-modeling`, `/codebase-design`, `/tdd`

## Decisions so far

- [Map & Initial Research Scope Definition](file:///.issues/043-project-management-and-settings-view-map.md) — Initialized wayfinder map to address missing project directory management & project settings UI post-onboarding.
- [Ticket 044: Research Project Onboarding, Storage, and Settings UI Architecture](file:///.issues/044-research-project-onboarding-storage-and-settings-ui-architecture.md) — Analyzed onboarding and storage architecture; surfaced gaps in repository CRUD and Settings menu; recommended modular extraction, path re-binding, workspace health checking, and non-technical visual status badges.
- [Ticket 045: Extend ProjectRepository with Path Updating, Deletion, and Workspace Health Checking](file:///.issues/045-extend-project-repository-and-workspace-health.md) — Implemented `update()`, `update_base_path()` (with auto-bootstrapping), `delete()` (with active session reset to None), `HealthCheckItem`, `WorkspaceHealth`, and `check_workspace_health()`. Added unit tests in `tests/test_repository.py`.
- [Ticket 046: Extract Project Management and Implement Project Settings Actions](file:///.issues/046-extract-project-management-and-settings-actions.md) — Extracted onboarding and management into `src/project/management.py` and created action handlers in `src/project_settings_actions.py` for viewing details, switching active project, registering projects, path re-binding, and unregistering projects. Added unit tests in `tests/test_project_management.py`.
- [Ticket 047: Wire Project & Storage Management Submenu and CLI UI](file:///.issues/047-wire-project-management-submenu-and-cli-ui.md) — Wired `select_project_management_action()` submenu in `src/cli_menu.py` and `src/workflow_cli.py`. Added `tests/test_cli_menu.py`. Code review passed; all 69 unit tests passing cleanly.

## Child Tickets

- [Ticket 044: Research Project Onboarding, Storage, and Settings UI Architecture](file:///.issues/044-research-project-onboarding-storage-and-settings-ui-architecture.md) (Closed)
- [Ticket 045: Extend ProjectRepository with Path Updating, Deletion, and Workspace Health Checking](file:///.issues/045-extend-project-repository-and-workspace-health.md) (Closed)
- [Ticket 046: Extract Project Management and Implement Project Settings Actions](file:///.issues/046-extract-project-management-and-settings-actions.md) (Closed)
- [Ticket 047: Wire Project & Storage Management Submenu and CLI UI](file:///.issues/047-wire-project-management-submenu-and-cli-ui.md) (Closed)




## Not yet specified

<!-- Fog of war: in-scope fog you can't ticket yet -->
- Non-technical user feedback and potential quick action shortcuts for switching workspace roots.

## Out of scope

- Multi-tenant cloud synchronization or network database integrations.
