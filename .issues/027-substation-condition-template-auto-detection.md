# Substation Condition Template Auto-Detection Rules

Labels: wayfinder:research
Assignee: antigravity
Status: Closed
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md)

## Question

How can the Quick Report generator automatically infer and match the appropriate Substation Condition template from `templates/QUICK REPORT/SUBSTATION CONFIGURATION/` based on testsheet equipment count and layout metadata (transformer count, switchgear type, battery bank), with interactive CLI fallback?

## Resolution

The Substation Condition Page generation engine is specified as a **Single-Page 3-Pair Template Chunking Engine (Approach B)** using `MASTER_SUBSTATION_CONDITION_PAGE.docx` (`docxtpl` + `docxcompose`):

1. **Full Equipment Naming & Labeling Rules**:
   - `SWG` $\rightarrow$ Expanded in full as `SWITCHGEAR` (e.g. `SWITCHGEAR 1`, `SWITCHGEAR 1 NAMEPLATE`).
   - `TX` $\rightarrow$ Expanded in full as `TRANSFORMER` (e.g. `TRANSFORMER 1`, `TRANSFORMER 1 NAMEPLATE`).
   - `FP` $\rightarrow$ Uses dynamic `fp.labelsource` (e.g. `FEEDER PILLAR TX1`, `LVDB`, `FP (D)`).
   - **Switchgear Labeling Seam**: `_resolve_switchgear_label` seam created with clear `TODO` stub for site letter labels (`A`, `B`, `C`), defaulting to numerical indexing (`1`, `2`, `3`) for now.

2. **Styling & Border Rules**:
   - **NO shaded background fills** (`fill="auto"` / clear white).
   - **Active Slots**: Clean solid black cell borders (`w:val="single"`, `w:color="000000"`).
   - **Absent / Unused Slots**: Nil borders (`w:val="nil"`), text cleared via `_remove_empty_cell_borders_sub_cond()` on final page chunk.

3. **Canonical 2-Column Pair (Left, Right) Row Sequence**:
   - **Pair 1**: `(SUBSTATION OVERVIEW, SIGNBOARD)`
   - **Pair 2+**: `(SWITCHGEAR [N], SWITCHGEAR [N] NAMEPLATE)`
   - **Pair 3+**: `(TRANSFORMER [N], TRANSFORMER [N] NAMEPLATE)`
   - **Pair 4+**: `(FEEDER PILLAR [N], FEEDER PILLAR [N] NAMEPLATE)` via `fp.labelsource`
   - **Pair 5+**: `(BATTERY CHARGER [N], BATTERY CHARGER [N] NAMEPLATE)`
   - **Pair 6**: `(RTU, RTU NAMEPLATE)` activated when `swg_type == 'MRMU'`
   - **Pair 7**: `(EFI, SF6 GAS INDICATOR)` or `(SF6 GAS INDICATOR 1, SF6 GAS INDICATOR 2)` when `swg_type in {'SF6', 'MRMU'}`
   - **Pair 8**: `(FIRE EXTINGUISHER [LOCATION], FIRE EXTINGUISHER EXPIRY DATE)`
   - **Pair 9+**: `(TRANSFORMER [N] OIL LEVEL INDICATOR, TRANSFORMER [N+1] OIL LEVEL INDICATOR)`

4. **Dynamic Page Chunking Engine (`generate_substation_condition_pages`)**:
   - Assembles active 2-column pairs for target substation.
   - Chunks active pairs into single-page sub-documents of max 3 pairs per page using `MASTER_SUBSTATION_CONDITION_PAGE.docx` (with header `"SUBSTATION CONDITION"`).
   - Applies `_remove_empty_cell_borders_sub_cond()` on final page chunk if `< 3` pairs.
   - Compiles sub-documents via `_append_document_body(start_on_new_page=True)` / `docxcompose`.


