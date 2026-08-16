<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- claimed-by: assistant -->
<!-- blocked-by: none -->
# Design Populate Data MSMS pipeline

## Question

What should the 6 ETL stages look like for the Populate Data MSMS workflow (testsheet data → fill CSVs in TO BE FILLED/)?

## Context

This is a **new** workflow. The user selects a DailyDateFolder from testsheet packages, and the script:
1. Looks up that date in TOTAL PE's `DataCycle1` sheet → finds substations tested that day → gets WO numbers
2. Finds matching CSV(s) in `TO BE FILLED/` by date
3. Reads testsheet workbooks for that date, extracts readings
4. Matches readings to CSV rows by WO + METERNAME and fills value columns
5. Filled CSVs stay in TO BE FILLED/ for user manual review + move to COMPLETED/

**Blocked by** [Reverse-engineer METERNAME ↔ testsheet field mapping](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/006-metername-mapping.md) — the core matching logic depends on having the mapping table.

## Deliverable

Full 6-stage ETL pipeline design specification for `PopulateDataMsmsWorkflow`.

## Resolution

- **Request Model & CLI Selection (`PopulateDataMsmsRequest`)**:
  - Uses `mode: PopulateMode` (`SPECIFIC_FOLDERS`, `ALL`, `AUTO`) with `target_folder_names: Sequence[str] = ()` (identical to `PopulateTotalPeRequest`).
  - Optional `overwrite: bool = False` flag for idempotent re-runs.
  - CLI presentation layer uses `cli_selectors.select_pahang_date_folder(environment)` scanning `TESTSHEET/`.

- **Stage 1: PreflightGuard (`PopulateDataMsmsPreflightGuard`)**:
  - Validates `TOTAL PE.xlsx` exists and contains `DataCycle1` sheet (fails fast with `RuntimeError` if missing).
  - Validates at least one row in `DataCycle1` has a non-blank `WORK ORDER` (Column F) (fails fast with `RuntimeError` if `Propagate WO` has not run).
  - Validates `MSMS/TO BE FILLED/` directory exists and contains `.csv` files (fails fast with `FileNotFoundError`).
  - Validates `TESTSHEET/` directory exists and target date folders exist when `SPECIFIC_FOLDERS` mode is set.

- **Stage 2: Extractor (`PopulateDataMsmsExtractor`)**:
  - Reads testsheet numeric readings using `PCE Testsheet` + `TestsheetReadingMapper` ([research/007-canonical-testsheet-mapper.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/007-canonical-testsheet-mapper.md) / `src/testsheet/mapper.py`).

  - Reads visual inspection defect records from `QR03 VI` sheet in ENGR workbooks via `MasterQr03DefectRepository` (`src/quick_report/defects.py`).
  - Reads `TOTAL PE.xlsx` (`DataCycle1` sheet) to build `fl_erms` → `WONUM` lookup table.
  - Reads `.csv` files from `MSMS/TO BE FILLED/`.

- **Stage 3: Filter (`PopulateDataMsmsFilter`)**:
  - 2-step lookup: Testsheet `station_code` / `fl_erms` → `TOTAL PE.xlsx` WO number → `WONUM` column in CSV.
  - Unmatched substations (CSV rows with WO missing testsheet): Skip CSV row (leave blank), log warning in Auditor.
  - Already-populated rows: Skip unless `overwrite=True`.

