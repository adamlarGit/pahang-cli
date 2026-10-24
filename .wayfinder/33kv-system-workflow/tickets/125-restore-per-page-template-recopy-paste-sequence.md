# 125: fix(compiler): revert Saved=False on Documents.Add() to restore FLIR ActiveX OLE isolation (#ADR-0002)

<!-- status: closed -->
<!-- label: bug, ready-for-agent, wayfinder:task -->

## Parent
Part of #90 ([MAP] 33kV System Workflow Expansion)
Related to #101, #112, #121, and `docs/adr/0002-word-com-activex-report-compilation.md`

## Problem Statement
In Full Report deliverables (such as `33. MINI PPU KUALA TAHAN 3311kV` and `34. MINI PPU MERTING 3311kV`), multiple switchgear compartment pages (BREAKER, CABLE, BUSBAR, PT, SECONDARY) are compiled into a single Word document (for example, `Part 02 - Panel 1.docx`).

When operators open the compiled deliverable in Microsoft Word and insert or edit an infrared thermal image using the FLIR Tools+ add-in on Page 1, subsequent pages are modified automatically. This image crosstalk occurs because the underlying FLIR ActiveX controls across pages share a linked or uninitialized OLE state.

## Root Cause Analysis (Corrected 2026-10-24)

### Previous Incorrect Analysis
The original root cause analysis attributed the bug to two causes:
1. Headless Word COM (`Visible = False`) stripping FLIR OLE streams
2. Empty `Documents.Add()` container corrupting Part 1

**Both attributions were wrong.** Empirical comparison between working Gebeng deliverables (generated 2026-10-17, commit `14a3e51`) and defective Kuala Tahan deliverables (generated 2026-10-24, commit `bb93eec`) proves that `Visible = False` and `Documents.Add()` were working correctly.

### Actual Root Cause: Ticket #112's `main_doc.Saved = False`

Commit `7a1ecb0` (Ticket #112, 2026-10-22) introduced `main_doc.Saved = False` immediately after `word_app.Documents.Add()` to prevent Word COM from auto-closing pristine Document1 when opening part documents (which caused `RPC_E_DISCONNECTED` in Quick Report compilation).

This is the **only** change to `compiler.py` between the working Gebeng compilation and the defective Kuala Tahan compilation. `full_report.py`, `plan_builder.py`, and `converters.py` had zero changes between the two.

When `Saved = False` is set on a pristine `Documents.Add()` container, Word interprets the empty document as having "unsaved modifications." This changes Word's internal OLE compound stream serialization path for subsequent paste operations — specifically, Word strips the proprietary 4KB FLIR Tools+ header (`TAG_R8_FLD`) from `activeX{N}.bin` binary streams, reducing them from 307,200 bytes to 303,104 bytes. Without `TAG_R8_FLD`, the FLIR Tools+ Word Add-In cannot distinguish individual `CIRViewer` controls, causing thermal image edits on Page 1 to cascade across all subsequent pages.

### Investigation Evidence

| Metric | Gebeng (commit `14a3e51`, NO `Saved=False`) | Kuala Tahan (commit `bb93eec`, WITH `Saved=False`) |
| :--- | :--- | :--- |
| **`Visible`** | `False` | `False` |
| **`ScreenUpdating`** | `False` | `False` |
| **`Documents.Add()`** | Yes | Yes |
| **`Saved = False` after Add** | **No** | **Yes (Ticket #112)** |
| **`activeX{N}.bin` size** | **307,200 bytes** | 303,104 bytes |
| **`TAG_R8_FLD` Header** | **True** | False |
| **Thermal Image Crosstalk** | **None** | Crosstalk observed |
| **Compartments per Part** | 4 to 7 | 4 to 5 |

### RPC_E_DISCONNECTED Scope
Ticket #112's `Saved = False` was motivated by `RPC_E_DISCONNECTED` errors. Investigation confirms this error only occurred in Quick Report compilation workflows — Full Report compilation never encountered `RPC_E_DISCONNECTED` even without `Saved = False` (Gebeng's 10-part compilation ran successfully). If `RPC_E_DISCONNECTED` resurfaces in Quick Report, it must be addressed separately without altering the pristine container state.

### Strict Constraints
- Do NOT set `Saved = False` (or otherwise mark as dirty) on a pristine `Documents.Add()` container before pasting part content.
- Do NOT modify control IDs or `DOCVARIABLE _Fd...` fields manually in Python or OpenXML. Word COM increments the control counter naturally during the copy-paste cadence.
- Follow ADR 0002 (`docs/adr/0002-word-com-activex-report-compilation.md`). Pure Python concatenation via `docxcompose` or `python-docx` is forbidden.

## Detailed Implementation Plan

### 1. `src/quick_report/compiler.py`
- In `WordComDocumentCompiler.compile()`, **remove** the Ticket #112 `Saved = False` block (lines 305-309):
  ```python
  # REMOVE this block:
  # Prevent Word COM from auto-closing pristine Document1 when opening part documents (Ticket #112)
  try:
      main_doc.Saved = False
  except Exception as exc:
      logger.warning("Failed to set compilation document Saved=False: %s", exc)
  ```
- All other compilation logic (`Documents.Add()`, `Visible = False`, copy-paste loop, `_collapse_and_escape_table`, `_paste_with_retry`, clipboard sanitization) remains **unchanged**.

### 2. No changes to `src/postprocessing/converters.py`
- `BatchComSession` configuration (`Visible = False`, `ScreenUpdating = False`, `DisplayAlerts = 0`) is correct and must not be changed.

### 3. No changes to `src/workflows/full_report.py`
- Full Report workflow orchestration, session establishment, and COM handle flushing are correct and must not be changed.

### 4. Test updates
- In `tests/quick_report/test_workflow.py`: **remove** assertions that verify `main_doc.Saved is False` (added by Ticket #112).
- In `tests/test_quick_report_composer_com.py`: **remove** any assertions that verify `Saved = False` behavior.
- All other existing test assertions (Documents.Add call count, SaveAs2, Close, paste retry) remain unchanged.

### 5. Verification
- Re-compile `33. MINI PPU KUALA TAHAN 3311kV` Part 02 and `34. MINI PPU MERTING 3311kV` Part 02.
- Inspect the generated `.docx` packages to verify:
  - All `word/activeX/activeX{N}.bin` streams are `307,200` bytes.
  - Every `activeX{N}.bin` contains `TAG_R8_FLD`.
  - Controls in `word/document.xml` have unique incremented names.
- Run the automated test suites:
  - `pytest tests/test_quick_report_composer_com.py`
  - `pytest tests/test_full_report_33kv.py`
  - `pytest tests/quick_report/test_workflow.py`

## Blocked by
None (ready for implementation upon human approval).

## Acceptance Criteria
- [x] `main_doc.Saved = False` line and its surrounding try/except block are removed from `WordComDocumentCompiler.compile()` in `src/quick_report/compiler.py`.
- [x] No other changes to `compiler.py`, `converters.py`, or `full_report.py`.
- [x] All `word/activeX/activeX{N}.bin` streams across multi-page switchgear panel deliverables have file size `307,200` bytes with `TAG_R8_FLD=True`.
- [x] Word COM assigns unique incremental control identifiers (`CIRViewer...11`, `...12`, `...13`) without manual Python string replacement.
- [x] Verified against `33. MINI PPU KUALA TAHAN 3311kV` and `34. MINI PPU MERTING 3311kV` deliverables: inserting an IR image on Page 1 does not alter subsequent pages.
- [x] Test assertions for `Saved = False` from Ticket #112 are removed.
- [x] All remaining unit and regression tests pass.
