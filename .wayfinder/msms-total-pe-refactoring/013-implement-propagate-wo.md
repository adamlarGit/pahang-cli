<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 011-implement-repositories-and-storage -->
# Implement Propagate Work Orders Workflow

## Objective

Implement `PropagateWoWorkflow` (`src/workflows/propagate_wo.py`): A standalone 6-stage ETL workflow that reads work order mappings from `DATA MSMS.xlsx` and propagates `WONUM` into Column F (`WORK ORDER`) of `TOTAL PE.xlsx` (`DataCycle1` sheet), strictly preserving all other columns and formulas (specified in [004-design-propagate-wo.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/004-design-propagate-wo.md)).

## Detailed Requirements

### 1. Workflow Pipeline (`src/workflows/propagate_wo.py`)
- **Stage 1 (PreflightGuard)**: Verifies `DATA MSMS.xlsx` exists and contains WO records; verifies `TOTAL PE.xlsx` exists and has `DataCycle1` sheet.
- **Stage 2 (Extractor)**: Reuses `TESTSHEET` date discovery to find active test dates; extracts `fl_erms` $\to$ `WONUM` from `DATA MSMS.xlsx` and reads `TOTAL PE.xlsx`.
- **Stage 3 (Filter)**: Scopes by optional `target_date` filter; matches unique `fl_erms` to rows where Column F (`WORK ORDER`) is currently blank.
- **Stage 4 (Transformer)**: Constructs `PropagateWoPlan` mapping row indices to work order strings.
- **Stage 5 (Loader)**: Writes Column F in `TOTAL PE.xlsx` via `TotalPeRepo.propagate_work_orders()` using openpyxl, leaving all other columns untouched.
- **Stage 6 (Auditor)**: Reports count of WOs matched and populated, already-populated rows skipped, and unmatched substations.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_propagate_wo.py`: Unit and integration tests verifying:
  - Matching by `fl_erms` and population of Column F in `DataCycle1`.
  - Date filtering behavior (only target date rows updated when date specified).
  - Idempotency (already filled Column F values are skipped unless overwrite is set).
  - Total preservation of formulas and non-WO columns.
- [x] 100% test pass.

