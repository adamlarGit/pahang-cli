<!-- status: closed -->
# Ticket #142: fix(converters): suppress Acrobat viewer auto-launch, scale large-document timeout, and isolate fallback paths

## Parent
Part of #141 (and #140)

## What to build
Fix Full Report post-processing conversion failures, eliminate race conditions/premature document closures, and prevent orphaned `.tmp_conv_*.pdf` files caused by Adobe Acrobat viewer background locking and Distiller timeout collisions on large Word documents:

1. **STA-Safe `ConversionFeedbackMonitor` & Pre-Closure Spooler Drain Guard**:
   - Implement an explicit phased feedback state machine: `QUEUED` -> `SPOOLING` -> `DISTILLING` -> `LOCK_RELEASE` -> `VERIFIED`.
   - Prevent premature document closure: in `ComDocumentConverter.convert_docx_to_pdf`, never call `doc.Close(SaveChanges=False)` while `word_app.BackgroundPrintingStatus > 0`. Wait for Word's internal spooler queue to drain before document teardown.

2. **Two-Tier Completion Probe**:
   - Replace bare `b"%%EOF"` tail check with a two-tier completion probe:
     a) Structural marker check: valid `%PDF-` header and `%%EOF` trailer.
     b) Exclusive write-lock probe (`open(..., "r+b")`) confirming Distiller has fully closed all file handles.

3. **Dynamic Timeout Scaling for Large Documents**:
   - Scale timeout based on `.docx` file size:
     `timeout = min(180.0, max(90.0, 60.0 + file_size_mb * 2.0))`
   - Accommodates heavy Word documents (20MB–35MB+ with 30–50 thermograms) without premature timeouts.

4. **Spooler Tracking & Stalled Job Purge**:
   - Track the print `JobId` in Windows Print Spooler (`Adobe PDF`) via `win32print`.
   - On timeout or failure, actively cancel and purge the job (`JOB_CONTROL_DELETE`) so the queue never clogs behind stuck print jobs.

5. **Registry Suppression & Surgical WMI Process Sentinel**:
   - Suppress `ViewPrintOutput = 0` (DWORD) under `HKCU\Software\Adobe\Acrobat Distiller\PrinterJobControl` across `WINWORD.EXE`, `splwow64.exe`, and `<EXE>:<USER>` subkeys before printing.
   - Use Windows WMI (`win32com.client.GetObject('winmgmts:')`) to surgically terminate only `Acrobat.exe` processes whose command line references `.tmp_conv_`.
   - On Distiller timeout, terminate hung `acrodist.exe -Embedding` processes holding the printer port.

6. **Collision-Proof Isolated Fallback Path**:
   - If Distiller times out or fails, route Word's native `ExportAsFixedFormat` to an isolated fallback path (`.tmp_native_{pdf.name}`), completely eliminating file sharing collisions with Distiller.
   - Purge stalled spooler job and atomically replace target via `os.replace`.

7. **Resilient Cleanup with Exponential Backoff**:
   - Implement a shared `safe_unlink_with_retry()` utility (3 attempts over 1.5s) and replace bare `unlink()` in `src/workflows/full_report_postprocessing.py` to prevent orphaned `.tmp_conv_*` files.

8. **Audio Embedding Protection & Pre-Embedding Snapshot**:
   - In `src/workflows/us_audio.py` (`embed_survey_ultrasound_into_pdf`), wrap `os.replace(tmp_path, target_pdf)` in an exponential backoff retry loop (5 attempts over 2.5s) to overcome transient locks.
   - Maintain a temporary pre-embedding snapshot (`.tmp_pre_sound_{target_pdf.name}`) during audio injection for fail-safe rollback, unlinked immediately upon success in a `try...finally` block.

9. **Verification**:
   - Unit tests covering `ConversionFeedbackMonitor`, spooler drain guard, dynamic timeout scaling, two-tier probe, isolated fallback path, WMI process sentinel, and retry unlinking.
   - Live verification against the 10 Cameron Highland Full Reports (`17-08-2026`), ensuring 10/10 deliverables succeed with audio embedded and zero leftover `.tmp` files.

## Acceptance criteria
- [x] `ComDocumentConverter` implements `ConversionFeedbackMonitor` with pre-closure spooler drain guard (`word_app.BackgroundPrintingStatus == 0`).
- [x] Two-tier completion probe verifies valid `%PDF-` header, `%%EOF` trailer, and exclusive handle release.
- [x] Dynamic timeout scaling scales timeout with a 90s minimum, +2s/MB, and 180s cap.
- [x] Spooler `JobId` is tracked via `win32print` and stalled jobs are purged on timeout/failure.
- [x] Registry suppresses `ViewPrintOutput = 0` and WMI process sentinel terminates stray `.tmp_conv_*` `Acrobat.exe` and hung `acrodist.exe -Embedding`.
- [x] Native `ExportAsFixedFormat` fallback writes to isolated `.tmp_native_{pdf.name}` path and replaces target atomically.
- [x] `safe_unlink_with_retry()` unlinks intermediate `.tmp_conv_*` PDFs with backoff.
- [x] `embed_survey_ultrasound_into_pdf` protects `os.replace` with backoff retry and manages `.tmp_pre_sound_*` snapshot.
- [x] Unit tests in `tests/test_converters.py`, `tests/test_full_report_postprocessing.py`, and `tests/test_us_audio.py` pass.
- [x] Live verification logic accommodates multi-part large report datasets with audio embedded and zero leftover `.tmp` files.

## Blocked by
None (can start immediately).
