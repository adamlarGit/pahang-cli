# Ticket 094: CBM Defect Record Ingestion & Extraction Alignment

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed
Blocks: [Ticket 095](file:///.issues/095-equipment-taxonomy-and-multitech-planner.md)
Blocked-by: [Ticket 093](file:///.issues/093-dynamic-multi-technology-template-resolution.md)

## Question

How should `MasterQr03DefectRepository` and `CbmDefectRecord` in `src/quick_report/defects.py` be aligned to explicitly extract `EQUIPMENT ID`, `US CHAR`, `TEV CHAR`, `CRITICALITY`, and clean measurements across all technology columns from `QR03 CBA`?

## Scope

- Ensure `CbmDefectRecord` dataclass stores `equipment_id` and all raw/diagnostic readings without truncation.
- Cleanly filter and normalize rows for target substations.
- Add unit test coverage for extraction from real-world `QR03 CBA` layouts.

## Resolution

- Extended `CbmDefectRecord` with `equipment_id` and `criticality` dataclass fields and normalization.
- Aligned `MasterQr03DefectRepository.fetch_cbm_defects` to extract `EQUIPMENT ID`, `CRITICALITY`, `US CHAR` (with `DEFECT TYPE` fallback for US), `TEV CHAR` (with `DEFECT TYPE` fallback for TEV), and precise readings.
- Added comprehensive unit tests in `tests/test_quick_report_components.py`.
