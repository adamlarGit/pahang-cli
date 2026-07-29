# Research Investigation: Standalone Utility Actions in `pahang-cli`

## Executive Summary

The `pahang-cli` application includes a dedicated **Utility Actions** menu (`src/utility_actions.py`) intended to provide standalone batch automation scripts (such as PDF conversion, file renaming, signature replacement, and diagonal formatting) that operators can invoke with or without an active project loaded.

Currently, **9 out of the 11 utility actions** return stubs (`_make_stub_runner`), **1 action** (WhatsApp report) is partially wired but crashes when executed without an active project environment (`env is None`), and **1 action** (`remove_desktop_ini`) is fully implemented.

This report audits all 11 utility actions, maps them to existing domain modules in `src/` and technical specifications in `docs/workflows/utility_actions.md`, analyzes parameter/context requirements for standalone execution, and formulates a modular architecture to un-stub all 11 utility actions.

---

## 1. Audit of `src/utility_actions.py` & The 11 Utility Actions

`src/utility_actions.py` (156 lines) defines:
- **`UtilityAction` Dataclass** (lines 9–27): Holds action `label`, `_runner_factory` callable, and a `run()` method with execution timing profiling.
- **`UTILITY_ACTIONS` Registry** (lines 138–150): Immutable tuple of 11 registered actions.
- **`_make_stub_runner(action_name)`** (lines 29–34): Helper returning a dummy runner printing `[UTILITY STUB] Running ...`.

### Status Matrix of all 11 Utility Actions

| # | Utility Action Label | Current Runner Function | Status | Existing Domain Code / References | Standalone Context Requirement |
|---|---|---|---|---|---|
| 1 | Create raw material folders | `_load_raw_material_runner()` (L37-91) | **Partially Implemented** | `src/workflows/raw_material.py`, `src/workflows/service.py` | Prompts for date folder / directory; synthesizes fallback `ProjectEnvironment` if `env is None`. |
| 2 | Rename files (match names from input dir) | `_load_rename_files_runner()` (L94-95) | **STUB** | Spec in `docs/workflows/utility_actions.md` §5 | Input dir prompt (name source), Target dir prompt (files to rename). |
| 3 | Extract PE pages from PDF (black-page detection) | `_load_pdf_extract_runner()` (L98-99) | **STUB** | Spec in `docs/workflows/utility_actions.md` §7 | Target PDF path / directory prompt, Output directory prompt. |
| 4 | Combine PDFs from primary and secondary folders | `_load_combine_pdfs_runner()` (L102-103) | **STUB** | Spec in `docs/workflows/utility_actions.md` §4 | Primary PDF folder prompt, Secondary PDF folder prompt, Output dir prompt. |
| 5 | Convert DOCX to PDF (batch) | `_load_docx_to_pdf_runner()` (L106-107) | **STUB** | Spec in `docs/workflows/utility_actions.md` §2 | Target `.docx` folder prompt, Output folder prompt. |
| 6 | Convert Testsheet to PDF (batch) | `_load_testsheet_to_pdf_runner()` (L110-111) | **STUB** | Spec in `docs/workflows/utility_actions.md` §1 | Target `.xlsx` testsheet folder prompt, Output folder prompt. |
| 7 | Rename FLIR raw files numbering | `_load_rename_flir_runner()` (L114-115) | **STUB** | `CameraConfig` in `src/project/models.py`, Spec §8 | Target raw image dir prompt, `CameraConfig` selection/preset prompt. |
| 8 | Apply diagonal borders to blank cells | `_load_diagonal_runner()` (L118-119) | **STUB** | Spec in `docs/workflows/utility_actions.md` §3 | Target `.xlsx` testsheet folder prompt. |
| 9 | Replace signature images in testsheets | `_load_replace_images_runner()` (L122-123) | **STUB** | Spec in `docs/workflows/utility_actions.md` §9 | Target testsheet folder prompt, Signature base folder (`OTHERS/SIGN`) prompt. |
| 10 | Generate WhatsApp report (from Quick Reports) | `_load_whatsapp_runner()` (L126-129) | **Partially Implemented (Broken when env=None)** | `src/whatsapp/generator.py`, `src/workflows/whatsapp.py` | Target Quick Report batch folder prompt; needs fallback when `env is None`. |
| 11 | Remove desktop.ini files (recursive) | `_load_remove_desktop_ini_runner()` (L132-135) | **Fully Implemented** | `src/remove_desktop_ini_workflow.py`, `scripts/remove_desktop_ini.ps1` | Interactive target folder prompt with `Path.cwd()` default. Fully standalone. |

