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
A deep module interface (`src/project/storage.py`) acting as the authoritative seam for physical workspace directory (`TESTSHEET/`, `PYTHON/`, `QUICK REPORT/`, `FULL REPORT/`, `RAW MATERIAL/`, `WHATSAPP/`) and template path resolution.

### PahangStation
Regional station location (e.g. `RAUB`, `KUANTAN`, `CAMERON HIGHLAND`, `BENTONG`, `TEMERLOH`, `PEKAN`).

### MonthFolder
Monthly tracking folder inside station directories strictly formatted as `<INDEX_2DIGITS>. <FULL_MONTH_NAME>` (e.g., `01. JANUARY`, `02. FEBRUARY`, `03. MARCH`, `04. APRIL`, `05. MAY`, `06. JUNE`, `07. JULY`, `08. AUGUST`, `09. SEPTEMBER`, `10. OCTOBER`, `11. NOVEMBER`, `12. DECEMBER`). Enforced via `format_month_folder()`.

### DailyDateFolder
Daily inspection folder inside month folders formatted as `DD-MM-YYYY` (e.g., `01-05-2026`, `09-05-2026`). In the CLI and workflows, operators select an existing inspection date folder from `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/`. The folder name itself represents the canonical date of the inspection run.

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

- **Canonical 7-Part Document Sequence**:
  The document assembly sequence executed by `QuickReportComposer`:
  1. **Part 1: Front Page**: Substation metadata, PO number, crew and calibration details, and PE signboard photo.
  2. **Part 2: CBM Defect Summary**: Tabular overview of diagnostic defects across IR, US, and TEV. Generated only when CBM defects exist.
  3. **Part 3: VI Defect Summary**: Tabular kejanggalan inventory from the visual inspection checklist. Generated only when VI defects exist.
  4. **Part 4: CBM Defect Detail Pages**: In-depth diagnostic defect reports (SWG, TX, FP, Blackbox, Battery) with thermal crosshairs, parameter tables, and PRPD graphs. Generated only when CBM defects exist.
  5. **Part 5: Substation Condition Pages**: 2-column condition photo pairs capturing physical substation and asset baseline state.
  6. **Part 6: VI Defect Detail Pages**: 2-column photo grid documenting each observed visual defect with callouts and captions. Generated only when VI defects exist.
  7. **Part 7: Sticker Page**: On-site normal condition sticker and defect notification stickers.

- **Deprecation of "Visual Report"**:
  "Visual Report" is an obsolete legacy colloquialism that arose when early versions of the generator only handled visual defects. The canonical deliverable is strictly named **Quick Report**. Visual inspection defect deliverables are canonically defined as **VI Defect Summary** (Part 3) and **VI Defect Detail Pages** (Part 6) (collectively, "VI Defect Findings"). Code, CLI presentation labels, and documentation must avoid the term "Visual Report".

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
- **Panel-Level Specs (`SwitchgearPanelSpec`)**: Every switchgear is composed of attached panels/bays. Each panel maintains its own `panel_no` (1..N physical order), `panel_feeder_no` (SCADA panel numbering), `name` (feeder/panel label such as `INCOMING 1`, `TX 1`, `BUS COUPLER`), `panel_type` (`VCB`, `LBS`, `SWITCH`, `TEE-OFF`), `serial_no` (individual breaker serial number if distinct), `status` (`CLOSE`, `TRIP`, `OPEN`), `load_amp` (operating current in Amperes, e.g. `120A`), `cable_type` (e.g. `XLPE 3C 240mm2`), `heater_amp` (anti-condensation heater current in Amperes, e.g. `0.5A`), and sub-row chamber photo attributes: `cable_photo`, `breaker_photo`, `secondary_photo`, `busbar_photo`, `pt_photo`, and `has_pt_measurement`.

