# Task: Rewrite TestsheetExtractor with Fixed-Cell Extraction

Labels: wayfinder:task
Type: task
Status: open

## Question

Replace the generic keyword-scanning `TestsheetExtractor` with Johor's fixed-cell extraction approach. Expand `TestsheetData` model to include QR02 CBA fields. Preserve RAW DATA photo range extraction.

## Specification

### 1. Expand `TestsheetData` (`src/testsheet/models.py`)

Add fields matching Johor's model:
- `fl_erms: str` — from `PCE Testsheet` cell W5
- `substation_name_erms: str` — from `PCE Testsheet` cell C5
- `substation_name_site: str` — from `PCE VI` cell C7
- `gps_coordinate: str` — from `PCE VI` cell C8
- `substation_type: str` — from `PCE VI` cell N1
- `building_type: str | None` — from `PCE VI` row 9 checkbox pattern
- `cycle_1: datetime | None` — from `PCE Testsheet` cell P4

Keep existing fields: `pe_number`, `substation_name`, `station_name`, `date_str`, `fl_number`, `type_code`, `wo_number`, `photo_ranges`.

### 2. Rewrite `TestsheetExtractor.extract_testsheet_data()` (`src/testsheet/extractor.py`)

**Phase 1: PCE Testsheet sheet** (fixed cells)
- `W5` → `fl_erms` (via `normalize_fl_erms()`)
- `C5` → `substation_name_erms` (via `clean_val()`)
- `P4` → `cycle_1` inspection date (via `to_excel_date()`)

**Phase 2: PCE VI sheet** (fixed cells, optional — sheet may not exist)
- `C7` → `substation_name_site`
- `C8` → `gps_coordinate`
- `N1` → `substation_type`
- Row 9 checkbox pattern → `building_type`:
  - D9 marked → C9 text; G9 → F9; I9 → H9; K9 → J9; M9 → L9; O9 → N9/P9
  - Normalize via `normalize_building_type()` → `"ATTACH"`, `"INDOOR"`, `"OUTDOOR"`

**Phase 3: RAW DATA sheet** (preserve existing photo range extraction)
- IR start/end, DG start/end from keyword scanning (unchanged logic)

### 3. Add helper functions to `src/testsheet/extractor.py`

Port from Johor reference:
- `normalize_fl_erms(val)` — strip whitespace, handle `.0` float suffix
- `clean_val(val)` — strip tabs/spaces, return None if empty/dash/NONE
- `is_marked(val)` — checkbox detection (not empty, not NO/N/A/FALSE/0/-)
- `normalize_building_type(val)` — map to ATTACH/INDOOR/OUTDOOR
- `to_excel_date(val)` — parse date string or datetime into datetime object

### 4. Backward compatibility

Ensure `extract_photo_ranges()` and `SubstationTestsheetRepository.discover_packages()` still work correctly for the Raw Material workflow after the rewrite.
