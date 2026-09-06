# Changelog

All notable changes to Pahang CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.15.0] - 2026-09-07
 
### Added
- **Configurable US+TEV PRPD Graph Generation (`src/quick_report/prpd.py`)**: Implemented dual-mode PRPD graph generation supporting Option C (Headless Chromium composite $1200\times380$ px image combining the UltraTEV measurement table and Flot scatter plot) and Option B (Pure PRPD scatter graph via native Matplotlib FlatBuffers and JSON decoders).
- **PrpdConfig Domain Model & Storage Seams (`src/project/models.py`, `src/project/repository.py`, `src/project/environment.py`)**: Added typed `PrpdConfig` dataclass (`mode: "option_c" | "option_b"`) persisted in `project_config.json` alongside `CameraConfig`. Exposed via `get_prpd_config()` and `save_prpd_config()`.
- **Interactive PRPD Style Configuration Submenu (`src/cli_menu.py`, `src/settings_actions.py`, `src/workflow_cli.py`)**: Added `Configure PRPD Graph Style` menu item under Settings allowing operators to switch between Option C (default) and Option B.
- **Resilient Multi-Path Chromium Locator (`src/quick_report/prpd.py`)**: Added `find_chrome_executable()` checking 64-bit, 32-bit, and LocalAppData Google Chrome installations with Microsoft Edge (`msedge.exe`) fallback.
- **Architectural Decision Record (`docs/adr/0001-prpd-graph-generation-strategy.md`)**: Documented context, decisions, and trade-offs for PRPD generation strategies.

### Changed
- **Unified Substation Asset Discovery (`src/quick_report/prpd.py`)**: Extracted `_discover_substation_assets()` helper scanning SWG feeders (with panel number regex extraction and collision resolution) and transformer folders in a single pass, eliminating ~190 lines of duplicate asset crawling across generator paths.

### Fixed
- **Domain Model Typing & Repository Seam (`src/project/models.py`, `src/project/environment.py`, `src/project/__init__.py`)**: Defined `PrpdMode` Literal type alias (`"option_c" | "option_b"`) and immutable `VALID_PRPD_MODES` tuple, strictly typing `PrpdConfig`. Fixed feature envy in `ProjectEnvironment.get_prpd_config()` and `save_prpd_config()` by delegating directly through `self._get_repository()`.
- **Uniform Catalog Schema on Missing Chromium (`src/quick_report/prpd.py`)**: Guaranteed `generate_all_substation_prpd_graphs()` returns a uniform catalog populated with `{"us": None, "tev": None}` for all discovered assets rather than an empty dictionary when Headless Chromium is unavailable.
- **Isolated Option C Render Temp Files (`src/quick_report/prpd.py`)**: Modified `render_prpd_option_c_image()` to write PID- and timestamp-unique temporary HTML files (`_temp_render_c_<pid>_<timestamp>.html`) strictly to `output_dir` rather than raw input survey directories, accompanied by dynamic HTTP handler routing and guaranteed cleanup in `finally`.
- **CBM Defect Page On-Demand Fallback Wiring (`src/quick_report/cbm_render.py`)**: Wired `mode=pe_info.get("prpd_mode", "option_c")` into fallback calls for `generate_prpd_graphs_for_swg_panel()` and `generate_prpd_graphs_for_transformer()`.

## [1.14.7] - 2026-09-07

