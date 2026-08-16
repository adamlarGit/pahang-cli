# Ticket 091: High-Level E2E Workflow Verification & Test Suite

Labels: wayfinder:tdd
Parent: [Map 086: Generate TESTSHEET Folder Structure Workflow Map](file:///.issues/086-generate-testsheet-folder-structure-map.md)
Status: Closed / Implemented

## Question

What high-level workflow integration test suite is needed in `tests/test_generate_testsheet_folder_workflow.py` to verify the end-to-end behavior of the TESTSHEET folder generation workflow and prevent regressions?

## Resolution / Agreed Architecture

1. **Integration Test Suite (`tests/test_generate_testsheet_folder_workflow.py`)**:
   - Test 1: **Single Date Folder Provisioning**:
     - Provisions `<tmp>/TESTSHEET/KUANTAN/01. AUGUST/10-08-2026/UNSORTED RAW DATA/` with `DG/`, `IR/`, and `US+TEV/`.
     - Asserts all directories exist on disk and `result.total_dates_processed == 1`.
   - Test 2: **Multi-Date Batch Generation**:
     - Provisions multiple dates (`("11-08-2026", "12-08-2026")`).
     - Asserts both date hierarchies exist and `result.total_dates_processed == 2`.
   - Test 3: **Idempotent Re-Run & Data Preservation**:
     - Re-running the workflow over existing date folders succeeds without error.
     - Preserves dummy files previously created inside `UNSORTED RAW DATA/DG/`.
   - Test 4: **Invalid Date Best-Effort Filtering**:
     - Submitting `("10-08-2026", "invalid-date")` provisions `10-08-2026`, records a warning for `invalid-date`, and does not crash.
   - Test 5: **Preflight Fail-Fast on Empty Inputs**:
     - Submitting empty `target_dates=()` raises `ValueError`.

2. **Test Suite Execution**:
   - Run `python -m pytest tests/test_generate_testsheet_folder_workflow.py` and ensure 100% pass rate.
