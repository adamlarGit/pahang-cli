# Decision Ticket: Raw Material Pre-check Validation and Warning Policies

## Question

What pre-check validation rules and warning/error handling policies should be enforced during automated Raw Material Creation & Sorting?

## Status

CLOSED (Locked by User)

## Locked Resolution

1. **TOTAL PE Alignment Prerequisite**: `TOTAL PE.xlsx` must contain substation records for the target station and date (verifying `Populate TOTAL PE` was executed first). If not, raises `RuntimeError` directing user to run populate first.
2. **Input Directory Verification**: Verifies `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/` exists and contains at least one `.xlsx` testsheet file and the `UNSORTED RAW DATA/` directory.
3. **Missing Photo Warning Policy**: Missing individual photos (`IR` FLIR files or `DG` IMG files) do not crash the workflow. Warnings are collected into `AutomatedRawMaterialSummary.warnings` and reported to the user.
4. **Automated Destination Provisioning**: Destination folders (`RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/IR`, `/DG`, `/US+TEV`) are generated automatically by `pahang-cli` during sorting.