### SubstationEquipmentPackage
The top-level composite equipment domain entity attached to `TestsheetData.equipment`. Bundles all 5 equipment categories:
1. **Environment & Metadata**: `building_type`, `substation_type`.
2. **Switchgear**: `switchgears: tuple[SwitchgearSpec, ...]` (with `switchgear` property pointing to primary unit for backwards compatibility).
3. **Transformers**: `transformers: tuple[TransformerSpec, ...]` (`tx_id`, `rating_kva`, `construction_year`, `manufacturer`, `serial_no`, `type`, `hv_cable_type`, `lv_cable_type`, component thermals). Supports 0 TX (SSU), 1 TX, 2 TX, or up to 4 TX.
4. **LVDB / Feeder Pillar**: `lvdb_specs: tuple[LVDBSpec, ...]` (`name`, `label`, `source`, `manufacturer`, `model`, `serial_no`, `rating`, `cable_type`, `feeders: tuple[LVDBFeederSpec, ...]`).
5. **Auxiliary & Safety**: `battery_banks: tuple[BatteryBankSpec, ...]`, `fire_extinguisher: FireExtinguisherSpec`, `has_battery_charger`, `has_rtu`, `has_sf6`, `has_efi`.

### LvdbExtractionAndClassificationPolicy
Classification and naming policy for LVDB / Feeder Pillar:
- **Detection**: Inspect `R48`/`R52` on `PCE Testsheet`. If prefix is `FP` $\to$ Feeder Pillar (`"FEEDER PILLAR"`). If prefix is `LVDB` $\to$ LVDB (`"LVDB"`).
- **Active Unit Detection**: Unit is active if an IR photo number is present in `S49`/`S53`, non-empty manufacturer/model/serial/rating fields exist, or active feeder cables are populated in rows 45/47.
- **Feeder Cable Extraction**: Rows 44–45 (Slot 1) and Rows 46–47 (Slot 2) parse all 13 incomer and outgoing feeder ways (`IN1..IN3`, `OT1..OT10`) using `FEEDER_CHANNEL_COLUMNS`. Inactive sentinels (`SPARE`, `N/A`, `-`) are omitted. Board-level `cable_type` is resolved from the most common active feeder cable type.
- **Naming Rule**:
  - `Label + Source`: Formatted as `f"{label} {source}".strip()` (e.g. `LVDB TX1`, `FP TX1`, `FP1 TX1`, `FP2 TX2`). `label` normalizes index spacing (e.g. `FP 1` $\to$ `FP1`), and `source` falls back to `TX1` (slot 1) or `TX2` (slot 2) if blank.
  - **Model**: Extracted from cells `V48` (slot 1) and `V52` (slot 2) (e.g. `J-SLOTTED`, `DIN TYPE`) and populated onto `LVDBSpec.model`.

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

### CbmDefectDetailSwitchgearPolicy
Domain rendering rules governing switchgear panel CBM defect detail pages (`swg-panel.docx`):
- **Anti-Condensation Heater (`panel.heateramp`)**:
  - For `VCB` switchgear: Formatted strictly as `"ON:{amp}A/OFF:0.0A"`, where `{amp}` is normalized to a 2-decimal float using half-up rounding (e.g., `0.3` $\to$ `0.30`, `0.58` $\to$ `0.58`, `0.65` $\to$ `0.65`, `1` $\to$ `1.00`, `0` $\to$ `0.00`, stripping any trailing `"A"`/`"a"` or whitespace). The `OFF` state strictly remains `OFF:0.0A`. If cell H in `PCE Testsheet` is unpopulated, empty, `"-"`, or `"N/A"`, it outputs `"-"`.
  - For Non-VCB switchgear (`RMU SF6`, `RMU OIL`, `MRMU`, `OCB`): Strictly outputs `"-"` because these switchgear types do not have anti-condensation heaters.
- **Load Current (`panel.loadamp`)**:
  - Formatted strictly as an integer (whole number string without trailing decimal points or `"A"` suffix, e.g. `17.0` $\to$ `"17"`, `150A` $\to$ `"150"`, `0.0` $\to$ `"0"`). Returns `"-"` if empty, unpopulated, or non-numeric.
