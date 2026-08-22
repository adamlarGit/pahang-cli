# Ticket 084: Dynamic Substation Condition Pairs Transformer

Labels: wayfinder:grilling
Parent: [Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map](map.md)
Status: Closed

## Question

How should `QuickReportTransformer._build_substation_condition_pairs()` in `src/quick_report/transformer.py` (and `src/quick_report/substation_condition.py`) be refactored as a pure ETL Stage 4 Transformer stage to dynamically construct 2-column condition pairs from `pkg.data.equipment` instead of returning hardcoded static pairs?

## Resolution

Specified the dynamic stream-packing 2-column condition pair builder algorithm in `src/quick_report/transformer.py` and `src/quick_report/substation_condition.py`:
1. **Substation Overview**: `("SUBSTATION OVERVIEW", "SIGNBOARD")` (Always present).
2. **Switchgear**:
   - 1 Switchgear: `("SWITCHGEAR", "SWITCHGEAR NAMEPLATE")`
   - 2 Switchgears: `("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE")` and `("SWITCHGEAR 2", "SWITCHGEAR 2 NAMEPLATE")`
   - 0 Switchgear: Omitted.
3. **Transformer**:
   - 1 Tx: `("TRANSFORMER", "TRANSFORMER NAMEPLATE")`
   - Multiple: `(f"TRANSFORMER {i}", f"TRANSFORMER {i} NAMEPLATE")`
   - 0 (e.g. SSU / CS without Tx): Omitted.
4. **LVDB / Feeder Pillar**:
   - 1 Unit: `("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE")` or `("LVDB", "LVDB NAMEPLATE")`
   - Multiple: `(f"{label} {source}", f"{label} {source} NAMEPLATE")` (e.g. `("LVDB TX1", "LVDB TX1 NAMEPLATE")` or `("FEEDER PILLAR TX1", "FEEDER PILLAR TX1 NAMEPLATE")`)
   - 0: Omitted.
5. **Battery Charger & RTU**:
   - If 1 Battery Charger: `("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE")`
   - If 2 Battery Chargers: `("BATTERY CHARGER 1", "BATTERY CHARGER 1 NAMEPLATE")` and `("BATTERY CHARGER 2", "BATTERY CHARGER 2 NAMEPLATE")`
   - If `has_rtu`: `("RTU", "RTU NAMEPLATE")`
6. **Fire Extinguisher**:
   - `INDOOR` & `ATTACH`: Included (`("FIRE EXTINGUISHER", "FIRE EXTINGUISHER EXPIRY DATE")`)
   - `OUTDOOR` & `COMPACT` (CS): **Omitted**.
7. **Indicators & Single-Item Stream Packing**:
   - Dual SF6: `("SF6 INDICATOR 1", "SF6 INDICATOR 2")`
   - Dual Tx Oil Level: `("TRANSFORMER 1 OIL LEVEL INDICATOR", "TRANSFORMER 2 OIL LEVEL INDICATOR")`
   - Single items (`EFI`, single `SF6 INDICATOR`, single `TRANSFORMER OIL LEVEL INDICATOR`) are streamed and zipped into pairs.
   - Any unmatched trailing odd item renders as a half-pair `(item, "")` with right-cell borders stripped cleanly via `_remove_empty_cell_borders_sub_cond()`.
8. **Pure Stage 4 Separation**: Logic is side-effect-free, operating purely on `pkg.data.equipment` and returning `tuple[tuple[str, str], ...]`.


