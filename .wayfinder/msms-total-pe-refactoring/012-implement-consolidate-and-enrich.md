<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 011-implement-repositories-and-storage -->
# Implement Consolidate MSMS & Enrich MSMS Workflows

## Objective

Implement the 6-stage ETL workflows for:
1. **Consolidate MSMS Workflow** (`src/workflows/consolidate_msms.py`): Ingests scattered `.xls` files from `PYTHON/MSMS/` into master `DATA MSMS.xlsx`, moves processed files to `PYTHON/MSMS/COMPLETED/` (specified in [002-design-consolidate-msms.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/002-design-consolidate-msms.md)).
2. **Enrich MSMS Workflow** (`src/workflows/enrich_msms.py`): Enriches `DATA MSMS.xlsx` columns D–G with substation metadata from `TOTAL PE.xlsx` for human verification (specified in [003-design-enrich-msms.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/003-design-enrich-msms.md)).

## Detailed Requirements

### 1. ConsolidateMsmsWorkflow (`src/workflows/consolidate_msms.py`)
- **Stage 1 (PreflightGuard)**: Verifies `DATA MSMS.xlsx` exists, `PYTHON/MSMS/` exists, and `.xls` files are present.
- **Stage 2 (Extractor)**: Reads `.xls` files using `pd.read_html` via `MsmsRepo`.
- **Stage 3 (Filter)**: Identifies new work orders, skipping any already present in `DATA MSMS.xlsx`.
- **Stage 4 (Transformer)**: Normalizes FL ERMS (slash at pos 8), constructs `ConsolidateMsmsPlan`.
- **Stage 5 (Loader)**: Appends new rows to `DATA MSMS.xlsx`, moves processed `.xls` files to `PYTHON/MSMS/COMPLETED/`.
- **Stage 6 (Auditor)**: Reports count of files processed, rows appended, duplicate WOs skipped, errors.

### 2. EnrichMsmsWorkflow (`src/workflows/enrich_msms.py`)
- **Stage 1 (PreflightGuard)**: Verifies `DATA MSMS.xlsx` and `TOTAL PE.xlsx` exist.
- **Stage 2 (Extractor)**: Reads `DATA MSMS.xlsx` and `TOTAL PE.xlsx` (`DataCycle1` sheet).
- **Stage 3 (Filter)**: Matches exact WO strings where target cells (cols D–G) in `DATA MSMS.xlsx` are blank.
- **Stage 4 (Transformer)**: Maps `substation_name_erms`, `fl_erms`, `cycle_date`, `substation_number` into `EnrichMsmsPlan`.
- **Stage 5 (Loader)**: In-place updates blank cells in `DATA MSMS.xlsx`.
- **Stage 6 (Auditor)**: Reports telemetry on matched, already populated, and unmatched rows.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_consolidate_msms.py`: Unit and integration tests with synthetic `.xls` HTML files, verifying append behavior, deduplication, and file movement to `COMPLETED/`.
- [x] `tests/test_enrich_msms.py`: Unit tests verifying metadata population across columns D–G without overwriting existing data.
- [x] 100% test pass.