- **Ultrasound Characteristic Presentation (`us.char` / `panel.us.char`)**:
  - On CBM defect detail pages displaying ultrasound measurements (switchgear panels and transformers), an unspecified characteristic defaults to `"NORMAL"` instead of `"-"`. Standard shorthand defect codes (`C` $\to$ `CORONA DISCHARGE`, `T` $\to$ `TRACKING`, `A` $\to$ `ARCING`, `MV` $\to$ `MECHANICAL VIBRATION`) are preserved and expanded. CBM summary table severity remains untouched (only populated when an active defect characteristic is present).
- **Busbar Position (`panel.busbarposition`)**:
  - For `VCB` switchgear: Defaults to `"MAIN"`. If the panel name contains `"TRANSITION"` (e.g., `"TRANSITION PANEL"`), it outputs `"-"`.
  - For Non-VCB switchgear (`RMU SF6`, `RMU OIL`, `MRMU`, `OCB`): Strictly outputs `"-"`.
- **Panel Serial Number (`panel.serialnumber`)**:
  - For `RMU SF6` and `MRMU` switchgear: Panels share the switchgear serial number from Column O in `PCE VI` sheet (`swg.serialnumber`). In `TestsheetExtractor` (Stage 2), `swg1_serial` propagates to attached panels with blank serial numbers onto `SwitchgearPanelSpec.serial_no`.
  - For `VCB` and `RMU OIL` switchgear: Panel serial numbers represent individual breaker or OLU serial numbers extracted from Column I in `PCE Testsheet` (`"SERIAL NO (ONLY BREAKER & OLU)"`).
  - Document Presentation (Stage 4/5): `panel.serialnumber` consumes `matched_panel.serial_no`. If a panel serial number is missing, unpopulated, or unlinked (`matched_panel is None`), `panel.serialnumber` resolves to `"-"`.

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

### FlirActiveXIsolationPolicy
The architectural rule governing Quick Report compilation in `src/quick_report/composer.py`. Mandates that multi-part documents containing FLIR Tools+ ActiveX controls (`CIRViewer`) merge through Microsoft Word COM Automation (`Documents.Add()`, read-only part opening, clipboard copy, page break, and paste). Prohibits pure Python OpenXML concatenation (`docxcompose`, `python-docx`) to prevent control identifier collisions and binary compound file corruption.

### ReportTarget
The polymorphic target identifier accepted by `QuickReportWorkflow` entry points (`generate()` and `inspect()`). Supports `Path` (direct folder path), bare date string formatted as `DD-MM-YYYY` matching an inspection date folder, a single Functional Location string (e.g. `"CCHL/PCE/J00059"`), a comma-separated FL string (e.g. `"CCHL/PCE/J00059, CCHL/PCE/J00060"`), or a `Sequence[str]` / `Sequence[Path]` of dates, paths, or FLs. Disambiguates folder vs. FL modes strictly based on directory existence or calendar date format matching.

### QuickReportInspection & SubstationInspectionItem
Immutable dry-run telemetry models (`src/workflows/models.py`) returned by `QuickReportWorkflow.inspect()`. Captures proposed substation output stems, defect counts, target deliverable paths, station identifiers, missing template diagnostics, and warnings without initializing Word COM automation or performing disk writes.

### DocumentCompiler
The abstract compilation interface (`src/quick_report/compiler.py`) isolating Microsoft Word COM automation from document composition. Implemented by `WordComDocumentCompiler` for production multi-part assembly via Word COM automation, and `FakeDocumentCompiler` for rapid, headless unit testing without external COM dependencies.

### MultiStationSelectionPolicy
The presentation policy governing Quick Report batch generation when an inspection date spans multiple stations. Presents all matching stations pre-selected by default in an interactive CLI checkbox prompt (`cli_selectors.select_multiple`), and delegates batch compilation of selected stations through a single Word COM session via `QuickReportWorkflow.generate(target, station=chosen_stations)`.

