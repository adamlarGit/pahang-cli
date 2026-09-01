<!-- label: wayfinder:task -->
<!-- status: open -->
<!-- blocked-by: 005 -->
# 006: Dead Code Cleanup & Redundant Logic Removal

## Question

What dead, duplicated, or obsolete code and imports should be purged following the post-processing pipeline refactor?

## Context

1. **Cleanup Checklist**:
   - Audit `src/workflows/postprocessing_pipeline.py` for any duplicate COM helper functions, unused openpyxl manipulations, or redundant signature functions.
   - Audit `src/postprocessing/converters.py` for any obsolete mock classes or legacy converter methods replaced by the shared COM session.
   - Audit `src/project_workflow_actions.py` to remove duplicate adapter logic.
   - Ensure all unused imports across `src/workflows/` and `src/postprocessing/` are purged.
   - Run linter / pytest across the entire test suite to ensure zero regressions after dead code removal.

## Verification

- Run full test suite: `pytest -q`
- Verify 100% test pass rate with zero dead code warnings.
