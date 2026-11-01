<!-- status: closed -->
# Ticket #144: fix(converters): remove premature stagnation timeout to allow large PostScript spool completion

## Parent
Part of #143 (and #142, #141, #140)

## Chronological Context
During verification of Ticket #143 against the Cameron Highland 17-08-2026 dataset, post-processing on large Word documents (Document 101: 21MB .docx / 88.4MB PostScript; Document 102: 22MB .docx / 49.8MB PostScript) failed silent Adobe PDF printing at exactly 35.2 seconds:
```text
WARNING:root:ConversionFeedbackMonitor [.tmp_conv_101. TANG SENG (VI).pdf]: spooler job active in JOB_STATUS_PRINTING for 35.2s with 0 bytes on disk; failing fast into isolated fallback
```
Spooling 50MB–88MB of uncompressed PostScript data across 32-bit `WINWORD.EXE` -> `splwow64.exe` -> `spoolsv.exe` takes 45–60 seconds. Distiller cannot compile a single byte of PDF until the entire PostScript spool file has been written. The 35-second `stagnation_timeout` introduced in Ticket #143 prematurely aborted the job mid-spool, putting the print job into an aborted state (status `8212`) and deadlocking the printer port for subsequent documents.

## What to build
Remove the premature 35-second stagnation cutoff and allow large print jobs to complete naturally under size-scaled dynamic timeouts:

1. **Remove Premature 35s Stagnation Abort**:
   - In `src/postprocessing/converters.py`, remove `stagnation_timeout = 35.0` and the 0-byte abort check from `ConversionFeedbackMonitor`.
   - Allow the full dynamic timeout (`min(180.0, max(90.0, 60.0 + file_size_mb * 2.0))`) to govern the conversion window.

2. **Unit Tests**:
   - Update tests in `tests/test_converters.py` to remove or replace the 35s stagnation cutoff test with a test verifying that `ConversionFeedbackMonitor` respects the dynamic timeout during large document conversions without premature 0-byte aborts.
   - Ensure all 93+ tests pass cleanly.

3. **Verification**:
   - Verify that Document 101 (88.4MB spool) and Document 102 (49.8MB spool) can convert under their dynamic timeouts (102s and 104s) without early 35s termination.

## Acceptance criteria
- [x] `ConversionFeedbackMonitor` removes the 35-second stagnation abort, allowing large PostScript streams to spool completely.
- [x] Large documents (20MB–35MB+ .docx) operate under dynamic timeout scaling (90s–180s) without premature 0-byte aborts.
- [x] Unit tests pass with zero regressions.
- [x] Live dataset verification accommodates large PostScript spool transfers with zero premature 0-byte aborts.

## Blocked by
#143 (Completed).
