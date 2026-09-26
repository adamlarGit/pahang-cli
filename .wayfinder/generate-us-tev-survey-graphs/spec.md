# Specification: Standalone US+TEV Survey Graph Generation Utility

## Problem Statement
During automated generation of Quick Reports and Full Reports, edge cases occur where Phase-Resolved Partial Discharge (PRPD) ultrasound (US) and Transient Earth Voltage (TEV) graphs fail to generate or are omitted. Currently, operators have no mechanism within the Pahang CLI to independently generate or regenerate these graphs for specific substations without re-running entire multi-stage report pipelines.

Furthermore, field raw data analysis reveals that Vacuum Circuit Breaker (VCB) switchgear cubicles contain multiple measurement points per panel (e.g., Cable Box, Circuit Breaker, Upper Busbars). The existing preview script (`scripts/generate_prpd_option_c_html.py`) uses blind numeric suffixes (`_2`, `_3`), which strips physical engineering meaning and introduces label inversions between manifest parsing and fallback filesystem traversal.

## Solution
Introduce a dedicated, standalone utility workflow accessible directly from the CLI's Utility Actions menu:
1. **Interactive Target Selection**: Operators select target inspection date(s) using the existing `MultiDateSelectionPolicy` (interactive Station $\to$ Month $\to$ Date folder drill-down or range-aware text input), followed by an interactive multi-select checklist strictly filtered to substations possessing valid UltraTEV survey data.
2. **Deterministic Multi-Point Measurement Discovery**: A robust survey discovery engine extracts all measurement points from `survey_summary.js` (with fallback reading `measurement_metadata.js`), establishing an unambiguous naming schema:
   `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png`
3. **Dual-Mode Rendering Engine**: Reuses proven PRPD generation infrastructure from `src/quick_report/prpd.py`, adhering to workspace `PrpdConfig.mode` (`option_c` vs `option_b`) with strict pre-flight browser checking in Option C mode.
4. **Isolated Raw Material Destination**: Outputs all rendered graphs directly to:
   `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<SUBSTATION>/RAW DATA/US+TEV/graphs/`
   with idempotent overwrite behavior.
5. **Strict Scope Isolation**: Downstream Quick Report and Full Report workflows remain completely untouched; operators manually insert regenerated graphs where earlier generation failed.

## User Stories
1. **As a CLI operator**, I want an option labeled `"Generate US+TEV survey graphs"` in the Utility Actions menu, so that I can generate PRPD graphs on demand without triggering full report generation.
2. **As a CLI operator**, I want to pick target inspection dates using either interactive folder browsing (Station $\to$ Month $\to$ Date) or date range syntax, so that I can target specific inspection runs using familiar date selection patterns.
3. **As a CLI operator**, I want the substation checklist to display a single merged list of all substations across selected dates prefixed with `[{date_str}]`, showing only substations that actually have an extracted `RAW DATA/US+TEV/` survey directory, so that I do not waste time selecting substations lacking acoustic or electrical raw data.
4. **As a reliability engineer**, I want generated graph filenames to clearly indicate the tested compartment (e.g., `VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png` and `VCB_PANEL_1_CABLE_BOX_TEV.png`), so that multiple test points on VCB panels are immediately distinguishable without inspecting internal JSON files.
5. **As a system administrator**, I want the utility to halt before processing any substations with a clear, descriptive error if Option C is configured but neither Google Chrome nor Microsoft Edge is installed, so that I know exactly how to resolve the prerequisite or switch to Option B in Settings.
6. **As an operations supervisor**, I want batch execution to be resilient across substations (`SubstationIsolatedBatchResiliencePolicy`), skipping zero-measurement surveys with a warning and isolating single-station failures so the remainder of the batch completes.
7. **As a developer**, I want `scripts/generate_prpd_option_c_html.py` to share the same underlying discovery and naming engine as the CLI workflow, so that preview scripts and production utilities produce identical graph artifacts.

---

## Implementation Decisions

### Decision 1: Ubiquitous Naming Schema (`{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}`)
All discovered survey measurements will be named according to:
```
{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png
```
- **Asset & Subasset**: Normalized by removing whitespace, special characters, and leading `$`. (e.g., `VCB`, `PANEL_1`, `SWG`, `FEEDER_1`, `TX1`, `TRANSFORMER`).
- **Component**: Extracted from `$COMPONENT`. If present and not `$NONE`, sanitized (e.g., `CIRCUIT_BREAKER`, `CABLE_BOX`, `UPPER_BUSBARS`, `PRIMARY_CABLES`). If `$NONE` or absent, the component token is cleanly omitted: `{ASSET}_{SUBASSET}_{TECH}.png`.
- **Technology**: Canonical technology tag (`TEV` or `US`).
- **Standardized Tokens**:
  - `$CIRCUIT_BREAKER` $\to$ `CIRCUIT_BREAKER`
  - `$CABLE_BOX` $\to$ `CABLE_BOX`
  - `$UPPER_BUSBARS` / `$LOWER_BUSBARS` $\to$ `UPPER_BUSBARS` / `LOWER_BUSBARS`
  - `$PRIMARY_CABLES` $\to$ `PRIMARY_CABLES`
  - `$CT_CHAMBER` $\to$ `CT_CHAMBER`
