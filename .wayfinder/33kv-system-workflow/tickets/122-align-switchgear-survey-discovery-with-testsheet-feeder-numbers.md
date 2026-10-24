<!-- status: closed -->
# Ticket #122: fix(prpd): align switchgear survey discovery with testsheet feeder and link numbers

## Parent
Part of #90

## What to build
Upgrade switchgear survey asset discovery and adapter fallback to match survey feeder directories against the testsheet's actual feeder numbers (`panel.panel_feeder_no`) and names (`panel.name`) rather than naively treating leading digits in directory names as 1-based sequential panel indices. Forward `feeder_no` through `SwitchgearScanAdapter._resolve_prpd` to ensure fallback matching succeeds.

## Acceptance Criteria
- [x] `_discover_substation_assets` in `src/quick_report/prpd.py` matches survey directories using panel feeder numbers and feeder names from the testsheet, avoiding naive sequential index collision.
- [x] `SwitchgearScanAdapter._resolve_prpd` forwards `feeder_no=panel.panel_feeder_no` to `generate_prpd_graphs_for_swg_panel`.
- [x] For `33. MINI PPU KUALA TAHAN` and `34. MINI PPU MERTING` (22-10-2026), all switchgear panels 1 through 5 resolve to their corresponding survey folders (`7_LOCAL_TX`, `5_SPARE`, `3_PE_...`, `1_PE_...`, `31_TX_...`) without `<BLANK>` or inverted feeder assignments.
- [x] Automated regression tests pass verifying feeder-aligned PRPD discovery.

## Blocked by
None (can start immediately).
