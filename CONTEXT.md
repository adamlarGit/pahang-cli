# Pahang CLI Domain Model Context

This file serves as the ubiquitous language and domain model reference for the Pahang CLI project, establishing shared vocabulary across all workflow modules.

## Concepts

### ProjectMetadata
An immutable domain object (`src/project/models.py`) representing logical Pahang project metadata (`key`, `name`, `po_number`, `state`, `voltage_type`, `technologies`, `base_path`). Validates voltage rating (`11kV` or `33kV`).

### ProjectRepository
An interface (`src/project/repository.py`) providing methods for accessing and persisting `ProjectMetadata` without global mutable state.

### ProjectEnvironment
A composite facade (`src/project/environment.py`) combining `ProjectMetadata` and `WorkspaceStorage`.

### PrpdConfig & PrpdMode
Domain configuration model (`src/project/models.py`) controlling the Phase-Resolved Partial Discharge (PRPD) graph generation strategy across Quick Report CBM defect detail pages.
- **`PrpdMode`**: Supported generation modes:
  - `"option_c"` (Default): High-fidelity composite rendering (1200x380 px) combining the UltraTEV measurement table (`.panel-info`, 320 px) and native Flot PRPD scatter graph (840 px) executed via Headless Chromium / Edge.
  - `"option_b"`: Pure PRPD scatter graph generated via native Python Matplotlib decoding binary FlatBuffers (`eventData.js`, UE01) and JSON acoustic events (`ultrasonic_phase_plot.js`).
- Persisted in `project_config.json` alongside `CameraConfig` via `ProjectRepository.get_prpd_config()` and `save_prpd_config()`. Configurable interactively via CLI Settings menu (`Configure PRPD Graph Style`).

### WorkspaceStorage
A deep module interface (`src/project/storage.py`) acting as the authoritative seam for physical workspace directory (`TESTSHEET/`, `PYTHON/`, `QUICK REPORT/`, `RAW MATERIAL/`, `WHATSAPP/`) and template path resolution.

### PahangStation
Regional station location (e.g. `RAUB`, `KUANTAN`, `CAMERON HIGHLAND`, `BENTONG`, `TEMERLOH`, `PEKAN`).

### MonthFolder
Monthly tracking folder inside station directories strictly formatted as `<INDEX_2DIGITS>. <FULL_MONTH_NAME>` (e.g., `01. JANUARY`, `02. FEBRUARY`, `03. MARCH`, `04. APRIL`, `05. MAY`, `06. JUNE`, `07. JULY`, `08. AUGUST`, `09. SEPTEMBER`, `10. OCTOBER`, `11. NOVEMBER`, `12. DECEMBER`). Enforced via `format_month_folder()`.

### DailyDateFolder
Daily inspection folder inside month folders formatted as `DD-MM-YYYY` (e.g., `01-05-2026`, `09-05-2026`).

### InitialSubstationFolder
The numerical PE subdirectory (`001/`, `002/`, `003/`) created inside `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/` during initial raw material sorting. Contains `RAW DATA/` with `IR/`, `DG/`, and `US+TEV/` subfolders.

### DefectStatusSuffix
Dynamic technology defect indicator suffix appended to Quick Reports, testsheets, and raw material folders during post-processing. Calculated by querying master ENGR worksheets (`QR03 VI` for visual defects -> `"VI"`, `QR03 CBA` for diagnostic defects -> `"IR"`, `"US"`, `"TEV"`). Joined in strict order `(IR+US+TEV+VI)`. If no defects exist, suffix is empty (`""`).

### PahangRenamedSubstationStem
The Pahang-specific Quick Report document, testsheet, and raw material folder naming format:
`<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)` (e.g. `002. RM CHEROH (IR+US+VI)` or `001. SSU CHEROH (VI)` or `005. KUALA SEMANTAN`).
**Pahang Rule**: Omits the 8-digit date string `<DDMMYYYY>` from document and folder stems.

### TestsheetExtractor & TestsheetData
The deep module in `src/testsheet/` (`extractor.py`, `models.py`, `repository.py`) responsible for parsing testsheet Excel workbooks (`PCE Testsheet`, `PCE VI`, `RAW DATA`) and discovering testsheet packages across Pahang's `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/` directory hierarchy.

### RawPhotoRanges
Data schema returned by `TestsheetExtractor` containing start and end photo bounds specifically for Infrared (`IR`) thermal photos and Digital (`DG`) camera photos (`PhotoRange`).

