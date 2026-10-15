<!-- status: closed -->
Part of #90
Specification: [spec.md](../spec.md)

# 097: feat(33kv-postprocessing): 33kV pre-flight validation, signature alignment, diagonal borders, per-sheet PageSetup PDF export & deliverable stitching

**What to build:** Extend post-processing pipeline for 33kV projects: update pre-flight file integrity checks to support PPU/SSU naming and multi-sheet testsheets, rewrite `select_and_sort_sheets()` with voltage-aware sequential ordering, implement 33kV signature image anchor coordinates for all 3 sheet layout families, implement 33kV diagonal borders blanking in `diagonal_borders.py` (with refined TX groups), implement programmatic per-sheet PageSetup in `ComDocumentConverter` (with individual per-sheet margins), and stitch final client deliverable `<STEM>.pdf`.

**Blocked by:** #96

**Status:** closed

## Detailed Design & Architecture

1. **Pre-Flight Validation & File Renaming Synchronization (`src/workflows/postprocessing_preflight.py` & `src/workflows/rename_files.py`)**:
   - Pair Quick Reports (.docx), testsheets (.xlsx), and raw material folders by matching numerical prefixes via `extract_numerical_prefix()`.
   - Robust to dynamic defect suffixes (e.g. pairing `09. PPU SEMAMBU YARD 33-11kV (VI).docx` with `09. PPU SEMAMBU YARD 33-11kV.xlsx` and `09. PPU SEMAMBU YARD 33-11kV (VI)/`).

2. **Sequential Voltage-Aware Sheet Selection (`src/postprocessing/converters.py`)**:
   - In `select_and_sort_sheets(worksheet_names, target_sheets)`:
     - Detect 33kV workbooks (presence of `33kV (Main)`, `11kV (Main)`, etc.).
     - Sort sheets in strict sequential order:
       1. `33kV (Main)`
       2. `33kV (Extra)`, `33kV (Extra) (2)`, `33kV (Extra) (3)` ... (sorted sequentially by extra index)
       3. `11kV (Main)`
       4. `11kV (Extra)`, `11kV (Extra) (2)`, `11kV (Extra) (3)` ... (sorted sequentially by extra index)
       5. `TX`
       6. `Visual Inspec.` / `Visual Inspection`
     - Strictly exclude `RAW DATA` and unpopulated extra template sheets.
     - Preserve existing `PCE Testsheet` / `PCE VI` selection and sorting for 11kV workbooks.

