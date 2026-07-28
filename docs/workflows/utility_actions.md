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
- **COM PageSetup & Adobe PDF Printer Discovery (`[TRIAL/EXPERIMENTAL FEATURE]`):**
  - Enabled when `USE_ADOBE_PDF_TRIAL = True`.
  - **Printer Discovery:** Uses Python `winreg` (`HKEY_CURRENT_USER\Software\Microsoft\Windows NT\CurrentVersion\Devices`) to dynamically locate the exact system port assigned to the `Adobe PDF` virtual printer (e.g., `Adobe PDF on Ne07:`).
  - **COM PageSetup Enforcement:** Iterates through every target sheet and applies:
    - `PaperSize = 9` (A4 format)
    - `Zoom = False`
    - `FitToPagesWide = 1`
    - `FitToPagesTall = False`
  - **Export Fallback:** Attempts `ws.ExportAsFixedFormat(0, str(pdf_path))` (`xlTypePDF`). If COM printer redirection fails or `Adobe PDF` is not installed on the colleague's machine, it falls back seamlessly to Excel's native high-quality PDF engine.

---

## 2. Convert DOCX to PDF (`src/docx_to_pdf_workflow.py`)
- **Purpose:** Batch converts `.docx` Word documents into `.pdf` using `Word.Application` COM automation while preserving table borders and font rendering exactness.
- **Execution Safeguards:** Runs with `word_app.Visible = False` inside a `try...finally` block, ensuring `word_app.Quit()` is invoked even if Word encounters a corrupted document.

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

## 10. Remove desktop.ini Files (`src/remove_desktop_ini_workflow.py` & `scripts/remove_desktop_ini.ps1`)
- **Purpose:** Recursively scans a user-specified target directory and deletes all hidden/system `desktop.ini` configuration files.
- **Interactive CLI Mechanics:** Interactively prompts the operator to enter their desired target folder path (with instant fallback to current working directory).
- **Execution & Fallback Engine:** On Windows systems, executes `scripts/remove_desktop_ini.ps1` via `powershell -ExecutionPolicy Bypass` with `-Force` attributes. Includes a native Python fallback (`os.walk` + `os.chmod` `S_IWRITE`) to ensure seamless cross-platform functionality.
