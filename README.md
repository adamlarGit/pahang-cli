# Pahang CLI

Interactive CLI application for Pahang area PE inspection workflows, testsheet parsing, and raw material photo sorting.

## Key Workflows

- **Populate TOTAL PE**: Scans daily `TESTSHEET/` input folders (`<STATION>/<MONTH>/<DD-MM-YYYY>/`) and upserts PE metadata into `TOTAL PE.xlsx` (`DataCycle1` sheet).
- **Automate Raw Material Creation & Sorting**: Validates `TOTAL PE.xlsx` pre-checks, provisions `RAW MATERIAL/` destination folder hierarchies, and matches/copies `IR` (`FLIR*`) and `DG` (`IMG_*`) photos from `UNSORTED RAW DATA/` using testsheet photo range bounds.

## Requirements

- Python >= 3.11
- openpyxl, pandas, questionary
