<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 093: feat(33kv-domain): Power Transformer domain model and TX sheet parser

**What to build:** Extend 33kV equipment extraction to parse Power Transformers ($\ge 5$ MVA) vs Local Transformers ($100-1000$ kVA) from the dedicated `TX` worksheet, capturing auxiliary component thermals (`Marshalling Kiosk`, `Conservator Tank`, `Body`, `Cooling Fin`), ultrasound readings, and station service LVDB into `PowerTransformerSpec` and `SubstationEquipmentPackage`.

**Blocked by:** #92

**Status:** ready-for-agent

## Detailed Design & Architecture

1. **Domain Model Hierarchy (`src/testsheet/models.py`)**:
   - `PowerTransformerSpec(TransformerSpec)`:
     - Subclasses `TransformerSpec` to ensure 100% backward compatibility with all downstream consumers.
     - Adds auxiliary thermal reading fields:
       - `marshalling_kiosk_temp: ThermalReadingSpec`
       - `conservator_temp: ThermalReadingSpec`
       - `body_temp: ThermalReadingSpec`
       - `cooling_fin_temp: ThermalReadingSpec`
     - Adds auxiliary photo numbers:
       - `marshalling_kiosk_photo: int | None = None`
       - `conservator_photo: int | None = None`
       - `body_photo: int | None = None`
       - `cooling_fin_photo: int | None = None`
     - Adds ultrasound fields:
       - `hv_ultrasound: str = ""`
       - `lv_ultrasound: str = ""`

2. **Classification Logic & Warning Policy**:
   - Classification gate:
     - Units with rating $\ge 5$ MVA (e.g. `5MVA`, `10MVA`, `15MVA`, `30MVA`) $\to$ instantiate `PowerTransformerSpec`.
     - Units with rating $100\text{ kVA} - 1000\text{ kVA}$ or labeled `LOCAL TX` $\to$ instantiate standard `TransformerSpec`.
     - Out-of-range or ambiguous ratings $\to$ log a non-fatal warning and default to standard `TransformerSpec` without halting the pipeline.
   - SSU Tolerance: If the `TX` sheet is absent or empty, produce `transformers = ()`.

3. **Two-Part `TX` Sheet Parser in `PpuTestsheetParser`**:
   - **Header Metadata (Rows 6–9)**:
     - TX 1..4 across columns G, K, N, Q: Model, Manufacturer, Rating (MVA), Serial No.
   - **Part 1: Primary Terminations & Ultrasound (Rows 14–28)**:
     - Stride = 3 rows (Row 14: TX 1, Row 17: TX 2, Row 20: TX 3, Row 23: TX 4, Row 26: Local TX).
     - Load (Col F), Cable Type (Col H).
     - HV Cable Ultrasound: Reading dB (Col J), Type Characteristic (Col K), File (Col M).
     - LV Cable Ultrasound: Reading dB (Col N), Type Characteristic (Col O), File (Col Q).
     - HV/LV Cable Thermography: Ref, Max, Delta, Avg, Photo.
   - **Part 2: Auxiliary Components (Rows 33–48)**:
     - Stride = 3 rows (Row 33: TX 1, Row 36: TX 2, Row 39: TX 3, Row 42: TX 4, Row 45: Local TX).
     - Marshalling Kiosk (Cols F–J).
     - Conservator Tank (Cols L–P).
     - Body (Cols R–V).
     - Cooling Fin (Cols X–AB).
     - Remarks (Col AC).
   - **Station Service LVDB Section (Rows 49–52)**:
     - Extract Rating (e.g. `D51` `800A`) and Photo (e.g. `G51` `IR: 544`).
     - Instantiate `LVDBSpec` and append to `equipment.lvdb_specs`.

4. **Unit Tests & Fixtures**:
   - Use shared PPU fixture factory (`tests/fixtures/ppu_workbook_factory.py`) with configurable transformer counts (0 TX for SSU, 1 TX, 2 TX, 4 TX + Local TX) and ratings.
   - Verify parsing in `tests/test_ppu_transformer_parsing.py`.

## Acceptance Criteria Checklist

- [ ] Implement `PowerTransformerSpec` as a subclass of `TransformerSpec` in `src/testsheet/models.py`.
- [ ] Implement transformer classification function handling $\ge 5$ MVA, $100-1000$ kVA, and logging warnings for out-of-range ratings.
- [ ] Implement `_extract_tx_sheet()` in `PpuTestsheetParser`:
  - [ ] Parse Rows 6–9 metadata (Model, Manufacturer, Rating, Serial No).
  - [ ] Parse Part 1 (Rows 14–28) HV/LV load, cable types, ultrasound, and cable thermals.
  - [ ] Parse Part 2 (Rows 33–48) Marshalling Kiosk, Conservator, Body, Cooling Fin thermals.
  - [ ] Parse Rows 49–52 station service LVDB into `LVDBSpec`.
  - [ ] Correlate all parts into unified `PowerTransformerSpec` / `TransformerSpec` instances.
  - [ ] Support 0-transformer substations (SSU).
- [ ] Add unit tests in `tests/test_ppu_transformer_parsing.py` verifying full extraction, classification, SSU tolerance, and out-of-range handling.
- [ ] Verify full test suite passes with 0 regressions.
