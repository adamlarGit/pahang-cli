<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 010-implement-normalizers-and-mapper, 012-implement-consolidate-and-enrich, 013-implement-propagate-wo, 014-implement-ingest-and-populate-msms -->
# Deprecate Legacy update_data_msms, Rewire Workflows to Normalizers & Purge Dead Code

## Objective

Complete the refactoring effort by:
1. Rewiring all existing workflows (`PopulateTotalPeWorkflow`, `QuickReportWorkflow`, `WhatsAppReportWorkflow`, `RawMaterialWorkflow`, `UpdateQr02CbaWorkflow`) to use centralized target-system normalizers in `src/core/normalizers.py` (fulfilling ticket [009-refactor-target-normalizers.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/009-refactor-target-normalizers.md)).
2. Deprecating and removing the legacy `update_data_msms.py` monolith (inventory in [001-audit-results.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/001-audit-results.md)).
3. Removing dead/stale helper functions across `src/` and verifying full regression test suite.

## Detailed Requirements

### 1. Rewire Existing Workflows to Centralized Normalizers
- Characterization testing: Run existing pytest suite for each workflow to record baseline behavior.
- Rewire `PopulateTotalPeWorkflow`, `RawMaterialWorkflow`, `UpdateQr02CbaWorkflow` to `normalize_for_excel()`.
- Rewire `QuickReportWorkflow` and `WhatsAppReportWorkflow` to `normalize_for_report()`.
- Delete ad-hoc local normalizers in workflow files and point all imports to `src.core.normalizers`.

### 2. Deprecate & Delete `update_data_msms.py`
- Remove the 10 deprecated functions identified in ticket 001:
  - `update_data_msms()`, `clean_text_basic()`, `clean_for_compare()`, `get_unique_non_empty()`, `parse_date_flexible()`, `detect_delimiter()`, `format_cycle_date()`, `build_station_code_lookup()`, `extract_station_number()`, `convert_location_to_fl_erms()` (centralized to normalizers).
- Remove obsolete ENGR $\to$ TOTAL PE data paths for Substation Name, Date, and Type (now owned exclusively by `PopulateTotalPe`).
- Remove deprecated `update_from_engr_and_msms()` on `TotalPeRepo`.
- Remove dead imports across `src/cli/`, `src/workflows/`, and `src/repositories/`.

### 3. Full Regression & Integration Validation
- Run full pytest test suite across all modules (`python -m pytest`).
- Verify zero regressions and 100% test pass.

## Acceptance Criteria & Tests
- [x] Characterization tests confirm 100% exact output preservation on existing workflows after normalizer rewiring.
- [x] `update_data_msms.py` deleted without leaving broken imports.
- [x] Entire test suite passes cleanly with zero warnings/errors.

