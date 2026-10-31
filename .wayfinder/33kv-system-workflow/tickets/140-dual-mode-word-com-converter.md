<!-- status: closed -->
# Ticket #140: feat(converters): dual-mode Word COM converter with silent Adobe PDF print and native fallback

## Parent
Part of #90

## What to build
A high-fidelity Word document to PDF conversion mechanism within `ComDocumentConverter.convert_docx_to_pdf` that:
1. Detects whether the `Adobe PDF` printer and Acrobat Distiller are available on the host machine.
2. When available, routes conversion through `Adobe PDF` with `High Quality Print(1)` preset, using Acrobat Distiller's transient `PrinterJobControl` registry automation to silently stream directly to the target PDF file without user dialog prompts.
3. Automatically falls back to Word's native `ExportAsFixedFormat(OptimizeFor=0)` when `Adobe PDF` is not available or if the print job encounters an exception.
4. Preserves full image resolution (e.g. 1200x380 component PNGs, uncompressed cover JPEGs) and A4 geometry across all consumer workflows.

## Acceptance criteria
- [x] `ComDocumentConverter.convert_docx_to_pdf` checks for `Adobe PDF` printer and runs silent print with transient `PrinterJobControl` registry automation for both `WINWORD.EXE` and `splwow64.exe`.
- [x] Active Acrobat Distiller joboptions preset `High Quality Print(1)` or equivalent non-downsampling profile is utilized.
- [x] Registry entries in `HKCU\Software\Adobe\Acrobat Distiller\PrinterJobControl` are cleaned up deterministically in a `finally` block even if errors occur.
- [x] Graceful fallback to `doc.ExportAsFixedFormat` occurs if `Adobe PDF` is missing or on error.
- [x] Unit tests in `tests/test_postprocessing_cli_adapter.py` / `tests/test_converters.py` verify both the Adobe PDF branch and fallback branch.

## Blocked by
None (can start immediately).