### Changed
- **Targeted Quick Report Package Discovery (`src/quick_report/extractor.py`)**: Replaced full eager testsheet extraction across all station directories with dual-tier lazy discovery. In FL mode, queries `TOTAL PE.xlsx` header index first to instantly resolve target PE number and date folder (<0.2s), falling back to FL prefix routing (`CRAU` -> `RAUB`, `CKTN` -> `KUANTAN`, etc.) and lightweight metadata parsing (`extract_testsheet_metadata`). Bypasses openpyxl parsing for all non-target project workbooks, reducing discovery runtime from >140s to ~0.4s.
- **Station-Scoped Master ENGR Defect Extraction (`src/quick_report/defects.py`, `src/core/normalizers.py`)**: Added `resolve_station_code` and station-scoped defect loading in `MasterQr03DefectRepository`. Authoritatively loads only the target station's master Excel workbook (`ENGR-750-36-CBA-<CODE>-<YEAR>.xlsx`), caching both `QR03 CBA` and `QR03 VI` DataFrames in memory. Clean/zero-defect substations immediately return empty defect lists without reloading cross-station workbooks, reducing defect extraction from 4.7s to ~0.4s.
- **Word COM Compilation & Teardown Tuning (`src/quick_report/composer.py`, `src/workflows/quick_report.py`)**: Configured `word_app.ScreenUpdating = False` and `DisplayAlerts = 0`. Added `_clear_clipboard()` via Win32 `EmptyClipboard` between part merges, eliminating the 5.0s OLE ActiveX clipboard flush stall upon document close. Added PID tracking (`win32process.GetWindowThreadProcessId`) and safe process termination in `finally` to prevent orphaned background Word processes.

## [1.14.6] - 2026-09-05

### Fixed
- **Multi-Switchgear & Transformer Survey Auto-Discovery (`scripts/generate_prpd_option_c_html.py`, `scripts/generate_prpd_option_b.py`, `src/quick_report/prpd.py`)**: Replaced rigid `SWG` and `TX` folder scanning with dual-layer auto-discovery. Primary discovery parses UltraTEV's native `survey_summary.js` manifest (`assets` -> `$SUB_ASSETS` -> `$MEASURES`), resolving exact paths directly from `"Data"` attributes and supporting `VCB`, `RMU`, `SWG_1..N`, `TX1..TX4`, and outdoor equipment (`H_POLE`, `LIGHTNING_ARRESTER`, `DROPOUT_FUSE`). Fallback dynamic folder traversal crawls all known switchgear and transformer variants when manifests are absent or malformed.
- **Switchgear Feeder & Panel Directory Matching (`src/quick_report/prpd.py`)**: Enhanced `find_swg_feeder_survey_dir` and `_is_survey_dir` to recognize `VCB` and `RMU` switchgear roots alongside `SWG`, with support for hyphenated and zero-padded folder naming formats (e.g. `PANEL-2`, `PANEL-02`, `FEEDER-03`).
- **Temporary Render File Teardown & Label Sanitization (`scripts/generate_prpd_option_c_html.py`)**: Enclosed headless Chrome render operations in `try ... finally` blocks to ensure temporary injected HTML files (`_temp_render_c.html`) are purged reliably, and sanitized asset/panel label names via `re.sub(r"[^\w]+", "_", ...)` to prevent invalid filename characters on Windows.
- **Test Environment Camera Config Isolation (`src/project/environment.py`)**: Fixed `ProjectEnvironment.get_camera_config` fallback so missing `project_config.json` cleanly defaults to standard `CameraConfig()` instead of reading global live `.cli_config.json`, eliminating test isolation leaks.

## [1.14.5] - 2026-09-04

### Fixed
- **Visual Defect Scoping & Cross-Equipment Collision Purge (`src/workflows/populate_data_msms.py`)**: Replaced naive substring keyword matching in `match_vi_defect` with domain-partitioned matching across Groups A–E (Switchgear, Feeder Pillar, Transformer, Secondary, Substation). Resolved critical row 845 regression where `SIGNBOARD` defects wrongfully matched `VI11_SG_LABELLING_RMU` via the substring `"SIGN"`.
- **EET Vendor Boundary Filter (`src/quick_report/defects.py`)**: Filtered `MasterQr03DefectRepository.fetch_vi_defects` to strictly extract records where `REPORT BY` is `'EET'`, preventing over 3,800 third-party contractor rows in master ENGR workbooks from polluting inspection results.
- **Transformer & Feeder Pillar Defect Routing**: Bound `VI11_TX_*` meters strictly to `LTX/DTX` defects with multi-transformer disambiguation (`DTX1` vs `DTX2`), bound `VI11_FP_*` meters strictly to `FP/LVDB` (omitting casing defects), and restricted switchgear earthing to defects explicitly remarked for switchgears.

