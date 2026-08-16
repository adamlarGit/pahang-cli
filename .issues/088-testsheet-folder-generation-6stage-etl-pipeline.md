# Ticket 088: 6-Stage ETL Pipeline Implementation for TESTSHEET Folder Generation

Labels: wayfinder:task
Parent: [Map 086: Generate TESTSHEET Folder Structure Workflow Map](file:///.issues/086-generate-testsheet-folder-structure-map.md)
Status: Closed / Implemented

## Question

How should `GenerateTestsheetFolderStructureWorkflow` in `src/workflows/generate_testsheet_folder.py` be structured into a strict 6-stage ETL pipeline (`PreflightGuard`, `Extractor`, `Filter`, `Transformer`, `Loader`, `Auditor`) with pure testable seams and zero silent fallbacks?

## Resolution / Agreed Architecture

1. **`GenerateTestsheetFolderPreflightGuard`**:
   - Asserts active project environment and ensures base `TESTSHEET/` directory exists (creates if missing).
   - Validates non-empty `request.station`, `request.month`, and `request.target_dates`.
   - Raises `ValueError` or `FileNotFoundError` immediately on precondition failure.

2. **`GenerateTestsheetFolderExtractor`**:
   - Discovers existing station directories in `TESTSHEET/` and month directories under `TESTSHEET/<STATION>`.
   - Inspects existing date subdirectories under `TESTSHEET/<STATION>/<MONTH>`.

3. **`GenerateTestsheetFolderFilter` (Best-Effort Policy)**:
   - Normalizes input date strings using `normalize_date_str()`.
   - Validates normalized date strings against canonical `DD-MM-YYYY` pattern (`^\d{2}-\d{2}-\d{4}$`).
   - Deduplicates identical date entries.
   - Filters out malformed dates and records warnings for invalid dates.
   - Raises `ValueError` only if ALL dates in the batch are invalid.

4. **`GenerateTestsheetFolderTransformer`**:
   - Formats month folder using canonical sequential month indexing (e.g. `01. AUGUST`, `02. SEPTEMBER`).
   - Computes target path hierarchy:
     - `month_dir = testsheet_dir / station / formatted_month`
     - For each date: `date_dir = month_dir / date_str`
     - `unsorted_dir = date_dir / "UNSORTED RAW DATA"`
     - Subfolders: `unsorted_dir / "DG"`, `unsorted_dir / "IR"`, `unsorted_dir / "US+TEV"`
   - Assembles immutable `GenerateTestsheetFolderPlan`.

5. **`GenerateTestsheetFolderLoader` (Idempotent Creation)**:
   - Iterates through required directories in `GenerateTestsheetFolderPlan`.
   - Safely provisions each directory on disk (`p.mkdir(parents=True, exist_ok=True)`).
   - Tracks which directories were newly created vs already existing.

6. **`GenerateTestsheetFolderAuditor` (Verification Only)**:
   - Verifies physical presence of all provisioned directories on disk.
   - Pure disk verification without polluting `history.json`.
   - Assembles final `GenerateTestsheetFolderResult`.

7. **Workflow Seam**:
   - `GenerateTestsheetFolderStructureWorkflow.execute(env, request)` orchestrates the 6 stages.
