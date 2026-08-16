<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Design Consolidate MSMS pipeline

## Question

What should the 6 ETL stages look like for the Consolidate MSMS workflow (PYTHON/MSMS/*.xls → DATA MSMS.xlsx)?

## Context

This is a **new** workflow. Currently users manually consolidate WO data from scattered `.xls` files into DATA MSMS.xlsx.

Each `.xls` file in `PYTHON/MSMS/` contains client-side data:
- Column A: Work Order number
- Column C: Location (raw flat string, needs slash-at-position-8 conversion to FL ERMS)
- Column D: Description (substation name)

The filenames (e.g., `45501696.xls`) are arbitrary server-generated IDs, not WO numbers.

DATA MSMS.xlsx becomes the **master WO data** — the single source of truth for WO → FL ERMS mapping.

## Design Decisions Needed

- **PreflightGuard**: What preconditions? (PYTHON/MSMS/ exists, .xls files present, DATA MSMS.xlsx exists or create fresh?)
- **Extractor**: Read all .xls files — which sheet, which header row? Handle format variations?
- **Filter**: Dedup strategy when multiple .xls files contain the same WO? Skip already-consolidated WOs?
- **Transformer**: Location → FL ERMS conversion. Column mapping to DATA MSMS schema. Any other transformations?
- **Loader**: Append to existing DATA MSMS.xlsx or overwrite? How to handle the existing manual entries?
- **Auditor**: What verification? Row counts? WO uniqueness check?

## Standards

Must follow [etl_pipeline_refactoring_methodology.md](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/etl_pipeline_refactoring_methodology.md).

## Resolution

- **PreflightGuard**: Requires `PYTHON/MSMS/` directory with at least 1 `.xls` file. Requires `DATA MSMS.xlsx` to pre-exist at `PYTHON/DATA MSMS.xlsx`. Fails fast with `FileNotFoundError` if missing.
- **Extractor**: Uses `pd.read_html(path, flavor='lxml')[0]` to read client HTML `.xls` files into DataFrames. Extracts Work Order (Col 0), Location (Col 2), Substation Description (Col 3). Warns and skips empty frameset files (0 WO rows).
- **Filter**: Deduplicates across input `.xls` files by keeping first occurrence. Skips Work Orders that already exist in `DATA MSMS.xlsx`.
- **Transformer** (Pure Logic): Converts Location by inserting slash after character 8 (`CKTN/PCEJ01565` → `CKTN/PCE/J01565`). Maps Col A = Work Order, Col B = Location, Col C = Description. Leaves Col D (`ERMS`), Col E (`FUNCTIONAL LOCATION`), Col F (`DATE`), Col G (`NUMBER`) blank for Enrich MSMS workflow. Constructs immutable `ConsolidateMsmsPlan(rows_to_append, files_to_move)`.
- **Loader** (Pure Write I/O): Appends `plan.rows_to_append` to `DATA MSMS.xlsx` using openpyxl. Moves processed `.xls` files in `plan.files_to_move` to `PYTHON/MSMS/COMPLETED/`.
- **Auditor & Resilience Policy**: Best-effort policy per file. Verifies `DATA MSMS.xlsx` file integrity (non-zero byte size) and WO uniqueness. Returns `WorkflowResult` execution telemetry.