## [1.14.4] - 2026-09-04

### Fixed
- **Transformer Overview & Detail Location Resolution (`src/quick_report/cbm_render.py`)**: Fixed an issue where the location field on Transformer overview pages erroneously inherited substation `building_type` (e.g. `INDOOR`). Transformer overview location now strictly defaults to `"-"`. Non-HV/LV Transformer detail defect pages (e.g. `BODY`) also default strictly to `"-"` instead of falling back to building type. Added regression tests in `tests/test_quick_report_components.py`.

## [1.14.3] - 2026-09-04

### Added
- **`LVDBFeederSpec` & Feeder Circuit Way Cable Ingestion (`src/testsheet/models.py`, `src/testsheet/extractor.py`)**: Immutable feeder specification capturing `channel` and `cable_type` across all incomer (`IN1..IN3`) and outgoing (`OT1..OT10`) feeder ways from `PCE Testsheet` rows 44–47. Unit-level default `cable_type` derived dynamically from active feeder insulation types.
- **Universal Feeder Channel Resolver (`src/testsheet/feeder_thermal.py`)**: Centralized `resolve_feeder_channel` utility mapping MSMS meter names (`TH_FPIN1_AVG_PE13R`), CBM defect IDs (`FP TX1 - OUTGOING F1`), and standalone bay labels (`OUTGOING F1`, `F1`, `INC 1`) into typed `FeederChannelResolution` with canonical column letters, cable cells, and board temperature coordinates.
- **Transformer Cable Types & 5-Point Component Thermal Ingestion (`src/testsheet/models.py`, `src/testsheet/extractor.py`)**: Explicit `hv_cable_type` and `lv_cable_type` fields on `TransformerSpec` parsed from rows 33/35/38/40, alongside structured 5-point thermal matrices (`ThermalReadingSpec` for HT Cable, HT Bushing, LV Cable, LV Bushing, Body) across Tx 1..4.

### Fixed
- **Feeder Pillar & Transformer Quick Report Cable Type Leakage (`src/quick_report/cbm_render.py`)**: Purged hazardous fallback loop that queried 11kV switchgear panels for Feeder Pillar defect pages, which leaked `NOT ACCESSIBLE` into Feeder Pillar reports whenever switchgear cable trenches were inaccessible. Bound `fp.cabletype` directly to `matched_lv.get_feeder_cable(...)`, and bound `tx.cabletype` directly to `matched_tx.hv_cable_type` or `matched_tx.lv_cable_type`.

## [1.14.2] - 2026-09-03

### Fixed
- **CBM Defect Overview Page Duplication**: Resolved issue where multiple defect rows for an equipment family (e.g. `FP TX1` with multiple feeders `OUTGOING F1`, `OUTGOING F2`, `OUTGOING F3`) generated duplicate overview pages. Canonicalized equipment grouping by equipment family (`_derive_family_group_key` in `src/quick_report/cbm_defect_planner.py`), producing exactly 1 overview page per equipment family followed by all individual defect detail pages in sequence.
- **Individual Defect Phase Preservation**: Refined multi-technology defect merging in `CbmDefectPlanner._merge_defects_by_area` to bucket on `(equipment_id, defect_area, phase)`. Individual defect rows for different phases (e.g. Red Phase vs Yellow Phase) or duplicate technologies are preserved as separate defect cards, while multi-technology measurements (`IR + US + TEV`) for the same defect merge into unified cards as intended.
- **Unicode Dash Resilience for Feeder Pillars & LVDB**: Updated `_build_fp_lvdb_render_context` in `src/quick_report/cbm_render.py` to regex-split on standard hyphens (`-`), en-dashes (`–`), and em-dashes (`—`) to extract `labelsource` and `feederno`.
- **IR Background Temperature Normalization**: Standardized temperature parsing and formatting in `src/core/normalizers.py` (`parse_background_temp`) and `src/quick_report/cbm_summary.py` (`format_temperature_reading`) to format numeric readings as 1-decimal floats with `' °C'` suffix (e.g. `32` → `32.0 °C`, `23.2` → `23.2 °C`), while cleanly handling booleans, sentinels, and invalid inputs.

