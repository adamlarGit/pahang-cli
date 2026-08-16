<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Design Enrich MSMS pipeline

## Question

What should the 6 ETL stages look like for the Enrich MSMS workflow (ENGR files → DATA MSMS.xlsx)?

## Context

This workflow **enriches** DATA MSMS.xlsx with cross-reference data from ENGR files for **human verification**. It allows users to skim through extracted data and quick-check if it matches what's in the ENGR system.

The enrichment adds (from the reference workflow):
- ENGR Substation Name (ERMS) — so user can compare against the .xls-sourced name
- ENGR FL ERMS — the canonical FL from ENGR
- Cycle Date — from ENGR `CYCLE 1` column

This is **decoupled** from Consolidate MSMS so either can run independently or be coupled to different data sources in the future.

## Design Decisions Needed

- **PreflightGuard**: DATA MSMS.xlsx must exist (run Consolidate first?). ENGR files must exist in PYTHON/ENGR FROM DRIVE/.
- **Extractor**: Read ENGR files — which sheet (`QR02 CBA`), header row, column mapping by voltage type (11kV vs 33kV).
- **Filter**: Only enrich rows that have FL ERMS? Skip rows already enriched?
- **Transformer**: FL ERMS matching between DATA MSMS and ENGR. Handle unmatched FLs?
- **Loader**: Update existing DATA MSMS.xlsx enrichment columns in place.
- **Auditor**: Report match rate (how many FLs matched vs unmatched). Flag mismatches for human review?

## Standards

Must follow [etl_pipeline_refactoring_methodology.md](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/etl_pipeline_refactoring_methodology.md).

## Key Reference

- ENGR column mappings differ by voltage type:
  - **11kV**: FL ERMS = Col I, Substation Name = Col J, Cycle Date = Col O, Type = Col M
  - **33kV**: FL ERMS = Col E, Substation Name = Col H, Cycle Date = Col Q, Type = Col I
- Reference implementation: [tnb/src/update_data_msms_workflow.py](file:///C:/Users/ADAM/Desktop/tnb/src/update_data_msms_workflow.py)

## Resolution

- **PreflightGuard**: Requires `DATA MSMS.xlsx` to pre-exist at `PYTHON/DATA MSMS.xlsx` (raises `FileNotFoundError` if missing, prompting user to run Consolidate MSMS first). Requires `TOTAL PE.xlsx` to pre-exist at `TESTSHEET/TOTAL PE.xlsx` (raises `FileNotFoundError` if missing). No longer reads raw ENGR files.
- **Extractor**: Reads `DATA MSMS.xlsx` into `data_msms_df` and `TOTAL PE.xlsx` (`DataCycle1` sheet) into `total_pe_df`.
- **Filter**: Matches rows between `DATA MSMS.xlsx` and `TOTAL PE.xlsx` by exact Work Order (`WO`) string matching (`str(wo_data_msms).strip() == str(wo_total_pe).strip()`). Filters target cells to ensure enrichment writes only into empty/blank cells. Flags unmatched Work Orders and logs warnings for human review.
- **Transformer** (Pure Logic): Maps enriched domain fields from `TOTAL PE.xlsx` to `DATA MSMS.xlsx`:
  - Col D: `substation_name_erms`
  - Col E: `fl_erms`
  - Col F: `cycle_date`
  - Col G: `substation_number`
  Constructs immutable `EnrichMsmsPlan(updates, matched_count, unmatched_count, unmatched_wos)`.
- **Loader** (Pure Write I/O): Updates empty cells in columns D, E, F, G in place for matched rows in `DATA MSMS.xlsx` using `openpyxl`.
- **Auditor & Resilience Policy**: Best-effort policy per Work Order. Verifies output `DATA MSMS.xlsx` file integrity (non-zero byte size). Logs execution history to `WorkflowHistoryRepository`. Reports match telemetry (`matched_count`, `unmatched_count`, list of `unmatched_wos`) in `WorkflowResult` for human review.

