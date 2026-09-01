<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 004 -->
# 005: End-to-End Integration Test Suite

## Question

How do we establish full end-to-end test coverage for the post-processing pipeline across date folders, FL selections, error scenarios, and signature modes?

## Context

1. **Test Location**: `tests/test_postprocessing_pipeline_e2e.py`.
2. **Scenarios to Cover**:
   - **Scenario A (Happy Path `by_date` with Signatures + WhatsApp)**:
     - Pre-flight checks pass.
     - Files renamed cleanly.
     - WhatsApp report created in `PYTHON/WHATSAPP/`.
     - Substation deliverable PDFs merged in `QUICK REPORT/<DATE>/`.
     - Intermediate testsheet PDFs saved in `TESTSHEET/<DATE>/processed_testsheet/pdf/`.
     - Original testsheets unchanged.
   - **Scenario B (Happy Path `by_fl` with `NONE` Signatures)**:
     - WhatsApp generation skipped.
     - Signature placeholders stripped without images.
     - Deliverable merged successfully.
   - **Scenario C (Pre-Flight Failure on Count Mismatch)**:
     - Discrepancy between testsheet and quick report count raises `PreFlightValidationError` and halts early.
   - **Scenario D (Substation Error Resilience)**:
     - 1 out of 3 substations raises an exception during COM conversion.
     - Remaining 2 substations process successfully; summary reports 2 succeeded, 1 failed.

## TDD Plan

1. **Red**: Write the comprehensive test suite with isolated `tmp_path` fixtures and mock converters.
2. **Green**: Ensure all scenarios pass against the orchestrator and CLI adapter.
3. **Refactor**: Minimize test boilerplate with shared pytest fixtures.