- **Stage 4: Transformer (`PopulateDataMsmsTransformer`)**:
  - **Shared Sheet Architecture & 4-Panel Rollover**: Handles switchgear panels arranged vertically (rows 10-25 per sheet) in 4-row blocks. Rollover formula: $\text{sheet\_index} = \lfloor(N - 1) / 4\rfloor + 1$, $\text{local\_slot} = ((N - 1) \bmod 4) + 1$.
  - **VCB Switchgear Resolution (`_PE13V` / `_PE13V2`)**: Panel index $N$ from `TNBLOCATION` `/11KV/N`. Uses all 4 compartment sub-rows: Cable (offset +0), Breaker (offset +1), Top Panel/Busbar (offset +2), PT (offset +3). Columns: K (REF/Tmin), L (MAX/Tmax), M (DIF/ΔT), N (AVG/Avg), Q (US), T (TEV dB), U (TEV Pulse). LV compartment is a stub (left blank in CSV).
  - **RMU SF6 / MRMU Switchgear Resolution (`_PE13R`)**: Fixed slot mapping: Cable 1 $\to$ Slot 1 (row 10), Cable 2 $\to$ Slot 2 (row 14), Cable 3 $\to$ Slot 3 (row 18), Fuse 1 $\to$ Slot 4 (row 22), Fuse 2 $\to$ Slot 5 (Sheet 2, row 10). Only the CABLE sub-row (offset +0) carries readings (other 3 sub-rows are empty/VCB-only). RMU Body maps to Overview row 26 with Avg only (N26; Tmin/Tmax/ΔT are stubs left blank), Body TEV $\to$ P6, Body US $\to$ hardcoded 0 dB.
  - **Transformer Resolution (`_PE13R` / `_PE13V`)**: `/TX/DTX1` $\to$ rows 33-37, `/TX/DTX2` $\to$ rows 38-42. Columns: F (REF/Tmin), G (MAX/Tmax), H (DIF/ΔT), I (AVG/Avg), K (US dB). HV maps to HT Cable (row 33/38), LV maps to LV Cable (row 35/40), Body maps to Body (row 37/42). TX3/TX4 deferred.
  - **Background & Metadata**: `BG_ROOM_TV` $\to$ P6, `BG_ROOM_HUM` $\to$ S6, `BG_ROOM_TEM` $\to$ regex extraction from W6 text (`r"BACKGROUND\s*TEMP\s*:\s*(\d+\.\d)\s*°?\s*C"`), `ACTSTART`/`ACTFINISH` formatted from Date (P4) and Time In/Out (P5/S5).
  - **LVDB / Feeder Pillar (`/FP/FP1`, `/FP/FP2`)**: All 64 numeric thermal meters (`TH_FPIN1..3_*`, `TH_FPOT1..12_*`, `TH_EARTH_*`) are stubs and left blank (`""`).
  - **Numeric GAUGE meters (`TH_*`, `TV_*`, `US_*`, `BG_*`)**: Extracted from target sheet via `TestsheetReadingMapper` and cleaned via `normalize_for_csv()`. Empty/missing cells remain completely blank (`""`).
  - **Visual Inspection CHARACTERISTIC meters (`VI11_*`) & `TNBCOMMENTS`**: Sourced exclusively from structured `QR03 VI` defect records in ENGR workbooks (via `MasterQr03DefectRepository`). If defect logged for category: `TNBNEWREADING = "YES"`, `TNBCOMMENTS = Col K (ADDITIONAL REMARKS)`, `TNBNEWREADINGDATE = <timestamp>`. If no defect logged: skip the CSV row completely (leave untouched).
  - **Timestamps**: `ACTSTART`, `ACTFINISH`, `TNBNEWREADINGDATE` formatted as ISO-8601 strings with timezone offset (`2026-06-09T14:17:06+08:00`).

- **Stage 5: Loader (`PopulateDataMsmsLoader`)**:
  - Updates CSV files **in place** inside `MSMS/TO BE FILLED/`, preserving column headers, delimiter, and line endings.

- **Stage 6: Auditor (`PopulateDataMsmsAuditor`)**:
  - Operates on **`best-effort` resilience policy**.
  - Verifies written `.csv` files exist, have non-zero byte size, and maintain valid CSV structure.
  - Telemetry (`PopulateDataMsmsResult`): `csv_files_processed`, `total_rows_evaluated`, `rows_populated`, `rows_skipped_already_filled`, `rows_skipped_no_testsheet`, `unmapped_meters_count`, `warnings`, `errors`.

- **Centralized Target-System Normalizer Architecture (`src/core/normalizers.py`)**:
  - `normalize_for_csv(val)`: Returns clean strings or `""` (empty string for database/CSV, NO `"-"` or `"NaN"`).
  - `normalize_for_excel(val)`: Returns native types (`float`/`int`/`date`) or `None` for openpyxl cells.
  - `normalize_for_report(val)`: Returns formatted strings with `"-"` placeholders for Word/PDF reports.
  - All existing workflows rewired to use these target-system normalizers; stale/redundant single-use helper functions deleted.
