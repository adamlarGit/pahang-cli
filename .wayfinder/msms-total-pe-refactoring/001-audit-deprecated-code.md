<!-- label: wayfinder:research -->
<!-- status: open -->
<!-- blocked-by: none -->
# Audit deprecated update_data_msms code paths

## Question

What functions, repository methods, and modules in the current `update_data_msms.py` and its dependencies are deprecated by the new workflow design? What code survives the refactoring?

## Context

The current `update_data_msms.py` is a monolithic workflow that:
1. Reads ENGR files → updates DATA MSMS.xlsx (substation name, FL ERMS, cycle date)
2. Reads ENGR + DATA MSMS → updates TOTAL PE.xlsx (substation name, date, type, WO)

After refactoring:
- Step 1 is replaced by Consolidate MSMS (.xls → DATA MSMS) + Enrich MSMS (ENGR → DATA MSMS)
- Step 2's name/date/type writes are deprecated (owned by Populate Total PE). Only WO propagation survives.

## Scope

- `src/workflows/update_data_msms.py` — the workflow file
- `src/msms/` — models, repository (`LocalExcelMsmsRepository`)
- `src/master/total_pe.py` — `LocalExcelTotalPeRepository` methods used by update_data_msms
- Column mapping constants in `src/msms/models.py`
- Any shared helpers (`load_engr_files`, `col_to_index`, etc.)

## Expected Output

A categorized inventory:
- **REMOVE**: Functions/methods/classes that are fully deprecated
- **REFACTOR**: Code that partially survives but needs modification
- **KEEP**: Code that is reusable as-is in the new pipelines