### FullReportDocument
The exhaustive asset census report deliverable (`CONDITION BASED ASSESSMENT FULL SCANNING REPORT`). In contrast to the exception-oriented defect brief of `QuickReportDocument` (which captures only anomalous equipment and baseline condition), `FullReportDocument` documents every inspected asset across the substation regardless of condition. Adheres to the sibling directory convention `FULL REPORT/<STATION>/<MONTH>/<DATE>/` (using `PahangRenamedSubstationStem`) and is assembled through an independent, decoupled post-processing pipeline. Detailed domain analysis and specifications are established in `docs/full_report_domain_analysis.md`.

### ExecutiveSummaryCensus
The comprehensive asset inventory domain model in `FullReportDocument`. Lists every bay, panel, cable, and bushing across the substation with color-coded operational status: Green for `NORMAL` (healthy components) and Red for `DEFECT` (anomalous components with test readings populated). Column 0 (`NO.`) groups sub-rows by major equipment category (`Switchgear`, `Transformer 1`, `Transformer 2`, `Feeder Pillar / LVDB`, `Battery Bank`) via OpenXML vertical merge (`<w:vMerge>`) carrying integer group labels (`1.`, `2.`, `3.`). Measurement cells reuse Quick Report formatting (`format_temperature_reading`, `format_db_reading`), and severity cells have text cleared with background fill (`00B050` or `EE0000`).

### TransformerHvCableSplitPolicy
The domain generation rule established in ADR 0004 governing Transformer High Voltage terminations. Unconditionally provisions an `HV CABLE SPLIT` row in Executive Summary Table 2 and a dedicated 4-quadrant scanning page (`tx-hv-sides.docx`) for each active transformer via `has_hv_cable_split(tx) -> True`, providing contractually complete 7-point transformer scanning records while safely falling back to blank image placeholders if secondary split photos were not taken on site.

### QuickReportIngestionSeam
The ingestion boundary defined by `DocumentSlicer(Protocol)` and implemented by production `WordComDocumentSlicer` (with `FakeDocumentSlicer` for headless unit testing) responsible for slicing completed sections from the finalized Quick Report Word document into modular intermediate parts (`temp_parts/front_page.docx`, `vi_summary.docx`, `cbm_defects/`, `condition_pages.docx`, `vi_defect_pages.docx`, `sticker_page.docx`). Uses Word COM Automation with forward-scoped paragraph boundary detection (`"SUBSTATION CONDITION"`, `"VISUAL DEFECT"`, `"NORMAL/DEFECT STICKER"`) to guarantee 100% preservation of inspector DrawingML callouts, red boxes, and FLIR Tools+ ActiveX controls without false-positive heading collisions. Title transformation (`QUICK` -> `FULL`) is executed via native Word COM Find & Replace during front page slicing.

### CbmDefectHeaderParser & D37 Naming Grammar
The CBM defect detail page inspection and metadata extraction service (`src/full_report/defect_parser.py`). Parses Table 1 from individual sliced CBM defect pages (`docx.table.Table` or 2D matrix) across Switchgear, Transformer, Feeder Pillar, and Battery Bank templates, extracting equipment category, instance, physical sequence (`p04`, `f02`, `s01`, `p00`), canonical equipment/panel ID (e.g. `CKN01309`), defect area (e.g. `FUSE_COMPARTMENT`), and severity. Generates standardized, fine-tuned left-to-right naming tokens adhering strictly to D37 grammar (`{eq_instance}_{seq}_{id}_{area}_{idx}.docx`), and saves sliced parts under `temp_parts/cbm_defects/` with automatic duplicate index incrementing (`_01`, `_02`) for downstream inline interleaving.

