# Ticket 056: MSMS Workflow Structure & TOTAL PE Integration

## Parent Map

[Map 054: MSMS Workflow Porting & Domain Architecture Map](file:///.issues/054-msms-workflow-and-domain-map.md)

## Type

`grilling` (HITL)

## Status

`CLOSED`

## Question

How should MSMS domain data operations (`src/msms/`) and workflow orchestration (`src/workflows/`) interact with `TotalPeRepository` to update the Work Order (`WO`) column in `TOTAL_PE.xlsx`?

## Resolution

Decided on **Option A**:
1. `src/msms/` provides `LocalExcelMsmsRepository` for reading/writing `DATA_MSMS.xlsx` and looking up Work Orders by Functional Location.
2. `src/workflows/update_data_msms.py` orchestrates updating `DATA_MSMS.xlsx` from ENGR files via `src/msms/`, and uses `TotalPeRepository` (`src/master/total_pe.py`) to update the `WO` column in `TOTAL_PE.xlsx`.