### AutomatedRawMaterialSummary
An immutable domain result schema returned by the Raw Material workflow detailing execution statistics (total PEs processed, copied IR photo count, copied DG photo count, extracted US+TEV survey zip count, warnings, and errors).


### Qr02Repository & LocalExcelQr02Transaction
The deep module in `src/master/qr02.py` implementing per-station ENGR `QR02 CBA` workbook operations with abstract `Qr02Repository` / `Qr02Transaction` interfaces, unit-of-work context manager, exact FL row matching, column updates (GPS, Type, Building Type, Cycle 1 date `DD-MMM-YYYY`, Vendor `"EET"`), atomic tempfile saves (`atomic_save`), and ghost cell cleanup (`_sanitize_ghost_formatting`).

### ENGR Station Code
The 3-letter station abbreviation mapping (e.g. `RAUB` -> `RAU`, `KUANTAN` -> `KTN`) used to resolve per-station ENGR CBA workbook filenames matching `PYTHON/ENGR FROM DRIVE/ENGR-750-36-CBA-<STATION_CODE>-<YEAR>.xlsx`.

### WhatsAppReportWorkflow
The 6-stage ETL pipeline deep module in `src/workflows/whatsapp.py` responsible for scanning `.docx` substation reports in Quick Report date folders, matching substation numbers against `TOTAL PE.xlsx` (`DataCycle1` sheet), formatting inspection dates and station mappings, and rendering WhatsApp report `.docx` files to `PYTHON/WHATSAPP/`.

### UpdateQr02CbaWorkflow
The 6-stage ETL pipeline deep module in `src/workflows/update_qr02_cba.py` responsible for discovering testsheet packages across `TESTSHEET/`, extracting testsheet data records, filtering target packages based on populate mode (`ALL`, `SPECIFIC_FOLDERS`, `AUTO`) and processing history, transforming records into station plans, and upserting QR02 CBA workbook records via `Qr02Repository`.

### QuickReportWorkflow
The 6-stage ETL pipeline deep module in `src/workflows/quick_report.py` responsible for discovering testsheet packages across `TESTSHEET/`, filtering targets, fetching per-station CBM and VI defects from master ENGR workbooks (`QR03 CBA.xlsx` and `QR03 VI.xlsx`), transforming station data into rendering plans with canonical defect status suffixes `(IR+US+TEV+VI)`, rendering multi-part `.docx` templates, and compiling final Word documents.

### SignatureReplacementWorkflow
The deep module in `src/workflows/replace_signatures.py` responsible for processing Excel testsheet signature placeholders (`{{signvendor}}`, `{{signtnb}}`). Supports signature image insertion or explicit `None` placeholder text removal (stripping `{{signvendor}}` and `{{signtnb}}` without inserting drawings to facilitate paper signing), anchor positioning, and worksheet table definition sanitization (`ws._tables.clear()`) prior to saving. Reused by both utility action and `PostProcessingPipelineWorkflow`.

### CombinePdfsWithSeparatorWorkflow
A standalone utility workflow that scans a target folder for PDFs, sorts them in ascending numerical order based on filename leading digits (`001`, `002`), and merges them into a single output PDF with `separator_sheet.pdf` inserted strictly between consecutive PDF files.

### UsTevArchiveMatching
The matching rule for discovering and pairing UltraTEV raw data archives (`.zip` files or directories in `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/UNSORTED RAW DATA/US+TEV/`) to a `SubstationTestsheetPackage`. Evaluates strict PE number token matching across filename delimiters (`_083-`, `_083_`, `083-`, `083_`, `_083.`, `_083`).

### UsTevDestinationFolder
The extracted UltraTEV survey folder created under `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM_3DIGITS>/RAW DATA/US+TEV/<ZIP_STEM>/`. Contains uncompressed instrument survey assets (`index.html`, `survey_metadata.js`, `survey_summary.js`, `resources/`, and equipment directories).

### UsTevCardinalityPolicy
Strict 1-to-1 archive enforcement policy for US+TEV. Each substation PE package must match at most one `.zip` archive in `UNSORTED RAW DATA/US+TEV/`. If multiple matching zip files or ambiguous records are discovered for a single PE number, the workflow raises a validation error to prevent misattribution.

### UsTevResiliencePolicy
Best-effort handling policy when a substation has no matching US+TEV archive in unsorted raw data. The workflow provisions an empty `RAW DATA/US+TEV/` directory, logs a non-blocking warning, and continues processing photos and other packages without halting.

