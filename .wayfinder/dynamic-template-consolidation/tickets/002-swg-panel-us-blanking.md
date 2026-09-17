---
id: "002"
title: "Switchgear Panel Ultrasound Dynamic Blanking & PRPD Optimization"
github_issue: 42
github_url: "https://github.com/adamlarGit/pahang-cli/issues/42"
status: closed
---

# Ticket 002: Switchgear Panel Ultrasound Dynamic Blanking & PRPD Optimization

<!-- status: closed -->

## Objective

Implement dynamic OpenXML blanking for the Ultrasound (US) measurement quadrant in Switchgear Panel templates (`swg-panel.docx`) across both Full Report and Quick Report.

The implementation must strictly mirror the established TEV blanking architecture in [`src/core/shading.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/core/shading.py), [`src/quick_report/prpd.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/quick_report/prpd.py), [`src/quick_report/cbm_render.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/quick_report/cbm_render.py), and [`src/full_report/scan_adapters.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/full_report/scan_adapters.py) to maintain architectural symmetry, eliminate cognitive overhead, and prevent maintenance drifting.

---

## Two-Tier Eligibility Model

US blanking follows the identical two-tier evaluation pattern established for TEV:

```
┌────────────────────────────────────────────────────────┐
│ Tier 1: Contract Awarded Technologies                  │
│ is_us_contract_awarded(technologies)                   │
│ - "US" in project technologies?                        │
│ - Defaults to True if technologies is None/unspecified │
│ - If False (e.g. IR-only project), blank US everywhere │
└──────────────────────────┬─────────────────────────────┘
                           │ Active
                           ▼
┌────────────────────────────────────────────────────────┐
│ Tier 2: Switchgear Compartment US Eligibility          │
│ is_swg_compartment_us_eligible(compartment)            │
│ - Excluded: SECONDARY COMPARTMENT, LINK BOX            │
│ - Eligible: BREAKER, CABLE, PT, BUSBAR, CABLE ENTRY,   │
│             FUSE COMPARTMENT, and other active areas   │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Combined Evaluation: is_swg_us_active(...)             │
│ = is_us_contract_awarded and                           │
│   is_swg_compartment_us_eligible                       │
└────────────────────────────────────────────────────────┘
```

### 1. Tier 1 (Contract Awarded Technologies)
- Helper: `is_us_contract_awarded(technologies: Sequence[str] | set[str] | None) -> bool` in [`src/core/shading.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/core/shading.py).
- Checks if `"US"` is present in normalized project technologies (e.g. `ProjectMetadata.technologies` or `pe_info.technologies`).
- Defaults to `True` when omitted or empty (assuming standard 3-modality contract).
- For IR-only contracts (e.g. `["IR"]`), US is marked inactive across all switchgear panels and compartments.

### 2. Tier 2 (Switchgear Compartment US Eligibility)
- Helper: `is_swg_compartment_us_eligible(compartment: str | None) -> bool` in [`src/core/shading.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/core/shading.py).
- Canonical constant: `US_BLANKED_SWG_COMPARTMENTS: frozenset[str] = frozenset({"SECONDARY COMPARTMENT", "LINK BOX"})`.
- Enforces exclusion-based enforcement mirroring TEV:
  - **US-Excluded / Blanked**:
    - `SECONDARY COMPARTMENT` (Control/metering compartment; no ultrasound testing performed).
    - `LINK BOX` (External cable link/grounding box; no ultrasound testing performed).
  - **US-Eligible**:
    - All other switchgear compartments: `BREAKER COMPARTMENT`, `CABLE COMPARTMENT`, `PT COMPARTMENT`, `BUSBAR COMPARTMENT`, `CABLE ENTRY`, `FUSE COMPARTMENT`, etc.
- Compartment Normalization (`normalize_swg_compartment`):
  - Precedence Rule: Must evaluate `LINK BOX` (and `CABLE LINK BOX`, `LINKBOX`) **before** generic `CABLE` keyword matching so that cable link boxes are not misclassified as `CABLE COMPARTMENT`.
  - Secondary Normalization: Normalize `SECONDARY COMPARTMENT`, `SECONDARY`, `CONTROL COMPARTMENT`, `METERING` to `SECONDARY COMPARTMENT`.

