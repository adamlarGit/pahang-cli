# Utility Workflows and Standalone Actions Analysis

## 1. Catalog of Utility Actions

The following utility actions are registered in `src/utility_actions.py` and point to standalone workflows.

### 1. Create raw material folders
- **Domain Operation**: Creates folder structures and sorts raw material inputs.
- **Target Input Type**: Directory (recursive).
- **Target Path Acquisition**: Uses `cli_selectors.select_pahang_date_folder(environment=env)`, then prompts for directory path via `prompt_directory_path` defaulting to `env.get_testsheet_dir()`.
- **Environment Interaction**: Uses `get_or_create_utility_environment()`. Consumes active `ProjectEnvironment` to detect defaults.

### 2. Rename files (match names from input dir)
- **Domain Operation**: Renames files in an output directory to match the names (and sequence) of files from an input directory based on numerical prefixes.
- **Target Input Type**: Directory (flat).
- **Target Path Acquisition**: Interactive `input()` prompt for `input_directory` and `output_directory`.
- **Environment Interaction**: None. Fully standalone.

### 3. Extract PE pages from PDF (black-page detection)
- **Domain Operation**: Extracts sections from a PDF based on black page triggers, effectively splitting out pages between black separator pages.
- **Target Input Type**: File (`.pdf`).
- **Target Path Acquisition**: Interactive `input()` prompt for `pdf_path`.
- **Environment Interaction**: None. Fully standalone.

### 4. Combine PDFs from primary and secondary folders
- **Domain Operation**: Merges matching PDFs (by name) from a secondary folder into corresponding PDFs in a primary folder.
- **Target Input Type**: Directories (flat - primary and secondary).
- **Target Path Acquisition**: Interactive `input()` prompt for `primary_folder` and `secondary_folder`.
- **Environment Interaction**: None. Fully standalone.

### 5. Convert DOCX to PDF (batch)
- **Domain Operation**: Converts all `.docx` files in a folder to `.pdf`.
- **Target Input Type**: Directory (flat).
- **Target Path Acquisition**: Interactive `input()` prompt for `input_directory`.
- **Environment Interaction**: None. Fully standalone.

### 6. Convert Testsheet to PDF (batch)
- **Domain Operation**: Converts all testsheet workbooks (Excel) in a folder to `.pdf`.
- **Target Input Type**: Directory (flat).
- **Target Path Acquisition**: Interactive `input()` prompt for `folder_path`.
- **Environment Interaction**: None. Fully standalone.

### 7. Rename FLIR raw files numbering
- **Domain Operation**: Copies and sequentially renames files from an input folder into an output folder (e.g., `FLIR0001.JPG`).
- **Target Input Type**: Directory (flat).
- **Target Path Acquisition**: Interactive `input()` prompt for `input_folder`, `output_folder`, and `starting_number`.
- **Environment Interaction**: None. Fully standalone.

### 8. Apply diagonal borders to blank cells
- **Domain Operation**: Processes Excel files applying diagonal borders to specific empty cells in PCE Testsheet/VI sheets.
- **Target Input Type**: File (`.xlsx`) or Directory (flat).
- **Target Path Acquisition**: Interactive `input()` prompt for `target_folder` (can be file or folder).
- **Environment Interaction**: None. Fully standalone.

### 9. Replace signature images in testsheets
- **Domain Operation**: Replaces placeholders (`{{signvendor}}`, `{{signtnb}}`) or embedded images with signatures.
- **Target Input Type**: File (`.xlsx`) or Directory (flat).
- **Target Path Acquisition**: Interactive `input()` loop for Excel file/folder and interactive CLI selector menus for selecting signatures from `OTHERS/SIGN`.
- **Environment Interaction**: Reads project root relative to script but does not use `ProjectEnvironment`.

### 10. Generate WhatsApp report (from Quick Reports)
- **Domain Operation**: Aggregates quick report data and formats a message for WhatsApp.
- **Target Input Type**: Driven by project environment.
- **Target Path Acquisition**: None required directly from user.
- **Environment Interaction**: Strongly coupled to `get_or_create_utility_environment()`.

