<!-- status: open -->
Part of #71
Specification: [spec.md](../spec.md)

# 072: feat(prpd): survey measurement discovery with multi-point component naming

**What to build:** Core survey auto-discovery engine that identifies all ultrasound and TEV measurement targets across UltraTEV survey folders, supporting Vacuum Circuit Breaker (VCB) multi-point cubicles without label collisions. Establishes the canonical `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}` naming schema across manifest-based parsing (`survey_summary.js`) using `raw_decode` and deterministic filesystem traversal fallback reading `measurement_metadata.js`.

**Blocked by:** None (can start immediately).

**Status:** Open

- [ ] Implement `DiscoveredMeasurement` domain model in `src/quick_report/prpd.py` (or shared discovery module):
  - Fields: `label` (str), `asset` (str), `subasset` (str), `component` (str | None), `sub_loc` (str | None), `tech` ("TEV" | "US"), `html_file` (str), `data_rel_path` (str), `meas_dir` (Path).
- [ ] Implement canonical label formatter `format_measurement_label(asset, subasset, component, tech)`:
  - Strips leading `$` and sanitizes tokens.
  - Formats as `{clean_asset}_{clean_subasset}_{clean_component}_{tech}` when component is present and not `$NONE`.
  - Formats as `{clean_asset}_{clean_subasset}_{tech}` when component is missing or `$NONE`.
  - Normalizes common components: `$CIRCUIT_BREAKER` $\to$ `CIRCUIT_BREAKER`, `$CABLE_BOX` $\to$ `CABLE_BOX`, `$UPPER_BUSBARS` $\to$ `UPPER_BUSBARS`, `$PRIMARY_CABLES` $\to$ `PRIMARY_CABLES`.
- [ ] Implement `discover_survey_measurements(survey_root: Path) -> list[DiscoveredMeasurement]`:
  - **Tier 1 (Manifest-driven)**: Reads `survey_summary.js` (`var survey_summary = {...};`). Parses using `json.JSONDecoder().raw_decode(content[content.find("{"):])` to prevent syntax crashes from software glitches that append duplicate trailer bytes.
  - Traverses `assets` $\to$ `$SUB_ASSETS` $\to$ `$MEASURES`:
    - Checks `$MEASURE_TYPE` for `"$TEV"` (target: `TEV.html`) or `"$ULTRA"` (target: `Ultrasonic.html`).
    - Extracts `$COMPONENT`, `$SUB_LOC`, and `Data` relative path.
    - Resolves absolute measurement directory: `survey_root / data_rel_path`.
  - If survey folder contains zero valid measurements, returns an empty list without raising an exception.
  - **Tier 2 (Deterministic Traversal Fallback)**: If `survey_summary.js` is missing or unparseable, scans subdirectories matching `SWG*`, `VCB*`, `RMU*`, `TX*`.
  - In fallback mode, inspects child measurement directories containing `TEV.html` or `Ultrasonic.html` and reads `measurement_metadata.js` (`var measurement_metadata = {"Trend": [...], "measurement_fields": [...]};`).
  - Extracts fields directly from `measurement_fields[0]["fields"]` matching literal fieldnames: `"$ASSET_NAME"`, `"$PANEL_NO"`, `"$SUB_ASSET_NAME"`, `"$COMPONENT"`, and `"$SUB_LOC"` without guessing from timestamped folder names.
- [ ] Implement deduplication safety:
  - In the rare event that two measurements on the same physical component share identical labels, appends an incrementing counter (`_2`, `_3`) while logging a warning.
- [ ] Add unit test suite in `tests/test_us_tev_discovery.py` using synthetic fixtures:
  - Build synthetic survey tree in `tmp_path` using patterns from `tests/test_prpd_generator.py`.
  - Test multi-point VCB survey with 5 measurements per panel (verifying `VCB_PANEL_1_CIRCUIT_BREAKER_TEV`, `VCB_PANEL_1_CABLE_BOX_TEV`, `VCB_PANEL_1_UPPER_BUSBARS_US`).
  - Test single-point RMU/SWG survey where each feeder has 1 TEV and 1 US point.
  - Test Transformer measurements (`TX1_TRANSFORMER_PRIMARY_CABLES_US` or `TX1_TRANSFORMER_US`).
  - Test fallback traversal when `survey_summary.js` is absent, verifying identical label generation by reading `measurement_metadata.js`.
  - Test resilient parsing against trailing corrupted bytes in `survey_summary.js`.
  - Test zero-measurement survey returns empty list without crashing.
