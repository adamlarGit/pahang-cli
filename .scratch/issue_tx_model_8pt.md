## What to build

Parse transformer model abbreviations (`H/S` and `C/T`) in full as `"HERMETICALLY SEAL"` and `"CONSERVATOR TANK"` across Quick Report and Full Report, and format `{{ tx.model }}` at 8 pt font size in all 12 transformer templates so the expanded name fits neatly in the table cell.

### Details & Specifications
1. **Canonical Normalization**:
   - Centralize `normalize_tx_model(val: str | None) -> str` in `src/core/normalizers.py`:
     - `"H/S"`, `"HS"`, `"H.S."`, `"H.S"`, `"HERMETICALLY"`, `"HERMETICALLY SEAL"`, `"HERMETICALLY SEALED"` -> `"HERMETICALLY SEAL"`
     - `"C/T"`, `"CT"`, `"C.T."`, `"C.T"`, `"CONSERVATOR"`, `"CONSERVATOR TANK"` -> `"CONSERVATOR TANK"`
     - Blank / Sentinels (`""`, `"-"`, `"N/A"`, `"NONE"`, `"NAN"`, `None`) -> `"-"`
     - Unknown non-empty values preserved as-is.
2. **Domain Models & Extractor**:
   - Add `model: str = ""` field to `TransformerSpec` (`src/testsheet/models.py`) with `__post_init__` fallback `normalize_tx_model(self.type)`.
   - Add `model: str = ""` field to `TransformerScanSpec` (`src/full_report/models.py`).
   - In `src/testsheet/extractor.py`, populate both `type=tx_type` and `model=normalize_tx_model(tx_type)`.
3. **Report Render Contexts**:
   - `src/quick_report/cbm_render.py`: use `normalize_tx_model` to populate `tx["model"]`.
   - `src/full_report/scan_adapters.py`: use `normalize_tx_model` to populate `tx["model"]`.
4. **Template Typography (8 pt)**:
   - Update `{{ tx.model }}` cell and run to 8 pt font (`<w:sz w:val="16"/>` and `<w:szCs w:val="16"/>`) across all 12 templates:
     - `templates/FULL REPORT/NORMAL IR US TEV/tx-overview.docx`
     - `templates/FULL REPORT/NORMAL IR US TEV/tx-hv-sides.docx`
     - `templates/FULL REPORT/NORMAL IR US TEV/tx-lv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR/tx-overview.docx`
     - `templates/QUICK REPORT/DEFECT IR/tx-hv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR/tx-lv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR US/tx-overview.docx`
     - `templates/QUICK REPORT/DEFECT IR US/tx-hv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR US/tx-lv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR US TEV/tx-overview.docx`
     - `templates/QUICK REPORT/DEFECT IR US TEV/tx-hv-sides.docx`
     - `templates/QUICK REPORT/DEFECT IR US TEV/tx-lv-sides.docx`
   - Clean up any fragmented XML runs in the `{{ tx.model }}` cell.
   - Leave adjacent labels and other metadata cells unchanged.
5. **Domain Documentation**:
   - Update `CONTEXT.md` under `TransformerExtractionPolicy` documenting canonical model mapping, pass-through policy, and 8 pt presentation.

## Acceptance criteria

- [ ] `normalize_tx_model` maps `H/S` and `C/T` aliases to `HERMETICALLY SEAL` and `CONSERVATOR TANK`, passes unknown non-empty models through as-is, and falls back to `"-"` for empty/sentinels.
- [ ] `TransformerSpec` and `TransformerScanSpec` contain `model` field.
- [ ] `src/quick_report/cbm_render.py` and `src/full_report/scan_adapters.py` populate `tx["model"]` with normalized values.
- [ ] All 12 transformer docx templates set `{{ tx.model }}` run and cell paragraph to 8 pt font (`w:val="16"`).
- [ ] `CONTEXT.md` documents `normalize_tx_model` behavior and 8 pt convention.
- [ ] Test suite passes with full regression coverage for new normalization and template font assertions.

## Blocked by

- None (can start immediately)
