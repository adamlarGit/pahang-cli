<!-- status: closed -->
# Ticket #132: fix(testsheet): parse LTX model from column W in sheet TX and normalize H/S to HERMETICALLY SEAL

## Parent
Part of #101

## What to build
In `PpuTestsheetParser._extract_tx_sheet()`, Slot 5 (LOCAL TX) columns are currently defined as `('T', 'U', 'V')`. In 33kV PMU/PPU testsheets (e.g. `40. PMU JENGKA 132-11-33kV (VI).xlsx`), cell `V6` contains `MODEL:` and cell `W6` contains the transformer model abbreviation `H/S`. Because column `W` was omitted from Slot 5 `cols`, `_get_tx_model()` terminates at column `V` and fails to capture `W6`, leaving the extracted model as empty string and rendering as dash `-` in Full Report deliverables.

Extend Slot 5 columns to `('T', 'U', 'V', 'W')` so that `_get_tx_model()` captures cell `W6`, and verify that `normalize_tx_model()` expands shorthand designations:
- `H/S` -> `HERMETICALLY SEAL`
- `C/T` -> `CONSERVATOR TANK`

Ensure `TransformerSpec.model` is populated with the normalized model string during extraction and in domain model spec initialization.

## Acceptance criteria
- [x] In `src/testsheet/parsers/ppu.py`, Slot 5 column definition is updated to include column `W` (e.g. `cols: ('T', 'U', 'V', 'W')`).
- [x] `_get_tx_model()` successfully extracts values located in cell `W6` when `V6` is `MODEL:`.
- [x] `TransformerSpec.model` is populated with `HERMETICALLY SEAL` when `W6` has `H/S` (or `CONSERVATOR TANK` when `W6` has `C/T`). Check whether `normalize_tx_model()` is applied during extraction or in spec population so `TransformerSpec.model` is normalized.
- [x] Unit tests verify extraction of Slot 5 local transformer model across candidate testsheets.

## Blocked by
#131
