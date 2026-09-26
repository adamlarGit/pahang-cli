# 6. Standalone US+TEV Survey Graph Generation Workflow

Date: 2026-09-26
Status: Accepted

## Context

During field condition-based maintenance inspections, Phase-Resolved Partial Discharge (PRPD) graphs (Ultrasound and Transient Earth Voltage) are acquired using EA Technology UltraTEV Plus2 survey instruments. Occasionally, due to edge-case instrument anomalies, software glitch trailer bytes, or rendering timeouts, specific PRPD graphs are omitted or require regeneration. Previously, operators had no mechanism to independently generate or regenerate these survey graphs without re-running entire multi-stage Quick Report or Full Report pipelines.

Furthermore, field inspection data revealed that Vacuum Circuit Breaker (`VCB_CUBICLE`) switchgear cubicles contain multiple measurement points per panel (e.g. Cable Box, Circuit Breaker, Upper Busbars, Lower Busbars, CT Chamber). The existing preview scripts utilized blind numeric suffixes (`_2`, `_3`), which stripped physical engineering context and introduced label discrepancies between manifest parsing and filesystem traversal.

## Decision

The system introduces a dedicated standalone CLI utility action and workflow engine for US+TEV PRPD survey graph generation:

### 1. Menu Placement & Zero-Arg Runner Architecture
- Registered at **Position #9 (index 8)** in `UTILITY_ACTIONS` (`src/utility_actions.py`), placed immediately after `"Rename FLIR raw files numbering"` to group sensor diagnostic utilities together.
- Follows the zero-argument callable returning a zero-argument runner contract: `_load_generate_us_tev_graphs_runner()` wrapping `get_or_create_utility_environment()`.

### 2. Multi-Date Drilldown & Substation Filtering
- Reuses `MultiDateSelectionPolicy` (`select_pahang_inspection_dates_interactive` or `prompt_target_inspection_dates_with_ranges`).
- Discovers testsheet packages across all selected dates via `QuickReportExtractor.extract()`.
- Strictly filters candidates using `discover_ultratev_survey_dir()` to only substations containing an extracted `RAW DATA/US+TEV/` directory.
- Presents a single merged interactive checklist with date disambiguation prefixes: `f"[{pkg.date_str}] {pe_name}"`.

### 3. Canonical Ubiquitous Naming Schema (`SurveyMeasurementNaming`)
- Standardizes all measurement outputs to:
  `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png`
- Strips leading `$` and normalizes tokens (e.g., `VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png`, `VCB_PANEL_1_CABLE_BOX_TEV.png`, `VCB_PANEL_1_UPPER_BUSBARS_US.png`).
- When `$COMPONENT` is absent or `$NONE`, cleanly omits the component token: `{ASSET}_{SUBASSET}_{TECH}.png`.
- Deduplication safety: in the rare event of identical components, appends an incrementing suffix (`_2`, `_3`) while logging a warning.

### 4. Two-Tier Discovery Engine
- **Tier 1 (Manifest-driven)**: Reads `survey_summary.js` using `json.JSONDecoder().raw_decode()`, ensuring complete immunity to corrupted duplicate trailer bytes.
- **Tier 2 (Deterministic Traversal Fallback)**: If `survey_summary.js` is absent or damaged, traverses `SWG*`, `VCB*`, `RMU*`, `TX*` and reads `measurement_metadata.js` inside each measurement folder, extracting literal fieldnames (`$ASSET_NAME`, `$PANEL_NO`, `$COMPONENT`, `$SUB_LOC`) without guessing from folder timestamps.

### 5. Dual-Mode Rendering & Browser Pre-flight Check (`BrowserPrerequisitePolicy`)
- Respects active workspace `PrpdConfig.mode` (`option_c` vs `option_b`).
- In Option C, executes a strict pre-flight check for Google Chrome / Microsoft Edge before processing any substations, raising `BrowserPrerequisiteError` immediately if missing.
- Reuses `SurveyHttpServer` and `render_prpd_option_c_image()` for Option C composite graphs, and `decode_tev_event_data()` / `decode_ultrasonic_phase_plot()` / `generate_prpd_figure()` for Option B Matplotlib plots.

### 6. Isolated Output Destination & Overwrite Policy (`UsTevGraphOutputDirectory`)
- All generated graphs are saved directly to:
  `<SUBSTATION_FOLDER>/RAW DATA/US+TEV/graphs/`
- Overwrites existing image files idempotently without modifying vendor raw files.

### 7. Substation-Isolated Batch Resilience (`SubstationIsolatedBatchResiliencePolicy`)
- Zero-measurement surveys are skipped with a non-blocking warning.
- Errors on individual substations are caught and logged, allowing remaining substations in the batch to complete. Consolidated execution summary is displayed at batch conclusion.

## Consequences

### Positive
- **Independent Diagnostic Capability**: Operators can regenerate missing PRPD graphs in seconds without running full document compilers.
- **Unambiguous Multi-Point VCB Naming**: Eliminates blind `_2` suffixes and preserves engineering compartment semantics.
- **Strict Scope Isolation**: Downstream Quick Report and Full Report pipelines, Word templates, and scan adapters remain 100% untouched, introducing zero regression risk.
- **Tooling Parity**: Developer preview script (`scripts/generate_prpd_option_c_html.py`) shares the exact discovery and naming engine.

### Negative and Known Limitations
- Generated graphs stored in `RAW DATA/US+TEV/graphs/` are not automatically ingested by existing Quick Report or Full Report pipelines. Operators manually insert regenerated graphs into Word documents where earlier automated insertion failed.
