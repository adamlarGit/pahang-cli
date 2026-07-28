# Changelog

All notable changes to Pahang CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-07-29

### Added
- **Manage Projects & Workspace Storage Submenu**: Dedicated UI under Settings to view project details, inspect folder health status badges (`[OK]`, `[MISSING]`), switch active projects, register new projects, and update workspace root directory paths (`src/project_settings_actions.py`, `src/cli_menu.py`).
- **Domain Management Module**: Extracted project onboarding, project registration wizard, and active project selection out of `workflow_cli.py` into `src/project/management.py`.
- **Repository CRUD & Workspace Health Extensions**: Added `update()`, `update_base_path()` (with automatic folder bootstrapping), and `delete()` (with session reset to `None`) to `ProjectRepository` (`src/project/repository.py`), alongside `WorkspaceHealth` folder checking in `LocalWorkspaceStorage` (`src/project/storage.py`).
- **Camera Photo Pattern Configurations**: Ported IR single file (`FLIR`) and dual pair (`IR_`/`DC_`) camera configuration presets (`src/project/models.py`).
- **CLI Selector Enhancements**: Multi-digit selection (`1..10..11`) and bracketed shortcut navigation (`src/cli_selectors.py`).
- **Utility Actions**: Ported `remove_desktop_ini` workflow action and PowerShell script (`src/remove_desktop_ini_workflow.py`, `scripts/remove_desktop_ini.ps1`).

### Changed
- Refactored `src/workflow_cli.py` to route Settings menu commands cleanly to `src/project_settings_actions.py`.
- Enforced `--frozen` flag on `uv sync`/`uv run` launchers in `start_cli.bat`.

## [1.1.0] - 2026-07-24

### Added
- Interactive date folder selector (`src/cli_selectors.py`) for Pahang 3-tier inspection folders.
- Deep module for testsheet parsing (`src/testsheet/`) including models, extractor, and repository.
- Workflow `Populate TOTAL PE` (`src/populate_total_pe_workflow.py`) scanning `TESTSHEET/` and upserting `TOTAL PE.xlsx` (`DataCycle1`).
- Workflow `Raw Material Creation & Sorting` (`src/raw_material_workflow.py`) for automated folder provisioning and `IR`/`DG` photo sorting.
- Comprehensive unit and integration test suite (`tests/`).