### Removed
- **Unused Criticality Field Cleanup**: Removed unused `criticality` field from `CbmDefectRecord` in `src/quick_report/defects.py`, deleted unused `_CRITICALITY_PRIORITY` dictionary and resolution logic from `src/quick_report/cbm_defect_planner.py`, and cleaned up test assertions.
- **Domain Terminology Alignment**: Purged non-domain "apparatus" terms from internal variables (`apparatus_groups` → `family_groups`, `apparatus_keys` → `family_keys`) and docstrings, standardizing strictly on `EQUIPMENT`, `EQUIPMENT ID`, and `equipment family`.

## [1.14.1] - 2026-09-03

### Fixed
- **Missing `matplotlib` Dependency in `pyproject.toml` and `uv.lock`**: Added explicit `matplotlib>=3.8.0` dependency to `pyproject.toml` and synchronized `uv.lock` so that downstream client installations running `start_cli.bat` (`uv sync --frozen`) correctly resolve and install all PRPD rendering libraries.

## [1.14.0] - 2026-09-03

### Added
- **Automated PRPD Graph Generation Pipeline (`src/quick_report/prpd.py`)**: Pure-Python PRPD decoder supporting EA Technology UltraTEV Plus2 survey files (`.UE01` FlatBuffers binary decoding and `.json` fallback phase plots), 4-tier repetition density scatter binning (`#00FF00`, `#0000FF`, `#FF0000`, `#640000`), 50Hz zero-crossing sine wave reference overlay, dynamic noise/discharge threshold lines, and matplotlib-rendered 300 DPI high-resolution output charts.
- **UltraTEV Survey Feeder Matching Policy (`src/quick_report/prpd.py`)**: 3-tier hierarchical feeder matching (`feeder_code` exact match -> normalized substring matching -> apparatus type/ordinal fallback), multi-transformer layout resolution (`TX 1` vs `TX 2`), and automatic latest-timestamp survey selection across multiple inspection runs.
- **Testsheet Ultrasound & TEV Measurement Ingestion Schema (`src/testsheet/models.py`, `src/quick_report/cbm_defect_pages.py`)**: Structured schema extraction parsing Switchgear ultrasound (rows 10/14/18/22, cols Q/S/T/U/V for `CB`, `BUSBAR`, `CABLE`, `PT`, `CT`), Switchgear TEV (cols S/U for `CB`, `CABLE`), Transformer ultrasound (rows 33–42, cols K/L/V/X for `HV BUSHING`, `LV BUSHING`, `BODY TANK`, `CONSERVATOR TANK`, `TAP CHANGER`, `CABLE BOX`, `COOLING RADIATOR`), and background TEV reference (cell `P6`).
- **Dynamic OpenXML Severity Shading & Sanitization (`src/quick_report/cbm_render.py`)**: Low-level WordprocessingML table cell shading applying `#EE0000` (bold white text) for defect values exceeding thresholds and `#00B050` (bold white text) for normal/acceptable values, coupled with placeholder literal text stripping across all CBM detail page slots.
- **Part 4 CBM Defect Detail Pages & Context Integration (`src/quick_report/cbm_defect_pages.py`)**: Seamless integration of PRPD graphs as `docxtpl.InlineImage` instances into multi-technology CBM defect detail templates (`DEFECT IR`, `DEFECT IR US`, `DEFECT IR US TEV`), with safe null fallback handling, apparatus label normalization, and dynamic multi-page rendering.
- **Batch Substation PRPD Catalog Generation (`src/quick_report/prpd.py`)**: `generate_all_substation_prpd_graphs()` discovery and batch rendering of all PRPD graphs for switchgears and transformers in a substation workspace with structured catalog lookup.
- **Comprehensive Test Suites & Documentation**: Added unit and E2E integration test suites in `tests/test_prpd_generator.py`, `tests/test_cbm_severity_and_measurements.py`, `tests/test_cbm_defect_pages_integration.py`, and `tests/test_e2e_real_substations.py` (tested against real inspection dataset `020 TRAS`), alongside `docs/prpd_graph_generation_guide.md` and `docs/prpd_option_c_specification.md`.

