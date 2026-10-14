<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 092: feat(33kv-testsheet): PpuTestsheetParser for 33kV/11kV multi-sheet workbooks

**What to build:** Implement `PpuTestsheetParser` implementing `TestsheetParserStrategy` for 33kV workbooks. Parses dual-voltage switchgear lineups across `33kV (Main/Extra)` and `11kV (Main/Extra)` sheets (handling stations with only 33kV, only 11kV, or dual-voltage lineups), `Visual Inspection` sheet findings, RHS/LHS overview bays, `RAW DATA` photo bounds, and Column Q secondary panel extraction. Create the shared PPU workbook test fixture factory.

**Blocked by:** #91

**Status:** ready-for-agent

## Detailed Design & Architecture

1. **Domain Model Extensions (`src/testsheet/models.py`)**:
   - Extend `SwitchgearPanelSpec`:
     - Add `cable_entry_photo: int | None = None`
     - Add `link_box_photo: int | None = None`
   - Define `VisualInspectionFinding`:
     - Immutable dataclass: `category: str`, `item_no: str`, `description: str`, `status: str`, `remarks: str`.
   - Extend `TestsheetData`:
     - Add `visual_findings: tuple[VisualInspectionFinding, ...] = ()`.

2. **Substation Number Resolution Hierarchy**:
   - `substation_number` is resolved in strict order:
     1. Cell `V2` on `33kV (Main)` (if sheet present and cell valid)
     2. Cell `V2` on `11kV (Main)` (if sheet present and cell valid)
     3. Filename leading numeric prefix (e.g. `01. PPU APMM...` $\to$ `1`)
     4. If all fail to produce a valid positive integer $\to$ raise `ValueError(f"Unable to determine substation number for {path.name}")`.

3. **Metadata Header Extraction & Fallback**:
   - Target value cells:
     - Substation Name (`D6`)
     - Functional Location (`D7`)
     - Date (`D8`)
     - Time (`D9`)
     - Ambient Temp (`U6`)
     - Humidity (`U7`)
     - Background TEV (`U8`)
     - Switchgear Details (`L6..L11`: Manufacturer `L6`, Year `L7`, Model `L8`, Serial No `L9`, Busbar/Switchgear Type `L10`, Rating `L11`).
   - Priority: Read from `33kV (Main)` if present; fall back cleanly to `11kV (Main)` when `33kV (Main)` is absent (e.g. SSU or 11kV-only station).
   - GPS coordinate: extracted from `Visual Inspec.` cell `D3` if present.

4. **Dual-Voltage Switchgear Assembly**:
   - Support three topologies:
     - Dual-voltage: Both `33kV (Main)` and `11kV (Main)` present $\to$ `switchgears = (swg_33kv, swg_11kv)`.
     - 33kV only: Only `33kV (Main)` present $\to$ `switchgears = (swg_33kv,)`.
     - 11kV only: Only `11kV (Main)` present $\to$ `switchgears = (swg_11kv,)`.
   - If neither sheet contains active populated panels $\to$ raise `ValueError(f"No populated 33kV or 11kV switchgear lineups found in {path.name}")`.
   - Append extra sheets: `33kV (Extra)` panels appended to 33kV switchgear; `11kV (Extra)` panels appended to 11kV switchgear.

5. **Panel Stride & Compartment Mapping**:
   - Stride = 6 rows (Rows 15–62):
     - Row 1: `BREAKER` $\to$ `breaker_photo` (Col P) & Breaker Serial (Col V)
     - Row 2: `CABLE ` $\to$ `cable_photo` (Col P)
     - Row 3: `BUSBAR (TOP)` $\to$ `busbar_photo` (Col P)
     - Row 4: `PT COMPARTMENT` $\to$ `pt_photo` (Col P)
     - Row 5: `CABLE ENTRY` $\to$ `cable_entry_photo` (Col P)
     - Row 6: `LINK BOX` $\to$ `link_box_photo` (Col P)
   - Unpopulated template bays (blank panel no/feeder name) are skipped.
   - Secondary Compartment: Inspect Column Q across panel rows for regex `r"(?:\bSP:|\bSP\s*:)\s*(\d+)"` $\to$ populate `secondary_photo`.

6. **Overview Bays & Photos (Rows 63–74)**:
   - Extract RHS Overview (Rows 63–68) and LHS Overview (Rows 69–74):
     - FRONT, BACK, TOP, CABLE CELLAR, MBB, RBB.
   - Aggregate all distinct overview photo numbers into `SwitchgearSpec.photo_numbers`.
   - Prepend synthetic `OVERVIEW RHS` and `OVERVIEW LHS` panels to `SwitchgearSpec.panels`.

7. **Visual Inspection Findings Extraction**:
   - Parse `Visual Inspec.` sheet:
     - Checklist items 1.1–7.2 (Rows 8–76): record items marked `'NO'` or having non-empty remarks.
     - Category 8 "Other Findings" (Rows 78–80): capture all non-empty free-text remark lines into `VisualInspectionFinding(category="Other Findings", ...)`.
   - Stored in `TestsheetData.visual_findings`.

8. **Photo Range Bounds (`RAW DATA`)**:
   - Extract `ir_start`, `ir_end`, `dg_start`, `dg_end` from `RAW DATA` sheet (supporting grid table and label schemas).

9. **Shared Test Fixture Factory (`tests/fixtures/ppu_workbook_factory.py`)**:
   - Builder function `create_ppu_testsheet_workbook(...)` generating openpyxl 33kV workbooks with configurable panel counts, transformer ratings, dual-voltage sheets, and visual findings.
   - Reusable across all downstream 33kV tests.

## Acceptance Criteria Checklist

- [ ] Extend `SwitchgearPanelSpec` with `cable_entry_photo` and `link_box_photo`.
- [ ] Define `VisualInspectionFinding` dataclass and add `visual_findings` to `TestsheetData`.
- [ ] Implement `PpuTestsheetParser`:
  - [ ] Implement `substation_number` resolution (`V2` on 33kV $\to$ `V2` on 11kV $\to$ filename digits $\to$ `ValueError`).
  - [ ] Implement metadata header extraction from `33kV (Main)` with fallback to `11kV (Main)`.
  - [ ] Implement 6-row switchgear panel stride parsing (Breaker, Cable, Busbar, PT, Cable Entry, Link Box).
  - [ ] Implement Column Q `SP:` regex parsing for `secondary_photo`.
  - [ ] Implement RHS and LHS overview extraction (storing in `SwitchgearSpec.photo_numbers` and prepending synthetic panels).
  - [ ] Implement dual-voltage, 33kV-only, and 11kV-only switchgear board construction.
  - [ ] Implement `Visual Inspec.` findings parsing (checklist defects + Category 8 other findings).
  - [ ] Implement `RAW DATA` photo bounds extraction.
- [ ] Create shared PPU fixture factory in `tests/fixtures/ppu_workbook_factory.py`.
- [ ] Add unit tests in `tests/test_ppu_testsheet_parser.py` testing dual-voltage, 11kV-only, overview bays, `SP:` extraction, and fail-fast validation.
- [ ] Run full test suite verifying 0 regressions.
