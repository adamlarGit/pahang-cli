# 2. Word COM Automation for Quick Report Compilation and FLIR ActiveX Isolation

Date: 2026-09-07
Status: Accepted

## Context

Quick Report generation renders individual document sections as separate `.docx` files on disk, then compiles them into a single deliverable report. CBM defect detail templates, including `swg-panel.docx` and `tx-detail.docx`, contain embedded FLIR Tools+ ActiveX controls identifiable by `CIRViewer` prefixes and `shapeid="_x0000_i1027"`. Engineers use these controls for interactive thermal image adjustments in Microsoft Word.

When merging multiple CBM defect pages using pure Python OpenXML libraries, two failure modes occur:

1. **ActiveX Image Crosstalk and Coupling**: Pure Python libraries like `docxcompose` or `python-docx` concatenate OpenXML body elements without re-instantiating internal OLE containers. Every defect page keeps the identical control identifier `CIRViewer121111113121`. Inserting or changing an infrared thermal image on one defect page automatically overwrites images on all other defect pages.
2. **Document Package Corruption**: In OpenXML, an ActiveX control links an XML node in `word/document.xml` to a binary OLE Compound File stream at `word/activeX/activeX{N}.bin`. Renaming control attributes directly in XML via Python string replacement breaks binary header offsets and checksums inside `activeX{N}.bin`. Microsoft Word flags the file as corrupt and displays an unreadable content recovery dialog.

Pure Python libraries cannot re-compile binary OLE Compound File streams in memory.

## Decision

Compile Quick Report deliverables exclusively through Microsoft Word COM Automation via `win32com.client` using the recopy and paste sequence in `src/quick_report/composer.py`.

Specifically:

1. **Master Document Container**: Initialize a blank container via `word_app.Documents.Add()`.
2. **Read-Only Part Ingestion**: Open each rendered part document read-only via `word_app.Documents.Open(part_path, False, True)`, copy its content to the Windows clipboard, and close the part file immediately.
3. **Table Range Escaping**: Execute `_collapse_and_escape_table()` to collapse the selection to the end of the document, and insert a 1 pt paragraph if the insertion point sits inside an open table.
4. **Section Separation and Paste**: Insert a page break via `rng.InsertBreak(7)` between parts, then paste via `_paste_with_retry()` using `rng.PasteAndFormat(16)` with fallback to `rng.Paste()`.
5. **Clipboard Sanitization**: Clear the Windows clipboard via `_clear_clipboard()` calling Win32 `EmptyClipboard` between parts and on document close, preventing the 5-second OLE serialization stall.
6. **No Pure Python Fallback**: Pure Python document concatenation via `docxcompose` or `python-docx` is banned from the Quick Report compilation pipeline. The compiler raises a `RuntimeError` if COM automation is unavailable.

## Why This Works

When Microsoft Word pastes content into a fresh `Documents.Add()` container, Word's native ActiveX container engine handles the OLE plumbing:

1. **Unique Control Identifiers**: Word assigns a new control identifier for each pasted page, such as `CIRViewer121111113121`, `CIRViewer1211111131211`, and `CIRViewer1211111131212`.
2. **Binary Stream Re-instantiation**: Word generates matching, isolated `activeX1.bin`, `activeX2.bin`, and subsequent binary streams inside the document package with valid headers.

## Consequences

- **Positive**:
  - Eliminates thermal image crosstalk across CBM defect pages.
  - Produces clean `.docx` deliverables without Microsoft Word unreadable content warnings.
  - Keeps FLIR Tools+ ActiveX controls fully operational for field engineers.
- **Negative and Constraints**:
  - Requires a Windows host with Microsoft Word installed. Report compilation cannot run headlessly on Linux without a Windows runner.
  - Slower than pure Python OpenXML concatenation.
  - Requires process lifecycle management to avoid orphaned `WINWORD.EXE` background instances.