### 11. Update DATA_MSMS and TOTAL PE WO
- **Domain Operation**: Syncs tracking sheets.
- **Target Input Type**: Driven by project environment.
- **Target Path Acquisition**: None required directly from user.
- **Environment Interaction**: Strongly coupled to `get_or_create_utility_environment()`.

### 12. Remove desktop.ini files (recursive)
- **Domain Operation**: Scans and deletes hidden `desktop.ini` files.
- **Target Input Type**: Directory (recursive).
- **Target Path Acquisition**: Interactive `input()` prompt for target folder, defaults to `Path.cwd()`.
- **Environment Interaction**: None. Fully standalone.

---

## 2. Standalone vs Project-Scoped Rationale Analysis

### Standalone Capabilities Rationale
Utilities like PDF extraction, batch file renaming, and DOCX-to-PDF conversion operate on raw files that might come from external systems (like FLIR cameras, vendors, or test equipment) before they are structurally part of a defined project workspace. Standalone targeting allows users to:
- Test scripts on isolated samples outside the main workspace.
- Recover from corrupted subsets of files without having to rebuild or mock an entire project structure.
- Reuse Pahang CLI tools for general office/PDF automation unrelated to a specific project.

### Improvement Potential: Unifying Smart Defaults with Freedom
Currently, most utilities rely on raw Python `input()` calls. This prevents them from using the context of an active workspace.
We can improve them such that:
a) **Smart Defaults**: If `ProjectEnvironment` is active, use `env.base_path` or context-aware subfolders (like `env.get_testsheet_dir()`) as the default value in the CLI prompt.
b) **Full Freedom**: The user can simply overwrite the default prompt with any custom path.

---

## 3. Detailed Findings & Proposed Architecture

### Extracted Function Signatures & Inputs
- `rename_files_match(input_directory: str | Path, output_directory: str | Path)` -> Prompts via raw `input()`.
- `extract_pdf_sections_and_clean(pdf_path: str | Path)` -> Prompts via raw `input()`.
- `combine_primary_secondary_pdfs(primary_folder: str | Path, secondary_folder: str | Path, ...)` -> Prompts via raw `input()`.
- `convert_docx_folder_to_pdf(input_directory: str | Path, ...)` -> Prompts via raw `input()`.
- `convert_testsheet_folder_to_pdf(folder_path: str | Path, ...)` -> Prompts via raw `input()`.
- `copy_and_rename_flir_files(input_folder: str | Path, output_folder: str | Path, starting_number: int)` -> Prompts via raw `input()`.
- `process_diagonal_target(target_path: str | Path)` -> Prompts via raw `input()`.
- `batch_replace_pce_images(...)` -> Prompts via custom input loop.
- `remove_desktop_ini_files(target_directory: str | Path)` -> Prompts via raw `input()`, defaults to `Path.cwd()`.

### Proposed Architecture for Unification

1. **Standardize Input Prompting**: Replace raw `input()` calls in all `run_*` entrypoints with a unified CLI helper (e.g., `prompt_directory_path` from `cli_selectors.py` or a new `prompt_path` function that handles both files and directories).
2. **Context Injection Framework**: Pass an optional `ProjectEnvironment` to the `run_*` methods.
   ```python
   def run_docx_to_pdf(env: ProjectEnvironment | None = None) -> DocxToPdfSummary:
       default_path = env.get_testsheet_dir() if env else None
       input_directory = cli_selectors.prompt_directory_path(
           "Enter the path to the folder to convert to PDF",
           default=default_path
       )
       # ...
   ```
3. **Registry Update**: In `utility_actions.py`, update `UtilityAction.run` or the runner factories to pass the resolved environment to these actions, similar to how `_load_raw_material_runner` currently works.

This approach gracefully bridges the standalone nature of the tools with the convenience of a project workspace context, preserving flexibility while removing friction.
