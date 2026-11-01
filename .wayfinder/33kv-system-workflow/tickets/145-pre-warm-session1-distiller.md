<!-- status: closed -->
# Ticket #145: fix(converters): pre-warm Session 1 Distiller instance to prevent Session 0 port monitor fallback

## Parent
Part of #144 (and #143, #142, #141, #140)

## Chronological Context
During verification of Ticket #144 against the Cameron Highland 17-08-2026 dataset, documents 101 and 102 still failed silent Adobe PDF printing, timing out after ~100s and falling back to native `ExportAsFixedFormat`.
Forensic inspection of the Windows process tree and Distiller logs revealed:
1. When Word prints an 88MB PostScript spool file to the `Adobe PDF` printer, the Windows Print Spooler port monitor (`AdobePdf.dll`) executing inside `spoolsv.exe` (running as `NT AUTHORITY\SYSTEM` in Session 0) looks for an active Acrobat Distiller instance listening on `\\.\pipe\PMtoDistiller`.
2. If `acrodist.exe` is not already active and listening in the interactive user desktop session (Session 1), `AdobePdf.dll` falls back to `CreateProcessW` inside Session 0!
3. In Session 0 (Non-interactive Services Session), Distiller has no desktop window station and `HKCU` maps to the SYSTEM profile (`systemprofile`), preventing it from reading the user's `PrinterJobControl` registry settings. `acrodist.exe` freezes at 0% CPU, completely deadlocking the port monitor.
4. When `PdfDistiller.PdfDistiller` is dispatched via COM (`win32com.client.Dispatch("PdfDistiller.PdfDistiller")`) from the interactive desktop session, `acrodist.exe` launches in Session 1 under user `ADAM` and establishes its COM server. When Word subsequently prints, `AdobePdf.dll` successfully routes the PostScript spool stream to the Session 1 Distiller, which compiles the deliverable PDF in seconds without ever touching Session 0.

## What to build
Ensure that Acrobat Distiller is actively pre-warmed and maintained in the interactive user session (Session 1) throughout batch Word conversions:

1. **Pre-warm Distiller COM Instance in Session 1**:
   - Implement `_ensure_session_distiller_warmed() -> object | None` in `src/postprocessing/converters.py`.
   - Dispatch `PdfDistiller.PdfDistiller` via COM inside Session 1, catching and logging any exceptions gracefully if Distiller COM is unavailable.
2. **Retain Distiller Application in BatchComSession**:
   - In `BatchComSession.__enter__`, pre-warm and hold an active reference `self.distiller_app = _ensure_session_distiller_warmed()`.
   - In `BatchComSession.__exit__`, safely release the COM reference (`del self.distiller_app`).
3. **Guard Standalone and Batch docx Printing**:
   - In `ComDocumentConverter._convert_docx_via_adobe_pdf`, ensure a warm Distiller reference exists before invoking `doc.PrintOut(Background=False)`.
4. **Unit Tests**:
   - Add unit tests in `tests/test_converters.py` validating that Distiller COM dispatch is called during batch session setup and Word conversion, verifying fallback safety if COM dispatch raises an error.

## Acceptance criteria
- [x] `_ensure_session_distiller_warmed()` dispatches `PdfDistiller.PdfDistiller` via COM in the interactive user session.
- [x] `BatchComSession` pre-warms and holds the Distiller COM reference across batch document conversions, releasing it cleanly on exit.
- [x] `ComDocumentConverter._convert_docx_via_adobe_pdf` verifies a warm Session 1 Distiller instance prior to issuing `doc.PrintOut(Background=False)`.
- [x] Unit tests in `tests/test_converters.py` cover pre-warm dispatch, COM session retention, and error degradation.
- [x] All unit tests pass with zero regressions.

## Blocked by
#144 (Completed).
