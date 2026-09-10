# Word COM Automation: Hard Page Breaks vs Section Breaks

This document captures the architectural trade-offs, Word COM automation mechanics, and empirical behavior comparing Microsoft Word Hard Page Breaks (`wdPageBreak = 7`) and Section Breaks (`wdSectionBreakNextPage = 2`) for multi-part report compilation in `pahang-cli` (Quick Report and Full Report).

---

## 1. Executive Summary & Comparison Matrix

In Word COM automation, report deliverables are compiled by stitching modular `.docx` parts (Front Page, Executive Summary Census, Component Scanning pages, Substation Condition photo grids, Visual Defect details, and Sticker pages) into a consolidated master document.

| Architectural Dimension | Hard Page Break (`wdPageBreak = 7`) | Section Break (`wdSectionBreakNextPage = 2`) |
| :--- | :--- | :--- |
| **Section Count** | Exactly 1 section throughout the entire document. | $N$ sections (one per document part). |
| **PageSetup & Margins** | **Shared across all pages**. In Word, `PageSetup` (margins, paper size, orientation) belongs to `Section`, not to individual pages or paragraphs. All stitched parts inherit the container's margins. | **Independent per part**. Each part preserves its own custom top, bottom, left, and right margins, paper size (A4), and orientation (portrait vs landscape). |
| **Header & Footer Behavior** | **Single uniform story**. Headers and footers apply globally across the document without section boundary logic. | **Linked by default (`LinkToPrevious = True`)**. Automation must explicitly sever linkages (`LinkToPrevious = False`) on all 3 header/footer types (primary, first-page, even/odd) before inserting or modifying headers in new sections. |
| **DrawingML & ActiveX Isolation** | Safe when assembled in fresh `Documents.Add()` containers per ADR 0002. However, floating shapes and defect callouts can reflow across page boundaries if table spacing shifts. | **Strict bounding container**. Floating shapes, red inspection callout boxes, and ActiveX controls cannot float across section boundaries, preventing vertical layout shift. |
| **Table Escaping Complexity** | Lower risk, but still requires collapsing insertion points outside tables (`_collapse_and_escape_table`) to avoid inserting breaks inside table cells. | **High risk if adjacent to tables**. Inserting a section break immediately inside or adjacent to a table without a separating paragraph can corrupt Word's internal OpenXML table definition. |
| **COM Overhead & Performance** | **Fastest**. Single layout and pagination thread. Minimal COM object hierarchy (`Sections.Count == 1`). | **Marginal overhead**. Each section adds internal `PageSetup` structures and 6 header/footer stories. Documents with 5–15 sections exhibit negligible performance delta (<0.2s difference). |

---

## 2. Hard Page Break (`wdPageBreak = 7`)

### How It Operates
A hard page break is inserted into the Word range via:
```python
rng.InsertBreak(7)  # wdPageBreak = 7
```
This inserts an ASCII form-feed / page-break control character within the current section's body story.

### Advantages
1. **Zero Header/Footer Contamination**: Because there is only one section, there is no risk of Word COM's notorious `LinkToPrevious` header mutation bug, where pasting content into Section $N$ retroactively mutates Section 1.
2. **Simplified Range Management**: Range collapse and table escaping are straightforward. Once escaped from a table, inserting `wdPageBreak` reliably advances the insertion point to the top of the next page.
3. **Pristine Benchmark Parity**: Canonical benchmark deliverables (`005. TALAPIA`, `179. CENDERAWASIH NO.1`, `144. TELEKOM TANAH PUTIH`) use zero Word headers, footers, or page numbers, making a single continuous section completely natural.

### Limitations
1. **Container Margin Override**: If a blank container is created via `word_app.Documents.Add()`, Word applies the global `Normal.dotm` default margins (typically 1.0 inch / 2.54 cm). Even if individual templates were designed with 0.5-inch margins for dense equipment tables or photo grids, pasting text retains character styles but forces the section margins to 1.0 inch.
2. **Cannot Mix Page Orientations**: A single section cannot mix portrait (e.g. equipment scan pages) and landscape pages (e.g. wide equipment tables). (In `pahang-cli`, landscape testsheets are appended via PDF merge, mitigating this).

