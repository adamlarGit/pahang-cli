<!-- status: closed -->
Part of #66
Specification: [spec.md](../spec.md)

# 067: feat(cli): multi-date interactive checklist & range-aware text selectors

**What to build:** Core CLI selection utilities and grammar parsing for multi-date selection. Adds `expand_date_range_syntax` to parse and expand single dates, comma-separated dates, and ranges (`01-05-2026..05-05-2026` or `01-05-2026 to 05-05-2026`). Enhances `select_multiple` to support unchecked default state and toggle-all shortcuts (`'a'` / `'all'`). Implements `select_pahang_inspection_dates_interactive` allowing operators to drill down Station $\to$ Month $\to$ multi-select date folders with zero-selection loop-back resilience. Implements `prompt_target_inspection_dates_with_ranges` with on-screen visual syntax guide and tolerant confirmation when missing dates are detected.

**Blocked by:** None (can start immediately).

**Status:** Closed

- [x] Implement `expand_date_range_syntax(raw_str: str) -> tuple[str, ...]` in `src/cli_selectors.py`:
  - Tokenizes input on commas (`,`).
  - Detects range operators (`..`, ` to `, ` TO `, ` - `).
  - Normalizes date tokens via `normalize_date_str()`.
  - Expands ranges sequentially using calendar day arithmetic (`datetime.timedelta(days=1)`).
  - Validates that range start date is before or equal to range end date; raises `ValueError` if inverted.
  - Returns deduplicated, chronologically ordered tuple of `DD-MM-YYYY` date strings.
- [x] Enhance `select_multiple()` and `_fallback_select_multiple()` in `src/cli_selectors.py`:
  - Support `checked=False` options properly.
  - In `questionary.checkbox`, ensure instructions note `'a'` to toggle all, `<space>` to select, `<enter>` to confirm.
  - In `_fallback_select_multiple`, support `'all'` to check everything, `'none'` / `'clear'` to uncheck, and cleanly handle empty input when no default items are checked.
- [x] Implement `select_pahang_inspection_dates_interactive(environment: ProjectEnvironment) -> tuple[Path, ...] | None` in `src/cli_selectors.py`:
  - Prompts Station selection via existing `select_or_create_testsheet_station(environment)`.
  - Prompts Month selection via existing `select_or_create_testsheet_month(environment, station)`.
  - Discovers all child directories matching `is_pahang_date_folder()`, sorted by date descending.
  - If 0 folders found, displays diagnostic warning and loops back to Month selection.
  - Prompts operator via `select_multiple()` with all date folders unchecked (`checked=False`).
  - If operator cancels or selects 0 items, loops back to Month/Station selection instead of crashing or returning `None`.
  - Returns tuple of resolved `Path` objects.
- [x] Implement `prompt_target_inspection_dates_with_ranges(environment: ProjectEnvironment) -> tuple[Path, ...] | None` in `src/cli_selectors.py`:
  - Displays formatted visual syntax box:
    ```text
    Enter target date(s). Supported formats:
      - Single date:   01-05-2026
      - Multiple:      01-05-2026, 02-05-2026, 05-05-2026
      - Date range:    01-05-2026..05-05-2026 (or 01-05-2026 to 05-05-2026)
      - Combined:      01-05-2026..03-05-2026, 10-05-2026
    ```
  - Prompts for input string; handles cancel / empty gracefully.
  - Expands ranges via `expand_date_range_syntax()`.
  - Locates matching date folders across `environment.storage.get_testsheet_dir()`.
  - If some dates exist and some are missing, displays summary:
    - Lists found date folders.
    - Lists missing date folders.
    - Prompts `confirm("Proceed with the X found dates?", default=True)`.
  - If 0 date folders match, alerts operator and loops back to prompt.
  - Returns tuple of resolved `Path` objects.
- [x] Add comprehensive unit tests in `tests/test_cli_selectors.py`:
  - Unit test `expand_date_range_syntax` for single date, comma-separated, `..` range, `to` range, whitespace tolerance, and inverted range validation.
  - Test `select_pahang_inspection_dates_interactive` with mock filesystem and simulated zero-selection / cancel loops.
  - Test `prompt_target_inspection_dates_with_ranges` with partial matching and tolerant confirmation confirmation/rejection.
