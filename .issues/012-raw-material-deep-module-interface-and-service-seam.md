# Decision Ticket: Raw Material Deep Module Interface and Service Seam

## Question

How should testsheet parsing and raw material photo sorting be structured between `src/testsheet/` and `src/raw_material_workflow.py` to support the single-input directory flow?

## Status

CLOSED (Locked by User)

## Locked Resolution

1. **Testsheet Seam (`src/testsheet/`)**:
   - `src/testsheet/models.py`: Defines `TestsheetData`, `RawPhotoRanges` (containing `PhotoRange` for `IR` and `DG`), and `SubstationTestsheetPackage`.
   - `src/testsheet/extractor.py`: `TestsheetExtractor` handles openpyxl parsing of `RAW DATA` worksheet bounds for `IR` and `DG` directly from `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>.xlsx`.
   - `src/testsheet/repository.py`: `SubstationTestsheetRepository` discovers testsheets and `UNSORTED RAW DATA/` paths across `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/`.

2. **Raw Material Workflow (`src/raw_material_workflow.py`)**:
   - Consumes `TestsheetExtractor.extract_photo_ranges()` to get `IR` and `DG` photo ranges cleanly.
   - Automatically provisions destination directories: `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<TECHNOLOGIES>)/RAW DATA/`.
   - Executes photo sorting from `UNSORTED RAW DATA/` into destination `IR/` and `DG/` folders (with `US+TEV` raw data sorting deferred to a separate dedicated session).

3. **Workflow Service Integration (`src/workflows/service.py`)**:
   - Exposes `WorkflowService.run_raw_material(env, request)` returning `AutomatedRawMaterialSummary`.