### Changed
- **Substation RAW DATA Directory Path Resolution (`src/project/storage.py`, `src/quick_report/transformer.py`)**: Added `get_substation_raw_data_dir()` on `WorkspaceStorage` supporting standard station/month/date folder structures as well as flat/unparented date folder layouts, wiring PRPD graphs and raw inspection data directly into `QuickReportTransformer` and `QuickReportComposer`.

## [1.13.1] - 2026-09-03

### Fixed
- **Populate TOTAL PE Scoped Folder Discovery (`src/workflows/populate_total_pe.py`)**: Scoped package discovery directly to target date directories when running in `SPECIFIC_FOLDERS` mode, eliminating whole-tree directory walks and dropping single-folder execution time from ~106s to ~1.2s (~88× faster).
- **Fast Read-Only Testsheet Metadata Extraction (`src/testsheet/extractor.py`)**: Added `extract_testsheet_metadata()` with `openpyxl.load_workbook(path, data_only=True, read_only=True)` to stream only the 6 required header fields (`PE NO`, `FL NUMBER`, `SUBSTATION NAME`, `DATE`, `TYPE`, `WO`) in ~0.06s/file without parsing heavy equipment specifications.
- **Lazy Package Discovery & In-Memory Pre-Filtering (`src/testsheet/repository.py`, `src/master/total_pe.py`)**: Added `eager_extract=False` to `SubstationTestsheetRepository.discover_packages()` and in-memory `(substation_number, date_str)` pre-filtering in `AUTO` mode, coupled with `iter_rows(values_only=True)` streaming in `LocalExcelTotalPeRepository.get_existing_auto_keys()`.

## [1.13.0] - 2026-09-01

### Added
- **6-Stage 1-Click Post-Processing Pipeline (`src/workflows/postprocessing_pipeline.py`)**: Lean orchestrator coordinating pre-flight integrity validation, renaming sync, WhatsApp reporting, testsheet digital signature stamping / `mode="none"` placeholder sanitization, blank cell diagonal borders, and in-place deliverable PDF merging into `QUICK REPORT/<DATE>/<STEM>.pdf`.
- **Pre-Flight Integrity Validator (`src/workflows/postprocessing_preflight.py`)**: Fail-fast validation ensuring symmetric item counts between `QUICK REPORT/`, `TESTSHEET/` (`.xlsx` only, strictly ignoring subdirectories like `UNSORTED RAW DATA/`, `processed_testsheet/`, `pdf/`), and `RAW MATERIAL/` across 3-tier Pahang workspaces (`<STATION>/<MONTH>/<DATE>/`).
- **Shared Batch COM Session Context Manager (`src/postprocessing/converters.py`)**: `BatchComSession` managing single-initialization Word and Excel COM application lifecycles with uniform virtual PDF printer configuration and guaranteed `try...finally` cleanup.
- **Smart Target-Type Renaming Filter (`src/workflows/rename_files.py`)**: Enhanced `rename_files_match` with automatic content sniffing and explicit `target_type` parameters (`testsheet` vs `raw_material`), isolating auxiliary folders and loose files.
- **Per-Substation Batch Error Resilience & Summary Box**: Per-substation error isolation allowing unaffected substations to complete while logging failures, outputting a structured CLI audit summary with metrics and execution timer.
- **Comprehensive Test Suites**: Added 48 new unit and E2E integration tests in `tests/test_com_session.py`, `tests/test_postprocessing_preflight.py`, `tests/test_postprocessing_orchestrator.py`, `tests/test_postprocessing_cli_adapter.py`, `tests/test_postprocessing_pipeline_e2e.py`, and `tests/test_rename_files.py`.

