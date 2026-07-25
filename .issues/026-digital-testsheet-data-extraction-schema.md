# Digital Testsheet Data Extraction and Context Mapping Schema

Labels: wayfinder:research
Assignee: antigravity
Status: Closed
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md)

## Question

How should data fields extracted from digital testsheets (`src/testsheet/` `TestsheetExtractor`) and master workbooks (`QR02 CBA`, `QR03 VI`, `QR03 CBA`) be mapped into Quick Report Jinja template rendering contexts (`QuickReportContext`) for front page, summary tables, and detail pages?

## Resolution

The data extraction and context mapping schema is specified as follows:

1. **Single Source of Truth (Digital Testsheet)**:
   - Digital Testsheet is the main source of truth for Quick Report context. Fallbacks to Master QR02 CBA workbook are removed.
   - `substation_name_erms`: Extracted directly from `PCE Testsheet!C5`.
   - `gps_coordinate`: Extracted directly from `PCE VI!C8`.
   - `substation_type`: Extracted directly from `PCE VI!N1`.
   - `building_type`: Extracted directly from `PCE VI` Row 9 Checkboxes (`INDOOR`, `OUTDOOR`, `ATTACH`).

2. **Date & Time Formatting Rules**:
   - **Front Page Date**: `DD MMM YYYY` (e.g. `01 MAY 2026`).
   - **Individual CBM Defect Page Date**: `DD/MM/YYYY` (e.g. `01/05/2026`).
   - **Time**: Parsed from 24-hr `HHMM` (e.g. `1030`) into 12-hr `HH:MM AM/PM` (e.g. `10:30 AM`).

3. **CBM Technical Summary (Part 2A) Pairing & SI Units**:
   - Pairs IR, US, and TEV defects 1-to-1 matching on `(equipment, defect_area, remarks)` into `PreparedTechSummaryRow`.
   - `IR` reading: float + `" °C"` (e.g. `54.2 °C` or `"-"`).
   - `US` and `TEV` readings: **integer + `"dB"` without space** (e.g. `2dB`, `16dB`, or `"-"`).
   - `CBM DEFECT SUMMARY.docx` template table extended with `{{ item.us_reading }}` and `{{ item.tev_reading }}` placeholders alongside `{{ item.ir_reading }}`.

4. **Overview vs Defect Row Context Strategy**:
   - **Overview Pages**: Equipment metadata (`brand`, `model`, `rating`, `serialnumber`) extracted from Digital Testsheet.
   - **Specific Defect Pages**: Equipment metadata taken directly from that specific `QR03 CBA` defect row. Missing fields format to `"-"`.
   - **Strategy Seam**: Encapsulated in a flexible provider interface (`cbm_render.py`) for easy post-trial fine-tuning.

