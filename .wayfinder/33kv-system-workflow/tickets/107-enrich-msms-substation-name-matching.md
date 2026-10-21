<!-- status: closed -->
# Ticket #107: feat(msms): substation name matching and SAP FL synchronization in Enrich MSMS workflow

## Parent
Part of #90

## Acceptance Criteria
- [x] `EnrichMsmsFilter` supports fallback matching on normalized Substation Name and station tokens.
- [x] When matched, Column E (`FUNCTIONAL LOCATION`) in `DATA MSMS.xlsx` is updated with the true SAP FL from `TOTAL PE.xlsx`.
- [x] Columns D (`ERMS`), F (`DATE`), and G (`NUMBER`) in `DATA MSMS.xlsx` are populated from `TOTAL PE.xlsx`.
- [x] Running `EnrichMsmsWorkflow` against 33kV Thunder Cycle 4 data matches all 25 rows without unhandled errors.
- [x] Existing 11kV enrichment behavior remains 100% backward compatible.
- [x] Unit and integration tests verify 33kV enrichment and SAP FL synchronization.
