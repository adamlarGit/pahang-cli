# Ticket 089: Interactive Station & Month Hierarchy Selectors

Labels: wayfinder:task
Parent: [Map 086: Generate TESTSHEET Folder Structure Workflow Map](file:///.issues/086-generate-testsheet-folder-structure-map.md)
Status: Closed / Implemented

## Question

How should interactive CLI selectors in `src/cli_selectors.py` be enhanced to guide the operator through choosing an existing Station and Month from `TESTSHEET/` with a seamless `[+] Add New Station` and `[+] Add New Month` option and single/multi-date input prompts?

## Resolution / Agreed Architecture

1. **`select_or_create_testsheet_station(environment: ProjectEnvironment) -> str | None`**:
   - Scans `environment.storage.get_testsheet_dir()` for existing station directories.
   - Presents alphabetically sorted station options + `[+] Add New Station` + `Cancel`.
   - If `[+] Add New Station` selected: Prompts for station name and converts to uppercase (e.g. `"KUANTAN"`).

2. **`select_or_create_testsheet_month(environment: ProjectEnvironment, station: str) -> str | None`**:
   - Scans `environment.storage.get_testsheet_dir() / station` for existing month folders (e.g. `01. AUGUST`).
   - Presents existing month folders + `[+] Add New Month` + `Cancel`.
   - If `[+] Add New Month` selected:
     - Calculates the next sequential index `N = len(existing_months) + 1` (e.g., `01.` for first month, `02.` for second month).
     - Opens a selection menu of the 12 standard month names (`JANUARY` to `DECEMBER`).
     - Combines index and chosen month into canonical name: `f"{N:02d}. {MONTH_NAME}"` (e.g., `01. MARCH`, `02. APRIL`).

3. **`prompt_target_inspection_dates(default_date: str | None = None) -> tuple[str, ...] | None`**:
   - Prompts: `"Enter target date(s) (e.g. 10-08-2026 or 10-08-2026, 11-08-2026) [Default: DD-MM-YYYY]: "`.
   - If operator presses Enter: uses today's date formatted `DD-MM-YYYY`.
   - Normalizes comma-separated date entries via `normalize_date_str()`.
   - Returns tuple of normalized date strings or `None` if cancelled ('c'/'cancel').
