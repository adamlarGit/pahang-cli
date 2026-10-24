# 2. Word COM Automation for Report Compilation and FLIR ActiveX Isolation

Date: 2026-09-07 (Updated: 2026-10-24)
Status: Accepted

## Context

Report generation renders individual document sections as separate `.docx` files on disk, then compiles them into deliverable reports. This applies to both Quick Report defect deliverables and Full Report switchgear panel chunks (for example, `Part 02 - Panel 1 (33kV - SPARE).docx`), where multiple switchgear compartment scan pages (BREAKER, CABLE, BUSBAR, PT, SECONDARY) are merged into a single deliverable.

CBM defect detail templates, including `swg-panel.docx` and `tx-detail.docx`, contain embedded FLIR Tools+ ActiveX controls identifiable by `CIRViewer` prefixes (such as `CIRViewer1211111131211`) and `shapeid="_x0000_i1032"`. Engineers use these controls for interactive thermal image adjustments in Microsoft Word.

When merging multiple pages that contain FLIR ActiveX controls using pure Python OpenXML libraries, two failure modes occur:

1. **ActiveX Image Crosstalk and Coupling**: Pure Python libraries like `docxcompose` or `python-docx` concatenate OpenXML body elements without re-instantiating internal OLE containers. Every page keeps the identical control identifier. Inserting or changing an infrared thermal image on one page in Microsoft Word automatically overwrites or alters images across all other pages.
2. **Document Package Corruption**: In OpenXML, an ActiveX control links an XML node in `word/document.xml` to a binary OLE Compound File stream at `word/activeX/activeX{N}.bin`. Renaming control attributes directly in XML via Python string replacement breaks binary header offsets and internal OLE stream structures inside `activeX{N}.bin`. Microsoft Word flags the file as corrupt and displays an unreadable content recovery prompt.

Pure Python libraries cannot recompile or re-index binary OLE Compound File streams in memory.

## Decision

Compile both Quick Report and Full Report multi-page deliverables exclusively through Microsoft Word COM Automation via `win32com.client` using the per-page copy-and-paste ingestion sequence in `src/quick_report/compiler.py`.

Specifically:

1. **Headless COM (`Visible = False`, `ScreenUpdating = False`)**: Word COM runs in headless mode during document compilation. Empirical testing (see Forensic Evidence below) confirms that `Visible = False` and `ScreenUpdating = False` correctly preserve FLIR OLE compound stream serialization, provided the `Documents.Add()` container is not artificially marked as dirty (see Constraint 2).
2. **Pristine `Documents.Add()` Container**: Initialize the compilation document via `word_app.Documents.Add()`. The pristine container must remain in its default state — do NOT set `main_doc.Saved = False` or otherwise mark the empty document as dirty before pasting. Setting `Saved = False` on a pristine `Documents.Add()` container causes Word's OLE serialization to strip the proprietary 4KB FLIR stream header (`TAG_R8_FLD`) from ActiveX binary streams during subsequent paste operations, shrinking `activeX{N}.bin` from 307,200 bytes down to 303,104 bytes and causing thermal image crosstalk across pages.
3. **Per-Page Copy-Paste Ingestion Cadence**: For each rendered part file (indexed 0 through N-1), open the part read-only via `word_app.Documents.Open(part_path, False, True)`, copy its content via `part_doc.Content.Copy()`, collapse the insertion point to the end of the destination document via `_collapse_and_escape_table(main_doc)`, insert a page break for parts after the first (`rng.InsertBreak(7)`), paste the content via `_paste_with_retry(rng)`, and close the part file immediately.
4. **No Manual Identifier or Field Rewriting**: Do not attempt to string-replace control names (`CIRViewer...`), shape IDs, or Word field variables (`DOCVARIABLE _Fd...`) in Python. Word's native ActiveX container engine assigns incremented control identifiers (`CIRViewer1211111131211`, `CIRViewer12111111312111`, etc.) automatically during the copy-paste cadence.
5. **Clipboard Sanitization**: Clear the Windows clipboard via Win32 `EmptyClipboard` between parts and on document close to prevent OLE serialization hangs.
6. **No Pure Python Fallback**: Pure Python document concatenation via `docxcompose` or `python-docx` is strictly forbidden from the compilation pipeline. The compiler raises a `RuntimeError` if COM automation is unavailable.

