<!-- status: closed -->
# Ticket #106: feat(msms): multi-tier substation matching and locked-file detection in Propagate Work Orders workflow

## Parent
Part of #90

## Acceptance Criteria
- [x] `PropagateWoExtractor` extracts substation names and dates alongside FLs from `DATA MSMS.xlsx` and `TOTAL PE.xlsx`.
- [x] `PropagateWoFilter` successfully resolves 33kV substations using multi-tier matching (FL -> normalized Substation Name -> station token / date).
- [x] Running `PropagateWoWorkflow` against the 33kV Thunder Cycle 4 dataset achieves 100% match rate (25/25 work orders populated in `TOTAL PE.xlsx`).
- [x] 11kV regression tests pass with 100% parity.
- [x] Preflight guard or loader detects locked `TOTAL PE.xlsx` file and alerts the operator cleanly.
- [x] Unit and integration tests verify multi-tier matching and locked-file detection.
