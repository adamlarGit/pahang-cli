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
Monthly tracking folder inside station directories formatted as `<INDEX>. <MONTH_NAME>` (e.g., `01. MAY`, `02. JUNE`, `01. JUN`).

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
An immutable domain result schema returned by the Raw Material workflow detailing execution statistics (total PEs processed, copied IR photo count, copied DG photo count, warnings, and errors).

### Qr02Repository & LocalExcelQr02Transaction
The deep module in `src/master/qr02.py` implementing per-station ENGR `QR02 CBA` workbook operations with abstract `Qr02Repository` / `Qr02Transaction` interfaces, unit-of-work context manager, exact FL row matching, column updates (GPS, Type, Building Type, Cycle 1 date `DD-MMM-YYYY`, Vendor `"EET"`), atomic tempfile saves (`atomic_save`), and ghost cell cleanup (`_sanitize_ghost_formatting`).

### ENGR Station Code
The 3-letter station abbreviation mapping (e.g. `RAUB` -> `RAU`, `KUANTAN` -> `KTN`) used to resolve per-station ENGR CBA workbook filenames matching `PYTHON/ENGR FROM DRIVE/ENGR-750-36-CBA-<STATION_CODE>-<YEAR>.xlsx`.