---

## 2. Technical Investigation & Detailed Analysis per Action

### Action 1: Create raw material folders
- **Label**: `Create raw material folders`
- **File & Line**: `src/utility_actions.py` (lines 37–91, 139)
- **Status**: Functional Standalone Runner.
- **Existing Logic**:
  - `src/workflows/raw_material.py`: `RawMaterialWorkflow` orchestrator.
  - `src/workflows/service.py` (L51-64): `WorkflowService.run_raw_material()`.
  - `src/workflows/models.py`: `RawMaterialRequest` and `RawMaterialResult`.
- **Standalone Mechanics**:
  - Checks `load_project_environment()`. If `env is None`, uses `cli_selectors.select_pahang_date_folder` or `cli_selectors.prompt_directory_path` to get `target_dir`.
  - Synthesizes a transient `ProjectEnvironment` anchored at `base_p` (searches parent directories containing `"TESTSHEET"` or `"PYTHON"`).
  - Executes `WorkflowService().run_raw_material(env, request)`.

### Action 2: Rename files (match names from input dir)
- **Label**: `Rename files (match names from input dir)`
- **File & Line**: `src/utility_actions.py` (lines 94–95, 140)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §5.
- **Core Logic & Mechanics Needed**:
  - Bulk renames files across directories based on custom regex/numbering patterns matching names from an input reference directory (e.g. matching `QUICK REPORT/` naming conventions).
- **Standalone Parameters Required**:
  - Input directory prompt (`cli_selectors.prompt_directory_path("Select Input Directory (Source Names)")`).
  - Target directory prompt (`cli_selectors.prompt_directory_path("Select Target Directory (Files to Rename)")`).

### Action 3: Extract PE pages from PDF (black-page detection)
- **Label**: `Extract PE pages from PDF (black-page detection)`
- **File & Line**: `src/utility_actions.py` (lines 98–99, 141)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §7.
- **Core Logic & Mechanics Needed**:
  - Scans multi-page PDF documents (e.g., scanned vendor reports), performs black-page detection (detecting separator pages inserted during scanning by evaluating page content stream or pixel brightness), and extracts discrete PE inspection sections into separate PDFs.
- **Standalone Parameters Required**:
  - Source PDF file / directory prompt.
  - Output directory prompt (`prompt_directory_path("Select Output Directory for Extracted PDFs")`).

### Action 4: Combine PDFs from primary and secondary folders
- **Label**: `Combine PDFs from primary and secondary folders`
- **File & Line**: `src/utility_actions.py` (lines 102–103, 142)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §4.
- **Core Logic & Mechanics Needed**:
  - Merges PDF files from a Primary folder (e.g., Quick Reports) and Secondary folder (e.g., Testsheets) into compiled substation deliverable PDFs using `pypdf.PdfMerger`.
  - Filename matching: matches files sharing substation names/PE numbers and orders them (`Quick Report.pdf` + `Testsheet.pdf`).
- **Standalone Parameters Required**:
  - Primary PDF directory prompt.
  - Secondary PDF directory prompt.
  - Output compiled directory prompt.

### Action 5: Convert DOCX to PDF (batch)
- **Label**: `Convert DOCX to PDF (batch)`
- **File & Line**: `src/utility_actions.py` (lines 106–107, 143)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §2.
- **Core Logic & Mechanics Needed**:
  - Batch converts `.docx` files to `.pdf` via `win32com.client.Dispatch("Word.Application")`.
  - Runs headlessly (`word_app.Visible = False`) inside `try...finally` to ensure `word_app.Quit()` is always called.
  - Cross-platform fallback using `libreoffice` or `docx2pdf`.
- **Standalone Parameters Required**:
  - Target directory prompt containing `.docx` files.
  - Output directory prompt (defaults to same folder).

