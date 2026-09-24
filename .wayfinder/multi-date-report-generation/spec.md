# Specification: Multi-Date Report Generation for Quick Report and Full Report

## Problem Statement

Currently, when generating Quick Reports or Full Reports via the Pahang CLI (`QuickReportAction` and `generate_full_reports_action`), operators choose between two selection modes:
1. **Manual FL Input**: Comma-separated functional location strings.
2. **Select Testsheet Folder**: Navigates the directory tree (`TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/`) to select a single inspection date folder.

In operational reality, site inspection runs often span consecutive days (e.g., 2 to 5 days per week). Under the current single-folder selection model, operators who want to generate reports for an entire week or month of inspections are forced to re-launch the workflow repeatedly for every individual date folder. This repetitive manual interaction is tedious, error-prone, and inefficient because Microsoft Word COM automation must be repeatedly initialized and torn down for each separate date run rather than processing multiple dates within an optimized batch.

Furthermore, operators frequently know the dates they inspected (e.g. `01-05-2026` to `04-05-2026`) and want to specify them directly as a date range or comma-separated list without drilling down through the interactive folder tree every time.

## Solution

Extend date selection across both **Quick Report** and **Full Report** generation workflows to support multi-date selection through two complementary interaction modes, unified under a shared domain policy (`MultiDateSelectionPolicy`):

1. **Dual-Mode Entry Selection**:
   Update the selection menu across `QuickReportAction` and `generate_full_reports_action` to:
   - `Manual FL Input` (preserved as-is)
   - `Browse Date Folders (Interactive Checklist)`: Drill down Station $\to$ Month $\to$ multi-select checkbox list of daily inspection date folders.
   - `Enter Target Date(s) (Text Input / Range)`: Direct keyboard entry supporting single dates, comma-separated lists, and continuous date ranges.
   - `Cancel`: Return to main menu.

2. **Interactive Date Checklist (`select_pahang_inspection_dates_interactive`)**:
   - Operator selects Station, then Month.
   - The CLI displays all available `DD-MM-YYYY` inspection date folders in that month as an interactive checkbox list.
   - **Default State**: All date checkboxes are **unchecked by default** (`[ ]`).
   - **Keyboard Navigation**: `<space>` to select individual items, `'a'` to toggle all (select/deselect all), `<enter>` to confirm.
   - **Resilience**: If the operator cancels or submits 0 items, the CLI gracefully loops back to the Month/Station selection step rather than aborting the workflow.

3. **Text & Range Input with Tolerant Validation (`prompt_target_inspection_dates_with_ranges`)**:
   - Displays clear on-screen formatting tips and examples before the prompt.
   - Supports syntax:
     - Single date: `01-05-2026`
     - Comma-separated: `01-05-2026, 02-05-2026, 05-05-2026`
     - Date range: `01-05-2026..05-05-2026` or `01-05-2026 to 05-05-2026`
     - Mixed: `01-05-2026..03-05-2026, 08-05-2026`
   - Automatically expands ranges and queries `TESTSHEET/` for matching inspection date folders.
   - **Tolerant Confirmation**: If some entered dates exist and some do not, displays a breakdown of found vs. missing dates and prompts: `"Proceed with the X found dates? [Y/n]"`. If 0 dates match, alerts the operator and prompts to re-enter.

4. **Telemetry and Substation Review**:
   - **Quick Report**: Executes automated batch generation across all discovered packages for the chosen dates. Progress messages display the date tag: `[1/15] [01-05-2026] Generating quick report for 001. PMU BENTONG...`.
   - **Full Report**: Retains the pre-flight inspection checklist with each substation prefixed by its date: `[01-05-2026] 001. PMU BENTONG [READY]`. Progress messages display the date tag: `[1/15] [01-05-2026] Generating Full Report for 001. PMU BENTONG...`.
   - **Resilience**: Operates under `SubstationIsolatedBatchResiliencePolicy`, compiling packages across all selected dates in a single shared COM session while isolating failures to individual substations.
   - **Output Isolation**: Reports are strictly routed to their canonical daily output folders:
     - `QUICK REPORT/<STATION>/<MONTH>/<DD-MM-YYYY>/<STEM>.docx`
     - `FULL REPORT/<STATION>/<MONTH>/<DD-MM-YYYY>/<STEM>.docx`

