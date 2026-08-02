# Changelog

All notable changes to Pahang CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-08-03

### Refactored
- **Quick Report 6-Stage ETL Pipeline**: Refactored `QuickReportWorkflow` into a 6-stage ETL pipeline (`QuickReportExtractor`, `QuickReportFilter`, `QuickReportTransformer`, `CbmDefectPlanner`, `QuickReportComposer` Loader, `QuickReportWorkflow` orchestrator) following `etl_pipeline_refactoring_methodology.md`.
- **End-to-End Typed Defect Records & Plans**: Data flows end-to-end as strongly typed `CbmDefectRecord`, `ViDefectRecord`, `CbmDefectGroup`, and `CbmDefectFamilyPlan` dataclasses, deferring `.to_dict()` conversions strictly to the template rendering boundary (`DocxTemplate.render()`).
- **Pure CBM Defect Planner**: Created `CbmDefectPlanner` stage (`src/quick_report/cbm_defect_planner.py`) to match equipment items to family specs and template files in-memory without disk write I/O or Word rendering.
- **Deep Renderer Integration**: Updated `cbm_summary.py` (`prepare_tech_summary_rows`), `vi_summary.py` (`build_vi_summary_context`), `vi_defect_pages.py` (`build_vi_defect_page_context`), and `cbm_defect_pages.py` (`generate_cbm_defect_pages`) to accept typed records directly with unified `_get_field()` property access.
- **QR03 Master Sheet Caching**: `MasterQr03DefectRepository` now caches opened Excel worksheets per workflow run to avoid reopening workbooks 2N times.
- **Fail-Fast Defect Repository**: Defect source failures now raise explicit `FileNotFoundError` or `RuntimeError` instead of returning empty lists silently.

### Fixed
- **Quick Report Detail Pages Data Loss**: Fixed `additional_remarks` data loss in detail pages and eliminated dead keys (`temperature`, `us_value`, `tev_value`, `defect_from`).
- **Switchgear & Transformer Panels**: Fixed SWG panel missing IR/TEV readings, removed invalid TX panel key, and removed duplicate helper functions in `cbm_render.py`.
- **Substation Condition Pair Coupling**: Decoupled `generate_substation_condition_pages` from package objects, consuming pre-planned `condition_pairs` directly from `plan.condition_pairs`.
- **Circular Imports**: Fixed circular import dependency between `src.quick_report` and `src.workflows` using local method imports and `TYPE_CHECKING` guards.

## [1.5.1] - 2026-08-01

### Fixed
- **Quick Report Defect Data Pipeline**: Wired `MasterQr03DefectRepository` in `_process_station` to fetch CBM and VI defects from QR03 master workbooks instead of empty lists.
- **Word COM Range Collapsing**: Fixed `_compile_document` Range handling (`InsertBreak` + `Paste` on collapsed Range) to prevent Word RPC crashes when appending ActiveX/FLIR parts.
- **Substation Condition Template Variables**: Updated context variables to `header_left` and `header_right` to correctly populate equipment titles and dehighlight unused cards.
- **Visual Summary Template Alignment**: Updated `2. VI SUMMARY TEMPLATE Jinja2 DYNAMIC.docx` table properties (centered alignment, fixed layout, `ADDITIONAL REMARKS` header, `0.4 in` row height, matching column widths) to align with sample report `061. DESA RANGIN INDAH (VI).docx`.

### Changed
- **DocxTemplate Jinja Summary & Defect Rendering**: Refactored `cbm_summary.py`, `vi_summary.py`, and `vi_defect_pages.py` to render native `DocxTemplate` Jinja tags without manual row deletion or empty dict padding.

## [1.5.0] - 2026-08-01

### Added
- **Programmatic Summary Table Generation**: Replaced template Jinja loop rendering in `vi_summary.py` and `cbm_summary.py` with programmatic `python-docx` table creation (`1 + len(defects)` dynamic rows).
- **Shared Table Formatting Helper**: Added `format_table_cell` in `src/quick_report/utils.py` to enforce cell vertical alignment (`w:vAlign="center"`), zero paragraph spacing (`w:before="0" w:after="0"`), horizontal centering (`w:jc="center"`), Tahoma 10pt font, and bold header shading (`#D9D9D9`).

