# Utility Actions — Technical Specifications & COM Mechanics

This document details the standalone batch processing tools available under the **Utility Actions** menu in `pahang-cli`.

---

## 1. Convert Testsheet to PDF (`src/testsheet_to_pdf_workflow.py`)
- **Purpose:** Converts multi-worksheet Excel testsheets into formatted PDF deliverables via Windows COM Automation (`win32com.client`).
- **Sheet Filtering & Duplication Handling:**
  - `_is_pce_testsheet_sheet(ws)` matches any tab whose base name starts with `PCE Testsheet` (case-insensitive), correctly capturing duplicated tabs like `PCE Testsheet (2)`.
  - `_is_pce_vi_sheet(ws)` matches tabs starting with `PCE VI`.
  - All non-target sheets (instructions, scratch calculations) are ignored during export.
- **Custom Sorting (`_get_sheet_sort_key`):**
  - All `PCE Testsheet` tabs (and their `(2)` copies) are sorted numerically first (`priority = 0`), followed by `PCE VI` (`priority = 1`).
- **COM PageSetup & Uniform Printer Metrics:**
  - **Printer setup:** `configure_uniform_printer()` runs once per COM session so Excel lays pages out with stable A4 metrics. It only sets `ActivePrinter` for layout; nothing is printed.
  - **COM PageSetup Enforcement:** Iterates through every target sheet and applies:
    - `PaperSize = 9` (A4 format)
    - `Zoom = False`
    - `FitToPagesWide = 1`
    - `FitToPagesTall = False`
  - **Export:** `ws.ExportAsFixedFormat(0, str(pdf_path))` (`xlTypePDF`) through Excel's native PDF engine.

---

## 2. Convert DOCX to PDF (`src/workflows/docx_to_pdf.py`)
- **Purpose:** Batch converts `.docx` Word documents into `.pdf` using `Word.Application` COM automation while preserving maximum image resolution (High Fidelity), table borders, and font rendering exactness.
- **High-Fidelity Mechanics:**
  - Exports natively and never prints through a virtual printer (ADR 0009).
  - Enforces `word_app.Options.DoNotCompressImages = True` and `doc.DoNotCompressImages = True` at runtime.
  - Exports via `doc.ExportAsFixedFormat(..., OptimizeFor=0, BitmapMissingFonts=True, DocStructureTags=True)` (`wdExportOptimizeForPrint`).
- **Execution Safeguards:** Runs with `word_app.Visible = False` and `word_app.DisplayAlerts = 0` inside a `try...finally` block, ensuring `word_app.Quit()` is invoked even if Word encounters a corrupted document.

---

## 3. Add Diagonal Lines to Excel Cells (`src/diagonal_workflow.py`)
- **Purpose:** Inserts diagonal strikethrough borders across designated empty or N/A table cells on completed testsheets.
- **Target Ranges & Duplicated Sheets:**
  - Imports `_is_pce_testsheet_sheet` and `_is_pce_vi_sheet` from `src.testsheet_to_pdf_workflow` to inspect every matching tab in a workbook (ensuring `PCE Testsheet (2)` receives diagonal formatting alongside the primary tab).
  - Applies thin diagonal border styling (`openpyxl.styles.Border`) across target cell ranges defined in `TESTSHEET_RANGES_TO_PROCESS`.

---

## 4. Combine PDF Files (`src/combine_pdfs_workflow.py`)
- **Purpose:** Merges multiple PDF documents within a folder into a single compiled document using `PyPDF2.PdfMerger`.
- **Sorting Order:** Sorts filenames alphabetically/numerically (`Quick Report.pdf` + `Testsheet.pdf`) to compile the final package.

---

## 5. Rename Files (`src/rename_files_workflow.py`)
- **Purpose:** Bulk renames engineering files across directories based on custom numbering or regex patterns (`QUICK REPORT/` naming conventions).

---

## 6. Extract Data from PDF (`src/raw_material_workflow.py`)
- **Purpose:** Extracts raw text tables and key-value fields from vendor PDF reports.

---

## 7. Extract Text/Data from PDF (`src/pdf_extract_workflow.py`)
- **Purpose:** Utility for scraping specific text zones or form fields from standardized PDF templates.

---

## 8. Rename FLIR Images (`src/rename_flir_workflow.py`)
- **Purpose:** Renames thermal and visual FLIR image pairs based on timestamp sorting or camera EXIF metadata (`FLIR0001.jpg`, `FLIR0002.jpg`).

---

## 9. Replace Excel Images (`src/replace_images_workflow.py`)
- **Purpose:** Scans Excel workbooks and replaces embedded images (`PCE Testsheet` / `PCE VI`) or text placeholders (`{{signvendor}}` / `{{signtnb}}`) with `.png` signatures.
- **Interactive CLI Mechanics:** Dynamically browses `OTHERS/SIGN` (relative to project root so it works across any workstation) for subfolders containing `.png` files, displays available signature counts, and hides empty subfolders (e.g. `OMAR`). Passes the selected person directory path into `replace_pce_images` so that each individual placeholder or image replacement dynamically calls `random.choice(png_files)` (`get_img_file`). Ensures every sheet across single workbooks or batch processing runs receives naturally varied signature styles. Features separate selection prompts for `img1` and `img2`, PNG format enforcement, and a robust path validation loop (`while True`).

---

## 10. Generate US 16-bit Audio & Embed Sounds into PDFs (`src/workflows/us_audio.py`)
- **Purpose:** Standalone utility workflow to downscale UltraTEV 24-bit heterodyne demodulated `8k.wav` acoustic recordings to 16-bit PCM in memory and either export canonical 16-bit WAV files into `<SUBSTATION>/RAW DATA/US+TEV/sounds/` or embed ISO 32000-1 Sound Annotations into deliverable Full Report and Quick Report PDFs.
- **Interactive Modes:**
  1. `Embed ultrasound sounds into existing report PDFs (Full & Quick Report)`
  2. `Export converted 16-bit WAV files to RAW DATA/US+TEV/sounds/`
  3. `Both (Export WAV files and embed into PDFs)`
- **Checklist & Prerequisite Resilience:**
  - Reuses `select_pahang_inspection_dates_interactive` / `prompt_target_inspection_dates_with_ranges` for multi-date selection.
  - Automatically filters substations across dates strictly to those possessing valid US+TEV surveys.
  - Displays deliverable PDF availability tags (`[PDF READY]` vs `[NO PDF]`).
  - If Mode 1 (`embed_pdf`) is selected and zero deliverable PDFs are found on disk, presents an actionable notice offering to switch to Mode 2 (`export_wav`) or cancel without crashing.

---

## 11. Remove desktop.ini Files (`src/remove_desktop_ini_workflow.py` & `scripts/remove_desktop_ini.ps1`)
- **Purpose:** Recursively scans a user-specified target directory and deletes all hidden/system `desktop.ini` configuration files.
- **Interactive CLI Mechanics:** Interactively prompts the operator to enter their desired target folder path (with instant fallback to current working directory).
- **Execution & Fallback Engine:** On Windows systems, executes `scripts/remove_desktop_ini.ps1` via `powershell -ExecutionPolicy Bypass` with `-Force` attributes. Includes a native Python fallback (`os.walk` + `os.chmod` `S_IWRITE`) to ensure seamless cross-platform functionality.

