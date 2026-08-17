# Changelog

All notable changes to Pahang CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.2] - 2026-08-17

### Fixed
- **Camera Photo Pattern Integration in Raw Material Workflow**: Wired `CameraConfig` from `ProjectEnvironment` into `RawMaterialWorkflow` and `RawMaterialFilter`, resolving an issue where Raw Material creation & photo sorting ignored active camera configurations and fell back to hardcoded `FLIR` and `IMG_` prefixes.
- **Dual IR/DC Pair & Custom DG Prefix Photo Filtering**: Implemented `filter_ir_photos` supporting `dual_pair` mode (`IR_` thermal + paired `DC_` visual photo with offset) and `filter_dg_photos` supporting P-series (`P1000`/`P`) and custom prefixes.
- **ProjectEnvironment Camera Configuration Facade**: Added `get_camera_config()` and `save_camera_config()` methods to `ProjectEnvironment` to seamlessly synchronize project workspace camera settings.

## [1.8.1] - 2026-08-17

### Fixed
- **Missing `docxcompose` Dependency**: Declared `docxcompose>=1.4.0` in `pyproject.toml` dependencies and synchronized `uv.lock`, resolving `ModuleNotFoundError: No module named 'docxcompose'` on fresh repository clones and automated `start_cli.bat` environment provisioning.

## [1.8.0] - 2026-08-17
 
### Added
- **Generate TESTSHEET Folder Structure Workflow**: Added 6-stage ETL compliant workflow (`GenerateTestsheetFolderStructureWorkflow` in `src/workflows/generate_testsheet_folder.py`) registered as Action #1 in the Project Workflow menu. Features preflight validation, station & month discovery, date normalization/best-effort filtering, path hierarchy transformation, and safe idempotent provisioning of `<DATE>/UNSORTED RAW DATA/` with `DG/`, `IR/`, and `US+TEV/` subfolders without touching `history.json`.
- **Interactive Station & Month Hierarchy Selectors**: Added `select_or_create_testsheet_station`, `select_or_create_testsheet_month` (with automatic sequential indexing e.g. `01.`, `02.`), and `prompt_target_inspection_dates` with default today date and multi-date comma-separated parsing in `src/cli_selectors.py`.
- **Modular MSMS Workflow Suite**: Added dedicated decomposed workflows in `src/workflows/`:
  - `ConsolidateMsmsWorkflow`: Consolidates `PYTHON/MSMS/*.xls` workbooks into `DATA MSMS.xlsx`.
  - `EnrichMsmsWorkflow`: Enriches `DATA MSMS.xlsx` with substation metadata from `TOTAL PE.xlsx`.
  - `PropagateWoWorkflow`: Propagates Work Orders (WO) from `DATA MSMS.xlsx` back into `TOTAL PE.xlsx`.
  - `IngestMsmsCsvWorkflow`: Ingests MSMS CSV exports from `RAW DATA/` into `TO BE FILLED/`.
  - `PopulateDataMsmsWorkflow`: Populates `TO BE FILLED/` MSMS CSVs from testsheets.
- **Unit of Work & Repository Infrastructure**: Added `TotalPeRepository` and `MsmsRepository` under `src/repositories/` alongside `src/msms/repository.py`.
- **Canonical Testsheet Mapping**: Added `TestsheetMapper` in `src/testsheet/mapper.py` for canonical equipment and reading mappings.
- **Dynamic Substation Condition Configuration Templates**: Added template docx configurations (`CS WITH TX.docx`, `CS WITHOUT TX.docx`, `OD 1 TX 1 FP 1 BATTERY.docx`) in `templates/QUICK REPORT/SUBSTATION CONFIGURATION/`.
- **Comprehensive Unit & Integration Test Suites**: Added unit and E2E integration test suites covering domain models, pipeline stages, selectors, actions, MSMS operations, and workspace storage (`tests/test_generate_testsheet_folder_*.py`, `tests/test_consolidate_msms.py`, `tests/test_enrich_msms.py`, `tests/test_ingest_msms_csv.py`, `tests/test_populate_data_msms.py`, `tests/test_propagate_wo.py`, `tests/test_testsheet_mapper.py`, `tests/test_workspace_storage.py`).

### Removed
- **Monolithic MSMS Workflow**: Purged deprecated monolithic `src/workflows/update_data_msms.py`.

## [1.7.2] - 2026-08-13

### Fixed
- **Substation Condition & Visual Defect Blank Page Prevention**: Fixed blank page generation between Substation Condition pages (Part 5) and Visual Defect pages (Part 6) by stripping trailing `<w:sectPr>` section breaks and `<w:br w:type="page"/>` manual page breaks injected by `docxcompose` from the merged condition document's final paragraph prior to Word COM compilation.
- **Substation Condition Pair Card Labels**: Standardized condition pair card image headers to full verbose labels (e.g. `SWITCHGEAR 1 NAMEPLATE`, `TRANSFORMER 1 NAMEPLATE`, `FEEDER PILLAR 1 NAMEPLATE`, `BATTERY CHARGER NAMEPLATE`, `RTU NAMEPLATE`, `EFI / SF6 GAS INDICATOR`, `FIRE EXTINGUISHER EXPIRY DATE`, `TRANSFORMER OIL LEVEL INDICATOR`).

