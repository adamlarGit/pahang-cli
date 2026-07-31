# Ticket 063: CBA & VI Defect Data Extraction & Suffix Calculation

## Parent Map

[Map 061: Quick Report Engine Unstubbing & Photo Integration Map](file:///.issues/061-quick-report-engine-unstubbing-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Blocked-By

*(None — Frontier Ticket)*

## Question

How should diagnostic CBM defects (IR, US, TEV) and Visual Inspection (VI) defects be retrieved from QR03 CBA/VI sheets or testsheet data, normalized into defect records for `cbm_defects` and `vi_defects`, and mapped to calculate the canonical defect suffix `(IR+US+TEV+VI)` and populate CBM & VI summary and detail family pages?

## Resolution

Implemented `MasterQr03DefectRepository` in `src/quick_report/defects.py` to fetch CBM and VI defects from master Excel workbooks (`QR03 CBA.xlsx` and `QR03 VI.xlsx`) in the ENGR directory matching functional locations. Wired into `QuickReportComposer._process_station()` to dynamically compute canonical suffix `(IR+US+TEV+VI)` and omit CBM/VI summary & detail pages when no defects exist (returning empty suffix `""`). Unit tests added and verified.
