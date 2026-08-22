# Pahang CLI

Interactive CLI application for Pahang area PE inspection workflows, multi-project workspace management, testsheet parsing, and raw material photo sorting.

## Key Workflows & Features

- **Generate TESTSHEET Folder Structure**: Interactively select or provision target station and month hierarchies (with sequential `01.`..`12.` prefixing) and batch provision inspection date folders (`<DATE>/UNSORTED RAW DATA/` with `DG/`, `IR/`, and `US+TEV/`).
- **Manage Projects & Workspace Storage**: View active project metadata and folder health status badges (`[OK]`, `[MISSING]`), switch active projects, register new project paths, and update/re-bind workspace directory paths anytime from the Settings menu.
- **Populate TOTAL PE**: Scans daily `TESTSHEET/` input folders (`<STATION>/<MONTH>/<DD-MM-YYYY>/`) and upserts PE metadata into `TOTAL PE.xlsx` (`DataCycle1` sheet).
- **Automate Raw Material Creation & Sorting**: Validates `TOTAL PE.xlsx` pre-checks, provisions `RAW MATERIAL/` destination folder hierarchies, matches/copies `IR` and `DG` photos from `UNSORTED RAW DATA/` using testsheet photo range bounds, and automatically extracts `US+TEV` survey `.zip` archives into counterpart PE raw data directories.

- **Camera Photo Pattern Presets**: Configure single (`FLIR`/`IR_`) or dual pair (`IR_`/`DC_`) IR/visual camera patterns and DG prefixes per project.
- **Update QR02 CBA**: Extracts testsheet metadata (`PCE Testsheet`, `PCE VI`) and upserts per-station ENGR `QR02 CBA` Excel worksheets with atomic transactions and exact FL matching.
- **Generate Quick Report**: Interactively select 3-tier inspection date folders (`<STATION>/<MONTH>/<DATE>/`) and compile 7-part docx visual reports directly into counterpart `QUICK REPORT/<STATION>/<MONTH>/<DATE>/` directory trees with dynamic equipment condition pairs, room-based fire safety layouts, and canonical `(IR+US+TEV+VI)` defect suffixes.
- **Generate WhatsApp Report**: Interactively select quick report batches to generate formatted WhatsApp inspection summary text files and station reports.
- **Substation Post-Processing Pipeline**: 1-Click automated post-processing pipeline for substation deliverables combining signature replacement, diagonal borders, and PDF export/merging.
- **MSMS Suite & Work Order Sync**: Dedicated modular workflows to consolidate MSMS spreadsheets, enrich DATA MSMS with TOTAL PE metadata, propagate Work Orders (WO), ingest raw CSVs, and populate data MSMS records.
- **Standalone Utility Actions**: Batch DOCX/Testsheet to PDF conversion, PDF merging, diagonal cell borders, signature replacement, FLIR photo renaming, MSMS sync, and recursive `desktop.ini` removal.

## Requirements

- Python >= 3.11
- `uv` package manager
- openpyxl, pandas, questionary, python-docx, docxtpl, docxcompose, pywin32
