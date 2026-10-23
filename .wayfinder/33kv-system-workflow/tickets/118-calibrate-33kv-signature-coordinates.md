<!-- status: closed -->
# Ticket #118: fix(signatures): calibrate 33kV testsheet signature coordinates with declarative layout registry

## Parent
Part of #90

## Acceptance Criteria
- [x] Declarative signature layout registry maps 33kV sheets to calibrated single-cell/multi-cell `TwoCellAnchor` coordinates with EMU offsets.
- [x] Switchgear Vendor and TNB signatures anchor at `E77` and `L77` without overlapping measurement data on Row 74.
- [x] Transformer Vendor and TNB signatures anchor at `F73` and `R73`.
- [x] Visual Inspection Vendor and TNB signatures anchor at `D82` and `M82` (Column M, not Column L).
- [x] `templates/TESTSHEET 33kV/33kV_softcopy_testsheet_v1.0.xlsx` sheet `33kV (Extra) (2)` has `E77:F77` merged.
- [x] 11kV signature placement (`pce_testsheet` and `pce_vi`) remains 100% unchanged.
- [x] `pytest tests/test_postprocessing_33kv.py` passes with updated assertions.
