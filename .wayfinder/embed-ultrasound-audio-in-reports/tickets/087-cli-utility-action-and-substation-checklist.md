<!-- status: open -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#87](https://github.com/adamlarGit/pahang-cli/issues/87)
Specification: [spec.md](../spec.md)

# 087: feat(cli): utility action menu registration & interactive multi-date substation checklist

**What to build:** CLI integration of the ultrasound audio workflow. Registers a dedicated utility action labeled `"Generate US 16-bit audio & embed sounds into PDFs"` at Position #10 in the Utility Actions menu, provides sub-menu mode selection (export WAVs, embed into PDFs, or both), and reuses `MultiDateSelectionPolicy` to present a single merged substation checklist filtered strictly to substations containing valid US+TEV surveys.

**Blocked by:** #086 (standalone audio workflow engine).

**Status:** ready-for-agent

- [ ] Implement discovery and interactive selection helpers in `src/workflows/us_audio.py`:
  - `discover_us_audio_candidate_substations(environment: ProjectEnvironment, target_dates: Sequence[Path | str]) -> list[UsAudioCandidate]`:
    - Extracts substation packages across dates using `QuickReportExtractor`.
    - Resolves raw material directory and checks for UltraTEV survey presence via `discover_ultratev_survey_dir()`.
    - Resolves deliverable PDF targets: `FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf` and `QUICK REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf`.
    - Filters list strictly to substations possessing a valid US+TEV survey folder.
  - `select_us_audio_substations_interactive(candidates: list[UsAudioCandidate]) -> list[UsAudioCandidate]`:
    - Formats checklist labels with date prefix and PDF availability tag:
      `f"[{cand.package.date_str}] {cand.package.substation_name} [PDF READY]"` if `cand.full_report_pdf or cand.quick_report_pdf` exists, else `f"[{cand.package.date_str}] {cand.package.substation_name} [NO PDF]"`.
    - Reuses `select_multiple` to present a single merged checklist.
    - Default state is all pre-checked with `'a'` key shortcut to toggle.
    - Zero-selection loops back safely without halting.
- [ ] Implement runner factory `_load_generate_us_audio_runner()` in `src/utility_actions.py`:
  - Prompts operator for mode:
    1. `"Embed ultrasound sounds into existing report PDFs (Full & Quick Report)"`
    2. `"Export converted 16-bit WAV files to RAW DATA/US+TEV/sounds/"`
    3. `"Both (Export WAV files and embed into PDFs)"`
  - Reuses `select_pahang_inspection_dates_interactive` / `prompt_target_inspection_dates_with_ranges` for multi-date selection.
  - Discovers candidates and validates mode prerequisites:
    - If Mode 1 (`embed_pdf`) is selected and zero candidates have deliverable PDFs on disk, displays an actionable notice explaining that reports must be compiled first, offering to switch to Mode 2 (`export_wav`) or return to menu.
  - Prompts substation checklist and executes `UsAudioWorkflow.run_batch()` with real-time console progress telemetry.
  - Displays summary box upon completion.
- [ ] Register action in `UTILITY_ACTIONS` list in `src/utility_actions.py`:
  - Placed at Position #10 (index 9) immediately after `"Generate US+TEV survey graphs"`.
  - Label: `"Generate US 16-bit audio & embed sounds into PDFs"`.
- [ ] Implement CLI integration unit tests in `tests/test_us_audio_cli.py`:
  - Test candidate filtering omits substations lacking US+TEV survey folders.
  - Test date-prefixed checklist formatting and `[PDF READY]` / `[NO PDF]` tags.
  - Test missing PDF notice in Mode 1 prompts user without crashing.
  - Test menu registration and runner dispatch.
