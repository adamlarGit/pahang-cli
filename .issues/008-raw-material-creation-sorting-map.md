# Map: Raw Material Creation & Sorting Workflow (Pahang CLI)

## Destination

Design and specify the deep module architecture, domain rules, Excel schemas, validation checks, and service seams for the Raw Material Creation & Sorting workflow in `pahang-cli`.

## Notes

- **Input Location**: `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/` containing testsheets and `UNSORTED RAW DATA/`
- **Output Destination**: Initial `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>/RAW DATA/` (renamed during Post-Processing Pipeline to `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)`)
- **Pahang Naming Rule**: Omits `<DDMMYYYY>` date string from document, testsheet, and folder stems.
- **Target Module**: `src/testsheet/` (deep module) & `src/raw_material_workflow.py` / `src/workflows/`
- **Domain Modeling**: [CONTEXT.md](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md)
- **Design Guidelines**: Follow deep module principles and preserve 100% architectural alignment with reference CLI.

## Decisions so far

- [Domain Context Initialization](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md) — Captured `PahangStation`, `MonthFolder`, `DailyDateFolder`, `InitialSubstationFolder`, `DefectStatusSuffix`, `PahangRenamedSubstationStem`, `TestsheetExtractor`, `RawPhotoRanges`, `PhotoSorter`, and `AutomatedRawMaterialSummary` in `CONTEXT.md`.
- [Substation Folder Naming, Defect Suffixes, and Pipeline Renaming](file:///.issues/009-pahang-raw-material-folder-naming-and-date-parsing.md) — Initial PE folder creation; Pahang stem format `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)` (omitting date string); defect indicators calculated from ENGR `QR03` sheets during Quick Report generation; post-processing pipeline renames `TESTSHEET` and `RAW MATERIAL` folders in place.
- [Pahang Testsheet RAW DATA Schema and Photo Filename Matching](file:///.issues/010-pahang-testsheet-raw-data-schema-and-photo-matching.md) — Source photos from `UNSORTED RAW DATA/`; `PhotoRange` bounds apply to `IR` & `DG`.
- [Raw Material Pre-check Validation and Warning Policies](file:///.issues/011-raw-material-precheck-validation-and-warning-policies.md) — Enforce `TOTAL PE.xlsx` pre-check, automatic folder provisioning, and non-blocking missing photo warning policy.
- [Raw Material Deep Module Interface and Service Seam](file:///.issues/012-raw-material-deep-module-interface-and-service-seam.md) — Align with reference CLI architecture by using `src/testsheet/` (`TestsheetExtractor`, `RawPhotoRanges`) for testsheet reading and `src/raw_material_workflow.py` for photo sorting.

## Not yet specified

- Raw data file sorting structure for `US+TEV` combined raw measurements (deferred to a dedicated Wayfinder session).
- Synthetic sample test cases for Pahang 5-level folder structure.

## Out of scope

- Including `<DDMMYYYY>` 8-digit date strings in Pahang document or folder stems.
- Calculating defect suffixes from raw photo files instead of authoritative ENGR `QR03 VI` and `QR03 CBA` master sheets.
- Direct execution on Johor-specific single-folder flat paths without `WorkspaceStorage` resolution.
