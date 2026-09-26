<!-- status: closed -->
Part of #71
Specification: [spec.md](../spec.md)

# 073: feat(workflow): US+TEV graph generation workflow and dual-mode rendering engine

**What to build:** The core workflow engine (`src/workflows/us_tev_graphs.py`) that coordinates Phase-Resolved Partial Discharge (PRPD) graph generation across discovered measurements for selected substations. Reuses existing PRPD rendering infrastructure from `src/quick_report/prpd.py`, supports both Option C (composite HTML table + Flot scatter plot via headless Chrome/Edge) and Option B (pure Matplotlib scatter plot decoding FlatBuffers/JSON), strictly enforces Chromium pre-flight presence in Option C mode, and saves outputs to `<SUBSTATION>/RAW DATA/US+TEV/graphs/` with idempotent overwrite and batch error isolation (`SubstationIsolatedBatchResiliencePolicy`).

**Blocked by:** #72

**Status:** Closed

- [x] Implement `BrowserPrerequisiteError(RuntimeError)` domain exception:
  - Raised when `PrpdConfig.mode == "option_c"` and `find_chrome_executable()` returns `None`.
  - Message explicitly guides operator to install Chrome/Edge or change PRPD mode to Option B in Settings.
- [x] Implement `UsTevGraphWorkflow` in `src/workflows/us_tev_graphs.py`:
  - `generate_substation_graphs(survey_root: Path, output_dir: Path, mode: str) -> list[Path]`:
    - Creates `output_dir = substation_raw_dir / "US+TEV" / "graphs"`.
    - Invokes `discover_survey_measurements(survey_root)` from Ticket #72.
    - If measurement list is empty, logs non-blocking warning: `[WARN] No valid US/TEV measurements found in survey <dir>`, and returns `[]`.
    - If `mode == "option_c"`:
      - Uses `SurveyHttpServer(survey_root, temp_dir=output_dir)` (`src/quick_report/prpd.py:257`) as context manager on a dynamic free port.
      - Iterates through discovered measurements.
      - Calls `render_prpd_option_c_image()` (`src/quick_report/prpd.py:351`) targeting `<output_dir>/<label>.png`.
      - Overwrites existing image files unconditionally.
    - If `mode == "option_b"`:
      - Iterates through discovered measurements.
      - For TEV: calls `decode_tev_event_data(meas.meas_dir / "eventData.js")` (`src/quick_report/prpd.py:452`).
      - For US: calls `decode_ultrasonic_phase_plot(meas.meas_dir / "ultrasonic_phase_plot.js")` (`src/quick_report/prpd.py:504`).
      - Generates Matplotlib PRPD figure via `generate_prpd_figure(events, tech_type, output_path)` (`src/quick_report/prpd.py:542`) targeting `<output_dir>/<label>.png`.
      - Overwrites existing image files unconditionally.
- [x] Implement batch substation processor adhering to `SubstationIsolatedBatchResiliencePolicy`:
  - Pre-flight browser check: if `mode == "option_c"`, invokes `find_chrome_executable()`. If missing, raises `BrowserPrerequisiteError` immediately before processing any substations.
  - Loops over selected substations:
    - Resolves `survey_root` via `discover_ultratev_survey_dir()`.
    - Runs `generate_substation_graphs()`.
    - Catches unexpected per-substation exceptions, records failure in `errors: list[str]`, and continues remaining substations.
  - Returns `UsTevWorkflowSummary` dataclass tracking total substations, total graphs generated, errors, and elapsed time.
- [x] Add unit and workflow tests in `tests/test_us_tev_graph_workflow.py`:
  - Test `BrowserPrerequisiteError` raised when Option C is selected and browser is mocked as missing.
  - Test Option B graph generation decodes events and writes PNGs with `{asset}_{subasset}_{component}_{tech}.png` names using synthetic FlatBuffers (`_build_synthetic_tev_flatbuffers()`) and JSON acoustic events.
  - Test Option C headless rendering pipeline with mocked `render_prpd_option_c_image`.
  - Test output directory resolution and overwrite idempotency.
  - Test zero-measurement survey handling and batch error isolation across multiple substations.
