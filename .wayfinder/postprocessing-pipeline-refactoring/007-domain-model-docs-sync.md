<!-- label: wayfinder:task -->
<!-- status: closed -->
<!-- blocked-by: 006 -->
# 007: Domain Model & Documentation Sync

## Question

How should the domain glossary in `CONTEXT.md` and repository documentation be updated to capture the finalized Post-Processing Pipeline architecture?

## Context

1. **`CONTEXT.md` Updates**:
   - Add `PostProcessingPipelineOrchestrator`: The lean orchestration service managing the 6-stage post-processing lifecycle.
   - Add `TestsheetImmutabilityPolicy`: Source testsheets in `TESTSHEET/<DATE>/` remain immutable; working copies live in `processed_testsheet/`.
   - Add `SubstationIsolatedBatchResiliencePolicy`: Per-substation errors are isolated during batch COM processing to prevent blocking valid stations.
   - Add `BatchComSession`: The shared Word and Excel COM application lifecycle context manager.
2. **Docs**:
   - Update `docs/workflows/` or workflow index referencing the post-processing pipeline capabilities.

## Verification

- Ensure `CONTEXT.md` adheres strictly to glossary format without implementation bloat.
