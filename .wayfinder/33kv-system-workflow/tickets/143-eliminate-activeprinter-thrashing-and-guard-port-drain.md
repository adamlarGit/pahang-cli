<!-- status: closed -->
# Ticket #143: fix(converters): eliminate ActivePrinter thrashing, persist ViewPrintOutput suppression, and guard port monitor drain

## Parent
Part of #142 (and #141, #140)  
Forensic Investigation: `docs/research/cameron_highland_postprocessing_failure_investigation.md`

## Chronological Context
During forensic testing on the Cameron Highland 17-08-2026 dataset (10 substations), Ticket #142 successfully prevented file sharing collisions on fallbacks and added dynamic timeouts. However, deep Windows Print Spooler and COM driver interactions revealed three secondary failure modes during sequential batch execution:
1. **`ActivePrinter` Thrashing & Session 0 Desynchronization**: Word's `ActivePrinter` property was re-assigned and restored 20 times across 10 documents, broadcasting device changes that desynchronized 32-bit Word COM from 64-bit `splwow64.exe`. On Document 101, the port monitor spawned `acrodist.exe` in non-interactive Session 0 (Services) where it froze forever at 0% CPU.
2. **Post-Print Port Teardown Latency**: The Adobe PDF port monitor takes ~10 seconds *after* PDF creation to finish spooler teardown. Returning from conversion immediately caused port contention on the next document.
3. **Premature `ViewPrintOutput` Deletion**: Deleting `ViewPrintOutput` in `finally:` right when the PDF was created caused Distiller to revert to default settings during the 10-second port monitor finalization, auto-launching `Acrobat.exe` in the background and locking `.tmp_conv_*.pdf` files against unlinking.

## What to build
Harden the converter and post-processing pipeline against multi-document batch printing race conditions:

1. **Persistent Registry Suppression**:
   - Keep `ViewPrintOutput = 0` (`winreg.REG_DWORD`) permanently set in `HKCU\Software\Adobe\Acrobat Distiller\PrinterJobControl` across root, `WINWORD.EXE`, `splwow64.exe`, and `<EXE>:<USER>` subkeys.
   - Do NOT delete `ViewPrintOutput` in `finally:` upon PDF completion so the port monitor never reverts to auto-launching `Acrobat.exe`.

2. **Pre-Unlink WMI Sentinel & Expanded Retry Budget (5.0s)**:
   - Call `terminate_stray_acrobat_processes()` directly inside `safe_unlink_with_retry()` before the first unlink attempt and before subsequent retries.
   - Expand the default retry budget from 1.5s to 5.0s (5 attempts: 0.2s, 0.5s, 1.0s, 1.5s, 1.8s) to eliminate all orphaned `.tmp_conv_*` files.

3. **Eliminate Word COM `ActivePrinter` Thrashing**:
   - In `_convert_docx_via_adobe_pdf()`, check if `word_app.ActivePrinter` already starts with `"Adobe PDF"`. If so, skip setting `ActivePrinter`.
   - Never restore `orig_printer` in `finally:` during sequential batch runs when running inside a `BatchComSession`, preventing device-change broadcast storms.

4. **Post-Print Spooler Port Drain Guard**:
   - Before returning from `_convert_docx_via_adobe_pdf()`, wait for the specific `JobId` to transition out of `JOB_STATUS_PRINTING` and retire from the spooler queue (with a bounded safety timeout), ensuring the serial port monitor is fully idle before the next document prints.

5. **Early Queue Stagnation Fail-Fast**:
   - If a print job is in `JOB_STATUS_PRINTING` but has produced 0 bytes of output after 35 seconds, fail-fast immediately into the isolated native fallback rather than stalling the pipeline for the full 140s dynamic timeout.

6. **Verification**:
   - Unit tests covering persistent suppression, active printer stabilization, spooler port drain guard, pre-unlink sentinel, and stagnation fail-fast.
   - Verification against the 10 Cameron Highland Full Reports (`17-08-2026`), ensuring 10/10 deliverables succeed in high fidelity with zero leftover `.tmp` files.

## Acceptance criteria
- [x] `ComDocumentConverter` leaves `ViewPrintOutput = 0` persistent in registry across batch runs.
- [x] `safe_unlink_with_retry()` calls `terminate_stray_acrobat_processes()` and operates with a 5.0s retry budget.
- [x] `_convert_docx_via_adobe_pdf()` skips `ActivePrinter` assignment and restoration when already configured for Adobe PDF.
- [x] `_convert_docx_via_adobe_pdf()` waits for the print job to be retired from the spooler queue before completing.
- [x] `ConversionFeedbackMonitor` fails fast into isolated fallback if 0 bytes written after 35 seconds of printing.
- [x] Unit tests pass with zero regressions.
- [x] Live dataset verification accommodates multi-document batches without Session 0 deadlock or orphaned temporary files.

## Blocked by
None (can start immediately).
