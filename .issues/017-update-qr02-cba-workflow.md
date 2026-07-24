# Task: Create Update QR02 CBA Workflow Orchestrator

Labels: wayfinder:task
Type: task
Status: open
Blocked by: 015, 016

## Question

Create `src/update_qr02_cba_workflow.py` — the top-level orchestration module that discovers testsheets, groups by station, extracts data, opens per-station ENGR transactions, upserts records, and tracks processing history.

## Specification

### 1. Core function: `run_update_qr02_cba(environment, request) -> UpdateQr02CbaSummary`

**Step-by-step flow:**

1. Resolve `TESTSHEET/` directory from environment
2. Discover testsheet packages via `SubstationTestsheetRepository.discover_packages()`
3. Filter by processing mode (Auto/All/Select) using history
4. **Group packages by station** (extracted from path)
5. For each station group:
   a. Extract `TestsheetData` from each `.xlsx` via `TestsheetExtractor`
   b. Resolve ENGR file path via `LocalExcelQr02Repository(storage, station, year)`
   c. Open transaction: `with repository.transaction() as tx:`
   d. `tx.upsert_qr02_cba_records(records)` — match by FL, write GPS/Type/BuildingType/Date/Vendor
6. Update `processed_folders.json` history (keyed `<STATION>/<MONTH>/<DD-MM-YYYY>`)
7. Return `UpdateQr02CbaSummary`

### 2. History tracking

- File: `PYTHON/processed_folders.json`
- Key: `"RAUB/01. MAY/01-05-2026"`
- Value: `{"last_processed": "...", "files_scanned": N}`
- Auto mode: skip date folders already in history
- All mode: ignore history, reprocess everything
- Select mode: process only the user-selected folder

### 3. Processing modes

Reuse existing `UpdateQr02CbaRequest.target_package_names`:
- Empty tuple = Auto mode (skip processed)
- Specific names = Select mode
- Extend with a flag or use "all" sentinel for All mode

### 4. Error handling

- Skip testsheets that fail extraction (log warning, continue)
- Raise if ENGR file not found for a station
- Atomic saves prevent ENGR corruption on partial failure