## User Stories

1. As a CLI operator, I want to select multiple inspection dates from a month folder using checkboxes, so that I can generate reports for several inspection days in a single command.
2. As a CLI operator, I want all dates in the interactive checklist to be unchecked by default, so that I can specifically pick only the dates I want without unchecking the rest.
3. As a CLI operator, I want a shortcut/toggle (`'a'`) to select all or deselect all dates in the checklist, so that I can run a full month of reports with a single keystroke.
4. As a CLI operator, I want the system to safely return to the month/station selector if I cancel or submit 0 dates, so that an accidental keypress does not exit the workflow.
5. As a CLI operator, I want to type target dates or date ranges (such as `01-05-2026..05-05-2026`), so that I can skip folder browsing entirely when I already know my inspection dates.
6. As a CLI operator entering dates via text, I want visual guidance and examples displayed above the prompt, so that I immediately understand all supported date and range formats.
7. As a CLI operator entering dates via text, I want tolerant confirmation when some dates are missing from `TESTSHEET/`, so that a non-working day or minor typo does not force me to re-type the entire list.
8. As a Quick Report operator, I want batch generation across multiple dates to proceed automatically without manual prompts per substation, so that large multi-day batches generate unattended.
9. As a Full Report operator, I want the pre-compilation review checklist to prefix each substation with its date (e.g. `[01-05-2026] 001. PMU BENTONG [READY]`), so that I can easily identify and toggle substations by date before compilation.
10. As a CLI operator watching batch progress, I want progress updates to include the date tag (e.g. `[1/15] [01-05-2026] Generating ...`), so that I know exactly which inspection folder is currently compiling.
11. As a system administrator, I want each generated report to land in its respective date directory, so that directory hierarchy conventions remain strictly preserved regardless of multi-date batching.
12. As a software developer, I want date range expansion, parsing, and directory matching to be pure functions covered by unit tests, so that date calculations are provably robust and fast.

## Implementation Decisions

### Decision 1: Core Range Syntax Grammar and Date Expansion Helper
Add `expand_date_range_syntax(raw_str: str) -> tuple[str, ...]` in `src/cli_selectors.py`:
- Recognizes delimiters: commas (`,`), range operators (`..`, ` to `, ` - `).
- Parses `DD-MM-YYYY` tokens via existing `normalize_date_str()`.
- Expands ranges iteratively: `datetime.strptime()` step by 1 day up to end date (inclusive).
- Rejects inverted ranges where start date > end date with a clean validation error.
- Preserves chronological order and eliminates duplicates while maintaining deterministic sequence.

### Decision 2: Interactive Date Folder Selector with Loop-Back Resilience
Add `select_pahang_inspection_dates_interactive(environment: ProjectEnvironment) -> tuple[Path, ...] | None` in `src/cli_selectors.py`:
- Navigates:
  1. `select_or_create_testsheet_station(environment)`
  2. `select_or_create_testsheet_month(environment, station)`
  3. Discovers all child folders matching `is_pahang_date_folder()`, sorted in descending chronological order.
  4. If 0 date folders found, prints diagnostic message and loops back to month selection.
  5. Presents options via `select_multiple(title, options)` with `checked=False` for all items.
  6. Instructions header: `Select date folder(s) to process (<space> to select, 'a' to toggle all, <enter> to confirm)`.
  7. If result is empty or `None`, loops back to Month selection instead of returning `None` immediately.

