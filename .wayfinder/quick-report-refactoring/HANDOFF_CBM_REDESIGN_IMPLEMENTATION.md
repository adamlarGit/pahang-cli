# Handoff: CBM Defect & Defect Summary Pipeline Implementation

## Target Map & Context
- **Map File**: `.issues/092-cbm-defect-and-summary-redesign-map.md`
- **Ordered Implementation Tickets**:
  1. `093-dynamic-multi-technology-template-resolution.md`
  2. `094-cbm-defect-record-ingestion-alignment.md`
  3. `095-equipment-taxonomy-and-multitech-planner.md`
  4. `096-part2-cbm-technical-summary-redesign.md`
  5. `097-part4-cbm-defect-pages-and-context-builders.md`
  6. `098-loader-stage-ordering-and-verification.md`
  7. `099-codebase-hygiene-and-dead-code-cleanup.md`

## Locked Decisions & Specification Summary

1. **5 Core Families & Canonical Taxonomy Aliasing (`src/quick_report/cbm_family.py`)**:
   - `swg`: `RMU SF6`, `RMU OIL`, `VCB 11kV`, `VCB 33kV`, `MRMU`, `CABLE SWG`, `EARTHING`, `SWITCHGEAR`, `GIS 33kV`
   - `tx`: `LTX/DTX`, `CABLE LTX/DTX`, `PTX`, `CABLE PTX`, `TRANSFORMER`
   - `fp_lvdb`: `FP (D)` (DIN), `FP (J)` (J-Slotted), `LVDB`, `CABLE LVDB/FP`, `FP`
   - `battery`: `BATTERY CHARGER`, `BATTERY BANK`, `BATTERY`
   - `blackbox`: `BLACK BOX`, `BLACKBOX`
   - Switchyard / overhead items not mapped to these 5 appear in Part 2 summary table, but skip Part 4 detail pages with an explicit log.

2. **Template Directory Resolution (`src/project/environment.py`, `src/project/storage.py`, `config.py`)**:
   - Resolve template folders based on `ProjectMetadata.technologies`:
     - If `TEV` in project techs -> `templates/QUICK REPORT/DEFECT IR US TEV/`
     - Else if `US` in project techs -> `templates/QUICK REPORT/DEFECT IR US/`
     - Else -> `templates/QUICK REPORT/DEFECT IR/`
   - **Fail fast with explicit `FileNotFoundError`** if the required technology template folder is missing on disk.

3. **Multi-Technology Defect Merging in Part 4 (`src/quick_report/cbm_defect_planner.py`)**:
   - Grouping by `(item_key, defect_area)` merges IR, US, and TEV readings on the same equipment component/defect area into a single detail card.

4. **Switchgear (SWG) Mapping & Testsheet Integration (`src/quick_report/cbm_render.py`)**:
   - `panel.name` / `panel.linknumber` <- `EQUIPMENT ID`
   - `panel.area` <- verbatim `f"{defect_area}/ {additional_remarks}"` (if remarks exist, else `defect_area`), no extra prefix
   - Best-effort matching against `PCE Testsheet` panel grid for operating parameters (`loadamp`, `heateramp`, `breakerstatus`, `cabletype`, `serialnumber`) with clean `"-"` fallback.

5. **Transformer (TX) Smart Routing (`src/quick_report/cbm_defect_planner.py`, `src/quick_report/cbm_render.py`)**:
   - Route to `tx-hv-sides.docx` if `DEFECT AREA` or `EQUIPMENT ID` contains `"HV"`, `"11kV"`, `"33kV"`.
   - Route to `tx-lv-sides.docx` if `"LV"`, `"415V"`.
   - Fallback: `CABLE LTX/DTX` -> HV, `LTX/DTX` -> LV.
   - `tx.number` <- `EQUIPMENT ID` (e.g. `TX 1`).
   - `tx.location` <- `INDOOR` vs `OUTDOOR` from testsheet building type.
   - Other details from testsheet with `"-"` fallback.

6. **Feeder Pillar & LVDB (`fp_lvdb`) Mapping (`src/quick_report/cbm_render.py`)**:
   - Split `EQUIPMENT ID` on `" - "`: `fp.labelsource` <- pillar ID (e.g. `FP TX1`), `fp.feederno` <- bay ID (e.g. `OUTGOING F5`).
   - `fp.area` <- verbatim `f"{defect_area}/ {additional_remarks}"`.
   - `fp.serialnumber`, `fp.cabletype`, `fp.model` from testsheet with `"-"` fallback.

7. **Black Box & Battery Mapping (`src/quick_report/cbm_render.py`)**:
   - `bbox.number` <- bare digit (e.g. `"1"`).
   - `bbox.location` <- `"LEFT"`, `"RIGHT"`, `"FRONT"`, `"REAR"`.
   - `batt.*` <- manufacturer, model, number, and testsheet serial number.

8. **Part 2 CBM Tech Summary Table (`src/quick_report/cbm_summary.py`)**:
   - 7 columns: `NO.`, `EQUIPMENT`, `DEFECT AREA`, `IR (Abs.T/∆T)`, `U/S (dB)`, `TEV (dB)`, `SEVERITY`.
   - Single IR column wired to temperature reading with unit `°C`.
   - `SEVERITY` outputs US defect characteristic (`CORONA`, `TRACKING`, `ARCING`) for US defects only; empty string `""` for IR and TEV.

9. **Loader Stage & Document Assembly (`src/quick_report/composer.py`)**:
   - Strictly indexed 2-digit prefixes in `temp_parts/` (`001_01_front_page.docx` through `001_07_sticker_page.docx`).

10. **Codebase Hygiene & Dead Code Cleanup (`Ticket 099`)**:
    - Purge obsolete functions, dead fallback branches, unused imports, and redundant data structures across `src/quick_report/` and `src/project/`.
