<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 096: feat(33kv-quick-report): PPU/SSU condition photo pairing and multi-voltage Quick Report plan

**What to build:** Implement `PpuSubstationConditionPairBuilderPolicy` to generate accurate 2-column condition pages for PPU/SSU substations, and compose Quick Report plans supporting dual-voltage switchgear boards (`33kV` and `11kV` lineups), power transformers, and visual defect callouts strictly fetched from the master ENGR workbook.

**Blocked by:** #93, #94, #95

**Status:** ready-for-agent

## Detailed Design & Architecture

1. **`PpuSubstationConditionPairBuilderPolicy` (`src/quick_report/substation_condition.py`)**:
   - Implements 33kV condition pair builder producing canonical 2-column photo slot pairs:
     - **Page 1**:
       - `("SUBSTATION OVERVIEW", "SIGNBOARD")`
       - `("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE")` (if 33kV switchgear present)
       - `("SWITCHGEAR 11kV", "SWITCHGEAR 11kV NAMEPLATE")` (if 11kV switchgear present)
     - **Page 2**:
       - `("POWER TX1", "POWER TX1 NAMEPLATE")` (if TX 1 is $\ge 5$ MVA Power Transformer)
       - `("POWER TX2", "POWER TX2 NAMEPLATE")` (if TX 2 is $\ge 5$ MVA Power Transformer)
       - `("LOCAL TX", "LOCAL TX NAMEPLATE")` (if local station service transformer present)
     - **Page 3**:
       - `("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE")` or `("LVDB", "LVDB NAMEPLATE")` (if present)
       - `("CONTROL PANEL 33kV", "CONTROL PANEL 11kV")` (or `("33kV CONTROL PANEL", "11kV CONTROL PANEL")` / `("CONTROL PANEL", "NER")`)
       - `("FIRE EXTINGUISHER", "FIRE EXTINGUISHER EXPIRY DATE")` (if present in equipment inventory)
     - **Page 4**:
       - `("NER", "")` (Neutral Earthing Resistor, if present and unpaired)
       - `("33kV CABLE CELLAR", "11kV CABLE CELLAR")` (if cable cellars present)
   - Dynamic equipment omission: Unpopulated equipment types are gracefully skipped without creating blank table slots or breaking oxml table layout.
   - Dispatcher: `build_substation_condition_pairs(pkg)` dispatches to `PpuSubstationConditionPairBuilderPolicy` when `environment.metadata.voltage_type == "33kV"`.

2. **Visual Defect Ingestion Strategy**:
   - Strictly fetch VI defects from the master ENGR workbook (`QR03 VI` in Contract 750-39) via `MasterQr03DefectRepository`.
   - Preserve existing 11kV defect mapping architecture; do not guess or fallback to testsheet checklist items.

3. **Multi-Voltage Switchgear Iteration**:
   - Update all Quick Report planning and rendering subsystems (`QuickReportTransformer`, `CbmDefectPlanner`, `cbm_render.py`, `cbm_summary.py`):
     - Replace calls relying on singular `equipment.switchgear` with iteration over `equipment.switchgears` (plural).
     - Match diagnostic defects against both 33kV and 11kV switchgear lineups via `all_panels = [p for swg in equipment.switchgears for p in swg.panels]`.
     - Attribute the correct physical switchgear model, manufacturer, and rating, rendering voltage-aware feeder lines (e.g. `GIS 33kV - PANEL 1P5` vs `VCB 11kV - PANEL 9`).

4. **Output Filename Formatting (`QuickReportTransformer`)**:
   - For 33kV projects (`voltage_type == "33kV"`):
     - Format output filename with 2-digit zero-padding: `f"{pe_number:02d}. {sanitized_name}{suffix}.docx"`.
   - For 11kV projects (`voltage_type == "11kV"`):
     - Retain 3-digit zero-padding: `f"{pe_number:03d}. {sanitized_name}{suffix}.docx"`.

5. **Multi-Page Condition Chunking & Border Cleaning**:
   - Reuse existing `generate_substation_condition_pages()` chunking logic (3 pairs / 6 photos per page) and `_remove_empty_cell_borders_sub_cond()` oxml border stripper to dynamically compile 1 to 4 condition page chunks (`_05_substation_condition_part{idx}.docx`).

## Acceptance Criteria Checklist

- [ ] Implement `PpuSubstationConditionPairBuilderPolicy` in `src/quick_report/substation_condition.py` following the 33kV on-site layout (`SUBSTATION OVERVIEW`, `SWITCHGEAR 33kV/11kV`, `POWER TX1/2`, `LOCAL TX`, `CONTROL PANEL 33kV/11kV`, `NER`, `CABLE CELLAR`).
- [ ] Connect `build_substation_condition_pairs` to dispatch to `PpuSubstationConditionPairBuilderPolicy` when `voltage_type == "33kV"`.
- [ ] Update `QuickReportTransformer`, `CbmDefectPlanner`, `cbm_render.py`, and `cbm_summary.py` to iterate `equipment.switchgears` (plural) and display appropriate voltage classes.
- [ ] Update `QuickReportTransformer._calculate_suffix()` / filename generator to format 2-digit prefixes (`f"{pe_number:02d}."`) for 33kV and 3-digit prefixes for 11kV.
- [ ] Verify VI defect fetching strictly resolves against master ENGR workbook `QR03 VI`.
- [ ] Add unit tests in `tests/test_quick_report_33kv.py` covering:
  - [ ] PPU condition pair generation with dual-voltage switchgear, power transformers, and NER.
  - [ ] SSU condition pair generation (0 TX, single-voltage switchgear).
  - [ ] Dual-voltage CBM defect attribution and header rendering.
  - [ ] 2-digit output filename generation.
- [ ] Verify full test suite passes with 0 regressions.
