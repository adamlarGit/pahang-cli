<!-- status: closed -->
# Ticket #124: fix(full-report): resolve compartment-specific ultrasound graphs and verify 22-10-2026 reports

## Parent
Part of #90

## What to build
Wire compartment-level ultrasound PRPD graph resolution into `SwitchgearScanAdapter` so individual compartment scan pages (Circuit Breaker, Cable Box, Upper Busbars) receive their respective distinct ultrasound graphs (or consult `RAW DATA/US+TEV/graphs/` where available) rather than replicating a single panel-level graph across all compartments. Re-run and end-to-end verify Full Report deliverables for the `22-10-2026` date (*33. MINI PPU KUALA TAHAN* and *34. MINI PPU MERTING*).

## Acceptance Criteria
- [x] `SwitchgearScanAdapter` resolves compartment-specific ultrasound graphs for Circuit Breaker, Cable Box, and Upper Busbars.
- [x] Full Reports generated for `22-10-2026` under `FULL REPORT/JERANTUT/01. OCTOBER/22-10-2026/` have populated, correctly attributed US graphs in all panel and transformer scanning documents (Part 02 through Part 07).
- [x] No regression on previously working substations (e.g. `25. MINI PPU SG KOYAN`).
- [x] Automated end-to-end verification tests pass.

## Blocked by
- #122: fix(prpd): align switchgear survey discovery with testsheet feeder and link numbers
- #123: feat(prpd): discover 33kV PTX and LTX transformer survey directories
