# Ticket 102: Testsheet Ultrasound & TEV Measurement Ingestion Schema

Labels: wayfinder:task, afk, state:closed

## Question

How should `TestsheetExtractor`, `TestsheetData`, `SwitchgearPanelSpec`, and `TransformerSpec` in `src/testsheet/` be extended to extract TEV background dB (cell `P6`), Ultrasound dB / char, and TEV dB / PPC across single-panel and multi-panel VCB / TX sheets in `PCE Testsheet` workbooks?

## Resolution

- **Testsheet Ingestion**:
  - `PCE Testsheet` cell `P6` -> `tev_background` (passed into `TestsheetData` and `pe_info["tev_bg"]`).
  - Switchgear Panels (rows 10, 14, 18, 22 on `PCE Testsheet`): Column Q (`us_reading`), Column S (`us_char`), Column T (`tev_reading`), Column U (`tev_ppc`), Column V (`tev_char`) with resilient fallback to sub-rows.
  - Transformers: `ws_pce` rows 33-42 mapped to `TransformerSpec` (TX1/TX2: Col K `us_reading`, Col L `us_char`; TX3/TX4: Col V `us_reading`, Col X `us_char`).
- **Context Integration**:
  - Extended `_build_swg_render_context` and `_build_tx_render_context` in `src/quick_report/cbm_render.py` to populate root `us` (`reading`, `char`), `tev` (`reading`, `ppc`, `char`, `bg`), and `ir` (`reading`, `severity`) dictionaries and nested `panel` / `tx` keys.
- **Verification**: Verified via `tests/test_cbm_severity_and_measurements.py` and `tests/test_testsheet_equipment_extractor.py`.
