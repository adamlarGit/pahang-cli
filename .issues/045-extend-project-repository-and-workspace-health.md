# Ticket 045: Extend ProjectRepository with Path Updating, Deletion, and Workspace Health Checking

Labels: `wayfinder:task`
Status: `Closed`

## Question

How should `ProjectRepository` (`src/project/repository.py`) and `LocalWorkspaceStorage` (`src/project/storage.py`) be extended with `update_base_path()`, `delete()`, and `validate_workspace_health()` methods to support editing project workspace root paths, unregistering projects, and verifying folder integrity for non-technical users?

## Resolution

- **Models**: Added `HealthCheckItem` and `WorkspaceHealth` dataclasses in `src/project/models.py`.
- **Repository Extensions**: Added abstract and concrete methods in `ProjectRepository` / `JsonFileProjectRepository`:
  - `update(project)`: General project metadata editing.
  - `update_base_path(key, new_path)`: Re-binds workspace root path in `.cli_config.json` and auto-bootstraps missing subfolders/templates via `_initialize_project_workspace()`.
  - `delete(key, session)`: Removes project from catalog and resets active project session state to `None` if the active project was deleted.
- **Storage Extensions**: Implemented `check_workspace_health()` in `WorkspaceStorage` & `LocalWorkspaceStorage` evaluating existence of core directories (`PYTHON/`, `TESTSHEET/`, `RAW MATERIAL/`, `QUICK REPORT/`, `ENGR FROM DRIVE/`, `WHATSAPP/`) and seed data files (`TOTAL PE.xlsx`, `DATA MSMS.xlsx`).
- **Tests**: Created comprehensive unit tests in `tests/test_repository.py` (all 61 tests passing).

