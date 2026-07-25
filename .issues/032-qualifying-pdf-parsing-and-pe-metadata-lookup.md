# Qualifying PDF Parsing and PE Metadata Lookup

Labels: wayfinder:research
Status: Closed
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

How should qualifying PDF filenames in Quick Report batch directories be matched and parsed (using regex pattern `^(\d+)\.?\s*(.*?)\s*(?:\((.*?)\))?\.pdf$`), and how are the extracted PE numbers cross-referenced against `TOTAL PE.xlsx` (`DataCycle1` sheet) to pull substation metadata (FL name, station, date, inspection findings)?

## Resolution

1. **PDF Filename Regex Parsing**:
   - Matches pattern `^(\d+)\.?\s*(.*?)\s*(?:\((.*?)\))?\.pdf$` (case-insensitive).
   - Group 1: Numerical PE prefix (parsed as `int` for numeric sorting and `TOTAL PE.xlsx` matching).
   - Group 2: Substation name stem.
   - Group 3: Defect suffix indicator (e.g., `VI`, `IR+US+VI`). If absent, defect value is strictly `"-"`.

2. **Defect vs Metadata Separation Rule**:
   - Defect findings are derived **strictly** from the PDF filename suffix `(...)` in the Quick Report batch folder, **not** from `TOTAL PE.xlsx`.
   - `TOTAL PE.xlsx` (`DataCycle1` sheet) is queried strictly for metadata: `SUBSTATION NAME`, `WO` (MSMS work order number), `DATE` of inspection, and `FL NUMBER` prefix (e.g. `CMRN` -> `MARAN` station name mapping).

3. **Fallback & Error Handling**:
   - Missing `WO` or unmapped fields fall back to `"-"`.
   - PDFs in the selected batch folder are processed in ascending numerical PE order.
