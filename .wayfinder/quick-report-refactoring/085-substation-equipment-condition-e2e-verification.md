# Ticket 085: Substation Equipment Condition E2E Verification & Test Suite

Labels: wayfinder:task
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](map.md)
Status: Closed

## Question

How can we verify end-to-end that the new equipment extractor and dynamic condition page generator correctly handle all real-world substation types (1 TX PCE, 2 TX PCE, CS Compact Substation, SSU 0 TX Switching Station, Dual Switchgear Station) without layout or data regression?

## Resolution

Established the canonical end-to-end extraction wiring rules, 5-variant test matrix, and 3-tier test suite architecture:

1. **LVDB vs FP Classification & Condition Naming**:
   - `R48`/`R52` inspection: Prefix `FP` $\to$ `FEEDER PILLAR`; prefix `LVDB` $\to$ `LVDB`.
   - Single active unit $\to$ `("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE")` or `("LVDB", "LVDB NAMEPLATE")`.
   - Multiple active units $\to$ `Label + Source`: `("LVDB TX1", "LVDB TX1 NAMEPLATE")`, `("FEEDER PILLAR TX1", "FEEDER PILLAR TX1 NAMEPLATE")` (falling back to sequential index if source is blank).

2. **Switchgear Unit Cardinality & Naming**:
   - `PCE VI` Rows 11–13 hold **Switchgear 1** (`Type 1`, `C12` Mfr, `F12` Model, `C13` Year, `J13` Rating, `O13` Serial No).
   - `PCE VI` Rows 14–16 hold **Switchgear 2** (`Type 2`, `C15` Mfr, `F15` Model, `C16` Year, `J16` Rating, `O16` Serial No).
   - `SubstationEquipmentPackage` holds `switchgears: tuple[SwitchgearSpec, ...]`.
   - 0 Switchgear $\to$ Omitted entirely.
   - 1 Switchgear $\to$ `("SWITCHGEAR", "SWITCHGEAR NAMEPLATE")`.
   - 2 Switchgears $\to$ `("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE")` and `("SWITCHGEAR 2", "SWITCHGEAR 2 NAMEPLATE")`.

3. **Transformer & Oil Level Indicator Dynamic Pairing**:
   - 0 TX $\to$ Omit all transformer pairs and oil level indicators.
   - 2 TX $\to$ `("TRANSFORMER 1", "TRANSFORMER 1 NAMEPLATE")`, `("TRANSFORMER 2", "TRANSFORMER 2 NAMEPLATE")`, and `("TRANSFORMER 1 OIL LEVEL INDICATOR", "TRANSFORMER 2 OIL LEVEL INDICATOR")`.
   - 1 TX $\to$ `("TRANSFORMER", "TRANSFORMER NAMEPLATE")`, with its oil level indicator dynamically stream-zipped with odd indicators (`EFI`, `SF6 INDICATOR`) or emitted as a half-pair `("TRANSFORMER OIL LEVEL INDICATOR", "")` with right-cell border stripped.

4. **Battery Charger & Bank Pairing**:
   - 1 Unit $\to$ `("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE")`.
   - 2 Units $\to$ `("BATTERY CHARGER 1", "BATTERY CHARGER 1 NAMEPLATE")` and `("BATTERY CHARGER 2", "BATTERY CHARGER 2 NAMEPLATE")`.
   - Triggered when `has_battery_charger is True` or `len(battery_banks) > 0`.

5. **5-Variant Test Matrix**:
   - **Variant A (1 TX Indoor PCE)**: 1 SWG, 1 TX (H/S), 1 FP, Indoor Fire Extinguisher (Valid), EFI, SF6 $\to$ 7 pairs $\to$ 3 pages (3 + 3 + 1, trailing border cleared).
   - **Variant B (2 TX Attach PCE)**: 1 SWG (8 panels across 2 sheets), 2 TX, 2 FP (`FP TX1` & `FP TX2`), Fire Extinguisher (Valid), EFI, SF6 $\to$ 9 pairs $\to$ 3 full pages (3 + 3 + 3).
   - **Variant C (SSU Switching Station — 0 TX)**: 1 SWG (12 panels across 3 sheets), 0 TX, 0 FP, 2 Battery Chargers (`BC1` & `BC2`), RTU, Attach Fire Extinguisher $\to$ 6 pairs $\to$ 2 full pages (3 + 3, no TX/Oil Level).
   - **Variant D (CS Compact Substation — Outdoor/Compact)**: 1 SWG, 1 TX, 1 FP, Fire Extinguisher **omitted**, EFI, SF6 $\to$ 6 pairs $\to$ 2 full pages (3 + 3, no fire extinguisher).
   - **Variant E (Dual Switchgear Station)**: 2 SWG units (`PCE VI` Rows 11–16), 1 TX, 1 LVDB, Fire Extinguisher $\to$ 8 pairs (`SWITCHGEAR 1`, `SWITCHGEAR 2`).

6. **3-Tier Test Suite Architecture**:
   - `tests/test_testsheet_equipment_extractor.py` (Stage 2 unit tests against synthetic in-memory OpenPyXL workbooks).
   - `tests/test_substation_condition_transformer.py` (Stage 4 Transformer unit tests verifying exact pair sequences).
   - `tests/test_substation_condition_docx.py` (Stage 5 Loader integration tests verifying multi-page docx rendering, paragraph shrinking to 0.5pt, and oxml border stripping for incomplete pages and half-pairs).

## Objectives

1. Add unit tests for `TestsheetExtractor` using real or mock testsheet data across different substation variants (1 TX, 2 TX, SSU, CS, Dual SWG).
2. Add unit/integration tests for `_build_substation_condition_pairs()` ensuring correct pair lists generated for each equipment package structure.
3. Test DOCX page generation with `generate_substation_condition_pages()` for arbitrary pair counts (e.g. 5 pairs -> 2 pages, 9 pairs -> 3 pages, 3 pairs -> 1 page) and verify clean cell border removal on incomplete final pages.
4. Execute `pytest` suite to ensure 100% pass rate.
