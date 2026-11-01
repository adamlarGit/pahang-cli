<!-- status: closed -->
# Ticket #147: feat(converters): native export with Source Image Restoration as the Full Report conversion path

## Parent
Part of #146 (and #145, #144, #143, #142, #141, #140).
Implements [ADR 0009](../../../docs/adr/0009-native-export-with-source-image-restoration.md) Decision §2–§4 (supersedes ADR 0008). Uses #146.

## Context
`ComDocumentConverter.convert_docx_to_pdf` currently tries Adobe PDF printing first and falls back to native export. After this ticket the Full Report path is: native export, then restoration, then the existing merge, testsheet append, and sound embedding. The Adobe code still exists but is no longer reached from Full Report. Deleting it is #148.

33kV substations are always multi-part. They range from 9 to 47 parts per substation, with "TX and Condition" parts up to about 18 MB and about 124 MB of DOCX for PMU JERANTUT. So per-part isolation and consistency matter more here than in 11kV.

## What to build

### 1. Conversion flow per DOCX (single file or one part)
1. **Snapshot.** Read the DOCX bytes into memory and record its size, mtime, and SHA-256 *before* Word opens it.
2. **Export.** Word `ExportAsFixedFormat` (unchanged parameters) to `.tmp_native_<token>_<name>`, with `token = uuid4().hex[:8]` per conversion.
3. **Consistency check.** Re-hash the DOCX after export.
   - If it changed (the operator saved it during conversion), redo steps 1–2 once.
   - If it changes again, keep the native PDF and warn `source changed during conversion`. This guarantees restoration never mixes pixels from a different revision.
4. **Validate the export.** It must exist, open, and have more than 0 pages. Retry the open with backoff to tolerate AV or indexer scans.
5. **Restore.** Call `restore_source_images(snapshot_bytes, native_tmp, restore_tmp)`.
6. **Publish.** Atomically publish the restored PDF to `pdf_path`. On `RestorationError` or any unexpected restoration exception, publish the **native** PDF instead, log a warning with the part name, and mark the report as a fallback.
7. **Clean up.** Every temp file is removed in `finally` on all paths.

### 2. Word session health (found by the 33kV rerun)
In one long-lived 32-bit Word session, the 41 MB "TX and Condition" part of PPU APMM came back from `ExportAsFixedFormat` **with no exception and no file**, after 31 large parts had gone through the same `WINWORD.EXE`. In a fresh Word instance it exported correctly in 9 s. Required behaviour:
- Treat "export returned but the output is missing, empty, or won't open" as an export failure.
- On an export failure, `Quit()` the batch's own Word instance, start a fresh one through `BatchComSession`, reopen the part, and retry **once**. Only after that does the part count as failed.
- **Recycle Word proactively** at every substation boundary during post-processing. This is the same rule Ticket #65 already applies to generation in `full_report.py`. This amends decision Q84 ("single shared `BatchComSession` without per-substation recycling"). **Approved by the maintainer on 01-11-2026 (Q112)**: restarting at substation boundaries has been tested and removes the silent-failure edge case.

### 3. Failure isolation
- A restoration failure affects **only that part**: the part keeps its native PDF and the substation still completes. This holds even for a 47-part substation.
- A Word export failure keeps today's behaviour: one retry with a fresh document handle, then the substation is marked failed.

### 4. Batch-level race safety (`FullReportPostProcessingWorkflow`)
- **Run lock.** Create `.postprocess.lock` in each date folder being processed, with an exclusive create holding PID and start time.
  - If the lock is held by a live process, skip that folder with a clear message.
  - If it was left by a dead PID, take it over.
  - Release it in `finally`.
- This prevents two CLI runs from colliding on the deterministic `.tmp_conv_<stem>_part_NN` and `.tmp_mrg_*` names.
- **Stale temp sweep.** After the lock is acquired, delete `.tmp_conv_*`, `.tmp_native_*`, `.tmp_restore_*` and `.tmp_mrg_*` left in that folder by dead runs.
- **Word owner files.** Never delete `~$*` files: they can mean the operator has the document open. Make sure every discovery path, including `_expand_multipart_siblings`, ignores them. The probe saw a killed Word session leave `~$` files next to the parts.
- **Keep the machine awake.** For the whole batch, call `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` and clear it in `finally`.
  - Why: during the 33kV probe the laptop slept for 12 minutes in the middle of the batch after a power-source change. Word resumed and finished correctly, but one part took 732 s instead of about 12 s.
  - This prevents idle sleep. It cannot stop a lid-close or a forced sleep, so the run must also stay correct when resumed. The probe showed it does.
- **Orphaned Word on interrupt.** If the run is interrupted, the batch session must still `Quit()` its own `DispatchEx` Word instance in `finally`, and must never touch Word instances it did not start.

### 5. Telemetry and operator notice
- Attach each part's `RestorationReport` to `FullReportPostProcessingTelemetry` and `Result`. Aggregate per report: restored, unmatched, ambiguous, and parts that fell back.
- Summary banner line per report, for example `[IMG] 01. PPU APMM 3311kV: restored 412 images across 32 parts, 37 unmatched, 0 fallbacks`. Show a warning row when any part fell back.
- Nothing is persisted (`Restoration Report` in CONTEXT.md).

### 6. Unchanged on purpose
- `configure_uniform_printer` runs once per batch session. It fixes pagination (ADR 0009 §1, "Kept").
- `merge_pdfs_batch`, testsheet append, and sound embedding are unchanged. Sound embedding still runs after merge and relies on the unchanged image rects.
- Excel testsheet conversion is unchanged.

## Acceptance criteria
- [x] `convert_docx_to_pdf` never calls `PrintOut` or Distiller for Full Report parts.
- [x] Snapshot and hash consistency check is in place, with the single redo and the warning on a second change.
- [x] Unique per-conversion temp names, all removed on success, on failure, and on a `KeyboardInterrupt` between steps.
- [x] Restoration failure in one part of a multi-part group yields a completed deliverable with that part native, plus a warning.
- [x] The run lock prevents concurrent post-processing of the same date folder. A dead-PID lock is taken over, and stale temps are swept.
- [x] An export that returns without writing a file triggers one retry in a fresh Word instance. Word is recycled at each substation boundary.
- [x] Restoration counts appear in the batch summary.
- [x] Unit and workflow tests use `FakeDocumentConverter` and the restoration module with a stub where needed. 33kV multi-part workflow tests (`tests/test_full_report_postprocessing_33kv.py`) are updated.
- [x] All tests pass with zero regressions.

## Blocked by
#146
