<!-- status: closed -->
# 60: feat(tx): expand transformer model abbreviations and set 8pt font for {{ tx.model }}

**What to build:**
Parse transformer model abbreviations (`H/S` and `C/T`) in full as `"HERMETICALLY SEAL"` and `"CONSERVATOR TANK"` across Quick Report and Full Report, and format `{{ tx.model }}` at 8 pt font size in all 12 transformer templates so the expanded name fits neatly in the table cell.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] `normalize_tx_model` maps `H/S` and `C/T` aliases to `HERMETICALLY SEAL` and `CONSERVATOR TANK`, passes unknown non-empty models through as-is, and falls back to `"-"` for empty/sentinels.
- [x] `TransformerSpec` and `TransformerScanSpec` contain `model` field.
- [x] `src/quick_report/cbm_render.py` and `src/full_report/scan_adapters.py` populate `tx["model"]`.
- [x] All 12 transformer docx templates set `{{ tx.model }}` run and cell paragraph to 8 pt font (`w:val="16"`).
- [x] `CONTEXT.md` documents `normalize_tx_model` behavior and 8 pt convention.
- [x] Test suite passes with full regression coverage for new normalization and template font assertions.