### CanonicalFullReportReferenceSamples
The ground-truth benchmark deliverables and source data sets used for deterministic Full Report development, verification, and regression testing:
1. `005. TALAPIA (IR+VI)`: PE 5 (`CRAU/PCE/J00251`), Raub Week 32 (04-Aug-2026), IR thermal hotspot on FP fuse contact + visual defects, 68 raw IR thermal/visual photo pairs.
2. `179. CENDERAWASIH NO.1 (IR+VI)`: PE 179 (`CKTN/PCE/J00030`), Kuantan Week 35 (28-Aug-2026), IR thermal hotspot in RMU TX fuse compartment + visual defects.
3. `144. TELEKOM TANAH PUTIH (TEV+VI)`: PE 144 (`CKTN/PCE/J00040`), Kuantan Week 35 (24-Aug-2026), severe internal TEV partial discharge across all 4 switchgear panels with PRPD scatter plot waveforms.
Both the manual reference deliverables (`FULL REPORT/...`) and their corresponding finalized Quick Reports (`QUICK REPORT/...`), testsheets (`TESTSHEET/...`), and raw data reside in the active project base path `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD`.

### SwitchgearArchetype
The 6 canonical hardware archetypes (`src/core/topology.py`) modeling physical switchgear chamber configurations and dynamic scanning requirements:
1. `VCB_CUBICLE`: Vacuum Circuit Breaker modular cubicles (e.g., Schneider Blokset, Tamco HV, ABB Uniswitch) with 4-5 chambers per bay (Breaker, Cable, Busbar, Secondary, and conditional PT).
2. `GIS_CUBICLE`: Gas-Insulated Switchgear cubicles (e.g., Siemens 8DA/8DB) sharing the multi-chamber cubicle topology.
3. `RMU_DUAL_CABLE_ENTRY`: Compact Ring Main Units with dual cable terminations per panel (e.g., Tamco Ringmaster/GR1, Lucy VRN2a SF6/Sabre), provisioning both `CABLE COMPARTMENT` and `CABLE ENTRY`.
4. `RMU_FUSE_CANISTER`: Ring Main Units featuring fuse canisters for transformer protection (e.g., Indkom INS24), provisioning `CABLE COMPARTMENT` for outgoing feeders and `FUSE COMPARTMENT` for transformer bays.
5. `RMU_OIL`: Legacy oil-insulated Ring Main Units (e.g., Lucy VRN2a Oil, OCB).
6. `RMU_STANDARD`: Generic Ring Main Units (e.g., Indkom JMW12, MRMU, standard SF6 RMUs) provisioning single `CABLE COMPARTMENT` per panel.

### VoltageClass
The normalized electrical voltage seam (`src/core/topology.py`) classifying board operating voltages into standard categories:
- `11kV` (`KV_11`): Distribution standard, typically requiring single Overview page.
- `33kV` (`KV_33`): Sub-transmission standard, requiring dual Overview pages (Front + Rear).
- `22kV` (`KV_22`): Intermediate distribution voltage.
- `6.6kV` (`KV_6_6`): Industrial / legacy distribution voltage.
- `LV` (`LV`): Low voltage switchgear.

### BayRole
The functional panel operational role classifier (`src/core/topology.py`) determining bay-level chamber layout:
- `STANDARD`: Outgoing lines, incomers, spares, and regular feeder panels.
- `TRANSFORMER`: Bays connected to local transformers (`TX`, `TRANSFORMER`, `ALATUBAH`, `TEE-OFF`, `FUSE`, `KVA`).
- `TRANSITION`: Bus transition and tool chambers (`TRANSITION`, `PERALIHAN`, `TRANSISYEN`, `TOOLS`). Transition bays never provision PT compartments.
- `BUS_SECTION`: Busbar sectioning bays (`BUS SECTION`, `BUS SEC`, `B/S`, `SECTION`).
- `BUS_COUPLER`: Bus coupling bays (`BUS COUPLER`, `COUPLER`, `B/C`).

### SwitchgearTopologyEngine
The two-phase resolution engine (`src/core/topology.py`) providing pure, COM-free deterministic compartment and layout resolution:
- **Phase 1 (Board Macro Classification)**: Evaluates switchgear type, manufacturer, model, and rating to classify the lineup into its `SwitchgearArchetype`, `VoltageClass`, and board-level `overview_compartments` (`OVERVIEW`, `OVERVIEW TOP`, `OVERVIEW BOTTOM`).
- **Phase 2 (Bay Dynamic Resolution & Presence Gates)**: Evaluates individual panel role (`classify_bay_role`) and empirical evidence gates:
  - `eval_pt_gate`: Enables `PT COMPARTMENT` only when sub-row r+3 contains valid photo evidence (`pt_photo`) or non-empty measurement data (`has_pt_measurement`).
  - `eval_secondary_gate`: Pure photo presence gate for transition bays checking Column P (`secondary_photo`), completely independent of heater current.

