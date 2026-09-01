<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: none -->
# 001: Pre-Flight Integrity Validator & File Filter

## Question

How can we reliably validate file count symmetry between `QUICK REPORT/`, `TESTSHEET/`, and `RAW MATERIAL/` before initiating post-processing, while strictly ignoring auxiliary directories and temporary files?

## Context

During pre-flight validation for a target date folder (e.g. `01-05-2026`):
1. **Target Quick Reports**: Count valid `.docx` files in `QUICK REPORT/<DATE>/` (ignoring temp files starting with `~$`).
2. **Target Testsheets**: Count **only valid `.xlsx` files** in `TESTSHEET/<DATE>/`:
   - **MUST IGNORE**: subdirectories such as `processed_testsheet/`, `UNSORTED RAW DATA/`, `pdf/`, etc.
   - **MUST IGNORE**: temporary Office lock files starting with `~$`.
3. **Target Raw Materials**: Count valid substation subdirectories in `RAW MATERIAL/<DATE>/` (excluding system or hidden folders).
4. **Validation Rule**:
   - If `quick_report_count == testsheet_count == raw_material_count` (or raw material count matches if folder exists), validation passes cleanly.
   - If there is any discrepancy in count, raise a clear, descriptive `PreFlightValidationError` detailing the exact counts found in each directory to fail-fast.

## TDD Plan

1. **Red**: Write unit tests in `tests/test_postprocessing_preflight.py` asserting:
   - Happy path: Identical counts return valid summary.
   - Auxiliary folder isolation: `processed_testsheet/` and `UNSORTED RAW DATA/` inside `TESTSHEET/` are not counted as testsheets.
   - Lock file isolation: `~$testsheet.xlsx` is ignored.
   - Mismatch failure: Raising `PreFlightValidationError` when testsheet count != quick report count.
2. **Green**: Implement the pre-flight validator function in `src/workflows/postprocessing_pipeline.py` (or a dedicated validator module).
3. **Refactor**: Ensure clean logging and typed return models.

## Resolution

- Implemented `validate_postprocessing_preflight(env, date_folder)` along with `filter_valid_quick_reports`, `filter_valid_testsheets`, and `filter_valid_raw_materials` in `src/workflows/postprocessing_preflight.py`.
- Defined `PreFlightValidationError` and `PreFlightValidationResult` models.
- Auxiliary directories (`processed_testsheet/`, `UNSORTED RAW DATA/`, `pdf/`, etc.) and lock files (`~$*.xlsx`, `~$*.docx`) are strictly isolated and excluded.
- Re-exported in `src/workflows/postprocessing_pipeline.py`.
- Created comprehensive test suite in `tests/test_postprocessing_preflight.py` (11 unit tests passing cleanly).
