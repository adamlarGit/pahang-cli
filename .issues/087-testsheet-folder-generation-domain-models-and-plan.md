# Ticket 087: TESTSHEET Folder Generation Domain Models & Request Schemas

Labels: wayfinder:domain-modeling
Parent: [Map 086: Generate TESTSHEET Folder Structure Workflow Map](file:///.issues/086-generate-testsheet-folder-structure-map.md)
Status: Closed / Implemented

## Question

What immutable domain request, plan, and result dataclasses are required to model the TESTSHEET folder generation workflow in `src/workflows/models.py` adhering to the project's deep module architecture and standard ETL patterns?

## Resolution / Agreed Architecture

1. **Request Schema (`GenerateTestsheetFolderRequest`)**:
   - `station: str` (e.g. `"KUANTAN"`)
   - `month: str` (e.g. `"01. AUGUST"`)
   - `target_dates: Sequence[str]` (e.g. `("10-08-2026", "11-08-2026")`)
   - `progress_sink: ProgressSink | None = None`
   - Workspace paths resolved strictly via `ProjectEnvironment`.

2. **Execution Plan Schemas (`DateFolderPlan`, `GenerateTestsheetFolderPlan`)**:
   - `DateFolderPlan`:
     - `date_str: str`
     - `date_dir: Path`
     - `unsorted_dir: Path`
     - `tech_dirs: tuple[Path, ...]` (`DG/`, `IR/`, `US+TEV/`)
     - `all_directories: tuple[Path, ...]`
   - `GenerateTestsheetFolderPlan`:
     - `station: str`
     - `month: str`
     - `month_dir: Path`
     - `date_plans: tuple[DateFolderPlan, ...]`
     - Property `all_directories_to_ensure: tuple[Path, ...]`

3. **Result Schema (`GenerateTestsheetFolderResult`)**:
   - `station: str`
   - `month: str`
   - `created_directories: Sequence[Path] = ()`
   - `existing_directories: Sequence[Path] = ()`
   - `total_dates_processed: int = 0`
   - `warnings: Sequence[str] = ()`
   - `errors: Sequence[str] = ()`
   - Helper properties: `created_count: int`, `is_successful: bool`
