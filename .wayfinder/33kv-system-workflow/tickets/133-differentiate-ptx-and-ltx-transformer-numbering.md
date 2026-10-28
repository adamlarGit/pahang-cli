<!-- status: closed -->
# Ticket #133: feat(full-report): differentiate PTX and LTX transformer numbering in 33kV reports

## Parent
Part of #90 / #101

## What to build
In 33kV PMU/PPU substations (such as `PMU JENGKA 132/11/33kV`, FL `CJEN/PMU/J00001`), transformer numbering in Full Report deliverables currently labels all units as `TX1`, `TX2`, and `TXLOCAL TX`.

Differentiate transformer identifiers by asset archetype:
1. **Power Transformers** (instances of `PowerTransformerSpec`, ratings >= 5 MVA from Slots 1-4) must be numbered sequentially as `PTX1`, `PTX2`, `PTX3`, `PTX4`.
2. **Local Station Service Transformers** (ratings in kVA from Slot 5 or with `LOCAL` in ID) must be numbered as `LTX` (and `LTX1`, `LTX2` only if multiple local transformers exist on site).
3. **Standard 11kV Distribution Transformers** (in SSU/PE with standard `TransformerSpec`) retain the conventional `TX1`, `TX2` designations.

Apply these designations to:
- The `Tx No.` table cell on transformer scan pages (`tx.number` / `tx.id` / `tx_block["number"]` / `tx_block["panel"]`).
- Scan render page item names (e.g. `PTX1 - OVERVIEW`, `PTX1 - HV BUSHING`, `LTX - OVERVIEW`).
- CBM defect page headers and defect forwarding banners on overview pages.
- Preserve condition overview placards in Table 26 as `POWER TX1`, `POWER TX2`, `LOCAL TX`.
- Preserve visual defect descriptions from testsheets 100% verbatim without regex inference.

## Acceptance Criteria
- [x] `normalize_tx_id()` in `src/core/normalizers.py` or `TransformerScanAdapter` correctly resolves `PTX{n}` for `PowerTransformerSpec` and `LTX` for local station service transformers.
- [x] Transformer scan pages render `PTX1`, `PTX2`, and `LTX` in the `Tx No.` cell.
- [x] Component scan page item titles use `PTX1 - <COMPONENT>` and `LTX - <COMPONENT>`.
- [x] Standard distribution transformers continue to resolve to `TX1`, `TX2`.
- [x] Condition overview placards in Table 26 remain `POWER TX1`, `POWER TX2`, and `LOCAL TX`.
- [x] Visual inspection defect descriptions are unmodified.
- [x] Unit and regression tests verify transformer numbering across PMU/PPU and standard distribution packages.

## Blocked by
#132 (can start immediately).
