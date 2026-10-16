<!-- status: closed -->
Part of #90
Specification: [spec.md](../spec.md)

# 098: feat(33kv-total-pe): Populate TOTAL PE from 33kV testsheets

**What to build:** Extend `PopulateTotalPeWorkflow` and `LocalExcelTotalPeRepository` to ingest 33kV substation testsheet packages extracted via `PpuTestsheetParser` and populate `PYTHON/TOTAL PE.xlsx` (`DataCycle1` sheet), recording `PE NO`, `FL NUMBER`, `SUBSTATION NAME`, `DATE`, and `TYPE` (`PPU`, `SSU`, `PMU`, `MPPU`) with master `QR02 CBA` enrichment, maintaining 100% parity with 11kV row-update behavior.

**Blocked by:** #92

**Status**: closed

- [x] Verify `PpuTestsheetParser` populates canonical metadata in `SubstationTestsheetPackage.data`:
  - `substation_number`: extracted from folder/file stem (e.g. `01. PPU APMM...` -> `1`)
  - `fl_erms`: extracted from cell `D7` on `33kV (Main)` (e.g. `CGBG/PPU/G00001`)
  - `date`: extracted from cell `D8` on `33kV (Main)` (e.g. `2026-10-07`)
  - Fallback `substation_name_erms`: extracted from cell `D6` on `33kV (Main)` (e.g. `PPU APMM 33/11kV`)
  - Fallback `substation_type`: categorized as `PPU`, `SSU`, or `PMU` based on substation stem / FL token.
- [x] Implement `QR02 CBA` master metadata enrichment in `PopulateTotalPeExtractor` (or repository) for 33kV projects:
  - Resolves `ENGR-750-39 -CBA-PAHANG - {YEAR}.xlsx` via `storage.get_engr_33kv_cba_path()`
  - Reads `QR02 CBA` sheet indexing by Column G (`FUNCTIONAL LOCATION`)
  - Enriches `substation_name` from Column H (`SUBSTATION NAME`) and `substation_type` from Column I (`TYPE`)
  - Falls back gracefully to testsheet cell `D6` (name) and stem/sheet token (type) if FL is not yet in `QR02 CBA`, logging a warning without aborting the batch.
- [x] Extend row lookup dictionary in `LocalExcelTotalPeRepository.upsert_packages`:
  - Support 2-digit zero-padded keys `(f"{pe_no:02d}", dt_str)`
  - Support Functional Location keys `(fl_num, dt_str)` and normalized variants.
- [x] Ensure `LocalExcelTotalPeRepository.upsert_packages` in `src/master/total_pe.py` safely writes 33kV package data into `DataCycle1`:
  - Col A (`PE NO`): integer PE number
  - Col B (`FL NUMBER`): FL string
  - Col C (`SUBSTATION NAME`): Substation name (from `QR02 CBA` Col H or cell `D6`)
  - Col D (`DATE`): formatted datetime / date with `"DD-MMM-YYYY"` number format
  - Col E (`TYPE`): substation type (`PPU`, `SSU`, `PMU`, `MPPU` from `QR02 CBA` Col I or fallback)
  - Col F (`WO`): incoming package `wo_number` (direct row update maintaining 11kV parity; populated by Action 10)
  - Columns beyond Col F (Cols G, H, I...) preserved untouched during upsert.
  - In `_sort_datacycle_sheet()`: carry all columns up to `max_column` and preserve cells with Excel formulas (`startswith("=")`).
  - Ghost formatting sanitized via `_sanitize_ghost_formatting`.
- [x] Ensure `PopulateTotalPeAction` in `src/project_workflow_actions.py` runs transparently for 33kV active project environments.
- [x] Add unit tests in `tests/test_populate_total_pe_33kv.py` verifying upsert operations, `QR02 CBA` enrichment, fallbacks, and 2-digit/FL lookup on synthetic 33kV workbooks.
