<!-- status: closed -->
Part of #90
Specification: [spec.md](../spec.md)

# 100: feat(33kv-msms): 33kV MSMS pipeline and TestsheetReadingMapper for T1SUB33

**What to build:** Extend the MSMS suite (`ConsolidateMsms`, `EnrichMsms`, `PropagateWo`, `IngestMsmsCsv`, `PopulateDataMsms`) to support 33kV projects operating under Maximo job plan `T1SUB33` (`TIER 1-ONLINE CONDITION ASSESMENT`), implementing a polymorphic `TestsheetReadingMapper` strategy seam and 33kV meter-to-cell coordinate mappings across `33kV (Main)`, `11kV (Main)`, `TX`, and `Visual Inspec.`.

**Blocked by:** #92, #98

**Status:** closed

- [x] Support Maximo job plan `T1SUB33` across MSMS CSV ingestion and validation (`src/workflows/ingest_msms_csv.py`):
  - Recognize canonical 33kV CSV filename conventions (e.g. `07-10-2026_001.csv`).
  - Validate required Maximo headers (`ACTFINISH`, `ACTSTART`, `JPNUM`, `WONUM`, `TNBLOCATION`, `METERNAME`, `TNBNEWREADING`).
  - Strictly maintain 3-stage directory lifecycle in `PYTHON/MSMS/` (`RAW DATA` -> `TO BE FILLED` -> `COMPLETED`).
- [x] Direct reuse of upstream MSMS workflows for 33kV:
  - `ConsolidateMsmsWorkflow`: parse Maximo `.xls` files into `DATA MSMS.xlsx`.
  - `EnrichMsmsWorkflow`: enrich location, ERMS, date, and PE number from `TOTAL PE.xlsx` (`DataCycle1`).
  - `PropagateWoAction`: propagate WONUM from `DATA MSMS.xlsx` to Column F (`WO`) in `TOTAL PE.xlsx`.
- [x] Implement polymorphic `ReadingMapperStrategy` seam in `TestsheetReadingMapper` (`src/testsheet/mapper.py`):
  - `PceReadingMapper`: preserves 100% existing 11kV coordinate mapping on `PCE Testsheet`.
  - `PpuReadingMapper`: routes 33kV meters across 4 sheet types:
    - 33kV switchgear meters (`SG_33_GIS_PRES_*`, `TH_S33_*`, `US_S33_*`, `TEV_S33_*`, `SG_33_LOADING`, `HEATER_33KV_*`) -> `33kV (Main)`
    - 11kV switchgear meters (`SG_11_LOADING`, `TH_S11_*`, `US_S11_*`, `TEV_S11_*`, `HEATER_11KV_*`, `BG_*_11_ROOM_*`) -> `11kV (Main)`
    - Power Transformer meters (`TH_PTXMT_*`, `TH_PTXLV_*`, `TH_PTXHV_*`, `TH_PTXFIN_*`, `US_PTX_*`, `BG_TEM_TX1_BAY_*`) -> `TX`
    - Visual inspection defect meters (`VI_NER_*`, `VI_FCBL_*`, `VI_BLDG_*`, `VI_SGERT_*`, `VI_PTX_*`) -> `Visual Inspec.` / master `QR03`
- [x] Correlate bay-level `TNBLOCATION` hierarchy paths to parent substation package:
  - Extract root substation token by trimming bay segments after `/33KV/`, `/11KV/`, or `/TX/` (e.g. `CGBG/PPUAPMM/33KV/3P5` -> `CGBG/PPUAPMM`).
- [x] Reading update logic in `PopulateDataMsmsWorkflow` (`src/workflows/populate_data_msms.py`):
  - Characteristic meters: default is already `"NO"` in raw CSVs; only update to `"YES"` with comment when a defect is detected in `Visual Inspec.` or master `QR03`, leaving sound equipment untouched (100% parity with 11kV).
  - Numeric gauge meters: format and populate measurements from testsheet cells.
  - Move completed CSVs to `PYTHON/MSMS/COMPLETED/`.
- [x] Add unit tests in `tests/test_msms_33kv.py` testing CSV ingestion, parent token extraction, `PpuReadingMapper` coordinate resolution, and reading population.