### 3. Combined Helper
- `is_swg_us_active(project_technologies=None, compartment=None) -> bool` in [`src/core/shading.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/core/shading.py).
- Returns `True` if and only if both Tier 1 and Tier 2 conditions are met.

---

## OpenXML Blanking Engine: `blank_swg_us_cells`

Must strictly match the XML DOM manipulation strategy implemented in `blank_swg_tev_cells()`:

- **Target Grid**: Rows 21–32 (indices 21..32 inclusive) and Columns 1–8 (indices 1..8 inclusive) in the 37x24 table of `swg-panel.docx`.
- **vMerge Masking Bypass**: Iterate over raw XML `<w:tc>` elements in each `<w:tr>` (accounting for `<w:gridSpan>`) rather than python-docx `table.cell(r, c)` to ensure continuation cells under the `{{ us.prpd }}` image (rows 23–26) are directly accessed and modified.
- **Operations on Target Cells (Cols 1..8)**:
  1. `clear_cell_text(tc)`: Remove paragraph runs, text nodes, and embedded drawing/pict objects.
  2. `clear_cell_shading(tc)`: Remove `<w:shd>` background fill element.
  3. `set_cell_no_borders(tc)`: Set all borders (`top`, `left`, `bottom`, `right`, `insideH`, `insideV`, `tl2br`, `tr2bl`) to `<w:val="nil"/>`.
- **Adjacent Spacer Border Clearing**:
  - **Left border**: Column 0 right border (`col_end == 0`) facing the US block set to `nil`.
  - **Right border**: Column 9 left border (`col_start == 9`) facing the US block set to `nil`.
  - **Top border (Row 20 spacer)**: Bottom border of cells in row 20 overlapping columns 1..8 (`max(col_start, 1) <= min(col_end, 8)`) set to `nil`.
  - **Bottom border (Row 33 spacer)**: Top border of cells in row 33 overlapping columns 1..8 (`max(col_start, 1) <= min(col_end, 8)`) set to `nil`.
- **Idempotency & Type Support**: Safe to call repeatedly; supports `docx.Document`, `DocxTemplate`, `Table`, or lists/tuples thereof.
- **Strict Layout Guard**: Guard with `len(table.rows) >= 33 and len(table.columns) == 24` to avoid corrupting unrelated document tables.

---

## Reference Implementation Blueprint

```python
def blank_swg_us_cells(target: Any) -> Any:
    """Blank Ultrasound (US) measurement cells in swg-panel.docx 37x24 table.

    Operates on rows 21–32 (indices 21..32 inclusive) and columns 1–8 (indices 1..8 inclusive).
    Iterates raw XML <w:tc> elements in each row's <w:tr> to bypass python-docx vMerge masking.
    - Clears cell text
    - Removes background cell shading (<w:shd>)
    - Sets all borders to <w:val="nil"/>
    Also clears bordering spacer borders facing the US block (col 0 right border,
    col 9 left border, row 20 bottom border, row 33 top border) to eliminate ghost borders.
    """
    tables = _collect_tables(target)
    for table in tables:
        if len(table.rows) >= 33 and len(table.columns) == 24:
            for r_idx in range(21, 33):
                row = table.rows[r_idx]
                col_idx = 0
                for tc in row._tr.findall(qn("w:tc")):
                    tcPr = tc.find(qn("w:tcPr"))
                    gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
                    span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
                    col_start = col_idx
                    col_end = col_idx + span - 1
                    col_idx += span

                    if col_start >= 1 and col_end <= 8:
                        clear_cell_text(tc)
                        clear_cell_shading(tc)
                        set_cell_no_borders(tc)
                    elif col_end == 0:
                        _set_tc_border_nil(tc, "right")
                    elif col_start == 9:
                        _set_tc_border_nil(tc, "left")

            if len(table.rows) > 20:
                row_20 = table.rows[20]
                col_idx = 0
                for tc in row_20._tr.findall(qn("w:tc")):
                    tcPr = tc.find(qn("w:tcPr"))
                    gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
                    span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
                    col_start = col_idx
                    col_end = col_idx + span - 1
                    col_idx += span
                    if max(col_start, 1) <= min(col_end, 8):
                        _set_tc_border_nil(tc, "bottom")

            if len(table.rows) > 33:
                row_33 = table.rows[33]
                col_idx = 0
                for tc in row_33._tr.findall(qn("w:tc")):
                    tcPr = tc.find(qn("w:tcPr"))
                    gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
                    span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
                    col_start = col_idx
                    col_end = col_idx + span - 1
                    col_idx += span
                    if max(col_start, 1) <= min(col_end, 8):
                        _set_tc_border_nil(tc, "top")

    return target
```

---

## Integration Pipeline

### 1. `src/core/shading.py`
- Add canonical constant: `US_BLANKED_SWG_COMPARTMENTS: frozenset[str] = frozenset({"SECONDARY COMPARTMENT", "LINK BOX"})`.
- Add `is_us_contract_awarded()`, `is_swg_compartment_us_eligible()`, `is_swg_us_active()`, and `blank_swg_us_cells()`.
- Update `apply_scan_post_processing()`:
  - Add `blank_us: bool = False` keyword argument.
  - If `blank_us` is `True`, invoke `blank_swg_us_cells(target)` before and after shading passes.
  - Strip `"US"` from defective technologies set (`def_techs`) when `blank_us` is `True` to prevent residual red shading.
  - Export all new functions in `__all__`.

### 2. PRPD Optimization (`src/quick_report/prpd.py`)
- Update `generate_prpd_graphs_for_swg_panel()`:
  - Add `include_us: bool = True` parameter.
  - Evaluate `should_gen_us = include_us and (compartment is None or is_swg_compartment_us_eligible(compartment))`.
  - When `should_gen_us` is `False`:
    - Option B: completely bypass US file decoding and figure rendering, keeping `us_png = None`.
    - Option C: set `us_dir = find_latest_measurement_dir(feeder_dir, "US") if should_gen_us else None`.

### 3. Full Report Scan Adapter (`src/full_report/scan_adapters.py`)
- In `SwitchgearScanAdapter`:
  - Evaluate `comp_us_active = is_swg_us_active(self.project_technologies, comp_name)`.
  - Pass `include_us=comp_us_active` to `_resolve_prpd()`.
  - When `comp_us_active` is `False`:
    - Blank panel US context values: `reading = ""`, `char = ""`, `severity = ""`, `prpd = ""`.
  - Inject render flags into context:
    - `"__blank_us__": not comp_us_active`
    - `"is_us_active": comp_us_active`

### 4. Full Report Scan Renderer (`src/full_report/scan_render.py`)
- In `FullReportScanPageRendererCore.render_page()`:
  - Resolve `should_blank_us = blank_us if blank_us is not None else (render_ctx.get("__blank_us__") or render_ctx.get("blank_us") or (render_ctx.get("is_us_active") is False))`.
  - Pass `blank_us=should_blank_us` to `apply_scan_post_processing()`.

### 5. Quick Report CBM Render (`src/quick_report/cbm_render.py`)
- In `_build_swg_render_context()`:
  - Extract project technologies via `_extract_project_technologies(pe_info)`.
  - Evaluate `is_us_active = is_swg_us_active(project_technologies=proj_techs, compartment=comp_target)`.
  - When inactive:
    - Blank US dictionary values: `reading = ""`, `char = ""`, `severity = ""`, `prpd = ""`.
    - Strip `"US"` from `def_techs`.
  - Inject context keys: `"__blank_us__": not is_us_active`, `"is_us_active": is_us_active`.
  - Pass `include_us=is_us_active` to `generate_prpd_graphs_for_swg_panel()`.
- In `_render_docx_template()`:
  - Resolve `should_blank_us` and pass to `apply_scan_post_processing()`.

---

## Acceptance Criteria

- [x] `is_us_contract_awarded` correctly handles `None`, `["IR", "US", "TEV"]`, `["IR", "US"]`, and `["IR"]`.
- [x] `is_swg_compartment_us_eligible` excludes `SECONDARY COMPARTMENT` and `LINK BOX`, while allowing standard compartments (`BREAKER`, `CABLE`, `PT`, `BUSBAR`, `CABLE ENTRY`, `FUSE`).
- [x] `normalize_swg_compartment` normalizes `LINK BOX`, `LINKBOX`, and `CABLE LINK BOX` without misclassifying as `CABLE COMPARTMENT`.
- [x] `blank_swg_us_cells` blanks text, removes shading, and sets borders to `nil` for rows 21–32, cols 1–8 of `swg-panel.docx`.
- [x] TEV measurement cells (cols 11–22) and IR/Visual quadrants (rows 1–20) remain untouched when blanking US.
- [x] IR-only contracts blank both US (cols 1–8) and TEV (cols 11–22) simultaneously, leaving only the IR+Visual pair.
- [x] PRPD graph generator skips US rendering and disk writes for US-excluded compartments and IR-only contracts.
- [x] Automated tests created in `tests/test_swg_us_dynamic_blanking.py` matching the rigor of `test_swg_tev_dynamic_blanking.py`.
