<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: none -->
# Refactor all workflows to use centralized target-system normalizers


## Question

How do we systematically rewire all existing workflows (`PopulateTotalPeWorkflow`, `QuickReportWorkflow`, `WhatsAppReportWorkflow`, `RawMaterialWorkflow`, `UpdateQr02CbaWorkflow`) to use target-system normalizers (`normalize_for_csv`, `normalize_for_excel`, `normalize_for_report`) in `src/core/normalizers.py` and eliminate stale/redundant normalizer helpers to prevent codebase-wide drift, while ensuring 1:1 behavioral fidelity and exact output preservation?

## Context

During the design of `PopulateDataMsmsWorkflow` (ticket [007-design-populate-data-msms.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/007-design-populate-data-msms.md)), we identified that missing/empty values require strictly different output representations depending on the target system:
1. **CSV Ingestion Target (`normalize_for_csv`)**: Requires empty strings `""` for empty cells (NO `"-"` or `"NaN"` strings).
2. **Excel Persistence Target (`normalize_for_excel`)**: Requires native Python types (`float`/`int`/`date`) or `None` (true openpyxl blank cell).
3. **Document Report Target (`normalize_for_report`)**: Requires formatted strings with `"-"` placeholders so Word/PDF report tables do not crash or show blank gaps.

If existing workflows continue using ad-hoc, per-file normalizers, format drift will persist across the codebase.

## Plan & Constraints

### 1. Baseline Verification & Characterization Testing (1:1 Output Guarantee)
- For every target workflow, run existing pytest tests (`python -m pytest tests/test_[workflow].py`).
- If no test exists for a workflow, write a baseline characterization test **first** to capture exact current input → output byte-for-byte / string-for-string results before refactoring.
- **Guarantee:** After refactoring, re-run characterization tests to verify 100% exact output preservation with zero behavioral drift or regression.

### 2. Intended Target System Audit per Workflow
- **`PopulateTotalPeWorkflow`**: Writes to `TOTAL PE.xlsx` (Excel target) → Uses `normalize_for_excel()`.
- **`QuickReportWorkflow`**: Renders Word/PDF reports (Report target) → Uses `normalize_for_report()`.
- **`WhatsAppReportWorkflow`**: Renders text/Docx reports (Report target) → Uses `normalize_for_report()`.
- **`RawMaterialWorkflow`**: Creates raw material Excel sheets (Excel target) → Uses `normalize_for_excel()`.
- **`UpdateQr02CbaWorkflow`**: Writes to `QR02 CBA` sheet in Excel (Excel target) → Uses `normalize_for_excel()`.

### 3. Implementation & Stale Code Purge
- Implement `normalize_for_csv`, `normalize_for_excel`, and `normalize_for_report` in `src/core/normalizers.py` with comprehensive unit tests in `tests/test_normalizers.py`.
- Rewire call sites in each workflow to their intended target-system normalizer.
- Audit all workflow files, extractor files, and helper modules for single-use or duplicate date/string/humidity/temperature normalizers.
- Delete dead/stale functions and redirect all imports to `src.core.normalizers`.
- Re-run full test suite (`python -m pytest`) to verify green status.