### Changed
- **Smart Commit Audit Workflow**: Audited intermediate commit history (`docs(skills): audit intermediate commits in smart-commit CHANGELOG step`) for automated CHANGELOG logging.

## [1.4.0] - 2026-07-29

### Added
- **Quick Report Generation Engine**: Core 7-part docx report assembly sequence (`src/quick_report/`) supporting front page technology binding (`IR`, `IR+US`, `IR+US+TEV`), CBM tech summary, visual defect pages, and dynamic canonical defect status suffix calculation `(IR+US+TEV+VI)`.
- **WhatsApp Report Generation Workflow**: Deep module workflow (`src/whatsapp/`) to generate automated WhatsApp summary text files and batch inspection summaries from quick report PDF packages.
- **Update QR02 CBA Workflow**: Orchestrated workflow (`src/workflows/update_qr02_cba.py`) that extracts substation metadata from testsheets (`PCE Testsheet`, `PCE VI`) and upserts records into per-station ENGR `QR02 CBA` Excel worksheets.
- **QR02 Master Repository**: Unit-of-work repository (`src/master/qr02.py`) with atomic save transactions, exact FL matching, and ghost cell formatting sanitization.
- **Station-Specific ENGR Path Resolution**: Added 3-letter station abbreviation mapping (`PYTHON/ENGR FROM DRIVE/ENGR-750-36-CBA-<STATION_CODE>-<YEAR>.xlsx`) to `config.py` and `LocalWorkspaceStorage`.

### Changed
- **Quick Report CLI Date Selection**: Updated `QuickReportAction` in `src/project_workflow_actions.py` to use `cli_selectors.select_pahang_date_folder` for interactive 3-tier tree navigation (`STATION` -> `MONTH` -> `DATE`).
- **Quick Report Output Directory Hierarchy**: Updated `QuickReportComposer._resolve_output_dir` in `src/quick_report/composer.py` to output reports at `QUICK REPORT/<STATION>/<MONTH>/<DATE>/`, matching `TESTSHEET/` counterpart folder structure.

### Refactored
- **Fixed-Cell Testsheet Extraction**: Rewrote `TestsheetExtractor` (`src/testsheet/extractor.py`) to use Johor fixed-cell extraction (`W5` FL, `C5` substation name, `P4` cycle 1 date, `C7` site name, `C8` GPS) for reliable data parsing.

### Fixed
- **Quick Report Folder Scope Bug**: Prevented Quick Report engine from recursively auto-generating reports for all date folders across an entire station when a specific date folder is selected.
- **Missing Parent Folder Mirroring**: Fixed issue where Quick Reports were saved directly under `QUICK REPORT/<DATE>` ignoring station and month directories.

## [1.3.0] - 2026-07-29

### Added
- **Standalone Utility Actions Un-stubbing**: Un-stubbed all 11 utility action runners in `src/utility_actions.py` to lazy-load domain workflow modules with interactive directory prompts when no active project is loaded.
- **Standalone Environment Helper**: Added `get_or_create_utility_environment()` in `src/project/environment.py` for transparent active vs. fallback environment resolution.
- **Document Converters Domain Package**: Created `src/postprocessing/converters.py` containing `ComDocumentConverter`, `DocumentConverter`, and `FakeDocumentConverter` for Word/Excel COM PDF exports and PyPDF2 stream merging.
- **Substation Post-Processing Pipeline**: 1-Click automated post-processing pipeline (`src/workflows/postprocessing_pipeline.py`) combining signature replacement, diagonal cell formatting, and PDF package merging.
- **MSMS Domain Package**: Created `src/msms/` (`models.py`, `repository.py`, `__init__.py`) providing `LocalExcelMsmsRepository` to manage `DATA_MSMS.xlsx` operations and Work Order lookups.
- **Update DATA_MSMS Workflow**: Added `src/workflows/update_data_msms.py` to update `DATA_MSMS.xlsx` from ENGR files and sync Work Order (`WO`) columns into `TOTAL_PE.xlsx` via `TotalPeRepository`.

### Refactored
- Moved `converters.py` into `src/postprocessing/` to enforce Deep Module Philosophy and separate technical rendering drivers from high-level workflow orchestrators.

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
