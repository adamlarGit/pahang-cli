# Ticket 064: Raw Photo Discovery & Numerical Range Matching (IR, DG, US, TEV)

## Parent Map

[Map 061: Quick Report Engine Unstubbing & Photo Integration Map](file:///.issues/061-quick-report-engine-unstubbing-map.md)

## Type

`research` (AFK)

## Status

`OPEN`

## Blocked-By

*(None — Frontier Ticket)*

## Question

How should photo stems and raw image files in `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/` (`IR/`, `DG/`, `US+TEV/`) be discovered, range-matched using numerical bounds from `PhotoRange` (start_num / end_num), and mapped to implement `_find_dg_photo`, `_find_ir_photo`, `_find_us_photo`, and `_find_tev_photo` in `src/quick_report/utils.py`?