### Changed
- **Testsheet Immutability**: Preserves raw inspection workbooks in `TESTSHEET/<DATE>/` as immutable sources of truth, writing modified working copies strictly to `TESTSHEET/<DATE>/processed_testsheet/`.
- **Ubiquitous Domain Glossary (`CONTEXT.md`)**: Synchronized new domain concepts (`PostProcessingPipelineWorkflow`, `PreFlightValidationPolicy`, `BatchComSession`, `TestsheetImmutabilityPolicy`, `SubstationIsolatedBatchResiliencePolicy`, `SignaturePlaceholderSanitizationPolicy`).

### Removed
- **Dead Code Cleanup**: Purged obsolete converter wrappers, duplicate helpers, and unused imports across workflows.

## [1.12.1] - 2026-09-01

### Changed
- **VI Defect Summary Empty Field Normalization**: Empty or blank spreadsheet values for `EQUIPMENT`, `DEFECT AREA`, and `ADDITIONAL REMARKS` are strictly normalized to `"-"` in VI summary table rows via `_normalize_summary_field` in `src/quick_report/vi_summary.py`.
- **VI Defect Card Description Formatting**: Added `format_vi_defect_description` in `src/quick_report/vi_defect_pages.py` joining non-empty `defect_area` and `remarks` with an en-dash (`" – "`, `\u2013`), cleanly omitting trailing/leading dashes when either field is blank, whitespace, `"-"`, or `"N/A"`.
- **Dynamic VI Defect Template & Context Update**: Updated `build_vi_defect_page_context` to bind pre-formatted `description` and surgically updated `10. VISUAL DEFECT Jinja2 DYNAMIC.docx` to reference `{{ defects[i].description }}` with 100% table cell alignment, font, and XML formatting preservation.

### Added
- **VI Component & End-to-End Test Suite**: Added comprehensive unit and integration tests in `tests/test_quick_report_components.py` validating all description combinations, blank value normalizations, and WordprocessingML table paragraph alignments.

## [1.12.0] - 2026-09-01

### Added
- **Dynamic Multi-Technology CBM Template Resolution**: Integrated `ProjectEnvironment.get_template()` and `WorkspaceStorage.get_cbm_defect_template()` to resolve technology template directories (`DEFECT IR`, `DEFECT IR US`, `DEFECT IR US TEV`) and summary templates (`CBM DEFECT IR SUMMARY.docx`, `CBM DEFECT IR+US SUMMARY.docx`, `CBM DEFECT IR+US+TEV SUMMARY.docx`) dynamically based on project technology set, with fail-fast `FileNotFoundError` validation.
- **Aligned CBM Defect Ingestion (`MasterQr03DefectRepository`)**: Aligned `CbmDefectRecord` and QR03 CBA extraction across standard and fallback columns to extract `equipment_id`, `criticality`, `us_char`, `tev_char`, and exact measurement values.
- **Canonical Equipment Taxonomy & Multi-Tech Defect Planner**: Expanded `QUICK_REPORT_FAMILY_SPECS` with canonical equipment aliases across 5 core families (`swg`, `tx`, `fp_lvdb`, `battery`, `blackbox`). Implemented multi-technology defect merging on `(item_key, defect_area)` and smart HV/LV side routing for transformers in `CbmDefectPlanner`.
- **Enriched Part 2 CBM Technical Summary Table**: Added multi-line apparatus labels (`format_summary_equipment`), combined `DEFECT AREA/ ADDITIONAL REMARKS` formatting, and US characteristic severity mapping.
- **Part 4 CBM Detail Pages & Testsheet Metadata Enrichment**: Enriched detail page render contexts with testsheet equipment specifications (switchgear panel name/feeder code splitting, transformer `HERMETICALLY SEAL` model expansion and rating extraction, LVDB model normalization), guaranteed `"-"` fallbacks, and zero raw Jinja tag leaks.
- **Strict 2-Digit Intermediate Part Ordering**: Standardized all 7 report part prefixes to 2-digit ordered format (`001_01_` through `001_07_`) in `composer.py` and across all page builders.

### Changed
- **Config & Storage Standardization**: Standardized `CBM_DEFECT_TEMPLATES` mapping in `config.py` and updated `LocalWorkspaceStorage._initialize_project_workspace` to copy all CBM defect template directories.

