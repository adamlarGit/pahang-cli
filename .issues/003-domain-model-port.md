# Ticket: Port src/project Domain Model (models, repository, storage, environment)

**Labels**: `wayfinder:grilling`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed
**Blocks**: [CLI Menu and Session Port](file:///.issues/004-cli-menu-and-session-port.md)

## Question

How should the project domain abstractions (`models.py`, `repository.py`, `storage.py`, `environment.py`) be organized in `src/project/` for Pahang?

## Resolution

- **Metadata Schema (`models.py`)**: Enhanced `ProjectMetadata` with `year` and `cycle` fields. Enforced `voltage_type` validation restricting values to `11kV` or `33kV`.
- **Dynamic Onboarding (`repository.py`)**: Designed `JsonFileProjectRepository` to start empty by default with support for multi-project registration and dynamic project key generation.
- **Storage Abstractions (`storage.py`)**: Updated `WorkspaceStorage` to use `get_whatsapp_dir()` returning `PYTHON/WHATSAPP` and `list_engr_files()` dynamically matching `ENGR-*.xlsx` in `PYTHON/ENGR FROM DRIVE/`.
- **Environment Facade (`environment.py`)**: Created `ProjectEnvironment` facade combining project metadata, workspace resolution, and Pahang template access.