### UsTevIdempotencyPolicy
Clean-overwrite policy for US+TEV destination folders. When extracting a zip archive into `RAW DATA/US+TEV/<ZIP_STEM>/`, if the target `<ZIP_STEM>` directory already exists, it is purged and re-extracted cleanly from source to prevent stale file artifacts.

### SwitchgearSpec & SwitchgearPanelSpec
The canonical switchgear domain model in `src/testsheet/models.py`.
- **Switchgear-Level Specs**: `switchgear_type` (e.g. `AIS`, `GIS`, `RMU`, `SF6`, `VCB`, `OCB`, `MRMU`), `manufacturer`, `model`, `manufactured_year`, `rating` (e.g. `12kV`, `630A` — attached strictly at the switchgear board level, not per panel), `serial_no` (overall board/tank serial number), and `panels: tuple[SwitchgearPanelSpec, ...]`.
- **Multi-Switchgear Support**: `PCE VI` Rows 11–13 hold Switchgear 1, and Rows 14–16 hold Switchgear 2. `SubstationEquipmentPackage` stores `switchgears: tuple[SwitchgearSpec, ...]`.
- **Panel-Level Specs (`SwitchgearPanelSpec`)**: Every switchgear is composed of attached panels/bays. Each panel maintains its own `panel_no` (1..N physical order), `panel_feeder_no` (SCADA panel numbering), `name` (feeder/panel label such as `INCOMING 1`, `TX 1`, `BUS COUPLER`), `panel_type` (`VCB`, `LBS`, `SWITCH`, `TEE-OFF`), `serial_no` (individual breaker serial number if distinct), `status` (`CLOSE`, `TRIP`, `OPEN`), `load_amp` (operating current in Amperes, e.g. `120A`), `cable_type` (e.g. `XLPE 3C 240mm2`), and `heater_amp` (anti-condensation heater current in Amperes, e.g. `0.5A`).

### SubstationEquipmentPackage
The top-level composite equipment domain entity attached to `TestsheetData.equipment`. Bundles all 5 equipment categories:
1. **Environment & Metadata**: `building_type`, `substation_type`.
2. **Switchgear**: `switchgears: tuple[SwitchgearSpec, ...]` (with `switchgear` property pointing to primary unit for backwards compatibility).
3. **Transformers**: `transformers: tuple[TransformerSpec, ...]` (`tx_id`, `rating_kva`, `construction_year`, `manufacturer`, `serial_no`, `type`, `hv_cable_type`, `lv_cable_type`, component thermals). Supports 0 TX (SSU), 1 TX, 2 TX, or up to 4 TX.
4. **LVDB / Feeder Pillar**: `lvdb_specs: tuple[LVDBSpec, ...]` (`name`, `label`, `source`, `manufacturer`, `serial_no`, `rating`, `cable_type`, `feeders: tuple[LVDBFeederSpec, ...]`).
5. **Auxiliary & Safety**: `battery_banks: tuple[BatteryBankSpec, ...]`, `fire_extinguisher: FireExtinguisherSpec`, `has_battery_charger`, `has_rtu`, `has_sf6`, `has_efi`.

### LvdbExtractionAndClassificationPolicy
Classification and naming policy for LVDB / Feeder Pillar:
- **Detection**: Inspect `R48`/`R52` on `PCE Testsheet`. If prefix is `FP` $\to$ Feeder Pillar (`"FEEDER PILLAR"`). If prefix is `LVDB` $\to$ LVDB (`"LVDB"`).
- **Active Unit Detection**: Unit is active if an IR photo number is present in `S49`/`S53`, non-empty manufacturer/serial/rating fields exist, or active feeder cables are populated in rows 45/47.
- **Feeder Cable Extraction**: Rows 44–45 (Slot 1) and Rows 46–47 (Slot 2) parse all 13 incomer and outgoing feeder ways (`IN1..IN3`, `OT1..OT10`) using `FEEDER_CHANNEL_COLUMNS`. Inactive sentinels (`SPARE`, `N/A`, `-`) are omitted. Board-level `cable_type` is resolved from the most common active feeder cable type.
- **Naming Rule**:
  - Single active unit $\to$ `("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE")` or `("LVDB", "LVDB NAMEPLATE")`.
  - Multiple active units $\to$ `Label + Source`: e.g. `("LVDB TX1", "LVDB TX1 NAMEPLATE")` or `("FEEDER PILLAR TX1", "FEEDER PILLAR TX1 NAMEPLATE")` (falling back to sequential index if source is blank).

