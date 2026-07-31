# Architectural Standard: Project-Centric Architecture

## Executive Overview
The **Pahang CLI** adheres to a strict **Project-Centric Architecture**. 

This design pattern guarantees **zero Git merge conflicts** for non-developer colleagues updating their local CLI via `start_cli.bat` while providing **100% per-project independence**.

---

## Core Principles for AI Agents & Developers

### 1. The Git Repository (`pahang-cli`) is Read-Only Code & Master Defaults
The root directory of this repository contains **only**:
- Python source code (`src/*.py`, `config.py`)
- Batch launcher scripts (`start_cli.bat`)
- Lockfiles and project metadata (`pyproject.toml`, `uv.lock`, `.gitattributes`, `.gitignore`)
- **Master Seed Templates** (`templates/`) used for initial project bootstrapping.

> **CRITICAL RULE:** **NEVER write, mutate, or output any runtime user state, cached data, user settings, or modified templates inside the Git repository directory.** Doing so breaks Git updates on colleagues' laptops.

---

### 2. The Project Workspace (`<base_path>/`) Owns ALL Local State
Every project workspace configured in `.cli_config.json` (e.g. `C:\Users\<Name>\Documents\PO 42234207...`) is a self-contained, independent directory completely ignored by Git.

All project-specific data, user modifications, settings, and templates **MUST live inside `<base_path>/`**:

```text
<base_path>/                             <-- Configured project root directory (Ignored by Git)
├── project_config.json                  <-- Per-project settings (Camera photo patterns, offsets)
├── .processed_folders.json              <-- Processed folder timestamps cache
│
├── templates/                           <-- Project-specific Word & Excel templates
│   ├── TELEGRAM\
│   ├── QUICK REPORT\
│   └── ...
│
├── PYTHON/                              <-- Excel data sheets (TOTAL PE.xlsx, CBA sheets)
├── QUICK REPORT/                        <-- Generated Word & Excel report outputs
├── TESTSHEET/                           <-- Input testsheet Excel files
└── RAW MATERIAL/                        <-- Input camera photos (IR, DC, DG)
```

---

## Template & Configuration Resolution Rules

### A. Template Resolution (`src/project/storage.py`)
- All template requests (`storage.get_template(key)`) MUST resolve strictly from `<base_path>/templates/<relative_path>`.
- On project initialization or load (`_initialize_project_workspace`), the CLI automatically copies any missing master templates from the repository `templates/` folder into `<base_path>/templates/`.
- Users customize templates inside `<base_path>/templates/`. These custom templates are never touched or overwritten by `git pull` updates.

### B. Project Configuration (`src/project/repository.py`)
- Camera photo patterns (`CameraConfig`: `ir_mode`, `ir_prefix`, `dc_prefix`, `dc_offset`, `dg_prefix`) are loaded from and saved to `<base_path>/project_config.json`.
- Each project workspace maintains its own camera configuration independent of other projects or global CLI settings.

### C. Processed Folders Cache (`src/workflows/populate_total_pe_workflow.py`)
- Processed folder history is stored inside `<base_path>/.processed_folders.json`.

### D. Workspace Path Resolution & Zero CWD Leakage (`src/quick_report/composer.py`, workflow actions)
- **Zero CWD Leakage**: Never resolve relative user inputs against `Path.cwd()` or `os.getcwd()` (which points to the `pahang-cli` repository install location).
- **Target Folder Resolution Standard**:
  - Absolute paths (`Path(str).is_absolute()`) are validated directly.
  - Relative input folder paths (e.g., `"CMRN/JULY 2026/01-07-2026"`) MUST be resolved strictly relative to the active project's workspace directory (`environment.get_testsheet_dir() / folder_str`).
- **Standard Implementation Pattern**:
  ```python
  candidate = Path(folder_str)
  folder_path = candidate if candidate.is_absolute() else environment.get_testsheet_dir() / folder_str
  if folder_path.exists():
      packages.extend(repo.discover_packages(folder_path))
  ```
