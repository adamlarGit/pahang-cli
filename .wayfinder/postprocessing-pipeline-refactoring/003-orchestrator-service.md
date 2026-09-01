<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 001, 002 -->
# 003: Lean Post-Processing Orchestrator Service

## Question

How should the post-processing service coordinate existing domain modules into a cohesive 6-stage lifecycle following the DRY principle, enforcing testsheet immutability and per-substation error isolation?

## Context

1. **Service Interface**: `WorkflowService.run_postprocessing_pipeline(env, request: PostProcessingRequest) -> PostProcessingSummary`.
2. **Execution Stages**:
   - **Stage 1 (Discovery & Scoping)**: Filter target packages by `PostProcessingRequest.mode` (`by_date` or `by_fl`).
   - **Stage 2 (Pre-Flight Validation & Renaming Sync)**:
     - Execute pre-flight file count validator (Ticket 001).
     - Run `rename_files_match(qr_dir, ts_dir)` and `rename_files_match(qr_dir, raw_mat_dir)` for target date folders.
     - Refresh target package paths.
   - **Stage 3 (WhatsApp Reporting)**: If `by_date` and requested, invoke `run_generate_whatsapp_report(env, report_dir)`.
   - **Stage 4 (Substation Processing Loop)**: Wrapped inside `batch_com_session()` (Ticket 002).
     - For each target substation package:
       1. Create working copy in `TESTSHEET/<DATE>/processed_testsheet/<STEM>.xlsx`. Original testsheet in `TESTSHEET/<DATE>/` is immutable.
       2. Signatures: If enabled, call `replace_pce_images(..., mode="placeholder")`. If disabled, call `replace_pce_images(..., mode="none")` to strip raw `{{signvendor}}` and `{{signtnb}}` tags cleanly.
       3. Diagonals: Call `diagonal_borders.process_workbook(working_copy)`.
       4. Testsheet PDF: Call `ComDocumentConverter.convert_testsheet_to_pdf` $\to$ `TESTSHEET/<DATE>/processed_testsheet/pdf/<STEM>.pdf`.
       5. Quick Report PDF: Call `ComDocumentConverter.convert_docx_to_pdf` $\to$ `QUICK REPORT/<DATE>/<STEM>.pdf`.
       6. PDF Merge: Call `ComDocumentConverter.merge_pdfs` merging Quick Report PDF + Testsheet PDF in-place into `QUICK REPORT/<DATE>/<STEM>.pdf`.
       7. Error Isolation: If a substation fails during conversion, catch exception, log traceback, record in `errors` list, and continue loop.
   - **Stage 5 (Summary Result)**: Return typed `PostProcessingSummary` (succeeded packages, deliverables, failed stations, warnings, timer).

## TDD Plan

1. **Red**: Write unit tests in `tests/test_postprocessing_orchestrator.py` mocking sub-functions:
   - Verify proper delegation to `rename_files_match`, `replace_pce_images`, `process_workbook`, and `ComDocumentConverter`.
   - Verify `mode="none"` placeholder stripping when signatures are skipped.
   - Verify testsheet immutability.
   - Verify per-substation error isolation.
2. **Green**: Implement orchestrator in `src/workflows/postprocessing_pipeline.py` and register in `WorkflowService`.
3. **Refactor**: Clean up and remove duplicated code.

## Resolution Summary

- Implemented `PostProcessingPipelineWorkflow` orchestrator in [`src/workflows/postprocessing_pipeline.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/postprocessing_pipeline.py) and registered in `WorkflowService.run_postprocessing_pipeline`.
- Defined request and result contracts (`PostProcessingRequest`, `PostProcessingSummary`, `PostProcessingMode`, `PostProcessingFailure`) in [`src/workflows/models.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py).
- Implemented `LocalTestsheetPackageRepository` with `find_packages()` in [`src/testsheet/repository.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/testsheet/repository.py) and `SubstationPackage` in [`src/testsheet/models.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/testsheet/models.py).
- Updated `replace_pce_images()` in [`src/workflows/replace_signatures.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/replace_signatures.py) to support `mode="none"` for clean placeholder stripping when signatures are disabled.
- Added `run_generate_whatsapp_report()` convenience helper in [`src/workflows/whatsapp.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/whatsapp.py).
- Implemented comprehensive unit test suite in [`tests/test_postprocessing_orchestrator.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/tests/test_postprocessing_orchestrator.py) verifying happy path (by date and by FL), pre-flight fail-fast, testsheet immutability, signature placeholder sanitization, and per-substation error isolation (all 6 tests passing, 499 total repo tests passing).

