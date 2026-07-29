# Ticket 055: Determine MSMS Domain Location (src/master vs src/msms)

## Parent Map

[Map 054: MSMS Workflow Porting & Domain Architecture Map](file:///.issues/054-msms-workflow-and-domain-map.md)

## Type

`grilling` (HITL)

## Status

`CLOSED`

## Question

Should the MSMS domain code and repository live as a module inside `src/master/` (alongside `total_pe.py` and `qr02.py`), or as a dedicated top-level domain package at `src/msms/`?

## Resolution

Decided on **Option A: Dedicated top-level domain package `src/msms/`**.
This isolates TNB Work Order management, MSMS repositories, and upcoming multi-source extraction logic into a deep, dedicated domain module alongside `src/testsheet/`, `src/quick_report/`, and `src/master/`.
