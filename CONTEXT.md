# Pahang CLI Domain Model Context

This file serves as the ubiquitous language and domain model reference for the Pahang CLI project, establishing shared vocabulary across all workflow modules.

## Concepts

### ProjectMetadata
An immutable domain object (`src/project/models.py`) representing logical Pahang project metadata (`key`, `name`, `po_number`, `state`, `voltage_type`, `technologies`, `base_path`). Validates voltage rating (`11kV` or `33kV`).

### ProjectRepository
An interface (`src/project/repository.py`) providing methods for accessing and persisting `ProjectMetadata` without global mutable state.

### ProjectEnvironment
A composite facade (`src/project/environment.py`) combining `ProjectMetadata` and `WorkspaceStorage`.

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











