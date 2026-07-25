# Quick Report Defect Data Extraction and Suffix Lookup

Labels: wayfinder:research
Status: Closed
Parent: [Map: Quick Report Generation Workflow (Pahang CLI)](file:///.issues/019-quick-report-generation-map.md)

## Question

How should testsheet workbooks (`PCE Testsheet`, `PCE VI`) and ENGR master worksheets (`QR03 VI`, `QR03 CBA`) be parsed to extract visual defect records, diagnostic defect records, calculate the Pahang `DefectStatusSuffix` (e.g., `(IR+US+VI)`), and populate defect summary tables in the generated Quick Report?

## Resolution

1. **Extractor & Master Data Sources**:
   - `PCE Testsheet` & `PCE VI` sheets in testsheets supply initial station metadata, FL ERMS, substation type, GPS coordinates, and photo ranges.
   - Master ENGR workbooks (`ENGR-750-39-CBA-PAHANG-2026.xlsx`) contain `QR03 VI` (visual defects) and `QR03 CBA` (diagnostic defects for IR, US, TEV).
2. **DefectStatusSuffix Calculation**:
   - Presence of entries in `QR03 VI` sets `VI = True`.
   - Presence of diagnostic entries in `QR03 CBA` sets `IR = True`, `US = True`, and/or `TEV = True`.
   - Indicators are joined in strict canonical order `(IR+US+TEV+VI)`. (e.g., `(IR+US+VI)`, `(VI)`, or empty `""` if clean).
   - Stem format: `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)` (omitting date string per Pahang rule).
3. **Table Binding & Pagination**:
   - Visual defect records populate `2. VI SUMMARY TEMPLATE Jinja2.docx` & `10. VISUAL DEFECT Jinja2.docx`.
   - Diagnostic defects populate `CBM DEFECT SUMMARY.docx` and configuration CBM pages.
   - Pagination chunks defect summary tables into 6-item batches (`defects_per_page = 6`).
4. **Architecture Seam**:
   - Create `src/master/qr03.py` with `LocalExcelQr03Repository` for querying master defect entries and computing `DefectStatusSuffix`.