- **Concrete Output Examples**:
  - `VCB_PANEL_1_CIRCUIT_BREAKER_TEV.png`
  - `VCB_PANEL_1_CABLE_BOX_TEV.png`
  - `VCB_PANEL_1_UPPER_BUSBARS_US.png`
  - `SWG_FEEDER_1_CABLE_BOX_TEV.png`
  - `TX1_TRANSFORMER_PRIMARY_CABLES_US.png`

### Decision 2: Concrete Schemas for Manifest Parsing & Deterministic Fallback

#### 2.1 Manifest Parsing (`survey_summary.js`)
Located at the root of the survey directory:
```javascript
var survey_summary = {"asset_types":[...],"assets":[...],"substation_id":0,"version":1};
```
- **Top-Level Keys**: `["asset_types", "assets", "substation_id", "version"]`
- **Parsing Strategy**: Extract using `json.JSONDecoder().raw_decode(content[content.find("{"):])`. This guarantees 100% parsing success across all surveys, avoiding crashes on rare UltraTEV software glitches that write duplicate trailer bytes after the closing bracket.
- **Hierarchy Traversal**:
  ```python
  for asset in data.get("assets", []):
      asset_name = asset.get("$ASSET_NAME", "SWG")
      for sub_asset in asset.get("$SUB_ASSETS", []):
          sub_name = sub_asset.get("$SUB_ASSET_NAME", "")
          for meas in sub_asset.get("$MEASURES", []):
              component = meas.get("$COMPONENT")
              meas_type = meas.get("$MEASURE_TYPE")  # "$TEV" or "$ULTRA"
              data_rel = meas.get("Data")            # e.g. "VCB/PANEL_1/20260917T133714_TEV"
  ```

#### 2.2 Deterministic Traversal Fallback (`measurement_metadata.js`)
If `survey_summary.js` is missing, damaged, or unparseable, directory traversal scans child directories under `SWG*`, `VCB*`, `RMU*`, `TX*`.
- Rather than guessing from folder timestamps (`20260917T133500_TEV`), the fallback reads the ~1KB `measurement_metadata.js` file inside the measurement directory:
  ```javascript
  var measurement_metadata = {"Trend":[...],"measurement_fields":[...]};
  ```
- Extracts `$ASSET_NAME`, `$PANEL_NO`, `$SUB_ASSET_NAME`, `$COMPONENT`, and `$SUB_LOC` directly from `measurement_fields[0]["fields"]` matching `fieldname`. Note: keys literally start with `$` (e.g. `{"fieldname": "$COMPONENT", "data": "$CABLE_BOX"}`).

### Decision 3: Option C Headless Browser Rendering Infrastructure
Option C reuses existing infrastructure in `src/quick_report/prpd.py`:
1. **Pre-flight Browser Check**: Calls `find_chrome_executable()` (`src/quick_report/prpd.py:115-153`). If neither `chrome.exe` nor `msedge.exe` is found, raises `BrowserPrerequisiteError` immediately before processing any substations.
2. **Local HTTP Server**: Runs `SurveyHttpServer` (`src/quick_report/prpd.py:257-348`) on a dynamic free port using `ThreadedTCPServer`.
3. **Template & Capture**: Calls `render_prpd_option_c_image()` (`src/quick_report/prpd.py:351-448`) which injects `OPTION_C_INJECTION_TEMPLATE` (setting Flexbox 1200x380 px, 320px table + 840px Flot graph) and invokes Chromium CLI with `--headless=new --window-size=1200,380`.
4. **Validation**: Validates image via `is_blank_or_invalid_image()` (`src/quick_report/prpd.py:172-255`) with up to 2 retries on blank output.

### Decision 4: Option B Matplotlib Rendering Infrastructure
Option B reuses existing native Python decoders in `src/quick_report/prpd.py`:
1. **TEV Decoding**: Calls `decode_tev_event_data(filepath)` (`src/quick_report/prpd.py:452-501`), extracting base64 gzip FlatBuffers payload with identifier `"UE01"` and unpacking 24-byte struct `<fiHHHHff` without requiring external libraries.
2. **Ultrasonic Decoding**: Calls `decode_ultrasonic_phase_plot(filepath)` (`src/quick_report/prpd.py:504-539`), parsing acoustic events and rounding amplitude to nearest 1/3 dB.
3. **Figure Plotting**: Calls `generate_prpd_figure(events, tech_type, output_path)` (`src/quick_report/prpd.py:542-669`), generating 4-tier repetition density Matplotlib scatter plots (Green `#00FF00`, Blue `#0000FF`, Red `#FF0000`, Dark Red `#640000`).

