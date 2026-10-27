<!-- status: closed -->
# Ticket #126: fix(raw-material): Align 33kV raw material destination hierarchy with RAW DATA subfolder

## Parent
Part of #90

## What to build
Ensure 33kV projects in the Raw Material workflow extract and sort all raw data (IR, DG, and US or US+TEV) into a dedicated `<SUBSTATION>/RAW DATA/` subfolder, establishing strict parity with the 11kV directory hierarchy.

When RawMaterialWorkflow runs on a 33kV date directory:
- Photos and survey archives are placed into `<SUBSTATION_FOLDER>/RAW DATA/IR/`, `<SUBSTATION_FOLDER>/RAW DATA/DG/`, and `<SUBSTATION_FOLDER>/RAW DATA/US/<ZIP_STEM>/` (or `US+TEV/`).
- For brand-new 33kV runs where destination folders do not yet exist, default to creating `RAW DATA/US/` (while 11kV distribution packages continue to default to `RAW DATA/US+TEV/`).
- If an existing 33kV substation directory has legacy loose `IR/`, `DG/`, or `US/` folders at its root (or loose in `<SUBSTATION_FOLDER>`), automatically consolidate/migrate them into `<SUBSTATION_FOLDER>/RAW DATA/`.
- Eliminates manual folder reorganization steps for field crew raw material sorting.

## Acceptance criteria
- [x] 33kV raw material destination resolution in `src/workflows/raw_material.py` appends `/ "RAW DATA"` to the resolved substation folder.
- [x] Default directory preference for new 33kV packages creates `RAW DATA/US/` (preserving `RAW DATA/US+TEV/` for 11kV).
- [x] Legacy loose `IR/`, `DG/`, or `US/` folders directly under existing 33kV substation directories are migrated into `RAW DATA/`.
- [x] Photo copy instructions (IR, DG) target `<SUBSTATION>/RAW DATA/IR` and `<SUBSTATION>/RAW DATA/DG`.
- [x] Archive extraction targets `<SUBSTATION>/RAW DATA/US/<ZIP_STEM>` (or `US+TEV/<ZIP_STEM>`).
- [x] Automated raw material unit and integration tests in `tests/test_raw_material_33kv.py` pass verifying 33kV package directory structures match 11kV with `RAW DATA/`.

## Blocked by
None (can start immediately).
