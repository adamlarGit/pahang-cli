<!-- label: wayfinder:research -->
<!-- status: open -->
<!-- blocked-by: none -->
# Audit shared repository interfaces

## Question

What methods on `LocalExcelTotalPeRepository`, `LocalExcelMsmsRepository`, and `WorkspaceStorage` need updating, splitting, or creating to support the new separated workflows?

## Context

The current repository interfaces were designed for the monolithic `update_data_msms.py` workflow where ENGR data flowed into both DATA MSMS and TOTAL PE simultaneously. With the refactoring into 5 independent workflows, the repository seams need to change:

- `LocalExcelTotalPeRepository` currently has `update_from_engr_and_msms()` — this method couples ENGR + MSMS updates. The ENGR side is deprecated; only WO propagation survives.
- `LocalExcelMsmsRepository` currently has `update_msms()` — this was designed for ENGR→MSMS flow. Needs refactoring for .xls→MSMS consolidation.
- `WorkspaceStorage` needs new path resolution methods for `PYTHON/MSMS/RAW DATA/`, `PYTHON/MSMS/TO BE FILLED/`, `PYTHON/MSMS/COMPLETED/`.

## Scope

- `src/master/total_pe.py` — `TotalPeRepository`, `LocalExcelTotalPeRepository`
- `src/msms/repository.py` — `LocalExcelMsmsRepository`
- `src/project/storage.py` — `WorkspaceStorage`
- Any other shared interfaces used by the workflows

## Expected Output

A categorized inventory:
- **NEW**: Methods/paths that need to be created
- **REFACTOR**: Methods that need signature or behavior changes
- **DEPRECATE**: Methods that should be removed (coupled to old monolithic flow)
- **KEEP**: Methods that are reusable as-is
