<!-- status: closed -->
# Ticket #123: feat(prpd): discover 33kV PTX and LTX transformer survey directories

## Parent
Part of #90

## What to build
Extend transformer survey directory discovery in `src/quick_report/prpd.py` to recognize 33kV transformer survey folders named `PTX` (Power Transformer) and `LTX` (Local Transformer). Map `PTX` to PowerTransformerSpec units and `LTX` to local transformer units so `TransformerScanAdapter` resolves ultrasound PRPD graphs for transformer HV Bushing and HV Cable scanning pages.

## Acceptance Criteria
- [x] `_discover_substation_assets` and `find_tx_survey_dir` in `src/quick_report/prpd.py` recognize `PTX` and `LTX` survey directories alongside standard `TX*` patterns.
- [x] `TransformerScanAdapter._resolve_prpd_us` successfully resolves ultrasound graphs for Power Transformers (`PTX`) and Local Transformers (`LTX`).
- [x] For `33. MINI PPU KUALA TAHAN` and `34. MINI PPU MERTING`, Part 07 TX scanning pages resolve non-empty US PRPD graph images.
- [x] Automated regression tests pass verifying `PTX` and `LTX` survey directory discovery and adapter resolution.

## Blocked by
None (can start immediately).