### Action 6: Convert Testsheet to PDF (batch)
- **Label**: `Convert Testsheet to PDF (batch)`
- **File & Line**: `src/utility_actions.py` (lines 110–111, 144)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §1.
- **Core Logic & Mechanics Needed**:
  - Converts multi-tab Excel testsheets (`.xlsx`) into PDF deliverables using `win32com.client.Dispatch("Excel.Application")`.
  - **Sheet Filtering**: `_is_pce_testsheet_sheet(ws)` (matches `PCE Testsheet`, `PCE Testsheet (2)`), `_is_pce_vi_sheet(ws)` (matches `PCE VI`). Non-target tabs ignored.
  - **Sheet Sorting**: `PCE Testsheet` tabs priority 0, `PCE VI` tabs priority 1.
  - **PageSetup Enforcement**: `PaperSize = 9` (A4), `Zoom = False`, `FitToPagesWide = 1`, `FitToPagesTall = False`.
  - Exports via `ws.ExportAsFixedFormat(0, pdf_path)` (`xlTypePDF`) with optional Adobe PDF printer discovery via `winreg`.
- **Standalone Parameters Required**:
  - Target directory prompt containing `.xlsx` testsheets.

### Action 7: Rename FLIR raw files numbering
- **Label**: `Rename FLIR raw files numbering`
- **File & Line**: `src/utility_actions.py` (lines 114–115, 145)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §8.
- **Existing Logic**: `CameraConfig` model in `src/project/models.py` (lines 717–751) and settings selection in `src/settings_actions.py` (lines 1004–1183).
- **Core Logic & Mechanics Needed**:
  - Renames thermal and visual raw photo pairs based on image timestamp/EXIF sorting or camera metadata.
  - Supports single `FLIR0001.jpg` / `IR_0001.jpg` mode or dual `IR_` + `DC_` pair mode with configured index offset.
- **Standalone Parameters Required**:
  - Photo directory prompt (`prompt_directory_path("Select directory containing raw camera photos")`).
  - Active or selected `CameraConfig` preset.

### Action 8: Apply diagonal borders to blank cells
- **Label**: `Apply diagonal borders to blank cells`
- **File & Line**: `src/utility_actions.py` (lines 118–119, 146)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §3.
- **Core Logic & Mechanics Needed**:
  - Inspects target `.xlsx` testsheets using `openpyxl`.
  - Filters target sheets (`PCE Testsheet*`, `PCE VI*`).
  - Iterates through defined cell ranges (`TESTSHEET_RANGES_TO_PROCESS`).
  - Applies thin diagonal strikethrough border (`openpyxl.styles.Border(diagonal=Side(style='thin'), diagonalDown=True)`) on blank, empty, or `"N/A"` cells. Saves workbook.
- **Standalone Parameters Required**:
  - Target directory containing completed `.xlsx` testsheets.

### Action 9: Replace signature images in testsheets
- **Label**: `Replace signature images in testsheets`
- **File & Line**: `src/utility_actions.py` (lines 122–123, 147)
- **Status**: Stub.
- **Specification Reference**: `docs/workflows/utility_actions.md` §9.
- **Core Logic & Mechanics Needed**:
  - Browses signature folder (`OTHERS/SIGN`) for subfolders containing PNG signature images.
  - Displays available signature count per folder, hiding empty subfolders.
  - Prompts operator for Vendor signature selection (Image 1) and TNB signature selection (Image 2).
  - Iterates through target `.xlsx` testsheets, substituting signature placeholders (`{{signvendor}}`, `{{signtnb}}`) or image shapes with randomly selected signature PNGs (`random.choice`).
- **Standalone Parameters Required**:
  - Target testsheet directory prompt.
  - Signature base directory prompt (`OTHERS/SIGN` default).
  - Interactive signature folder selectors.

### Action 10: Generate WhatsApp report (from Quick Reports)
- **Label**: `Generate WhatsApp report (from Quick Reports)`
- **File & Line**: `src/utility_actions.py` (lines 126–129, 148)
- **Status**: Partially Implemented / Broken when `env is None`.
- **Existing Logic**:
  - `src/whatsapp/generator.py`: `generate_whatsapp_report()`.
  - `src/workflows/whatsapp.py`: `select_quick_report_batch()`.
  - `src/project_workflow_actions.py` (lines 262–284): `WhatsAppReportAction.execute()`.
