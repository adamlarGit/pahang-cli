<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 094: feat(33kv-master): Contract 750-39 storage resolution and Qr02Cba33kVTransaction

**What to build:** Add statewide contract 750-39 workbook path resolution in `WorkspaceStorage` (`PYTHON/ENGR FROM DRIVE/ENGR-750-39 -CBA-PAHANG - {YEAR}.xlsx`), and implement `Qr02Cba33kVTransaction` for safely updating the shifted Column G–R layout on sheet `QR02 CBA` (Cycle 4, Vendor `"EET"`) without corrupting master records, utilizing two-tier FL resolution (`D7` with `TOTAL PE.xlsx` fallback).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Detailed Design & Architecture

1. **Storage Resolution (`src/project/storage.py`)**:
   - In `WorkspaceStorage.get_engr_cba_path()`:
     - When `voltage_type == "33kV"` (or contract is 750-39):
       - Strictly resolve to the exact filename: `self.get_engr_folder() / f"ENGR-750-39 -CBA-PAHANG - {year}.xlsx"`.
       - No globbing fallback.
       - Bypass the 11kV per-district 3-letter station abbreviation mapping (`config.ENGR_STATION_CODES`).
     - When `voltage_type == "11kV"`:
       - Retain exact existing per-station resolution (`ENGR-750-36-CBA-{code}-{year}.xlsx`).

2. **Two-Tier Functional Location (FL) Resolution**:
   - When updating `QR02 CBA` records for 33kV substations:
     - **Primary**: Cell `D7` on the testsheet (if populated with a valid FL string, e.g. `CGBG/PPU/G00001`).
     - **Fallback**: Query `PYTHON/TOTAL PE.xlsx` (`DataCycle1` sheet), matching `PE NO` (substation number) to retrieve `FL NUMBER` (Column B).
     - **Error Policy**: If neither source yields an FL, fail fast with `ValueError(f"Cannot resolve Functional Location for substation {substation_number} ({name}) from testsheet or TOTAL PE.xlsx")`.

3. **`Qr02Cba33kVTransaction` (`src/master/qr02.py`)**:
   - Target sheet: `"QR02 CBA"` (header at row 2).
   - Indexing: Index Functional Location from Column G (7).
   - New row population:
     - Col G (7): Functional Location
     - Col H (8): Substation Name
     - Col I (9): Type (PPU / SSU / MPPU)
     - Col J (10): System (default `"33/11"`)
   - Inspection record update:
     - Target Cycle: Default to **Cycle 4** for Project THUNDER (configurable via `cycle: int = 4`).
     - **Col Q (17)**: Cycle 4 Date formatted as `YYYY-MM-DD` (`NumberFormat = "d-mmm-yy"`).
     - **Col R (18)**: Cycle 4 Vendor populated with `"EET"`.
     - Columns K–P (Cycles 1–3) are preserved and left untouched unless explicitly specified.
   - Column protection: Strictly omit writing to GPS, Site Name, and Building Type columns.

4. **Transaction Factory & Dispatching**:
   - `create_qr02_transaction(workbook_path: Path | str, voltage_type: str = "11kV", cycle: int = 4, vendor: str = "EET") -> Qr02Transaction`:
     - If `voltage_type == "33kV"`: returns `Qr02Cba33kVTransaction(cba_path=workbook_path, cycle=cycle, vendor=vendor)`.
     - If `voltage_type == "11kV"`: returns `LocalExcelQr02Transaction(cba_path=workbook_path)`.
   - `LocalExcelQr02Repository`: Dispatches to `Qr02Cba33kVTransaction` when configured with `voltage_type == "33kV"`.

5. **Defect Repository Verification (`QR03 CBA` & `QR03 VI`)**:
   - Verify `MasterQr03DefectRepository` compatibility with the 750-39 workbook sheets (`QR03 CBA` and `QR03 VI`), ensuring diagnostic and visual defects are retrieved without error.

## Acceptance Criteria Checklist

- [ ] Update `WorkspaceStorage.get_engr_cba_path()` for 33kV to strictly resolve `ENGR-750-39 -CBA-PAHANG - {year}.xlsx` without globbing.
- [ ] Implement two-tier FL resolution logic in `UpdateQr02CbaTransformer` (testsheet `D7` $\to$ `TOTAL PE.xlsx` $\to$ `ValueError`).
- [ ] Implement `Qr02Cba33kVTransaction` in `src/master/qr02.py`:
  - [ ] Index Column G (`FUNCTIONAL LOCATION`).
  - [ ] Support new row creation (Cols G–J).
  - [ ] Populate Cycle 4 Date (Col Q) and Vendor `"EET"` (Col R).
  - [ ] Strictly omit GPS, Site Name, and Building Type writes.
- [ ] Wire `create_qr02_transaction` and update `LocalExcelQr02Repository` to dispatch based on `voltage_type`.
- [ ] Add unit and transaction tests in `tests/test_qr02_33kv.py` testing FL index matching, TOTAL PE fallback lookup, Cycle 4 upsert, and atomic save.
- [ ] Verify `MasterQr03DefectRepository` against 750-39 defect sheets.
- [ ] Verify full test suite passes with 0 regressions.