### TransformerExtractionPolicy
Extraction and counting policy for transformers from `PCE VI` and `PCE Testsheet`:
- **Authoritative Quantity Cell (`C17`)**: The `No of Transformer` cell (`C17`) on `PCE VI` is authoritative.
  - If `C17` has an integer `1..4`, up to that exact quantity of transformer rows are parsed.
  - If `C17` is `N/A`, `0`, empty, or contains non-accessible remarks (e.g. `NOT ACCESSIBLE`), `transformer_count` is 0 and empty tuple `()` is produced.
- **Coordinates on `PCE VI` (Rows 18–21 for Tx 1..4)**:
  - Column `D`: Transformer Type (`type`, e.g. `HERMETICALLY SEALED`, `CONSERVATOR`)
  - Column `F`: Rating (`rating_kva`, already formatted with `kVA`, e.g. `1000kVA`, `750kVA`, `500kVA`)
  - Column `I`: Construction Year (`construction_year`)
  - Column `K`: Manufacturer (`manufacturer`)
  - Column `O`: Serial Number (`serial_no`)
- **Coordinates on `PCE Testsheet` (Rows 33–42)**:
  - HV / LV Cable Types: Parsed from `C33`/`C35` (Tx 1), `C38`/`C40` (Tx 2), `O33`/`O35` (Tx 3), `O38`/`O40` (Tx 4).
  - 5-Point Component Thermal Readings: Parsed across `HT CABLE`, `HT BUSHING`, `LV CABLE`, `LV BUSHING`, `BODY` (Columns F–I for Tx 1/2, Columns R–U / Q–T for Tx 3/4).
- **Accessibility / False-Positive Guard**: If a Tx row or `C17` indicates `NOT ACCESSIBLE`, it is excluded from active testable transformers to prevent false positives in Quick Report condition pages and downstream workflows.

### MissingValuePresentationPolicy
Clear separation between data representation and document presentation:
- **Extractor & Domain Model Representation (Stage 2)**: Missing, empty, or unparseable spreadsheet cells are normalized to empty string `""` (or `None` for optional typed dates/integers) within immutable domain models. Non-fatal extraction warnings are logged where applicable.
- **Document Presentation Representation (Stage 4/5)**: The transformation and rendering stage converts empty string `""` (or missing values) into human-readable dash `"-"` in Jinja template rendering contexts for DOCX / PDF outputs.

### SubstationConditionPairBuilderPolicy
Canonical 2-column condition page generation rules for Quick Report Word output:
- **Singular vs Plural Naming**:
  - 1 Switchgear: `("SWITCHGEAR", "SWITCHGEAR NAMEPLATE")`
  - 2 Switchgears: `("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE")` and `("SWITCHGEAR 2", "SWITCHGEAR 2 NAMEPLATE")`
  - 0 Switchgear: Omitted.
  - 1 Transformer: `("TRANSFORMER", "TRANSFORMER NAMEPLATE")`
  - Multiple Transformers: `(f"TRANSFORMER {i}", f"TRANSFORMER {i} NAMEPLATE")`
  - 0 Transformer (SSU): Omitted.
  - 1 LVDB / FP: `("LVDB", "LVDB NAMEPLATE")` or `("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE")`
  - Multiple LVDB / FP: `(f"{label} {source}", f"{label} {source} NAMEPLATE")`
- **Auxiliary & Safety**:
  - Battery Charger: `("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE")` for 1 unit; `("BATTERY CHARGER 1", ...)` and `("BATTERY CHARGER 2", ...)` for 2 units. Omitted if 0 units.
  - RTU: `("RTU", "RTU NAMEPLATE")` (if present).
  - Fire Extinguisher: Included for `INDOOR` & `ATTACH BUILDING`. Omitted for `OUTDOOR` & `COMPACT` (CS).
- **Indicator Stream Packing**:
  - Dual SF6: `("SF6 INDICATOR 1", "SF6 INDICATOR 2")`
  - Single items (`EFI`, single `SF6 INDICATOR`, odd `TRANSFORMER OIL LEVEL INDICATOR`) are streamed and zipped in pairs.
  - Dual Tx Oil Level: `("TRANSFORMER 1 OIL LEVEL INDICATOR", "TRANSFORMER 2 OIL LEVEL INDICATOR")`
  - 0 Tx Oil Level: Omitted.
  - Unmatched trailing odd items render as a half-pair `(item, "")` with right-cell borders stripped cleanly via `_remove_empty_cell_borders_sub_cond()`.