- **Bug Analysis**:
  - Line 129 in `src/utility_actions.py`: `WhatsAppReportAction("Generate WhatsApp report").execute(None)`
  - Line 268 in `src/project_workflow_actions.py`: `select_quick_report_batch(environment.get_quick_report_dir())`
  - Passing `None` causes `AttributeError: 'NoneType' object has no attribute 'get_quick_report_dir'`.
- **Fix Needed**:
  - `_load_whatsapp_runner()` must attempt to get `env = load_project_environment()`.
  - If `env` is `None`, prompt operator for Quick Report directory via `cli_selectors.prompt_directory_path("Select Quick Report folder")`, synthesize a transient `ProjectEnvironment`, and invoke `WorkflowService().run_whatsapp(env, request)`.

### Action 11: Remove desktop.ini files (recursive)
- **Label**: `Remove desktop.ini files (recursive)`
- **File & Line**: `src/utility_actions.py` (lines 132–135, 149), `src/remove_desktop_ini_workflow.py` (lines 1–69)
- **Status**: Fully Implemented.
- **Existing Logic**: `src/remove_desktop_ini_workflow.py` (`remove_desktop_ini_files()`, `run_remove_desktop_ini()`) and `scripts/remove_desktop_ini.ps1`.
- **Standalone Mechanics**: Interactively prompts operator for target folder path with `Path.cwd()` default. Executes PowerShell script on Windows with Python `os.walk` + `os.chmod` fallback. Fully standalone.

---

## 3. Architectural Recommendations for Standalone Utility Workflows

### 3.1 Lazy-Loading Strategy in `src/utility_actions.py`
Maintain the existing `_runner_factory: Callable[[], Callable[[], object]]` architecture in `src/utility_actions.py`.
- **Benefit**: Prevents importing heavy COM automation dependencies (`win32com.client`), PDF manipulators (`pypdf`), or Excel engines (`openpyxl`, `docxtpl`) during CLI application startup.
- **Structure**: Each `_load_<action>_runner()` dynamically imports its target domain module inside the runner function body when selected by the user.

### 3.2 Workspace & Environment Context Resolution Pattern
Create a centralized helper `get_or_create_utility_environment(target_dir: Path | None = None) -> ProjectEnvironment` in `src/project/environment.py` (or `src/utility_actions.py`).

---

## 4. Implementation Roadmap & Action Items

1. **Phase 1: Shared Utility Context Helper**
   - Implement `get_or_create_utility_environment(target_dir: Path | None = None)` in `src/project/environment.py`.

2. **Phase 2: Fix Action 10 (WhatsApp Report)**
   - Refactor `_load_whatsapp_runner()` in `src/utility_actions.py` to use directory prompt fallback when `env is None`.

3. **Phase 3: Port COM Automation Workflows**
   - Create `src/workflows/testsheet_to_pdf.py` (Action 6) with sheet filtering (`PCE Testsheet`, `PCE VI`), custom sorting, A4 setup, and Excel COM export.
   - Create `src/workflows/docx_to_pdf.py` (Action 5) with Word COM export.

4. **Phase 4: Port Excel Formatting & Signature Workflows**
   - Create `src/workflows/diagonal_borders.py` (Action 8) using `openpyxl`.
   - Create `src/workflows/replace_signatures.py` (Action 9) with `OTHERS/SIGN` signature browsing and image replacement.

5. **Phase 5: Port File & PDF Manipulation Workflows**
   - Create `src/workflows/combine_pdfs.py` (Action 4) using `pypdf.PdfMerger`.
   - Create `src/workflows/pdf_extract.py` (Action 3) with black-page detection.
   - Create `src/workflows/rename_files.py` (Action 2) and `src/workflows/rename_flir.py` (Action 7) using `CameraConfig`.

6. **Phase 6: Verification & Test Suite**
   - Create unit tests under `tests/` for each utility workflow (e.g. `tests/test_testsheet_to_pdf.py`, `tests/test_diagonal_borders.py`, `tests/test_combine_pdfs.py`).
