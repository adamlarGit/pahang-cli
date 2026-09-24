<!-- status: closed -->
# refactor(tx): align transformer model normalization with MissingValuePresentationPolicy and clean smells (#60 review fixes)

## Parent

Follow-up to #60.

## What to build

Align transformer model normalization and domain model representation with `MissingValuePresentationPolicy`:
1. `normalize_tx_model(val)` returns `""` (empty string) for null, empty, or sentinel values (`_NULL_SENTINELS`), while preserving uppercase canonical names (`HERMETICALLY SEAL`, `CONSERVATOR TANK`) and unknown non-empty values as-is.
2. Eliminate redundant dead-code sentinel check in `normalize_tx_model`.
3. In `TransformerSpec.__post_init__`, ensure `model` is uniformly `""` on absent or sentinel `type` inputs.
4. Replace dynamic `getattr()` calls with typed attribute access (`tx.model or tx.type`) in `src/full_report/models.py` and `src/full_report/scan_adapters.py`.
5. Ensure presentation layer (`cbm_render.py` and `scan_adapters.py`) explicitly applies `"-"` fallback for template context.
6. Harmonize `CONTEXT.md` (`TransformerExtractionPolicy` and `MissingValuePresentationPolicy`).
7. Remove duplicate committed scratch file `.scratch/issue_tx_model_8pt.md`.
8. Update test assertions across test suite.

## Acceptance criteria

- [x] `normalize_tx_model` returns `""` for null/blank/sentinels, and maps aliases to canonical names.
- [x] Redundant sentinel check in `normalize_tx_model` is removed.
- [x] `TransformerSpec.model` defaults to `""` when `type` is missing or sentinel.
- [x] Dynamic `getattr()` replaced with typed access in full report models and adapters.
- [x] Presentation contexts in quick report and full report preserve `"-"` display.
- [x] `CONTEXT.md` domain docs aligned with `MissingValuePresentationPolicy`.
- [x] Duplicate scratch file `.scratch/issue_tx_model_8pt.md` is removed from git.
- [x] Full test suite passes.

## Blocked by

- None (can start immediately)