### PostProcessingPipelineWorkflow
The 6-stage orchestration service in `src/workflows/postprocessing_pipeline.py` managing the post-processing lifecycle under DRY principles. Orchestrates discovery, target scoping, pre-flight file integrity validation, date-level folder renaming synchronization, WhatsApp daily reporting (`by_date` mode), and per-substation deliverable document generation (signature stamping/sanitization, blank cell diagonal borders, COM PDF conversion, and deliverable PDF compilation) into client deliverable packages.

### PreFlightValidationPolicy
Strict fail-fast file count integrity validation policy (`src/workflows/postprocessing_preflight.py`) enforced prior to running post-processing. Requires exact 1:1 matching counts between valid Quick Report Word documents (`.docx`), Excel testsheet workbooks (`.xlsx` only, strictly ignoring auxiliary subdirectories like `processed_testsheet/`, `UNSORTED RAW DATA/`, and temporary lock files `~$`), and Raw Material substation folders across the target daily date directory (`<DD-MM-YYYY>`). Halts execution immediately with diagnostic mismatch reporting if directories are missing, empty, or have divergent item counts.

### BatchComSession
The shared COM application lifecycle context manager in `src/postprocessing/converters.py` (`batch_com_session()`) managing active instances of Microsoft Word and Excel COM servers across a post-processing batch run. Guarantees single-initialization and disposal per batch, standardizes virtual PDF printer configuration (`ActivePrinter`) for uniform sheet scaling, suppresses interactive alerts, and guarantees deterministic process termination via `try...finally` teardown.

### TestsheetImmutabilityPolicy
The data integrity policy governing testsheet modifications during post-processing. Raw inspection workbooks in `TESTSHEET/<DATE>/<STEM>.xlsx` are treated as immutable sources of truth and are never overwritten directly. All post-processing alterations (signature insertion or sanitization, blank cell diagonal line drawing) are written exclusively to working copies located in `TESTSHEET/<DATE>/processed_testsheet/<STEM>.xlsx`.

### SubstationIsolatedBatchResiliencePolicy
Per-substation error isolation policy during batch document post-processing. Failures encountered while converting, signing, or merging documents for an individual substation are trapped, logged, and collected into failure records (`PostProcessingFailure`), allowing remaining valid substations in the queue to continue processing to completion. Final batch status and all individual errors are consolidated into the immutable `PostProcessingSummary`.

### SignaturePlaceholderSanitizationPolicy
The clean placeholder sanitization policy implemented in `src/workflows/replace_signatures.py` when digital signature stamping is omitted or disabled (`mode="none"`). Ensures template tags `{{signvendor}}` and `{{signtnb}}` are cleanly stripped from testsheet cells without inserting image drawings, clearing cell values to prepare pristine blank signature boxes for manual wet-ink physical signing while preventing raw curly-brace template tags from appearing on client deliverables.

### HighFidelityDocumentExportPolicy
The cross-platform document rendering and PDF export fidelity policy governing Quick Report `.docx` and Testsheet `.xlsx` conversions in `src/postprocessing/converters.py`. Enforces:
1. **Dynamic Virtual Printer Discovery**: Standardizes `ActivePrinter` on both `Word.Application` and `Excel.Application` by discovering `Adobe PDF` (preferred driver metrics) or falling back to universal `Microsoft Print to PDF`.
2. **Template OpenXML High Fidelity**: Injects `<w:doNotCompressImages/>` and `<w:defaultImageDpi w:val="0"/>` (High Fidelity) into all `.docx` templates to lock image resolutions against host Word profile downsampling.
3. **Runtime COM Image Compression Suppression**: Enforces `word_app.Options.DoNotCompressImages = True` and `doc.DoNotCompressImages = True` across batch runs.
4. **Native COM Fixed Format Export**: Uses `doc.ExportAsFixedFormat` (`OptimizeFor=0` / `wdExportOptimizeForPrint`, `BitmapMissingFonts=True`, `DocStructureTags=True`) for Word, and `ws.ExportAsFixedFormat` (`Quality=0` / `xlQualityStandard`, `PaperSize=9` A4, `Orientation=2` Landscape) for Excel.
5. **Orientation Partitioning**: Strictly maintains Portrait orientation for Quick Report Word document pages and Landscape orientation for Excel testsheet pages during final client deliverable PDF merging.