### Removed
- **Dead Code Cleanup**: Purged unused helper functions (`_placeholder_literal`, legacy summary keys) and obsolete fallback branches across `src/quick_report/`.

## [1.11.0] - 2026-08-31

### Added
- **Feeder Pillar Thermal Synthesis (`src/testsheet/feeder_thermal.py`)**: Deterministic thermal synthesis engine for active Feeder Pillar incomers and outgoings using SHA-256 context hashing, indoor ($\pm 0.5^\circ\text{C}$) / outdoor ($\pm 1.0^\circ\text{C}$) jitter, and invariant delta-T ($\Delta T = T_{\text{max}} - T_{\text{ref}} < 1.0^\circ\text{C}$).
- **Active Feeder Cable Gating**: Checks cable type row 45 (FP1) or row 47 (FP2) for active insulation types (`XLPE`, `PILC`, `ABC`, `BUSBAR`, `B/B`), cleanly rejecting inactive sentinels (`SPARE`, `-`, `N/A`, `TIADA`) and leaving unpopulated ways blank.
- **Robust Testsheet Temperature Parsing**: Implemented regex extractor `extract_board_average_temperature()` handling testsheet string formats (`'AVG 28.5'`, `'AVG 34.5'`, `'27.2 °C'`) and native floats from cells `R50`/`R54`.
- **Interactive CLI Controls for Populate Data MSMS**: Added mode selection (`Auto`, `All`, `Select specific folder`) and interactive `Overwrite already filled readings? (y/N)` confirmation to Option 12 in `src/project_workflow_actions.py`.

### Changed
- **Single Decimal Place Quantization (`normalize_for_csv`)**: Enforced exact 1-decimal-place rounding via `Decimal.quantize(ROUND_HALF_UP)` for all numeric float readings in CSV output, eliminating floating point binary precision artifacts (e.g. `0.10000000000000142` $\to$ `0.1`) and formula averages (`39.45` $\to$ `39.5`).

## [1.10.1] - 2026-08-25

### Fixed
- **VI Defect NaN Leak**: Empty Excel cells in QR03 VI produced `"nan"` strings in VI summary and VI defect Word output pages. Root cause: `numpy.nan` is truthy, so `str(val or "")` bypassed the fallback. Extracted `_clean_val()` to module-level with explicit `pd.isna()` guard, shared by both CBM and VI extraction paths.
- **CbmDefectRecord Latent NaN Hole**: `__post_init__` used `(self.field or "").strip()` which also wouldn't catch NaN if constructed directly. Replaced with `_clean_val()` for defense in depth.

## [1.10.0] - 2026-08-22

### Added
- **Substation Equipment Package Domain Models**: Implemented immutable dataclasses `SwitchgearSpec`, `SwitchgearPanelSpec`, `TransformerSpec`, `LVDBSpec`, `BatteryBankSpec`, `FireExtinguisherSpec`, and composite `SubstationEquipmentPackage` in `src/testsheet/models.py`.
- **Comprehensive Testsheet Equipment Extractor**: Single-responsibility OpenPyXL extractor helper methods in `src/testsheet/extractor.py` extracting switchgears (with multi-sheet panel extraction), transformers (authoritative `C17`), active LVDB/FP slots, DC battery banks, and auxiliary flags.
- **Dedicated Room-Based Fire Extinguisher Presentation**: Dynamic per-room fire extinguisher pairs (`FIRE EXTINGUISHER\n(SWITCHGEAR ROOM)`, `FIRE EXTINGUISHER\n(TX ROOM)` / `TX1 ROOM` / `TX2 ROOM`) across Indoor/Attach substations with automatic suppression on Outdoor and CS Compact substations.
- **Dynamic 2-Column Condition Pair Stream Packing**: Implemented dynamic stream packing in `src/quick_report/substation_condition.py` and `QuickReportTransformer` generating canonical condition pair sequences across all substation variants.
- **Substation Condition Table Border Stripping**: Advanced 8-row table border stripping in `_remove_empty_cell_borders_sub_cond()` eliminating leftover border lines on trailing unused card slots, spacer rows, spacer columns, and half-pairs.
- **Comprehensive Test Suites**: Added unit and integration test suites covering equipment domain models, testsheet extractor, condition transformer, and docx generation (`tests/test_testsheet_equipment_models.py`, `tests/test_testsheet_equipment_extractor.py`, `tests/test_substation_condition_transformer.py`, `tests/test_substation_condition_docx.py`).