### Decision 3: Text Input Selector with Visual Formatting Guide and Tolerant Confirmation
Add `prompt_target_inspection_dates_with_ranges(environment: ProjectEnvironment) -> tuple[Path, ...] | None` in `src/cli_selectors.py`:
- Displays visual formatting box:
  ```text
  Enter target date(s). Supported formats:
    - Single date:   01-05-2026
    - Multiple:      01-05-2026, 02-05-2026, 05-05-2026
    - Date range:    01-05-2026..05-05-2026 (or 01-05-2026 to 05-05-2026)
    - Combined:      01-05-2026..03-05-2026, 10-05-2026
  ```
- Expands input via `expand_date_range_syntax()`.
- Searches for matching date folders under `TESTSHEET/` (via rglob/directory iteration).
- Partitions results into `found_paths` and `missing_dates`:
  - If `len(missing_dates) > 0` and `len(found_paths) > 0`:
    Displays:
    `✓ Found X date folder(s): ...`
    `⚠️ Missing Y date folder(s): ...`
    Prompts `confirm("Proceed with the X found dates?", default=True)`.
  - If `len(found_paths) == 0`:
    Displays error `No matching date folders found for specified dates.` and prompts re-entry.

### Decision 4: Quick Report Action Multi-Date Routing
In `QuickReportAction.execute()`:
- Update mode options:
  - `"manual"`: Manual FL Input
  - `"browse_dates"`: Browse Date Folders (Interactive Checklist)
  - `"enter_dates"`: Enter Target Date(s) (Text Input / Range)
  - `"__cancel__"`: Cancel
- Resolves `selected_targets: Sequence[Path] | Sequence[str]`.
- Passes `selected_targets` to `workflow.inspect()` and `workflow.generate()`.
- Preserves multi-station checkbox prompt if `unique_stations > 1`.
- In `QuickReportWorkflow.generate()`: format progress message with `[{plan.package.date_str}]`.

### Decision 5: Full Report Action Multi-Date Routing & Prefixed Checklist
In `generate_full_reports_action()`:
- Update mode options to match Quick Report.
- Inspects `selected_targets` via `active_workflow.inspect()`.
- In `select_substations_interactive()`:
  - Formats title: `f"[{getattr(item, 'date_str', '')}] {item.substation_name} [{'READY' if item.is_ready else 'NOT READY'}]"`.
- In `FullReportWorkflow.generate()`: format progress message with `[{pkg.date_str}]`.

### Decision 6: Ubiquitous Language & Domain Modeling
Add `MultiDateSelectionPolicy` to `CONTEXT.md` defining the rules, grammar, and telemetry expectations.

## Testing Decisions

1. **Unit Testing Syntax Parsing (`tests/test_cli_selectors.py`)**:
   - Single date string returns 1-element tuple.
   - Comma-separated date string returns all normalized dates.
   - Range `01-05-2026..04-05-2026` returns 4 dates in order.
   - Inverted range returns empty or raises validation error.
   - Whitespace and case tolerance (`to`, `TO`, `..`).
2. **Headless Selector Testing with Mock IO (`tests/test_cli_selectors.py`)**:
   - Test `prompt_target_inspection_dates_with_ranges` with mock `input()` for found and missing dates.
   - Test `select_pahang_inspection_dates_interactive` zero-selection loop-back.
3. **Action Integration Testing (`tests/test_project_workflow_actions.py`)**:
   - Test `QuickReportAction.execute` with multi-date inputs using `FakeDocumentCompiler`.
   - Test `generate_full_reports_action` with multi-date inputs and date-prefixed checklist.
4. **Workflow Progress Telemetry Testing (`tests/test_full_report_workflow.py`, `tests/quick_report/test_workflow.py`)**:
   - Verify date tags appear in progress sink messages during batch runs.

## Out-of-Scope Boundaries

- Stage 2 Post-Processing (`PostProcessingPipelineAction` and `postprocess_full_reports_action`): Kept focused on Stage 1 report generation as decided in grilling Round 1.
- Automatic creation of missing inspection date folders during report generation: If a date folder does not exist in `TESTSHEET/`, it cannot be generated.
