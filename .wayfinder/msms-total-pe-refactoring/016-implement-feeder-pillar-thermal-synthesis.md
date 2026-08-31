<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 014-implement-ingest-and-populate-msms -->
# Implement Feeder Pillar Thermal Synthesis & Active Feeder Gating

## Objective

Implement active feeder gating and mathematical thermal synthesis for Feeder Pillar (LVDB / FP) rows in `PopulateDataMsmsWorkflow`.

Currently, all `TH_FP*` meters are treated as stubs (`is_stub=True`), leaving them completely blank in the output MSMS CSVs. Since testsheets record a single board average temperature in cell `R50` (LVDB 1) or `R54` (LVDB 2), we will synthesize the 4 required reading metrics (`AVG`, `MAX`, `REF`, `DEL`) for all active feeders based on this base temperature while leaving inactive/spare feeders blank.

## Detailed Requirements

### 1. Active Feeder Gating (`is_active_feeder_cable`)
- Feeders are located across Rows 44–47 in `PCE Testsheet`:
  - **LVDB 1**: Row 44 (Config / Name), Row 45 (Cable Type)
  - **LVDB 2**: Row 46 (Config / Name), Row 47 (Cable Type)
- **Feeder Channels**:
  - Incomers 1–3: Column `D` (IN1), `E` (IN2), `G` (IN3)
  - Outgoings 1–10: Columns `I` through `R` (OT1..OT10)
- **Active Rule**:
  - Cell contains a non-empty cable insulation type string (e.g. `XLPE`, `PILC`, `ABC`, `BUSBAR`).
- **Inactive / Spare Rule**:
  - Cell is empty/blank, `-`, `SPARE`, or `N/A`.
  - Inactive feeders remain blank (`""`) in the MSMS CSV.
  - `TH_EARTH_*` and outgoings beyond populated channels remain blank (`""`).

### 2. Thermal Synthesis Engine (`synthesize_feeder_thermal_readings`)
- For active feeders, calculate `AVG`, `MAX`, `REF`, `DEL` (`ΔT`) from the base board average temperature $T_{\text{board}}$ (`R50` for LVDB 1, `R54` for LVDB 2):
  - **Indoor / Attached Substation** (`building_type in ("INDOOR", "ATTACH")` or `substation_type in ("PE", "ATTACH", "INDOOR")`):
    $$\text{jitter} \in [-0.5, +0.5]^\circ\text{C}$$
  - **Outdoor / Compact / PAT Substation** (`substation_type in ("CS", "PAT", "POLE")` or `building_type == "OUTDOOR"` or `_PE13O`):
    $$\text{jitter} \in [-1.0, +1.0]^\circ\text{C}$$
  - Feeder Base Average:
    $$T_{\text{avg}} = \text{round}(T_{\text{board}} + \text{jitter}, 1)$$
  - Delta-T ($\Delta T < 1.0^\circ\text{C}$):
    - Generate $\Delta T \in [0.2, 0.8]^\circ\text{C}$ rounded to 1 decimal place.
  - Reference & Maximum:
    $$\delta = \text{round}\left(\frac{\Delta T}{2}, 1\right)$$
    $$T_{\text{ref}} = \text{round}(T_{\text{avg}} - \delta, 1)$$
    $$T_{\text{max}} = \text{round}(T_{\text{ref}} + \Delta T, 1)$$
- **Strict Invariants**:
  1. $\Delta T = T_{\text{max}} - T_{\text{ref}}$ is mathematically exact.
  2. $\Delta T < 1.0^\circ\text{C}$ is strictly maintained at all times.
  3. Deterministic seeding: Given the same substation, WONUM, and feeder ID, numbers are 100% reproducible across runs.

### 3. Integration in `PopulateDataMsmsWorkflow`
- In `_evaluate_row()`:
  - Detect `TH_FPIN*_` and `TH_FPOT*_` meters.
  - Identify whether equipment is `FP1` or `FP2`.
  - Extract cable type from row 45 (FP1) or 47 (FP2).
  - If active, extract base board temp from `R50` (FP1) or `R54` (FP2), run thermal synthesis, and populate metric corresponding to suffix (`AVG`, `MAX`, `REF`, `DEL`).
  - If inactive or spare, leave row blank.

## Acceptance Criteria & Tests (TDD)
- [x] `tests/test_feeder_thermal.py`:
  - Test `is_active_feeder_cable()` on valid types (`XLPE`, `PILC`, `ABC`, `BUSBAR`) and inactive sentinels (`-`, `SPARE`, `N/A`, `""`, `None`).
  - Test `synthesize_feeder_thermal_readings()` invariant $\Delta T = T_{\text{max}} - T_{\text{ref}} < 1.0^\circ\text{C}$.
  - Test indoor vs. outdoor jitter bounds.
  - Test deterministic reproducibility.
- [x] Integration test in `tests/test_populate_data_msms.py` verifying active FP rows populated and inactive/spare rows left blank.
- [x] Full regression suite passing (424 tests).
