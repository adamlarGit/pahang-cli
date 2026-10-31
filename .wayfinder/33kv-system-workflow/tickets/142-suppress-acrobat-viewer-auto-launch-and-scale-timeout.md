<!-- status: open -->
# Ticket #142: fix(converters): suppress Acrobat viewer auto-launch, scale large-document timeout, and isolate fallback paths

## Parent
Part of #141 (and #140)

## What to build
Fix Full Report post-processing conversion failures and eliminate orphaned `.tmp_conv_*.pdf` files caused by Adobe Acrobat viewer background locking and Distiller timeout collisions on large Word documents:

1. **Suppress Acrobat Viewer Auto-Launch & Locking**:
   - Suppress `ViewPrintOutput` (`0`) during silent Adobe PDF printing via registry / DevMode automation.
   - Clean up any stray `Acrobat.exe` processes spawned by the printer driver holding locks on temporary `.tmp_conv_*.pdf` conversion files.

2. **Scale Timeout for Large Documents**:
   - Replace the fixed 30s timeout with a scaled timeout (e.g. 90s–120s or scaled by document file size) in `ComDocumentConverter` so heavy Word documents (20MB–35MB+) finish distilling PostScript without premature timeouts.

3. **Collision-Proof Fallback Path**:
   - Ensure the native `ExportAsFixedFormat` fallback writes to an isolated fallback file path if Distiller times out, rather than attempting to write to the file Distiller is actively writing to, preventing `"Word cannot save this document because it is in use elsewhere"`.

4. **Resilient Cleanup with Backoff**:
   - Enhance intermediate `.tmp_conv_*.pdf` file unlinking in `full_report_postprocessing.py` with retry/backoff, ensuring no orphaned `.tmp` files linger in deliverable folders.

5. **Verification**:
   - Unit tests covering viewer suppression, scaled timeouts, isolated fallback paths, and retry unlinking.
   - Live verification against the 10 Cameron Highland Full Reports (`17-08-2026`), ensuring 10/10 deliverables succeed with zero leftover `.tmp` files.

## Acceptance criteria
- [ ] `ComDocumentConverter` suppresses `ViewPrintOutput` and cleans up any stray background `Acrobat.exe` viewer handles targeting temporary PDF paths.
- [ ] `adobe_timeout` in `ComDocumentConverter` is scaled (default $\ge 90$s or dynamic) to accommodate 30MB+ Word documents with dozens of thermograms.
- [ ] Native `ExportAsFixedFormat` fallback writes to an isolated path when Distiller print encounters a timeout or exception, eliminating file sharing collisions.
- [ ] Intermediate `.tmp_conv_*` PDFs are unlinked reliably with retry/backoff so no temporary files linger in deliverable folders.
- [ ] Unit tests in `tests/test_converters.py` and `tests/test_full_report_postprocessing.py` pass.
- [ ] Verification against 17-08-2026 Cameron Highland dataset passes with 10/10 deliverables generated and zero `.tmp` files remaining.

## Blocked by
None (can start immediately).
