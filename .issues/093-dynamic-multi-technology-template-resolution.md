# Ticket 093: Dynamic Multi-Technology Template Resolution & Project Environment Integration

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed

## Question

How should `ProjectEnvironment` and `WorkspaceStorage` resolve CBM defect detail and summary templates dynamically based on `ProjectMetadata.technologies` (`DEFECT IR`, `DEFECT IR US`, `DEFECT IR US TEV`), while failing fast with an explicit `FileNotFoundError` if the required technology template folder is missing on disk?

## Scope

- Update `src/project/environment.py` and `src/project/storage.py` (and `config.py`) to resolve CBM defect template paths according to `project.technologies`.
- Add test coverage for single-tech (IR), dual-tech (IR+US), and triple-tech (IR+US+TEV) template resolution and fail-fast behavior.

## Resolution

- Defined `CBM_DEFECT_TEMPLATES` in `config.py`.
- Implemented `ProjectEnvironment.get_cbm_defect_folder_name()`, `ProjectEnvironment.get_template()` multi-tech resolution, and `ProjectEnvironment.get_cbm_summary_template()`.
- Implemented `WorkspaceStorage.get_cbm_defect_dir()` and `WorkspaceStorage.get_cbm_defect_template()` with fail-fast `FileNotFoundError` semantics.
- Added comprehensive unit tests in `tests/test_workspace_storage.py` and `tests/test_quick_report_components.py`.