### StrictZeroFallbackPolicy
The data integrity and evidence preservation invariant governing Full Report photo pairing. Enforces strict 1-to-1 matching between thermal/visual inspection photos and scanning page placeholders. Prohibits artificial duplication or placeholder cloning across compartments when empirical evidence was not captured on-site, ensuring zero photo duplication across report deliverables.

### PlanDocumentChunk
The immutable planned document fragment model (`src/full_report/plan_builder.py`) representing an individual Word output deliverable in a multi-part Full Report compilation plan. Encapsulates `chunk_index` (1-based sequence), `label` (human-readable chunk description such as `Part 01 - Summary`, `Part 02 - Panel 1 (INCOMING 1)`, `Part 07 - TX and Condition`), `output_filename` (zero-padded filename `<STEM> - Part {XX} - {label}.docx`), `destination_path` (resolved absolute output path in the date folder), and `parts: tuple[PlanPartItem, ...]` (ordered sequence of template slices and rendered pages belonging to this chunk).

### MultiPartPartitionPolicy
The domain partitioning rule (`src/full_report/plan_builder.py`) governing multi-part Full Report Word document splitting based on switchgear hardware archetype:
- **`VCB_CUBICLE` & `GIS_CUBICLE`**: Automatically partitions the planned Bill of Materials into modular, lightweight Word documents:
  - **Chunk 1 (`Part 01 - Summary`)**: Front Page, Executive Summary Census, Visual Defect Summary, and Switchgear Overview pages.
  - **Chunks 2..N+1 (`Part {XX} - Panel {no} ({name})`)**: Individual bay files containing per-panel chamber scan pages (Breaker, Cable, Busbar, Secondary, PT) and any inline CBM defect pages (such as TEV PRPD scatter plots or IR hotspots) attached directly behind their parent panel.
  - **Chunk N+2 (`Part {N+2:02d} - TX and Condition`)**: Balance of plant assets including Transformers, LVDB / Feeder Pillar, Battery Bank, Substation Condition photo grid, Visual Defect detail pages, and Sticker page.
- **Standard RMU Switchgear** (`RMU_STANDARD`, `RMU_DUAL_CABLE_ENTRY`, `RMU_FUSE_CANISTER`, `RMU_OIL`): Emits exactly one chunk containing all planned parts with default `<STEM>.docx` destination filename, preventing unnecessary partitioning on low-page-volume RMU reports.

### MultiPartDocumentDeliveryPolicy
The architectural deliverable policy established in ADR 0005 separating intermediate field inspection Word documents from final client deliverable files. For VCB and GIS switchgear, intermediate Word files are retained permanently in the substation date folder (`FULL REPORT/<STATION>/<MONTH>/<DATE>/`) as modular panel documents so field inspectors and report reviewers can safely open, review, and adjust FLIR Tools+ ActiveX thermal images without triggering Microsoft Word application freezes or memory bloat. The final deliverable presented to TNB is strictly a single, consolidated PDF per substation.

### MultiPartPdfStitchingPolicy
The post-processing assembly policy (`src/workflows/full_report_postprocessing.py`) governing the consolidation of multi-part Full Reports into client deliverable PDFs. Discovers matching `<STEM> - Part *.docx` files, groups them by substation stem (`_group_multipart_targets`), converts each part document sequentially to a temporary PDF, stitches the parts in strict numerical order using `merge_pdfs_batch()` on `DocumentConverter`, matches and appends the pre-existing signed testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf`, and writes the final unified `<STEM>.pdf` deliverable to the date folder before cleaning up intermediate temporary PDFs.