3. **Programmatic Per-Sheet `PageSetup` & Margins (`ComDocumentConverter`)**:
   - Classify worksheet type and configure independent PageSetup properties on each sheet before COM export:
     - **Switchgear sheets** (`33kV (Main/Extra)`, `11kV (Main/Extra)`):
       - `Orientation = 2` (xlLandscape)
       - `PaperSize = 9` (xlPaperA4)
       - `LeftMargin = RightMargin = 2.83 pt` (~1mm / 0.039")
       - `TopMargin = BottomMargin = 0 pt`
       - `FitToPagesWide = 1`, `FitToPagesTall = False`, `Zoom = False`
     - **Transformer sheet** (`TX`):
       - `Orientation = 2` (xlLandscape)
       - `PaperSize = 9` (xlPaperA4)
       - `LeftMargin = RightMargin = 2.83 pt` (~1mm / 0.039")
       - `TopMargin = BottomMargin = 0 pt`
       - `FitToPagesWide = 1`, `FitToPagesTall = False`, `Zoom = False`
     - **Visual Inspection sheet** (`Visual Inspec.` / `Visual Inspection`):
       - `Orientation = 1` (xlPortrait)
       - `PaperSize = 9` (xlPaperA4)
       - `LeftMargin = RightMargin = 18 pt` (0.25")
       - `TopMargin = BottomMargin = 54 pt` (0.75")
       - `FitToPagesWide = 1`, `FitToPagesTall = False`, `Zoom = False`

4. **Signature Anchor Geometries Across 3 Sheet Layouts (`src/workflows/replace_signatures.py`)**:
   - Sheet layout classifier: route sheets to layout keys (`"switchgear"`, `"transformer"`, `"visual_inspection"`, `"pce_testsheet"`, `"pce_vi"`).
   - Anchor coordinates:
     - **Switchgear** (`33kV (Main/Extra)`, `11kV (Main/Extra)`):
       - Vendor placeholder at `E77` (spans Cols 3–6, Rows 74–80)
       - TNB placeholder at `L77` (spans Cols 10–13, Rows 73–80)
     - **Transformer** (`TX`):
       - Vendor placeholder at `F73` (spans Cols 5–8, Rows 70–76)
       - TNB placeholder at `R73` (spans Cols 16–22, Rows 70–78)
     - **Visual Inspection** (`Visual Inspec.` / `Visual Inspection`):
       - Vendor placeholder at `D82` (spans Cols 3–6, Rows 80–86)
       - TNB placeholder at `M82` (spans Cols 11–16, Rows 80–87)
   - Support `mode="placeholder"` (insert signature image into anchor and strip placeholder) and `mode="none"` (cleanly remove `{{signvendor}}` and `{{signtnb}}` text).

5. **33kV Diagonal Borders Blank Cell Scan Ranges (`src/workflows/diagonal_borders.py`)**:
   - **Switchgear sheets**: scan measurement grids `C15:U62` and apply diagonal slashes to blank cells.
   - **Transformer sheet (`TX`)**: scan exact cell groups (handling merged cells safely via top-left cell evaluation):
     - Group 1: `F14:AD28` (Primary Terminations & Ultrasound)
     - Group 2: `F33:AD47` (Auxiliary Components)
     - Group 3: `D51:F54` (Station Service LVDB Section)
     - Group 4: `D57:O58` (Neutral Earthing Resistor Section)
     - Group 5: `C62:Q71` (Inspection Notes Section)
   - **Visual Inspection sheet**: strictly unslashed (0 diagonal cells).
   - Clean tables and repair openpyxl drawings/relationships via `_repair_openpyxl_zip()`.

6. **Deliverable Stitching**:
   - `converter.convert_docx_to_pdf()` generates portrait Quick Report PDF.
   - `converter.convert_testsheet_to_pdf()` compiles multi-orientation testsheet PDF (landscape switchgear/TX + portrait VI).
   - `converter.merge_pdfs()` sequentially concatenates Quick Report PDF + testsheet PDF into the final `<STEM>.pdf`.

## Acceptance Criteria Checklist

- [x] Update `validate_postprocessing_preflight()` and `rename_files_match()` to pair files by `extract_numerical_prefix()`.
- [x] Implement voltage-aware sequential sheet selection in `select_and_sort_sheets()`:
  - [x] Sort `33kV (Main)` → `33kV (Extra)` (sequentially numbered) → `11kV (Main)` → `11kV (Extra)` (sequentially numbered) → `TX` → `Visual Inspec.`.
  - [x] Strictly exclude `RAW DATA` and unpopulated extra sheets.
  - [x] Preserve 11kV ordering for `PCE Testsheet` / `PCE VI`.
- [x] Implement per-sheet `PageSetup` in `ComDocumentConverter`:
  - [x] Switchgear: Landscape A4, 1mm side margins, fit 1-page wide, unconstrained height.
  - [x] TX: Landscape A4, 1mm side margins, fit 1-page wide, unconstrained height.
  - [x] VI: Portrait A4, standard 0.25"/0.75" margins, fit 1-page wide.
- [x] Implement 3-family signature anchor geometries in `replace_pce_images()`:
  - [x] Switchgear placeholder replacement at `E77` (vendor) and `L77` (TNB).
  - [x] TX placeholder replacement at `F73` (vendor) and `R73` (TNB).
  - [x] VI placeholder replacement at `D82` (vendor) and `M82` (TNB).
  - [x] Placeholder sanitization in `mode="none"`.
- [x] Update `diagonal_borders.py` for 33kV:
  - [x] Switchgear: scan `C15:U62`.
  - [x] TX: scan groups `F14:AD28`, `F33:AD47`, `D51:F54`, `D57:O58`, `C62:Q71`.
  - [x] VI: strictly unslashed.
  - [x] Merged cells preserved and openpyxl zip repaired.
- [x] Verify sequential PDF concatenation produces canonical `<STEM>.pdf` combining portrait Quick Report, landscape switchgear/TX, and portrait VI.
- [x] Add unit tests in `tests/test_postprocessing_33kv.py` covering pre-flight validation, sheet selection/sorting, diagonal scan ranges, and signature anchors.
- [x] Verify full test suite passes with 0 regressions.
