<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Implement Shared Repository Interfaces & Storage Extensions

## Objective

Extend `WorkspaceStorage`, `TotalPeRepo`, and `MsmsRepo` with the required path helpers, data contracts, and persistence methods specified in ticket [008-audit-shared-repositories.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/008-audit-results.md).

## Detailed Requirements

### 1. WorkspaceStorage Extensions (`src/repositories/workspace_storage.py`)
Add methods for MSMS directory hierarchy under project environment:
- `get_msms_dir() -> Path`: Root `MSMS/` directory.
- `get_msms_raw_data_dir() -> Path`: `MSMS/RAW DATA/` directory.
- `get_msms_to_be_filled_dir() -> Path`: `MSMS/TO BE FILLED/` directory.
- `get_msms_completed_dir() -> Path`: `MSMS/COMPLETED/` directory.
- `get_python_msms_dir() -> Path`: `PYTHON/MSMS/` directory (for scattered `.xls` files).
- `get_python_msms_completed_dir() -> Path`: `PYTHON/MSMS/COMPLETED/` directory.
- `get_data_msms_path() -> Path`: Master `DATA MSMS.xlsx` workbook path.

### 2. MsmsRepo Implementation (`src/repositories/msms.py`)
- Implement `read_data_msms(path: Path) -> pd.DataFrame`: Reads `DATA MSMS.xlsx` master table.
- Implement `consolidate_xls_files(xls_paths: Sequence[Path], target_data_msms: Path) -> ConsolidateResult`:
  - Parses HTML table structure of Maximo `.xls` files via `pd.read_html`.
  - Appends new work orders, inserts FL ERMS slash at position 8 (`CKTN0001XXXX` $\to$ `CKTN0001/XXXX`).
  - Idempotently skips already consolidated work orders.
- Implement `enrich_from_engr(data_msms_path: Path, total_pe_path: Path) -> EnrichResult`:
  - Updates blank cells in `DATA MSMS.xlsx` (Substation Name ERMS, FL ERMS, Cycle Date, Substation Number) using `TOTAL PE.xlsx` (`DataCycle1` sheet).

### 3. TotalPeRepo Implementation (`src/repositories/total_pe.py`)
- Implement `propagate_work_orders(total_pe_path: Path, data_msms_path: Path, target_date: str | None = None) -> PropagateResult`:
  - Reads `DATA MSMS.xlsx` for `fl_erms` $\to$ `WONUM` mapping.
  - Updates Column F (`WORK ORDER`) in `TOTAL PE.xlsx` (`DataCycle1` sheet) for matching substations with blank WO cells.
  - Preserves all other columns and formulas in `TOTAL PE.xlsx`.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_workspace_storage.py`: Unit tests verifying all new MSMS path resolvers against mock `ProjectEnvironment`.
- [x] `tests/test_msms_repo.py`: Unit tests for `read_data_msms`, `consolidate_xls_files` (HTML table parsing & dedup), and `enrich_from_engr`.
- [x] `tests/test_total_pe_repo.py`: Unit tests for `propagate_work_orders` verifying exact Column F updates and formula preservation.
- [x] 100% test pass.

