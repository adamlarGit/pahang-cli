# Audit Results: Shared Repository and Storage Interfaces

**Ticket:** [Audit shared repository interfaces](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/008-audit-shared-repositories.md)  
**Status:** Resolved

---

## Categorized Inventory Summary

| Category | Class / Interface | Method / Path | Target Workflow |
| :--- | :--- | :--- | :--- |
| **KEEP** | `TotalPeRepository` | `get_existing_auto_keys()` | Populate Total PE |
| **KEEP** | `TotalPeRepository` | `upsert_packages()` | Populate Total PE |
| **KEEP** | `TotalPeRepository` | Internal helpers (`_sort_datacycle_sheet`, `_sanitize_ghost_formatting`, `_get_real_dimensions`) | All |
| **DEPRECATE** | `TotalPeRepository` | `update_from_engr_and_msms()` | Was monolithic ENGR+MSMS coupling |
| **NEW** | `TotalPeRepository` | `propagate_work_orders()` | Propagate WO |
| **KEEP** | `MsmsRepository` | `get_work_order_by_fl()` | Point lookups |
| **REFACTOR** | `MsmsRepository` | `update_msms()` → rename to `enrich_from_engr()` | Enrich MSMS |
| **NEW** | `MsmsRepository` | `consolidate_xls_files()` | Consolidate MSMS |
| **NEW** | `MsmsRepository` | `read_data_msms()` | Propagate WO, Populate Data MSMS |
| **KEEP** | `WorkspaceStorage` | All existing path methods | All |
| **REFACTOR** | `WorkspaceStorage` | `_initialize_project_workspace()`, `check_workspace_health()` | Include MSMS subdirs |
| **NEW** | `WorkspaceStorage` | `get_msms_dir()`, `get_msms_raw_data_dir()`, `get_msms_to_be_filled_dir()`, `get_msms_completed_dir()` | CSV workflows |
| **NEW** | `WorkspaceStorage` | `list_msms_xls_files()`, `list_msms_raw_csv_files()`, `list_msms_to_be_filled_csv_files()` | File discovery |
| **DEPRECATE** | Workflow | `src/workflows/update_data_msms.py` (entire file) | Replaced by 5 workflows |
| **REFACTOR** | Helper | `load_engr_files()` → move to shared module | Enrich MSMS |

---

## Detailed Findings

### 1. TotalPeRepository (`src/master/total_pe.py`)

- **KEEP** `get_existing_auto_keys()` — reads `(PE/Station, Date)` tuples for AUTO mode filtering. Used by Populate Total PE.
- **KEEP** `upsert_packages()` — upserts testsheet packages into TOTAL PE. Used by Populate Total PE.
- **DEPRECATE** `update_from_engr_and_msms()` — tightly coupled ENGR+MSMS updates. ENGR side deprecated (owned by Populate Total PE now). WO side replaced by new `propagate_work_orders()`.
- **NEW** `propagate_work_orders(total_pe_path, data_msms_df)` — matches FL ERMS in DataCycle1 against DATA MSMS, updates ONLY Column F (WO). Leaves all other columns untouched.
- **KEEP** all internal helpers (`_get_real_dimensions`, `_sanitize_ghost_formatting`, `_sort_datacycle_sheet`, `col_to_index`, `read_col`, `write_cell`).

### 2. MsmsRepository (`src/msms/repository.py`)

- **KEEP** `get_work_order_by_fl()` — point lookups of WO by FL ERMS. Reusable as-is.
- **REFACTOR** `update_msms()` → `enrich_from_engr()` — decouple from Location→FL conversion (that moves to Consolidate MSMS). New signature: `enrich_from_engr(data_msms_path, engr_excel, mapping)`.
- **NEW** `consolidate_xls_files(data_msms_path, xls_files)` — reads client .xls files (WO Col A, Location Col C → FL ERMS, Description Col D), populates DATA MSMS.xlsx.
- **NEW** `read_data_msms(data_msms_path)` — clean read abstraction for downstream workflows.

### 3. WorkspaceStorage (`src/project/storage.py`)

- **KEEP** all existing methods.
- **REFACTOR** `_initialize_project_workspace()` and `check_workspace_health()` — add MSMS subdirectory bootstrapping and health checks.
- **NEW** path resolution: `get_msms_dir()`, `get_msms_raw_data_dir()`, `get_msms_to_be_filled_dir()`, `get_msms_completed_dir()`.
- **NEW** file discovery: `list_msms_xls_files()`, `list_msms_raw_csv_files()`, `list_msms_to_be_filled_csv_files()`.

### 4. Legacy Workflow

- **DEPRECATE** entire `src/workflows/update_data_msms.py` — replaced by 5 independent workflow files.
- **REFACTOR** `load_engr_files()` — relocate to `src/msms/repository.py` or shared utility.
- **KEEP** `src/workflows/populate_total_pe.py` — no changes needed.
