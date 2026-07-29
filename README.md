# Pahang CLI

Interactive CLI application for Pahang area PE inspection workflows, multi-project workspace management, testsheet parsing, and raw material photo sorting.

## Key Workflows & Features

- **Manage Projects & Workspace Storage**: View active project metadata and folder health status badges (`[OK]`, `[MISSING]`), switch active projects, register new project paths, and update/re-bind workspace directory paths anytime from the Settings menu.
- **Populate TOTAL PE**: Scans daily `TESTSHEET/` input folders (`<STATION>/<MONTH>/<DD-MM-YYYY>/`) and upserts PE metadata into `TOTAL PE.xlsx` (`DataCycle1` sheet).
- **Automate Raw Material Creation & Sorting**: Validates `TOTAL PE.xlsx` pre-checks, provisions `RAW MATERIAL/` destination folder hierarchies, and matches/copies `IR` (`FLIR*`) and `DG` (`IMG_*`) photos from `UNSORTED RAW DATA/` using testsheet photo range bounds.
- **Camera Photo Pattern Presets**: Configure single (`FLIR`) or dual pair (`IR_`/`DC_`) IR/visual camera patterns per project.
- **Substation Post-Processing Pipeline**: 1-Click automated post-processing pipeline for substation deliverables combining signature replacement, diagonal borders, and PDF export/merging.
- **MSMS Integration & Work Order Sync**: Dedicated MSMS domain package for updating `DATA_MSMS.xlsx` and syncing Work Order (`WO`) numbers into `TOTAL_PE.xlsx`.
- **Standalone Utility Actions**: Batch DOCX/Testsheet to PDF conversion, PDF merging, diagonal cell borders, signature replacement, FLIR photo renaming, MSMS sync, and recursive `desktop.ini` removal.

## Requirements

- Python >= 3.11
- `uv` package manager
- openpyxl, pandas, questionary, python-docx, docxtpl, pypdf, pywin32