### Changed
- **Card Header Vertical Centering**: Programmatically and structurally added `<w:vAlign w:val="center"/>` across all substation configuration templates and rendered condition pages.
- **Auxiliary Flags & RTU Detection Logic**: Fine-tuned EFI (supporting both Good and Not Good defect indicators with N/A / MISSING guards), SF6 gas pressure indicators, and linked RTU presence to battery bank installations with Compact / CS substation exceptions.

### Fixed
- **Document Converter Status & File Path Propagation**: Fixed `convert_docx_to_pdf()` in `src/postprocessing/converters.py` to properly handle renamed output PDF filenames and propagate updated `OutputFile` paths back to callers.

### Removed
- **Dead Code & Legacy Branches**: Purged unused imports, obsolete static condition branches, and redundant variables across `src/quick_report/` and test suites.

## [1.9.0] - 2026-08-20

### Added
- **Automated US+TEV Survey Extraction in Raw Material Workflow**: Added automated discovery, tokenized PE matching, and extraction of EA Technology UltraTEV Plus2 survey `.zip` archives from `UNSORTED RAW DATA/US+TEV/` into `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<PE>/RAW DATA/US+TEV/<ZIP_STEM>/`.
- **Strict Tokenized PE Archive Matching (`UsTevArchiveMatching`)**: Implemented robust regex token matching across filename delimiters (`_083-`, `_083_`, `083-`, `083_`, `_083.`, `_083`), with automatic exclusion of `*_Archive.zip` backup bundles.
- **Strict Archive Cardinality & Resilience Policies (`UsTevCardinalityPolicy`, `UsTevResiliencePolicy`, `UsTevIdempotencyPolicy`)**: Enforces 1-to-1 archive pairing per PE (raising `RuntimeError` on ambiguous duplicates), provisions empty directories with non-blocking warnings on missing archives, and guarantees clean directory wipe-and-reextract on re-runs.
- **US+TEV Execution Telemetry & CLI Summary**: Added `us_tev_extracted_count` to `AutomatedRawMaterialSummary` and `RawMaterialResult`, alongside enhanced CLI summary reporting.

### Fixed
- **Combine PDFs With Separator Stream Exhaustion**: Refactored `combine_pdfs_with_separator()` to use `PyPDF2.PdfMerger` instead of raw `PdfReader`/`PdfWriter` stream loops, eliminating open stream handle leaks and preventing page truncation during large 10+ PDF merge batches.


## [1.8.3] - 2026-08-18


### Fixed
- **Word COM Batch RPC Crash (`0x800706BA: The RPC server is unavailable`)**: Hoisted single `Word.Application` COM session initialization above the batch conversion loop in `convert_docx_folder_to_pdf()` (`src/workflows/docx_to_pdf.py`), eliminating per-file `Quit()` process churn, Running Object Table (ROT) race conditions, and RPC disconnect crashes.
- **Batch Excel COM Session Hoisting**: Hoisted `Excel.Application` COM session management in `convert_testsheet_folder_to_pdf()` (`src/workflows/testsheet_to_pdf.py`) with unified `pythoncom.CoInitialize` / `CoUninitialize` and `excel_app.Quit()` in `finally:`.
- **Converter Interface Session Decoupling**: Updated `DocumentConverter.convert_docx_to_pdf()` and `convert_testsheet_to_pdf()` in `src/postprocessing/converters.py` to accept optional `word_app` and `excel_app` parameters for zero-overhead batch session reuse while maintaining safe isolated execution for standalone one-off calls.
- **Pytest Discovery Hygiene & Unit Tests**: Added `__test__ = False` on summary dataclasses and created dedicated unit test suites `tests/test_docx_to_pdf.py` and `tests/test_testsheet_to_pdf.py`.

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
