# Project & Utility Automation CLI (`pahang-cli`)

A unified, interactive Command Line Interface (CLI) for automating Pahang area PE inspection workflows, multi-project workspace management, testsheet parsing, dynamic Quick Report compilation, 1-Click post-processing, and MSMS data pipelines (`v1.14.0`).

---

## 📖 Documentation & Release History

To keep this landing page concise and maintainable as the suite scales, detailed technical mechanics and release logs are organized in dedicated documentation files:

- **[System Architecture & Overview Guide](file:///docs/project_centric_architecture.md)** — Core design, deep modules (`src/project/` repository/storage seams and `src/postprocessing/converters.py`), and Windows COM automation rules.
- **[ETL Pipeline Refactoring Methodology](file:///docs/etl_pipeline_refactoring_methodology.md)** — 6-stage ETL pipeline architecture, pre-flight guards, and repository seams across workflow engines.
- **[PRPD Graph Generation Guide](file:///docs/prpd_graph_generation_guide.md)** — Pure-Python PRPD decoders (UE01 FlatBuffers & JSON), 4-tier repetition density scatter bins, and dynamic CBM defect page embedding.
- **[Utility Actions Guide](file:///docs/workflows/utility_actions.md)** — Deep dive into standalone tools (batch PDF conversions, diagonal borders, signature replacement, and separator PDF merging).
- **[Changelog & Version History](file:///CHANGELOG.md)** — Chronological release notes (`v1.0.0` → `v1.14.0+`) following [Keep a Changelog](https://keepachangelog.com/).

---

## 🛠️ Windows System Prerequisites

1. **Operating System**: Microsoft Windows 10 / 11 (required for COM automation with Excel and Word).
2. **Microsoft Office**: Installed desktop versions of Microsoft Excel and Microsoft Word (required for `.xlsx` / `.docx` COM interactions and PDF conversions).
3. **Python**: Python `>=3.11` installed and accessible on `PATH`.
4. **Package Manager (`uv`)**: We use `uv` for fast dependency management and virtual environment execution. Install via PowerShell:
   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

---

## 🚀 Quick Start & Installation for Colleagues

1. **Clone or download this repository** to your local machine:
   ```powershell
   git clone <repository_url>
   cd pahang-cli
   ```

2. **Install the CLI using `uv`**:
   Install the package in editable mode so the `pahang-cli` terminal command is available globally:
   ```powershell
   uv sync
   uv pip install -e .
   ```

3. **Launch the CLI**:
   Open your PowerShell terminal anywhere and type:
   ```powershell
   pahang-cli
   ```
   *(To check version directly, run `pahang-cli --version` or `pahang-cli -v`)*

### 🔄 How to Pull Updated Code from GitHub
Whenever a new version is released on GitHub, simply double-click the **`start_cli.bat`** script in the project root directory!

It will automatically:
1. Pull the newest codebase from GitHub.
2. Synchronize your local environment dependencies (`uv`).
3. Launch the `pahang-cli` interactive prompt.

---

## 🪄 First-Run Onboarding Wizard & Automated Setup

When launching `pahang-cli` for the first time on a new computer:
- **Automatic Setup Wizard**: If your local project is not configured, `pahang-cli` prompts you to enter the path to your project root folder.
- **Multi-Project Workspace Management**: Switch active projects, register new projects, update directory paths, or view project health status anytime via **Settings > Manage Projects**.
- **Automated Structure & Seed Files**: Once a project path is entered, `pahang-cli` automatically:
  1. Creates all required subdirectories (`TESTSHEET/`, `QUICK REPORT/`, `RAW MATERIAL/`, `PYTHON/`, `OTHERS/SIGN/`).
  2. Copies initial working seed `.xlsx` files (`TOTAL PE.xlsx`, `DATA MSMS.xlsx`) from `templates/` into your project folder.
- **Global Templates**: All `.docx`, Jinja2 report templates, and condition templates are managed inside the package `templates/` folder — no manual template copying needed!

---

## 📁 Required Project Folder Structure

Each configured project workspace maintains the standard Pahang 3-tier directory hierarchy:

```text
PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD/
├── TESTSHEET/
│   └── <STATION>/                       # e.g., TEMERLOH, RAUB, KUANTAN, BENTONG
│       └── <MONTH>/                     # e.g., 08. AUGUST, 09. SEPTEMBER
│           └── <DD-MM-YYYY>/            # e.g., 28-08-2026/
│               ├── 001. STATION.xlsx    # Testsheet workbooks (PCE Testsheet, PCE VI)
│               └── UNSORTED RAW DATA/   # Raw instrument data (IR/, DG/, US+TEV/)
├── RAW MATERIAL/
│   └── <STATION>/<MONTH>/<DD-MM-YYYY>/  # Sorted PE photo & US+TEV archive directories
├── QUICK REPORT/
│   └── <STATION>/<MONTH>/<DD-MM-YYYY>/  # Generated .docx and deliverable .pdf reports
├── PYTHON/
│   ├── TOTAL PE.xlsx                    # Master PE index and cycle tracking
│   ├── DATA MSMS.xlsx                   # Master MSMS Work Order consolidated database
│   ├── WHATSAPP/                        # Generated WhatsApp daily summary reports (.docx)
│   └── MSMS/                            # Raw client MSMS (.xls / .csv) files
├── OTHERS/
│   └── SIGN/                            # Digital signature folders (e.g., OTHERS/SIGN/<NAME>/)
├── docs/                                # Technical architecture and workflow guides
└── templates/                           # Master templates for Word, Excel, and Quick Reports
```

---

## 📋 Interactive CLI Menu Overview

The interactive CLI provides three primary menus (`Project Workflows`, `Utility Actions`, and `Settings`).

### 🏗️ Project Workflows (Project-Scoped)
Automates end-to-end engineering tasks against the currently active workspace.

| # | Action Label | Core Description & Automation Summary |
| :-: | :--- | :--- |
| **1** | **Generate TESTSHEET Folder Structure** | Interactively select or provision target station and month hierarchies (with sequential `01.`..`12.` prefixing) and batch provision inspection date folders (`<DATE>/UNSORTED RAW DATA/` with `DG/`, `IR/`, and `US+TEV/`). |
| **2** | **Populate TOTAL PE (from testsheets)** | Scans daily `TESTSHEET/` input folders (`<STATION>/<MONTH>/<DD-MM-YYYY>/`), validates testsheets, updates `TOTAL PE.xlsx` (`DataCycle1` sheet), enforces duplicate PE protection, and sorts records numerically by `PE NO`. |
| **3** | **Automate Raw Material Creation & Sorting (from Testsheets)** | Validates `TOTAL PE.xlsx` pre-checks, provisions `RAW MATERIAL/` destination folder hierarchies, copies `IR`/`DG` photos using testsheet bounds, and extracts `US+TEV` survey `.zip` archives into counterpart PE raw data directories. |
| **4** | **Update QR02 CBA (from testsheets)** | Extracts testsheet metadata (`PCE Testsheet`, `PCE VI`) and upserts per-station ENGR `QR02 CBA` Excel worksheets with atomic transactions, exact FL matching, and ghost cell sanitization. |
| **5** | **Generate Quick Report (Visual Report)** | Interactively select 3-tier inspection date folders (`<STATION>/<MONTH>/<DATE>/`) or manual FLs and compile 7-part docx visual reports with dynamic multi-technology template resolution (`DEFECT IR`, `DEFECT IR US`, `DEFECT IR US TEV`), automated pure-Python PRPD phase plot rendering (UE01 FlatBuffers & JSON decoders, 4-tier density scatter bins), testsheet ultrasound/TEV measurement ingestion, dynamic cell severity shading (`#EE0000` defect, `#00B050` normal), UltraTEV feeder matching, multi-technology defect merging, and canonical `(IR+US+TEV+VI)` defect suffixes. |
| **6** | **Run Full Substation Post-Processing Pipeline (1-Click)** | **1-Click Automation**: 6-stage post-processing pipeline executing pre-flight integrity validation across 3-tier Pahang hierarchies, automated renaming sync, daily WhatsApp reporting, digital signature stamping / `mode="none"` placeholder sanitization, diagonal blank borders, shared COM session automation, per-substation error resilience, and deliverable PDF merging into `QUICK REPORT/<DATE>/<STEM>.pdf`. |
| **7** | **Generate WhatsApp Report** | Interactively select quick report batches to generate formatted WhatsApp inspection summary reports (`.docx`) in `PYTHON/WHATSAPP/`. |
| **8** | **Consolidate MSMS (PYTHON/MSMS/*.xls -> DATA MSMS)** | 6-stage ETL workflow reading scattered `.xls` work order files in `PYTHON/MSMS/`, deduplicating records, normalizing FL ERMS tokens, appending rows to `DATA MSMS.xlsx`, and archiving processed files to `COMPLETED/`. |
| **9** | **Enrich MSMS (TOTAL PE -> DATA MSMS metadata)** | 6-stage ETL workflow enriching blank metadata columns in `DATA MSMS.xlsx` (substation name, FL, cycle date, substation number) by matching Work Orders against `TOTAL PE.xlsx`. |
| **10** | **Propagate Work Orders (DATA MSMS -> TOTAL PE)** | 6-stage ETL workflow mapping Work Orders from `DATA MSMS.xlsx` to blank WO cells in `TOTAL PE.xlsx` with strict formula and column preservation. |
| **11** | **Ingest MSMS CSVs (RAW DATA -> TO BE FILLED)** | Ingests client MSMS CSV files from `RAW DATA/`, deduplicates by SHA-256 hash, normalizes filenames to canonical `DD-MM-YYYY_NNN.csv`, and moves them to `TO BE FILLED/`. |
| **12** | **Populate Data MSMS (Testsheets -> TO BE FILLED CSVs)** | Fills detailed diagnostic CSV readings in `TO BE FILLED/` from testsheets with active Feeder Pillar thermal synthesis, single-decimal-place rounding (`ROUND_HALF_UP`), and interactive overwrite controls. |

---

### 🧰 Utility Actions (Standalone Tools)
Batch processing and file utilities invokable across any specified folder without requiring an active project session.

| Action Label | Purpose & Technical Highlights |
| :--- | :--- |
| **Create raw material folders** | Standalone raw material directory creation and photo/archive sorting across any directory path. |
| **Rename files (match names from input dir)** | Bulk renames files or folders matching source directory numerical ordering with smart target-type filtering (`testsheet` vs `raw_material`), auxiliary folder isolation, and prefix alignment. |
| **Extract PE pages from PDF (black-page detection)** | Splits and extracts substation pages from combined vendor scan PDFs using intelligent dark/black boundary page detection. |
| **Combine PDFs from primary and secondary folders** | Merges matching PDF pairs between primary and secondary directories with upfront quantity validation. |
| **Combine PDFs with separator sheet** | Merges all PDFs in a target folder in ascending numerical order, inserting a standardized `separator_sheet.pdf` between consecutive documents. |
| **Convert DOCX to PDF (batch)** | Batch converts Word documents (`.docx`) to PDF via COM automation with exact typography and layout preservation. |
| **Convert Testsheet to PDF (batch)** | Batch converts Excel testsheets (`.xlsx`) to PDF via COM automation with standard tab recognition (`PCE Testsheet` first, `PCE VI` last), A4 `PageSetup`, and virtual PDF printer scaling. |
| **Rename FLIR raw files numbering** | Renames thermal/visual FLIR image pairs based on camera timestamp and EXIF sequence numbers. |
| **Apply diagonal borders to blank cells** | Inserts diagonal strikethrough borders across empty/blank cells across standard testsheet table ranges. |
| **Replace signature images in testsheets** | Replaces signature placeholders (`{{signvendor}}`, `{{signtnb}}`) with PNG signatures from `OTHERS/SIGN/<Person>` or sanitizes tags cleanly (`mode="none"`). |
| **Generate WhatsApp report (from Quick Reports)** | Generates formatted WhatsApp daily summary `.docx` reports from completed Quick Report batches. |
| **Propagate Work Orders (DATA MSMS -> TOTAL PE)** | Standalone Work Order propagation from `DATA MSMS.xlsx` into `TOTAL PE.xlsx`. |
| **Remove desktop.ini files (recursive)** | Recursively purges hidden Windows `desktop.ini` system files across any selected directory tree. |

---

### ⚙️ Settings (Top-Level)

| Action Label | Purpose |
| :--- | :--- |
| **Manage Projects** | View current project info & health status badges (`[OK]`, `[MISSING]`), switch active projects, add/register new projects, update workspace directory paths, or unregister projects. |
| **Configure Camera Photo Patterns** | Configure and manage IR and DG camera photo filename patterns (FLIR single, IR/DC dual-pair, custom presets) per project with active pattern auto-reversion. |
| **Rollback Version** | Interactively lists recent commit history, allowing safe application version rollback with automatic `git reset --hard` and `uv sync`. |

---

## 🤝 Contribution & Maintenance Standard

When contributing new workflows or modifying existing features:
1. **Automate Releases via `/smart-commit`**: Ask the agent to commit (`/smart-commit`). The pre-commit workflow updates documentation in-place, evaluates SemVer (`pyproject.toml`), formats a caveman commit, and tags releases.
2. **Update `CHANGELOG.md`**: Log every feature, fix, or breaking change under an unreleased/version header (`Keep a Changelog`).
3. **Update `docs/`**: Add deep technical mechanics directly to markdown guides inside `docs/` (e.g. `docs/workflows/`).
4. **Keep `README.md` Lean**: Maintain this landing page as a high-level overview. Do not append multi-page implementation details directly to `README.md`.
