<!-- label: wayfinder:task -->
<!-- status: open -->
<!-- blocked-by: none -->
# 002: Shared COM Session Context Manager

## Question

How should we manage Word and Excel COM application lifecycles during batch document conversions to ensure optimal performance and zero orphaned processes?

## Context

1. **Problem**:
   - Creating new `win32com.client.Dispatch("Word.Application")` and `win32com.client.Dispatch("Excel.Application")` instances for every individual substation in a loop causes high process thrashing and leaves orphan processes if an unhandled exception occurs.
2. **Design**:
   - Implement a context manager `batch_com_session()` (or integrate session management into `ComDocumentConverter` in `src/postprocessing/converters.py`).
   - The session creates a single `word_app` and `excel_app` upon entering the context, configures standard virtual printer settings (`Microsoft Print to PDF`), sets `Visible = False`, `DisplayAlerts = False`.
   - Passes the active COM references to `convert_testsheet_to_pdf` and `convert_docx_to_pdf`.
   - On exit (`finally`), gracefully calls `.Quit()` on both applications, releases COM pointers (`del word_app`, `del excel_app`), and executes `pythoncom.CoUninitialize()`.
   - Must support non-Windows environments and unit test mocking gracefully.

## TDD Plan

1. **Red**: Write unit tests in `tests/test_com_session.py` with mock COM objects verifying:
   - Both Word and Excel applications are instantiated once per batch.
   - Applications are properly passed to conversion methods.
   - `.Quit()` and cleanup are guaranteed even when an exception is raised inside the block.
2. **Green**: Implement `batch_com_session()` and update `DocumentConverter` methods to accept an optional active session.
3. **Refactor**: Clean up error logging and ensure thread safety.
