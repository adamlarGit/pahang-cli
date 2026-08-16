<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Design Propagate WO pipeline

## Question

What should the 6 ETL stages look like for the Propagate WO workflow (DATA MSMS.xlsx → TOTAL PE.xlsx, WO number only)?

## Context

This is the **final step** in the Update Data MSMS chain. It reads the master WO data from DATA MSMS.xlsx and writes **only the WO number** into TOTAL PE.xlsx's `DataCycle1` sheet.

Key boundary: Populate Total PE owns all non-WO columns (Substation Name, Date, Type). This workflow touches **only the WO column** (Column F in the reference).

The matching key is **FL ERMS** — each row in TOTAL PE has an FL in Column B, which is matched against DATA MSMS's FL ERMS column.

## Design Decisions Needed

- **PreflightGuard**: DATA MSMS.xlsx must exist with consolidated WO data. TOTAL PE.xlsx must exist with `DataCycle1` sheet.
- **Extractor**: Read DATA MSMS.xlsx (WO + FL ERMS columns). Read TOTAL PE.xlsx `DataCycle1` sheet (FL column).
- **Filter**: Only propagate WOs where FL ERMS matches? What about FLs in TOTAL PE that have no match in DATA MSMS?
- **Transformer**: Build a mapping of FL ERMS → WO number. Handle multiple WOs per FL?
- **Loader**: Write WO into TOTAL PE Column F for matched rows. Preserve all other columns untouched.
- **Auditor**: Report match rate. Flag TOTAL PE rows with no WO match. Flag DATA MSMS WOs with no TOTAL PE row.

## Standards

Must follow [etl_pipeline_refactoring_methodology.md](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/etl_pipeline_refactoring_methodology.md).

## Resolution

- **PreflightGuard**: Requires `DATA MSMS.xlsx` to pre-exist at `PYTHON/DATA MSMS.xlsx` (raises `FileNotFoundError` if missing). Requires `TOTAL PE.xlsx` to pre-exist at `TESTSHEET/TOTAL PE.xlsx` (raises `FileNotFoundError` if missing). Requires sheet `DataCycle1` to exist in `TOTAL PE.xlsx` (raises `RuntimeError` if missing).
- **Extractor**: Reuses standard date folder discovery logic from `TESTSHEET/` (`DailyDateFolder` / `TestsheetExtractor`) when `target_date` is requested. Reads `DATA MSMS.xlsx` (`fl_erms` and `Work Order` columns) and `TOTAL PE.xlsx` (`DataCycle1` sheet).
- **Filter**: Filters `TOTAL PE.xlsx` rows by optional `target_date` parameter (or processes all rows if `None`). Matches `fl_erms` between `TOTAL PE.xlsx` and `DATA MSMS.xlsx` using exact normalized string equality (`str(fl).strip().upper()`). Filters target rows to ensure writing only into empty/blank WO cells. Flags rows where WO cell is already populated (logs notice for audit telemetry). Flags target `fl_erms` entries missing from `DATA MSMS.xlsx` (logs warning for audit telemetry).
- **Transformer** (Pure Logic): Maps 1-to-1 unique `fl_erms` $\rightarrow$ `Work Order` from `DATA MSMS.xlsx`. Constructs immutable execution plan `PropagateWoPlan(updates, matched_count, already_populated_count, unmatched_count, unmatched_fls)`.
- **Loader** (Pure Write I/O): Writes `Work Order` into Column F (`Work Order` column) in sheet `DataCycle1` of `TOTAL PE.xlsx` for rows in `plan.updates` using `openpyxl`. Preserves all other columns (`substation_name_erms`, `date`, `type`) untouched.
- **Auditor & Resilience Policy**: Best-effort policy per row. Verifies output `TOTAL PE.xlsx` file integrity (non-zero byte size). Logs execution history to `WorkflowHistoryRepository`. Reports standardized `WorkflowResult` with telemetry (`matched_count`, `already_populated_count`, `unmatched_count`, list of `unmatched_fls`).

