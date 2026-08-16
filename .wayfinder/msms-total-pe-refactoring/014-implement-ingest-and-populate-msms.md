<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 010-implement-normalizers-and-mapper, 011-implement-repositories-and-storage -->
# Implement Ingest MSMS CSV & Populate Data MSMS Workflows

## Objective

Implement the two core CSV data population workflows:
1. **Ingest MSMS CSV Workflow** (`src/workflows/ingest_msms_csv.py`): Ingests client CSVs from `MSMS/RAW DATA/` into `MSMS/TO BE FILLED/` with normalized canonical filenames (`DD-MM-YYYY_NNN.csv`), specified in [005-design-csv-ingestion.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/005-design-csv-ingestion.md).
2. **Populate Data MSMS Workflow** (`src/workflows/populate_data_msms.py`): Extracts measurements from testsheets via `TestsheetReadingMapper` and defect records from `QR03 VI`, matching by `WONUM + METERNAME` to populate CSV reading columns in place (specified in [007-design-populate-data-msms.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/007-design-populate-data-msms.md) and [research/007-canonical-testsheet-mapper.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/007-canonical-testsheet-mapper.md)).

## Detailed Requirements

### 1. IngestMsmsCsvWorkflow (`src/workflows/ingest_msms_csv.py`)
- **Stage 1 (PreflightGuard)**: Verifies `MSMS/RAW DATA/` directory exists and contains `.csv` files.
- **Stage 2 (Extractor)**: Reads CSV files, validates required column headers (`WONUM`, `TNBLOCATION`, `METERNAME`).
- **Stage 3 (Filter)**: Content-hash deduplication (skips exact duplicate files).
- **Stage 4 (Transformer)**: Parses date using multi-pattern regex (`DD-MM-YYYY`, `DD.MM.YYYY`, `DDMMYYYY`) and generates canonical target path `MSMS/TO BE FILLED/DD-MM-YYYY_NNN.csv`.
- **Stage 5 (Loader)**: Moves normalized CSV files into `MSMS/TO BE FILLED/`.
- **Stage 6 (Auditor)**: Fail-fast on invalid headers / unparseable dates; reports count of ingested files.

### 2. PopulateDataMsmsWorkflow (`src/workflows/populate_data_msms.py`)
- **Stage 1 (PreflightGuard)**: Verifies `TOTAL PE.xlsx` exists and has populated WOs in `DataCycle1`; verifies `MSMS/TO BE FILLED/` has `.csv` files; verifies target `TESTSHEET/` date folders exist.
- **Stage 2 (Extractor)**:
  - Reads testsheet workbooks via openpyxl using `TestsheetReadingMapper`.
  - Reads structured defect records from `QR03 VI` sheet in ENGR workbooks via `MasterQr03DefectRepository`.
  - Reads `TOTAL PE.xlsx` (`DataCycle1` sheet) for `fl_erms` $\to$ `WONUM` lookup.
  - Reads `.csv` files from `MSMS/TO BE FILLED/`.
- **Stage 3 (Filter)**: Matches Testsheet `station_code` / `fl_erms` $\to$ `WONUM` $\to$ CSV rows. Skips unmatched substations with warnings. Skips already populated rows unless `overwrite=True`.
- **Stage 4 (Transformer)**:
  - Numeric GAUGE meters (`TH_*`, `TV_*`, `US_*`, `BG_*`): Looked up via `TestsheetReadingMapper`, sanitized via `normalize_for_csv()`.
  - Visual Inspection (`VI11_*`): Sourced exclusively from `QR03 VI` defect logs. If defect found: `TNBNEWREADING="YES"`, `TNBCOMMENTS=<defect remarks>`, `TNBNEWREADINGDATE=<ISO-8601>`. If no defect found: skip CSV row completely (leave untouched).
  - Timestamps: `ACTSTART` / `ACTFINISH` constructed from Date (`P4`) and Time In/Out (`P5`/`S5`) formatted as ISO-8601 with `+08:00` offset.
- **Stage 5 (Loader)**: Updates CSV files **in place** inside `MSMS/TO BE FILLED/`, preserving column headers, delimiter, and line endings.
- **Stage 6 (Auditor)**: Best-effort policy reporting `csv_files_processed`, `rows_populated`, `rows_skipped_already_filled`, `rows_skipped_no_testsheet`, warnings, errors.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_ingest_msms_csv.py`: Unit tests for date regex extraction, duplicate skipping, and canonical file naming.
- [x] `tests/test_populate_data_msms.py`: End-to-end integration tests using real testsheet packages and sample CSVs verifying:
  - Exact cell extraction for RMU (CENTERPOINT) and VCB (SSU BUKIT RANGIN).
  - Correct formatting of `ACTSTART`, `ACTFINISH`, `TNBNEWREADINGDATE`.
  - Correct population of `TNBNEWREADING` and `TNBCOMMENTS` for defect vs non-defect rows.
  - In-place preservation of untouched rows and column headers.
- [x] 100% test pass.