### Refactored
- **Shared DOCX Table Cell XML Utilities**: Consolidated duplicate `_clear_cell_text` and `_set_cell_no_borders` cell XML functions from `vi_defect_pages.py` and `substation_condition.py` into shared public helpers `clear_cell_text()` and `set_cell_no_borders()` in `src/quick_report/utils.py`.
- **Dynamic Builder Preservation**: Documented future-use reservation on `build_substation_condition_pairs()` in `substation_condition.py` for upcoming dynamic pair configuration logic.

## [1.7.1] - 2026-08-13

### Fixed
- **Visual Inspection (VI) Defect Page Blank Rendering**: Updated `generate_vi_defect_pages()` to render directly via `DocxTemplate` using raw dictionary context (bypassing `_render_docx_template` and `QuickReportContext` string wrapping) so empty/null values render as clean blank cells instead of `"-"`.
- **VI Defect Card Slot Padding & Key Alignment**: Updated `build_vi_defect_page_context()` to pad `context["defects"]` list to 6 items (`DEFECTS_PER_PAGE`) with empty dicts and populate flat slot variables (`equipment1..6`, `description1..6`, `remark1..6`). Updated `ViDefectRecord.to_dict()` to output key `"remarks"` mapping `additional_remarks` to match template tag `{{ defects.remarks }}`.
- **Word COM Batch Process Exhaustion & Fail-Fast**: Hoisted single `Word.Application` COM session creation above the batch loop in `QuickReportWorkflow.execute()`, avoiding per-substation process churn, handle/thread exhaustion, and `Normal.dotm` lock race conditions. Added fail-fast check if COM fails to initialize, early exit for 0 packages, and `gc.collect()` after `Quit()` in `finally`.
- **Date Formatting Standardization**: Standardized Quick Report date formatting to `DD MMM YYYY` (UPPERCASE, e.g. `12 AUG 2026`) for front page and `DD/MM/YYYY` (e.g. `12/08/2026`) for CBM defect pages in `src/core/normalizers.py`.

### Refactored
- **Composer COM Lifecycle Decoupling**: Removed `own_word` fallback path from `QuickReportComposer._compile_document()` so `word_app` is required, and purged unused `pythoncom`/`win32com` imports.

## [1.7.0] - 2026-08-12

### Added
- **Combine PDFs With Separator Workflow**: Added `CombinePdfsWithSeparatorWorkflow` (`src/workflows/combine_pdfs_with_separator.py`) to merge PDF packages with blank separator pages.
- **Signature Replacement & Diagonal Borders**: Added `ReplaceSignaturesWorkflow` (`src/workflows/replace_signatures.py`) and diagonal borders workflow (`src/workflows/diagonal_borders.py`).
- **Standalone Utility Workflows & Unit Tests**: Added unit tests for PDF separators (`tests/test_combine_pdfs_with_separator.py`), converters (`tests/test_converters.py`), diagonal borders (`tests/test_diagonal_borders.py`), signature replacement (`tests/test_replace_signatures.py`), and Word COM composer (`tests/test_quick_report_composer_com.py`).
- **Workflow Documentation & Visualizations**: Added workflow documentation and HTML interactive flowcharts (`docs/research_cli_comparison.md`, `docs/cbm_defect_pages_workflow.html`, `docs/quick_report_workflow.html`).

### Fixed
- **Word COM Document Compilation (`AttributeError: Open.Content`)**: Fixed document compilation failure during batch runs (e.g. substation KUANTAN) by strictly enforcing Word COM `word.Documents.Add()`, read-only `part_doc = word.Documents.Open(part_path, False, True)`, `part_doc.Content.Copy()`, `rng.InsertBreak(7)` section breaks, `rng.Paste()`, and `main_doc.SaveAs2(output_path)` per `docs/workflows/cbm_flir_activex_fix.md`.

### Refactored
- **Batch Word COM Session Reuse**: Updated `QuickReportWorkflow.execute()` to pre-initialize a single `Word.Application` COM session across the entire batch run, eliminating process startup overhead and asynchronous `Quit()` file lock conflicts (`PermissionError`).
- **Dead Code Cleanup & No Silent Fallbacks**: Completely removed `docxcompose` dependency/imports and dead fallback branches from `QuickReportComposer` to maintain strict code hygiene and fail fast if `win32com` is missing or fails.

## [1.6.0] - 2026-08-03

### Refactored
- **Typed Page Builders**: Introduced `CbmDefectPagePlan`, `CbmDefectPageBuilder`, `ViDefectPagePlan`, and `ViDefectPageBuilder` to decouple page order, filename formatting, and context building from DOCX rendering.
- **Strict Record Invariants**: Enforced `CbmDefectRecord` field invariants in `__post_init__` (technology uppercasing, string trimming, bidirectional reading synchronization).
- **Typed Summary Rows**: Added `CbmSummaryRow` and `ViSummaryRow` immutable dataclasses, making `prepare_tech_summary_rows` and `prepare_vi_summary_rows` strictly typed-only.
- **Purged Legacy Dict Fallbacks**: Completely eliminated `_payload_get()`, `_get_field()`, and `hasattr`/`isinstance(d, dict)` fallback checks across rendering modules.
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