## Why This Works

When Microsoft Word pastes content from separate rendered `.docx` part files into a `Documents.Add()` container, Word's native ActiveX container engine and the registered FLIR Word Add-In handle the OLE plumbing:

1. **Unique Control Identifiers**: Word assigns a new control identifier for each pasted page, incrementing suffixes sequentially (`CIRViewer1211111131211`, `CIRViewer12111111312111`, `CIRViewer12111111312112`).
2. **Binary Stream Re-instantiation**: Word generates matching, isolated `activeX1.bin`, `activeX2.bin`, and subsequent binary streams inside the document package.
3. **FLIR Stream Integrity**: When the `Documents.Add()` container is in its pristine default state (not marked dirty via `Saved = False`), Word preserves the 4KB proprietary FLIR stream containing `TAG_R8_FLD`, giving each binary stream the full 307,200-byte structure required by FLIR Tools+ to isolate thermal images and temperature spot readings.

## Constraint: Do NOT Set `Saved = False` on Pristine `Documents.Add()`

This constraint is the single most critical invariant in the compilation pipeline. Violating it causes the FLIR ActiveX crosstalk regression.

**Root Cause (discovered 2026-10-24)**: When `main_doc.Saved = False` is called immediately after `word_app.Documents.Add()`, Word interprets the empty document as having "unsaved modifications." This changes Word's internal OLE compound stream serialization path for subsequent paste operations. Specifically, Word strips the proprietary 4KB FLIR Tools+ header (`TAG_R8_FLD`) from `activeX{N}.bin` binary streams, reducing them from 307,200 bytes to 303,104 bytes. Without `TAG_R8_FLD`, the FLIR Tools+ Word Add-In (`WordAddin.WordAddin`) cannot distinguish individual `CIRViewer` controls in the document. Editing an IR thermal image on Page 1 cascades across all subsequent pages.

