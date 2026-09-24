<!-- status: closed -->
Part of #66
Specification: [spec.md](../spec.md)

# 069: feat(full-report): multi-date selection with date-prefixed substation checklist

**What to build:** Integrate multi-date selection into Full Report generation. Updates `generate_full_reports_action` in `src/project_workflow_actions.py` to present dual-mode date selection (`Browse Date Folders` and `Enter Target Date(s)`), updates `select_substations_interactive` to prefix each discovered substation item with its date, and updates progress telemetry in `FullReportWorkflow.generate` to display the inspection date tag on each compiling substation.

**Blocked by:** #67

**Status:** Closed

- [x] Update `generate_full_reports_action` in `src/project_workflow_actions.py`:
  - When `target is None`, present updated selection options:
    - `SelectOption("Manual FL Input", "manual")`
    - `SelectOption("Browse Date Folders (Interactive Checklist)", "browse_dates")`
    - `SelectOption("Enter Target Date(s) (Text Input / Range)", "enter_dates")`
    - `SelectOption("Cancel", "__cancel__", shortcut_key="c")`
  - Route `"browse_dates"` through `select_pahang_inspection_dates_interactive(environment)`.
  - Route `"enter_dates"` through `prompt_target_inspection_dates_with_ranges(environment)`.
  - If selection is cancelled or empty, print `"Processing cancelled."` and return `None`.
  - Pass the resolved multi-date target to `active_workflow.inspect(selected_target, environment, progress_sink=_cli_progress_sink)`.
  - In `select_substations_interactive()` call:
    - Update `get_title`:
      ```python
      def _format_substation_title(item: Any) -> str:
          st_name = getattr(item, "substation_name", str(item))
          ready_str = "READY" if getattr(item, "is_ready", True) else "NOT READY"
          date_tag = getattr(item, "date_str", "")
          prefix = f"[{date_tag}] " if date_tag else ""
          return f"{prefix}{st_name} [{ready_str}]"
      ```
    - Pass `get_title=_format_substation_title` to interactive selector.
  - Pass `selected_target` and chosen substations to `active_workflow.generate(selected_target, environment, station=chosen_station_names, progress_sink=_cli_progress_sink)`.
- [x] Update progress telemetry in `src/workflows/full_report.py`:
  - In `FullReportWorkflow.generate()`:
    - Resolve package date string: `pkg_date = getattr(pkg, 'date_str', '')`
    - Update progress sink message to include date tag:
      `f"[{pkg_idx + 1}/{len(packages)}] [{pkg_date}] Generating Full Report for {st_name}..."`
      (falling back to `f"[{pkg_idx + 1}/{len(packages)}] Generating Full Report for {st_name}..."` if date is blank).
- [x] Add unit and workflow tests:
  - In `tests/test_full_report_workflow.py`: test `FullReportWorkflow.generate()` with sequence of date folder targets, verifying that files land in their respective date output folders and progress sink formats date tags.
  - In `tests/test_project_workflow_actions.py`: test `generate_full_reports_action` with mocked multi-date selectors and verify that substation checklist items contain date prefixes.
