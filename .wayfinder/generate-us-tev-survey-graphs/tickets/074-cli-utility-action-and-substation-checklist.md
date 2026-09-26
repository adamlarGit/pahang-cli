<!-- status: closed -->
Part of #71
Specification: [spec.md](../spec.md)

# 074: feat(cli): utility action menu registration and US+TEV substation checklist

**What to build:** The CLI utility action integration that exposes `"Generate US+TEV survey graphs"` at position #9 within the Utilities menu (`src/utility_actions.py`). Reuses `MultiDateSelectionPolicy` for date selection (interactive Station $\to$ Month $\to$ Date folder drill-down or range text input), discovers substations using `QuickReportExtractor` and `WorkspaceStorage`, strictly filters a single merged interactive checklist to substations possessing valid UltraTEV survey directories, and executes `UsTevGraphWorkflow` with batch progress logging. Implements the standard zero-argument runner factory pattern wrapping `get_or_create_utility_environment()`.

**Blocked by:** #73

**Status:** Closed

- [x] Implement `discover_us_tev_candidate_substations(environment, target_dates) -> list[tuple[SubstationTestsheetPackage, Path, Path]]`:
  - Uses `QuickReportExtractor.extract(environment, folders=target_dates)` to discover testsheet packages across all target dates.
  - Resolves each substation's raw data path via `environment.storage.get_substation_raw_data_dir(station, month, date_str, substation_number)`.
  - Validates survey presence using `discover_ultratev_survey_dir(raw_dir)`.
  - Strictly returns only packages that have an existing, valid survey directory.
- [x] Implement single merged interactive substation checklist selector `select_us_tev_substations_interactive(candidates)`:
  - Merges candidates across all selected dates into a single checklist.
  - Formats options with inspection date and substation identifiers: `f"[{pkg.date_str}] {pkg.substation_name or pkg.substation_folder}"`.
  - Pre-checks all eligible candidates by default.
  - Supports keyboard shortcuts: `'a'` / `'all'` to toggle all, `<space>` to toggle individual, `<enter>` to confirm.
  - Implements loop-back resilience: if cancelled or 0 items selected, returns empty list to allow caller to gracefully loop back or exit.
- [x] Implement runner factory `_load_generate_us_tev_graphs_runner()` in `src/utility_actions.py`:
  - Follows the zero-argument callable returning a zero-argument runner contract: `Callable[[], Callable[[], object]]`.
  - Inner runner fetches environment internally via `get_or_create_utility_environment()`.
  ```python
  def _load_generate_us_tev_graphs_runner() -> Callable[[], object]:
      """Lazy loader for US+TEV survey graph generation utility action."""
      def _run() -> object:
          from src.project.environment import get_or_create_utility_environment
          from src.workflows.us_tev_graphs import run_generate_us_tev_graphs_action

          env = get_or_create_utility_environment()
          return run_generate_us_tev_graphs_action(env)

      return _run
  ```
- [x] Implement `run_generate_us_tev_graphs_action(environment: ProjectEnvironment)`:
  - Prompts operator for date selection mode: "Browse Date Folders (Interactive Checklist)" vs "Enter Target Date(s) (Text Input / Range)".
  - Invokes `select_pahang_inspection_dates_interactive(environment)` (Station $\to$ Month $\to$ Date) or `prompt_target_inspection_dates_with_ranges(environment)`.
  - Discovers candidate substations; if none found, prints an informative warning and returns cleanly.
  - Prompts single merged interactive checklist selection.
  - Resolves `mode = environment.get_prpd_config().mode`.
  - Catches `BrowserPrerequisiteError` gracefully, displaying clear guidance to the operator without unhandled crash tracebacks.
  - Runs `UsTevGraphWorkflow` with per-substation console progress output:
    `f"[{idx}/{total}] [{date}] {pe_name}: Generated {count} graphs -> {output_dir}"`.
  - Displays consolidated batch summary and elapsed timer on completion.
- [x] Register new action at **Position #9 (index 8)** in `UTILITY_ACTIONS` tuple in `src/utility_actions.py`:
  ```python
  # Inserted immediately following "Rename FLIR raw files numbering"
  UtilityAction("Generate US+TEV survey graphs", _load_generate_us_tev_graphs_runner),
  ```
- [x] Add CLI integration unit tests in `tests/test_us_tev_cli.py`:
  - Test `_load_generate_us_tev_graphs_runner` conforms to `Callable[[], Callable[[], object]]` factory signature.
  - Test `discover_us_tev_candidate_substations` correctly filters out substations missing `RAW DATA/US+TEV/`.
  - Test menu action execution with mocked date and substation selections.
  - Test error handling when browser is missing in Option C mode.
  - Test menu ordering and registration at position 9 in `UTILITY_ACTIONS`.