### Decision 5: Substation Discovery & Interactive Multi-Date Checklist
- Reuses `select_pahang_inspection_dates_interactive(environment)` (Station $\to$ Month $\to$ Date multi-select) or `prompt_target_inspection_dates_with_ranges(environment)`.
- Discovers testsheet packages across all target dates via `QuickReportExtractor.extract(environment, folders=dates)`.
- For each package, resolves `raw_dir = environment.storage.get_substation_raw_data_dir(...)`.
- Validates UltraTEV presence using `discover_ultratev_survey_dir(raw_dir)` (`src/quick_report/prpd.py:688-729`).
- **Strict Filtering**: Omits substations lacking an extracted `US+TEV` survey folder. If zero eligible substations are found, displays an alert and returns cleanly.
- **Single Merged Checklist**: Merges all eligible substations across all dates into a single interactive checklist. Each item is prefixed with its inspection date tag: `f"[{pkg.date_str}] {pkg.substation_name}"`. Pre-checked by default, with `'a'` shortcut to toggle all.

### Decision 6: Output Destination & Overwrite Policy
- Output directory is strictly created at:
  ```text
  RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<SUBSTATION>/RAW DATA/US+TEV/graphs/
  ```
- Keeps generated PNGs isolated alongside raw instrument directories without polluting vendor assets (`survey_summary.js`, `resources/`).
- Idempotent generation: existing `.png` files in `graphs/` are overwritten automatically.

### Decision 7: Batch Error Resilience (`SubstationIsolatedBatchResiliencePolicy`)
- **Zero-Measurement Surveys**: If an extracted survey folder contains zero valid US or TEV measurements, logs a non-blocking console warning (`[WARN] No valid US/TEV measurements found in survey <dir>`), counts 0 graphs generated for that station, and continues.
- **Substation Error Isolation**: If graph generation encounters an unexpected error on a specific substation (e.g. corrupted file, single-panel render timeout), the error is caught, recorded in `UsTevGraphResult.errors`, and execution continues with the remaining selected substations.
- **Consolidated Summary**: At batch completion, the utility displays a summary showing total substations processed, total graphs generated, elapsed execution time, and any error details.

### Decision 8: Scope Containment & Downstream Isolation (Known Limitation)
- **Known Limitation**: Generated graphs are saved to `RAW DATA/US+TEV/graphs/` for archiving, verification, and manual report insertion. Quick Report and Full Report pipelines render PRPD graphs on demand into temporary directories (`prpd_temp` or `.temp/full_report/.../prpd`) and do **not** automatically ingest pre-rendered graphs from `RAW DATA/US+TEV/graphs/`.
- Quick Report and Full Report code paths, adapters, and docx templates remain completely untouched to avoid regression risk.

### Decision 9: CLI Menu Placement
- Registered at **Position #9 (index 8)** in `UTILITY_ACTIONS` (`src/utility_actions.py`), immediately following `"Rename FLIR raw files numbering"`. This groups all raw inspection sensor tools (thermal FLIR and acoustic/electrical UltraTEV) together logically.

---

## Testing Decisions
1. **Survey Discovery & Naming Unit Tests (`tests/test_us_tev_discovery.py`)**:
   - Test manifest parsing against synthetic VCB survey fixtures (verifying `CIRCUIT_BREAKER`, `CABLE_BOX`, `UPPER_BUSBARS` tokens).
   - Test single-point RMU/SWG survey fixtures.
   - Test Transformer measurements (`TX1_TRANSFORMER_PRIMARY_CABLES_US`).
   - Test fallback traversal when `survey_summary.js` is absent, verifying identical label generation by reading `measurement_metadata.js`.
   - Test resilience against corrupted trailer bytes using `raw_decode`.
2. **Workflow Engine & Browser Verification Tests (`tests/test_us_tev_graph_workflow.py`)**:
   - Test `BrowserPrerequisiteError` raised when Option C is selected and browser is mocked as missing.
   - Test Option B graph generation decodes events and writes PNGs with `{asset}_{subasset}_{component}_{tech}.png` names using synthetic FlatBuffers / JSON fixtures from `tests/test_prpd_generator.py`.
   - Test Option C headless rendering pipeline with mocked survey server.
   - Test output directory resolution and overwrite idempotency.
   - Test zero-measurement survey handling and error isolation across a multi-station batch.
3. **CLI Discovery & Checklist Integration Tests (`tests/test_us_tev_cli.py`)**:
   - Test candidate filtering (substations with US+TEV vs without).
   - Test single merged checklist formatting with `[{date_str}]` prefix.
   - Test zero-candidate loop-back behavior.

---

## Out-of-Scope Boundaries
- **Automatic Report Ingestion**: Quick Report and Full Report will not automatically read from `RAW DATA/US+TEV/graphs/` during this iteration.
- **Modifying Docx Templates**: No Word template modifications or scan adapter changes.
- **Unsorted Raw Data Ingestion**: The utility operates strictly on extracted raw materials in `RAW MATERIAL/`, not on raw `.zip` files in `TESTSHEET/.../UNSORTED RAW DATA/`.