---

## 3. Section Break (`wdSectionBreakNextPage = 2`)

### How It Operates
A next-page section break is inserted via:
```python
rng.InsertBreak(2)  # wdSectionBreakNextPage = 2
```
This terminates the preceding section and initializes a new section on a fresh page.

### Advantages
1. **Independent PageSetup per Part**:
   Allows each report component to declare its own margins:
   - Front Page: standard margins (1.0 in or custom cover margins).
   - Executive Summary & CBM Scanning pages: compact margins (0.5 in / 1.27 cm) maximizing equipment table width and waveform chart clarity.
   - Substation Condition & VI Photo Grids: symmetrical photo grid margins (0.6 in).
   - Sticker Page: narrow margins (0.4 in) accommodating full-width sticker photos.
2. **Hard Layout Isolation**: Floating callouts (arrows, red rectangular defect boxes) are strictly contained within their originating section and will never bleed onto neighboring equipment pages.

### Required Safeguards for Section Breaks
If using section breaks in Word COM automation, the following safeguards are mandatory:

1. **Explicit Header/Footer Unlinking**:
   Word initializes every new section with `LinkToPrevious = True`. Before pasting or editing content in the new section, the automation must unlink headers and footers:
   ```python
   new_sec = main_doc.Sections(main_doc.Sections.Count)
   for header in new_sec.Headers:
       header.LinkToPrevious = False
   for footer in new_sec.Footers:
       footer.LinkToPrevious = False
   ```
2. **Strict Table Boundary Escaping**:
   Inserting `wdSectionBreakNextPage` inside a table or directly at the boundary of a table row without a trailing paragraph can corrupt the OpenXML `w:sectPr` placement. The compiler must always call `_collapse_and_escape_table` before break insertion.
3. **Explicit PageSetup Mirroring**:
   When opening a part document, copy its `PageSetup` explicitly into `new_sec.PageSetup` to enforce the part's intended margins:
   ```python
   new_sec.PageSetup.TopMargin = part_doc.PageSetup.TopMargin
   new_sec.PageSetup.BottomMargin = part_doc.PageSetup.BottomMargin
   new_sec.PageSetup.LeftMargin = part_doc.PageSetup.LeftMargin
   new_sec.PageSetup.RightMargin = part_doc.PageSetup.RightMargin
   ```

---

## 4. Container Margin Preservation Without Section Breaks (Pattern B)

When hard page breaks (`wdPageBreak`) are chosen for simplicity and benchmark fidelity, the container margin breakage can be completely avoided by copying the `PageSetup` and `CompatibilityMode` from the **first part** (`parts[0]`) onto `main_doc.PageSetup` immediately upon creation:

```python
main_doc = word_app.Documents.Add()
first_part_doc = word_app.Documents.Open(str(Path(parts[0]).resolve()), False, True)
try:
    # 1. Mirror PageSetup from first part
    main_doc.PageSetup.TopMargin = first_part_doc.PageSetup.TopMargin
    main_doc.PageSetup.BottomMargin = first_part_doc.PageSetup.BottomMargin
    main_doc.PageSetup.LeftMargin = first_part_doc.PageSetup.LeftMargin
    main_doc.PageSetup.RightMargin = first_part_doc.PageSetup.RightMargin
    main_doc.PageSetup.Orientation = first_part_doc.PageSetup.Orientation
    main_doc.PageSetup.PaperSize = first_part_doc.PageSetup.PaperSize

    # 2. Mirror CompatibilityMode (Word 2010 / 2013 / 2016 layout engine)
    if hasattr(first_part_doc, "CompatibilityMode"):
        try:
            main_doc.SetCompatibilityMode(first_part_doc.CompatibilityMode)
        except Exception:
            pass
finally:
    first_part_doc.Close(False)
```

This ensures `main_doc` adopts the exact custom margins and layout engine version of the project's canonical templates without requiring multi-section unlinking logic.
