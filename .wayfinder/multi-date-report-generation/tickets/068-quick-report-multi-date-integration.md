<!-- status: closed -->
Part of #66
Specification: [spec.md](../spec.md)

# 068: feat(quick-report): multi-date selection & date-aware progress telemetry

**What to build:** Integrate multi-date selection into Quick Report generation. Updates `QuickReportAction.execute` to present dual-mode date selection (`Browse Date Folders` and `Enter Target Date(s)`), routes multi-date selections into `QuickReportWorkflow.inspect()` and `generate()`, and updates progress telemetry in `QuickReportWorkflow.generate` to display the inspection date tag on each compiling substation.

**Blocked by:** #67

**Status:** Closed

- [x] Update `QuickReportAction.execute` in `src/project_workflow_actions.py`:
  - Update selection mode prompt options:
    - `SelectOption("Manual FL Input", "manual")`
    - `SelectOption("Browse Date Folders (Interactive Checklist)", "browse_dates")`
    - `SelectOption("Enter Target Date(s) (Text Input / Range)", "enter_dates")`
    - `SelectOption("Cancel", "__cancel__", shortcut_key="c")`
  - Route `"browse_dates"` through `select_pahang_inspection_dates_interactive(environment)`.
  - Route `"enter_dates"` through `prompt_target_inspection_dates_with_ranges(environment)`.
  - If selection is cancelled or empty, print `"Processing cancelled."` and return `None`.
  - Pass the resolved `tuple[Path, ...]` (or sequence of date strings) to `workflow.inspect(selected_targets, environment)`.
  - Check `inspection.missing_templates` and errors fail-fast guards.
  - If `unique_stations > 1`, preserve existing multi-station checkbox prompt (`chosen_stations`).
  - Pass `selected_targets` to `workflow.generate(selected_targets, environment, station=chosen_stations, progress_sink=_cli_progress_sink)`.
  - Output batch execution summary via `_print_quick_report_batch_summary(result)`.
- [x] Update progress telemetry in `src/workflows/quick_report.py`:
  - In `QuickReportWorkflow.generate()`:
    - Resolve package date string: `pkg_date = getattr(plan.package, 'date_str', '')`
    - Update progress sink message to include date tag:
      `f"[{i}/{len(plans)}] [{pkg_date}] Generating quick report for {station_name}..."`
      (falling back to `f"[{i}/{len(plans)}] Generating quick report for {station_name}..."` if date is blank).
- [x] Add unit and workflow tests:
  - In `tests/quick_report/test_workflow.py`: verify that passing multiple date folder paths generates reports into each date's corresponding output directory, and that progress sink captures date tags.
  - In `tests/test_project_workflow_actions.py`: test `QuickReportAction.execute` with mocked selector responses for both `"browse_dates"` and `"enter_dates"`.