**Why the constraint was violated (Ticket #112)**: Commit `7a1ecb0` introduced `main_doc.Saved = False` to prevent Word COM from auto-closing the pristine `Document1` when opening part documents, which caused `RPC_E_DISCONNECTED` errors. However, this side effect only manifested in Quick Report compilation workflows — Full Report compilation never encountered `RPC_E_DISCONNECTED` even without `Saved = False` (see Gebeng benchmark below). If `RPC_E_DISCONNECTED` resurfaces in Quick Report workflows, it must be addressed through a separate mechanism that does not alter the pristine container's `Saved` state.

## Forensic Evidence and Verification Benchmarks

### Investigation Methodology (2026-10-24)

A controlled comparison was performed between working and defective deliverables. Git history analysis isolated the exact commit that introduced the regression. The investigation confirmed:

- `src/quick_report/compiler.py` had exactly ONE change between the working and broken compilations: commit `7a1ecb0` (Ticket #112, `main_doc.Saved = False`).
- `src/workflows/full_report.py`, `src/full_report/plan_builder.py`, and `src/postprocessing/converters.py` had ZERO changes between the two compilations.
- Both compilations used identical Word COM configuration: `Visible = False`, `ScreenUpdating = False`, `DisplayAlerts = 0`.
- Both compilations used `Documents.Add()` for document initialization.

### Working Benchmark: Gebeng (Generated 2026-10-17, commit `14a3e51`)

Compiler configuration at generation time:
- `dispatched_word.Visible = False`
- `dispatched_word.ScreenUpdating = False`
- `main_doc = word_app.Documents.Add()` — pristine state, NO `Saved = False`

Deliverables in `FULL REPORT/GEBENG/01. OCTOBER/08-10-2026/`:

- **`05. SSU KPC GEBENG 33kV`** (10 Part files):
  - Part 02 through Part 09: each contains 4 to 7 switchgear compartment scan pages (BREAKER, CABLE, BUSBAR, PT, CABLE ENTRY, LINK BOX, SECONDARY) merged into a single document.
  - Every `activeX{N}.bin` stream: **307,200 bytes**, `TAG_R8_FLD=True`.
  - Every control has a unique incremental name.
  - Zero crosstalk when inserting or editing IR images.
- **`07. PMU GBID CABIN 33kV`** (7 Part files):
  - Same structure and metrics. All `activeX{N}.bin` streams: **307,200 bytes**, `TAG_R8_FLD=True`.

Additional working benchmarks: `25. MINI PPU SG KOYAN 3311kV`, `28. MINI PPU TERLA 3311kV`.

### Defective Deliverables: Kuala Tahan and Merting (Generated 2026-10-24, commit `bb93eec` which includes `7a1ecb0`)

Compiler configuration at generation time:
- `dispatched_word.Visible = False`
- `dispatched_word.ScreenUpdating = False`
- `main_doc = word_app.Documents.Add()` followed by `main_doc.Saved = False` (Ticket #112)

Deliverables in `FULL REPORT/JERANTUT/01. OCTOBER/22-10-2026/`:

- **`33. MINI PPU KUALA TAHAN 3311kV (VI)`** (7 Part files):
  - Part 02 through Part 06: each contains 4 to 5 switchgear compartment scan pages.
  - Every `activeX{N}.bin` stream: **303,104 bytes**, `TAG_R8_FLD=False`.
  - Controls share corrupted OLE structures, causing thermal image changes on Page 1 to overwrite all subsequent pages.
- **`34. MINI PPU MERTING 3311kV (VI)`** (7 Part files):
  - Same defective metrics. All `activeX{N}.bin` streams: **303,104 bytes**, `TAG_R8_FLD=False`.

### Comparative Summary

| Metric | Working (Gebeng, `14a3e51`) | Defective (Kuala Tahan, `bb93eec`) |
| :--- | :--- | :--- |
| **`Visible`** | `False` | `False` |
| **`ScreenUpdating`** | `False` | `False` |
| **`Documents.Add()`** | Yes | Yes |
| **`Saved = False` after Add** | **No** | **Yes (Ticket #112)** |
| **`activeX{N}.bin` size** | 307,200 bytes | 303,104 bytes |
| **`TAG_R8_FLD` Header** | `True` | `False` |
| **Control Identifiers** | Unique incremental | Collapsed / Linked |
| **Thermal Image Crosstalk** | None (100% isolated) | Crosstalk observed |

## Consequences

- **Positive**:
  - Eliminates thermal image crosstalk across multi-page switchgear panels and CBM defect pages.
  - Produces clean `.docx` deliverables without Microsoft Word unreadable content warnings.
  - Keeps FLIR Tools+ ActiveX controls fully operational for field engineers.
  - Runs headlessly (`Visible = False`) without requiring a visible Word window.
- **Negative and Constraints**:
  - Requires a Windows host with Microsoft Word and FLIR Tools+ installed. Report compilation cannot run headlessly on Linux without a Windows runner.
  - The `Documents.Add()` container MUST remain in its pristine default state. Any code that marks the container as dirty (`Saved = False`, or similar modifications to the empty document before pasting part content) will corrupt the FLIR OLE serialization.
  - Requires process lifecycle management to avoid orphaned `WINWORD.EXE` background instances.
  - If `RPC_E_DISCONNECTED` errors resurface in Quick Report compilation (the original motivation for `Saved = False`), they must be resolved through a mechanism that does not alter the pristine container state — for example, catching and retrying the disconnection, or switching to `Documents.Open(parts[0])` as a targeted Quick Report-only fix.
