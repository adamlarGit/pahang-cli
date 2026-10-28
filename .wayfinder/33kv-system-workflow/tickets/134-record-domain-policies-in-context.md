<!-- status: open -->
# Ticket #134: docs(domain): record LinkBoxSanitizationPolicy and TransformerDesignationPolicy in CONTEXT.md

## Parent
Part of #101 / #103

## What to build
Record the authoritative domain models agreed during the grilling session in `CONTEXT.md`:
1. **`LinkBoxSanitizationPolicy`**:
   - Documents the semantics and sanitization rules for switchgear compartments designated as `LINK BOX`.
   - Details field overrides: Equipment = `LINK BOX`, Manufacturer/Model/Area/Serial No/Heater/CB Position/Busbar Position/Cable Type = `-`, Rating = system operating voltage (`33kV` / `11kV`).
   - Preserves parent panel number, panel name, operating current, and thermals.
   - Enforces ultrasound and TEV blanking.
2. **`TransformerDesignationPolicy`**:
   - Documents the naming hierarchy for transformers across PMU/PPU and standard distribution substations.
   - Defines rules for Power Transformers (`PTX{n}`), Local Station Service Transformers (`LTX`, with `LTX{n}` for multi-unit configurations), and standard distribution units (`TX{n}`).
   - Documents testsheet coordinate origins (Sheet `TX`, row 6 headers, column W for LTX model, expansion of shorthand `H/S` and `C/T`).
   - Details propagation across `Tx No.` cell, scan page item titles, CBM defect pages, while preserving Table 26 placards and verbatim VI defect texts.

## Acceptance criteria
- [ ] `CONTEXT.md` contains formal entries for `LinkBoxSanitizationPolicy` and `TransformerDesignationPolicy`.
- [ ] All field mappings and rules match the agreed domain contracts.
- [ ] No regression or contradiction with existing ADRs or glossary definitions.

## Blocked by
#133
