<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Implement Core Foundation: Centralized Normalizers and Canonical Testsheet Mapper

## Objective

Build the fundamental data transformation layer for the MSMS refactoring:
1. **Target-System Normalizer Suite** (`src/core/normalizers.py`): Cleanly separating conversions for CSV, Excel, and Word/PDF reports.
2. **Canonical Testsheet Reading Mapper** (`src/testsheet/mapper.py`): Zero-side-effect coordinate resolution engine connecting MSMS `METERNAME` strings and `TNBLOCATION` paths to exact `PCE Testsheet` cells.

## Detailed Requirements

### 1. Centralized Normalizers (`src/core/normalizers.py`)
- Implement `normalize_for_csv(val: Any) -> str`: Returns sanitized string or `""` for missing/empty/NaN values (never `"-"` or `"NaN"`).
- Implement `normalize_for_excel(val: Any) -> Any`: Returns native Python types (`float`, `int`, `datetime.date`, `str`) or `None` for openpyxl cells.
- Implement `normalize_for_report(val: Any) -> str`: Returns formatted display strings with `"-"` placeholders for Word/PDF report tables.
- Date/Time parsing and ISO-8601 formatting helpers (`format_iso8601(dt, tz_offset="+08:00")`).
- Background temperature regex parser: `extract_background_temperature(text: str) -> float | None` handling flexible spacing in `BACKGROUND TEMP : XX.X °C`.

### 2. Canonical Testsheet Reading Mapper (`src/testsheet/mapper.py`)
- Implement `parse_equipment_index(tnb_location: str) -> tuple[str, int]`:
  - `/11KV/N` $\to$ `('11KV', N)`
  - `/TX/DTXN` $\to$ `('TX', N)`
  - `/FP/FPN` $\to$ `('FP', N)`
- Implement 4-panel rollover logic:
  - $\text{sheet\_index} = \lfloor(N - 1) / 4\rfloor + 1$
  - $\text{local\_slot} = ((N - 1) \bmod 4) + 1$
  - Sheet naming: `PCE Testsheet` for sheet 1, `PCE Testsheet (N)` for sheet $N \ge 2$.
- Implement `TestsheetReadingMapper`:
  - **RMU SF6 / MRMU (`_PE13R`)**: Fixed slot mapping (CBL1=1, CBL2=2, CBL3=3, FS1=4, FS2=5). Only CABLE sub-row (offset +0) is targeted. Body maps to Overview row 26 (Avg only: `N26`, other metrics are stubs). Body TEV $\to$ `P6`. Body US $\to$ hardcoded `0`.
  - **VCB (`_PE13V` / `_PE13V2`)**: Dynamic panel slot resolution from `/11KV/N`. Uses all 4 compartment sub-rows: Cable (+0), Breaker (+1), Top Panel (+2), PT (+3). Columns: K (REF), L (MAX), M (DIF), N (AVG), Q (US), T (TEV dB), U (TEV Pulse). LV compartment is marked stub (`is_stub=True`).
  - **Distribution Transformer (`_PE13R` / `_PE13V`)**: `/TX/DTX1` (rows 33–37) and `/TX/DTX2` (rows 38–42). Columns: F (REF), G (MAX), H (DIF), I (AVG), K (US dB). HV $\to$ HT Cable row, LV $\to$ LV Cable row, Body $\to$ Body row.
  - **LVDB / Feeder Pillar (`/FP/FP1`, `/FP/FP2`)**: All 64 thermal meters marked as stubs (`is_stub=True`).
  - **Background & Metadata**: `BG_ROOM_TV` $\to$ `P6`, `BG_ROOM_HUM` $\to$ `S6`, `BG_ROOM_TEM` $\to$ regex from `W6`, `EXECUTION_DATE` $\to$ `P4`, `TIME_IN` $\to$ `P5`, `TIME_OUT` $\to$ `S5`.
  - Method `get_target(meter_name: str, tnb_location: str = "") -> tuple[str, str] | None` returning `(sheet_name, cell_coordinate)` or `None` if stub/unmapped.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_normalizers.py`: Comprehensive unit tests covering all target conversions (CSV, Excel, Report), null handling, edge cases, and ISO timestamps.
- [x] `tests/test_testsheet_mapper.py`: Unit tests verifying exact cell coordinates for:
  - RMU Body, Cable 1–3, Fuse 1–2 (including Sheet 2 rollover).
  - VCB Panels 1–8 across Sheet 1 and Sheet 2 for all 4 active compartments.
  - TX1 and TX2 HV/LV/Body thermal and US readings.
  - LVDB and VCB LV stubs returning `None`.
  - Background readings and metadata timestamps.
- [x] 100% test pass with zero regressions.
